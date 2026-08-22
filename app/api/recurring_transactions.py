import datetime as dt
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.security import get_current_user_with_subscription_check
from app.database import engine
from app.models.category import Category, CategoryType
from app.models.enums import TransactionType
from app.models.recurring_transaction import RecurrenceFrequency, RecurringTransaction
from app.models.saving_account import SavingAccount, SavingAccountStatus
from app.models.transaction import Transaction
from app.schemas.recurring_transaction import (
    GeneratedItem,
    RecurringTransactionCreate,
    RecurringTransactionRead,
    RecurringTransactionUpdate,
    RunResult,
    SkippedItem,
)

router = APIRouter(prefix="/recurring-transactions", tags=["recurring-transactions"])

# Tope de ocurrencias generadas por regla en una sola corrida. Protege contra
# una plantilla con next_run muy antiguo (o mal configurada) que intentaría
# crear cientos de movimientos de golpe.
MAX_OCCURRENCES_PER_RUN = 60


def _add_months(d: dt.date, months: int) -> dt.date:
    """Suma meses conservando el día cuando existe. El 31 de enero + 1 mes es
    el 28/29 de febrero, no el 3 de marzo -- que es lo que haría sumar días."""
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    # Último día del mes destino
    if month == 12:
        last_day = 31
    else:
        last_day = (dt.date(year, month + 1, 1) - dt.timedelta(days=1)).day
    return dt.date(year, month, min(d.day, last_day))


def _advance(d: dt.date, freq: RecurrenceFrequency) -> dt.date:
    if freq == RecurrenceFrequency.weekly:
        return d + dt.timedelta(weeks=1)
    if freq == RecurrenceFrequency.biweekly:
        return d + dt.timedelta(weeks=2)
    if freq == RecurrenceFrequency.monthly:
        return _add_months(d, 1)
    if freq == RecurrenceFrequency.yearly:
        return _add_months(d, 12)
    raise ValueError(f"Frecuencia no soportada: {freq}")


def _validate_refs(
    session: Session, user_id: UUID, category_id: int, account_id: int, tx_type: TransactionType
) -> None:
    category = session.exec(
        select(Category).where(
            Category.id == category_id,
            Category.user_id == user_id,
            Category.is_active == True,  # noqa: E712
        )
    ).first()
    if not category:
        raise HTTPException(status_code=400, detail="Categoría inválida o inactiva.")

    expected = CategoryType.income if tx_type == TransactionType.income else CategoryType.expense
    if category.type not in (expected, CategoryType.both):
        raise HTTPException(
            status_code=400,
            detail="La categoría no corresponde al tipo de movimiento.",
        )

    account = session.exec(
        select(SavingAccount).where(
            SavingAccount.id == account_id, SavingAccount.user_id == user_id
        )
    ).first()
    if not account:
        raise HTTPException(status_code=400, detail="Cuenta inválida.")
    if account.status != SavingAccountStatus.active:
        raise HTTPException(status_code=400, detail="La cuenta no está activa.")


def _to_read(session: Session, r: RecurringTransaction) -> RecurringTransactionRead:
    category = session.get(Category, r.category_id)
    account = session.get(SavingAccount, r.saving_account_id)
    return RecurringTransactionRead(
        **r.dict(),
        category_name=category.name if category else None,
        account_name=account.name if account else None,
        account_currency=account.currency if account else None,
    )


