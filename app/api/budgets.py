import calendar
import datetime as dt
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, not_, or_
from sqlmodel import Session, select

from app.core.security import get_current_user_with_subscription_check
from app.database import engine
from app.models.budget import Budget
from app.models.category import Category, CategoryType
from app.models.debt import Debt
from app.models.enums import TransactionType
from app.models.saving_account import SavingAccount
from app.models.transaction import Transaction
from app.schemas.budget import BudgetCreate, BudgetProgress
from app.utils.currency_helpers import validate_currency_code

router = APIRouter(prefix="/budgets", tags=["budgets"])

# Movimientos que no cuentan como "gasto real" de una categoría presupuestada:
# una transferencia o un pago de deuda es patrimonio moviéndose de lugar, no
# dinero saliendo de verdad -- mismo criterio que ya usa GET /summary.
_EXCLUDED_SOURCE_TYPES = ["transfer", "investment_yield", "debt_payment"]


def _month_bounds(month_start: dt.date) -> tuple[dt.date, dt.date]:
    last_day = calendar.monthrange(month_start.year, month_start.month)[1]
    return month_start, month_start.replace(day=last_day)


def _parse_month(month: Optional[str]) -> dt.date:
    """'YYYY-MM' -> primer día de ese mes. Sin parámetro, el mes en curso."""
    if not month:
        return dt.date.today().replace(day=1)
    try:
        year, mo = month.split("-")
        return dt.date(int(year), int(mo), 1)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="`month` debe tener el formato YYYY-MM.")


def _calc_spent(
    session: Session,
    user_id: UUID,
    category_id: int,
    currency: str,
    month_start: dt.date,
    month_end: dt.date,
) -> float:
    """Gasto real de una categoría en una moneda, dentro de un mes -- misma
    lógica de exclusión que GET /summary (transferencias, rendimientos y
    pagos de deuda no cuentan), separado por cuentas y por compras con
    tarjeta de crédito en esa misma moneda.

    **Incluye las subcategorías.** Un presupuesto de "Transporte" que ignorara
    "Transporte › Gasolina" mostraría al usuario que le queda plata cuando ya
    la gastó -- el peor error posible en un presupuesto. Un presupuesto puesto
    directamente sobre la subcategoría solo cuenta esa.
    """
    from app.models.category import Category

    ids = [category_id] + [
        c.id
        for c in session.exec(
            select(Category).where(Category.parent_id == category_id)
        ).all()
    ]
    from_accounts = session.exec(
        select(func.sum(Transaction.amount))
        .join(SavingAccount, Transaction.saving_account_id == SavingAccount.id)
        .where(Transaction.user_id == user_id)
        .where(Transaction.category_id.in_(ids))
        .where(Transaction.type == TransactionType.expense)
        .where(Transaction.date >= month_start)
        .where(Transaction.date <= dt.datetime.combine(month_end, dt.time.max))
        .where(Transaction.is_cancelled == False)  # noqa: E712
        .where(Transaction.reversed_transaction_id.is_(None))
        .where(SavingAccount.currency == currency)
        .where(
            or_(
                Transaction.source_type.is_(None),
                not_(Transaction.source_type.in_(_EXCLUDED_SOURCE_TYPES)),
            )
        )
    ).first()

    from_credit_cards = session.exec(
        select(func.sum(Transaction.amount))
        .join(Debt, Transaction.debt_id == Debt.id)
        .where(Transaction.user_id == user_id)
        .where(Transaction.category_id.in_(ids))
        .where(Transaction.date >= month_start)
        .where(Transaction.date <= dt.datetime.combine(month_end, dt.time.max))
        .where(Transaction.is_cancelled == False)  # noqa: E712
        .where(Debt.currency == currency)
        .where(Transaction.source_type == "credit_card_purchase")
    ).first()

    return (from_accounts or 0.0) + (from_credit_cards or 0.0)


def _to_progress(session: Session, budget: Budget, month_start: dt.date, month_end: dt.date) -> BudgetProgress:
    category = session.get(Category, budget.category_id)
    spent = _calc_spent(session, budget.user_id, budget.category_id, budget.currency, month_start, month_end)
    return BudgetProgress(
        id=budget.id,
        category_id=budget.category_id,
        category_name=category.name if category else "(categoría eliminada)",
        currency=budget.currency,
        amount=budget.amount,
        effective_from=budget.effective_from,
        spent=spent,
        percentage=(spent / budget.amount * 100) if budget.amount > 0 else 0.0,
        created_at=budget.created_at,
    )