@router.post("", response_model=RecurringTransactionRead)
@router.post("/", response_model=RecurringTransactionRead)
def create_recurring(
    data: RecurringTransactionCreate,
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    if data.type not in (TransactionType.income, TransactionType.expense):
        raise HTTPException(status_code=400, detail="Solo se admiten ingresos o gastos.")
    if data.end_date and data.end_date < data.next_run:
        raise HTTPException(
            status_code=400, detail="La fecha de fin no puede ser anterior al primer movimiento."
        )

    with Session(engine) as session:
        _validate_refs(session, user_id, data.category_id, data.saving_account_id, data.type)
        recurring = RecurringTransaction(**data.dict(), user_id=user_id)
        session.add(recurring)
        session.commit()
        session.refresh(recurring)
        return _to_read(session, recurring)


@router.get("", response_model=List[RecurringTransactionRead])
@router.get("/", response_model=List[RecurringTransactionRead])
def list_recurring(user_id: UUID = Depends(get_current_user_with_subscription_check)):
    with Session(engine) as session:
        items = session.exec(
            select(RecurringTransaction)
            .where(RecurringTransaction.user_id == user_id)
            .order_by(RecurringTransaction.next_run)
        ).all()
        return [_to_read(session, r) for r in items]


@router.put("/{recurring_id}", response_model=RecurringTransactionRead)
def update_recurring(
    recurring_id: int,
    data: RecurringTransactionUpdate,
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    with Session(engine) as session:
        recurring = session.exec(
            select(RecurringTransaction).where(
                RecurringTransaction.id == recurring_id,
                RecurringTransaction.user_id == user_id,
            )
        ).first()
        if not recurring:
            raise HTTPException(status_code=404, detail="Recurrencia no encontrada")

        payload = data.dict(exclude_unset=True)
        new_category = payload.get("category_id", recurring.category_id)
        new_account = payload.get("saving_account_id", recurring.saving_account_id)
        if "category_id" in payload or "saving_account_id" in payload:
            _validate_refs(session, user_id, new_category, new_account, recurring.type)

        new_next_run = payload.get("next_run", recurring.next_run)
        new_end = payload.get("end_date", recurring.end_date)
        if new_end and new_end < new_next_run:
            raise HTTPException(
                status_code=400,
                detail="La fecha de fin no puede ser anterior al próximo movimiento.",
            )

        for field, value in payload.items():
            setattr(recurring, field, value)

        session.add(recurring)
        session.commit()
        session.refresh(recurring)
        return _to_read(session, recurring)


@router.delete("/{recurring_id}")
def delete_recurring(
    recurring_id: int, user_id: UUID = Depends(get_current_user_with_subscription_check)
):
    with Session(engine) as session:
        recurring = session.exec(
            select(RecurringTransaction).where(
                RecurringTransaction.id == recurring_id,
                RecurringTransaction.user_id == user_id,
            )
        ).first()
        if not recurring:
            raise HTTPException(status_code=404, detail="Recurrencia no encontrada")

        # Solo se borra la plantilla: los movimientos ya generados son hechos
        # contables y se conservan.
        session.delete(recurring)
        session.commit()
        return {"message": "Recurrencia eliminada. Los movimientos ya generados se conservan."}


@router.post("/run", response_model=RunResult)
def run_due_recurring(user_id: UUID = Depends(get_current_user_with_subscription_check)):
    """Genera los movimientos vencidos de todas las recurrencias activas.

    Idempotente: `next_run` solo avanza cuando su movimiento ya se creó, y
    ambas cosas se confirman juntas. Llamarlo dos veces seguidas no duplica
    nada porque en la segunda ya no hay fechas vencidas.
    """
    today = dt.date.today()
    generated: List[GeneratedItem] = []
    skipped: List[SkippedItem] = []
    total_created = 0

    with Session(engine) as session:
        rules = session.exec(
            select(RecurringTransaction).where(
                RecurringTransaction.user_id == user_id,
                RecurringTransaction.is_active == True,  # noqa: E712
                RecurringTransaction.next_run <= today,
            )
        ).all()

        for rule in rules:
            account = session.get(SavingAccount, rule.saving_account_id)
            if not account or account.status != SavingAccountStatus.active:
                skipped.append(
                    SkippedItem(
                        recurring_id=rule.id,
                        description=rule.description,
                        reason="La cuenta asociada ya no está activa.",
                    )
                )
                continue

            category = session.get(Category, rule.category_id)
            if not category or not category.is_active:
                skipped.append(
                    SkippedItem(
                        recurring_id=rule.id,
                        description=rule.description,
                        reason="La categoría asociada ya no está activa.",
                    )
                )
                continue

            created_ids: List[int] = []
            cursor = rule.next_run
            stopped_reason: Optional[str] = None

            while cursor <= today and len(created_ids) < MAX_OCCURRENCES_PER_RUN:
                if rule.end_date and cursor > rule.end_date:
                    break

                if rule.type == TransactionType.expense:
                    if account.balance < rule.amount:
                        # No se sobregira la cuenta: se detiene aquí y se
                        # informa. La fecha pendiente queda intacta para que
                        # el usuario pueda resolverlo y reintentar.
                        stopped_reason = (
                            f"Saldo insuficiente en {account.name} "
                            f"({account.balance:,.2f} {account.currency}) "
                            f"para el movimiento del {cursor.isoformat()}."
                        )
                        break
                    account.balance -= rule.amount
                else:
                    account.balance += rule.amount

                tx = Transaction(
                    user_id=user_id,
                    amount=rule.amount,
                    type=rule.type,
                    description=rule.description,
                    category_id=rule.category_id,
                    saving_account_id=rule.saving_account_id,
                    # Mediodía local evita que el movimiento se corra de día
                    # al convertirse a UTC, igual que hace el resto de la app.
                    date=dt.datetime.combine(cursor, dt.time(12, 0)),
                    source_type="recurring",
                )
                session.add(tx)
                session.flush()  # necesitamos el id antes del commit
                created_ids.append(tx.id)

                cursor = _advance(cursor, rule.frequency)

            if created_ids:
                session.add(account)
                rule.next_run = cursor
                rule.last_run_at = dt.datetime.utcnow()
                # Si ya pasó su fecha de fin, se desactiva sola.
                if rule.end_date and cursor > rule.end_date:
                    rule.is_active = False
                session.add(rule)
                generated.append(
                    GeneratedItem(
                        recurring_id=rule.id,
                        description=rule.description,
                        transaction_ids=created_ids,
                        count=len(created_ids),
                    )
                )
                total_created += len(created_ids)

            if stopped_reason:
                skipped.append(
                    SkippedItem(
                        recurring_id=rule.id,
                        description=rule.description,
                        reason=stopped_reason,
                    )
                )

        session.commit()

    return RunResult(generated=generated, skipped=skipped, total_created=total_created)