@router.post("", response_model=BudgetProgress)
@router.post("/", response_model=BudgetProgress)
def create_or_update_budget(
    data: BudgetCreate,
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    with Session(engine) as session:
        category = session.exec(
            select(Category).where(
                Category.id == data.category_id,
                Category.user_id == user_id,
                Category.is_active == True,  # noqa: E712
            )
        ).first()
        if not category:
            raise HTTPException(status_code=400, detail="Categoría inválida o inactiva.")
        if category.is_system:
            raise HTTPException(status_code=400, detail="No puedes presupuestar una categoría de sistema.")
        if category.type == CategoryType.income:
            raise HTTPException(status_code=400, detail="Solo puedes presupuestar categorías de gasto.")

        validate_currency_code(session, data.currency)

        current_month_start = dt.date.today().replace(day=1)
        effective_from = data.effective_from or current_month_start
        if effective_from.day != 1:
            effective_from = effective_from.replace(day=1)
        if effective_from < current_month_start:
            raise HTTPException(
                status_code=400,
                detail="No puedes fijar un presupuesto con vigencia en un mes que ya pasó.",
            )

        existing = session.exec(
            select(Budget).where(
                Budget.user_id == user_id,
                Budget.category_id == data.category_id,
                Budget.currency == data.currency,
                Budget.effective_from == effective_from,
            )
        ).first()
        if existing:
            # Editar el mismo mes en curso más de una vez actualiza esa fila
            # en vez de acumular versiones -- solo hay una vigencia por
            # (categoría, moneda, mes).
            existing.amount = data.amount
            budget = existing
        else:
            budget = Budget(
                user_id=user_id,
                category_id=data.category_id,
                currency=data.currency,
                amount=data.amount,
                effective_from=effective_from,
            )
        session.add(budget)
        session.commit()
        session.refresh(budget)

        month_start, month_end = _month_bounds(effective_from)
        return _to_progress(session, budget, month_start, month_end)


@router.get("", response_model=List[BudgetProgress])
@router.get("/", response_model=List[BudgetProgress])
def list_budgets(
    month: Optional[str] = Query(None, description="YYYY-MM, por defecto el mes en curso"),
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    month_start = _parse_month(month)
    _, month_end = _month_bounds(month_start)

    with Session(engine) as session:
        rows = session.exec(
            select(Budget)
            .where(Budget.user_id == user_id)
            .where(Budget.effective_from <= month_start)
            .order_by(Budget.effective_from)
        ).all()

        # La fila más reciente por (categoría, moneda) con effective_from
        # <= el mes consultado es la vigente -- como vienen ordenadas
        # ascendente, la última que sobrescribe el dict es esa.
        latest_by_pair: dict[tuple[int, str], Budget] = {}
        for row in rows:
            latest_by_pair[(row.category_id, row.currency)] = row

        result = [
            _to_progress(session, budget, month_start, month_end)
            for budget in latest_by_pair.values()
            if budget.amount > 0  # amount=0 es "pausado desde este mes"
        ]
        result.sort(key=lambda r: r.percentage, reverse=True)
        return result


@router.post("/{budget_id}/pause")
def pause_budget(budget_id: int, user_id: UUID = Depends(get_current_user_with_subscription_check)):
    with Session(engine) as session:
        reference = session.get(Budget, budget_id)
        if not reference or reference.user_id != user_id:
            raise HTTPException(status_code=404, detail="Presupuesto no encontrado.")

        current_month_start = dt.date.today().replace(day=1)
        existing = session.exec(
            select(Budget).where(
                Budget.user_id == user_id,
                Budget.category_id == reference.category_id,
                Budget.currency == reference.currency,
                Budget.effective_from == current_month_start,
            )
        ).first()
        if existing:
            existing.amount = 0
            session.add(existing)
        else:
            session.add(
                Budget(
                    user_id=user_id,
                    category_id=reference.category_id,
                    currency=reference.currency,
                    amount=0,
                    effective_from=current_month_start,
                )
            )
        session.commit()
        return {"message": "Presupuesto pausado desde este mes."}
