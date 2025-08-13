from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select
from datetime import datetime, date, time, timezone
from zoneinfo import ZoneInfo
from uuid import UUID
from typing import Optional, Dict
from sqlalchemy.orm import joinedload
from sqlalchemy import or_, not_
from collections import defaultdict

from app.database import engine
from app.models.transaction import Transaction
from app.models.category import Category
from app.models.enums import TransactionType
from app.schemas.summary import SummaryResponse, CategorySummary, DailySummary
from app.models.saving_account import Currency, SavingAccount
from app.models.debt import Debt
from app.core.security import get_current_user_with_subscription_check

router = APIRouter(prefix="/summary", tags=["summary"])


def _utc_bounds_for_local_day(d: date, tz: str):
    """Devuelve (start_utc, end_utc) para el día local `d` en tz IANA."""
    z = ZoneInfo(tz)
    start_local = datetime.combine(d, time.min).replace(tzinfo=z)
    end_local = datetime.combine(d, time.max).replace(tzinfo=z)
    # guardamos como naive UTC para comparar con columnas UTC/naive
    start_utc = start_local.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = end_local.astimezone(timezone.utc).replace(tzinfo=None)
    return start_utc, end_utc


def _to_local_day(dt: datetime, tz: str) -> date:
    """Convierte un datetime UTC (naive o tz-aware) al día local en tz IANA."""
    z = ZoneInfo(tz)
    # trata dt como UTC si viene naive (común cuando se guarda con datetime.utcnow())
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(z).date()


@router.get("/", response_model=Dict[Currency, SummaryResponse])
def get_summary(
    user_id: UUID = Depends(get_current_user_with_subscription_check),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    tz: Optional[str] = Query(None, description="Zona horaria IANA del navegador, ej. America/Bogota"),
):
    tz = tz or "UTC"

    with Session(engine) as session:
        today_local = _to_local_day(datetime.utcnow(), tz)
        if not start_date:
            start_date = today_local.replace(day=1)
        if not end_date:
            end_date = today_local

        start_utc, _ = _utc_bounds_for_local_day(start_date, tz)
        _, end_utc = _utc_bounds_for_local_day(end_date, tz)

        result: Dict[Currency, SummaryResponse] = {}

        for currency in [Currency.COP, Currency.USD, Currency.EUR]:
            # Transacciones de cuentas (no automáticas especiales)
            query_saving = (
                select(Transaction)
                .join(SavingAccount, Transaction.saving_account_id == SavingAccount.id)
                .where(Transaction.user_id == user_id)
                .where(Transaction.date >= start_utc)
                .where(Transaction.date <= end_utc)
                .where(Transaction.is_cancelled == False)
                .where(Transaction.reversed_transaction_id.is_(None))
                .where(SavingAccount.currency == currency)
                .where(
                    or_(
                        Transaction.source_type.is_(None),
                        not_(Transaction.source_type.in_([
                            "transfer",
                            "investment_yield",
                            "debt_payment"
                        ]))
                    )
                )
                .options(
                    joinedload(Transaction.category),
                    joinedload(Transaction.saving_account),
                )
            )

            # Compras con tarjeta de crédito en misma moneda
            query_credit_card = (
                select(Transaction)
                .join(Debt, Transaction.debt_id == Debt.id)
                .where(Transaction.user_id == user_id)
                .where(Transaction.date >= start_utc)
                .where(Transaction.date <= end_utc)
                .where(Transaction.is_cancelled == False)
                .where(Debt.currency == currency)
                .where(Transaction.source_type == "credit_card_purchase")
                .options(
                    joinedload(Transaction.category),
                    joinedload(Transaction.debt),
                )
            )

            transactions_saving = session.exec(query_saving).all()
            transactions_credit_card = session.exec(query_credit_card).all()
            transactions = transactions_saving + transactions_credit_card

            total_income = 0.0
            total_expense = 0.0

            expense_by_category = defaultdict(float)
            income_by_category = defaultdict(float)
            daily_summary = defaultdict(lambda: {"income": 0.0, "expense": 0.0})

            for tx in transactions:
                # Día local según tz del navegador
                tx_local_day = _to_local_day(tx.date, tz)

                if tx.type == TransactionType.income:
                    total_income += tx.amount
                    if tx.category:
                        income_by_category[(tx.category.id, tx.category.name)] += tx.amount
                    daily_summary[tx_local_day]["income"] += tx.amount
                elif tx.type == TransactionType.expense:
                    total_expense += tx.amount
                    if tx.category:
                        expense_by_category[(tx.category.id, tx.category.name)] += tx.amount
                    daily_summary[tx_local_day]["expense"] += tx.amount

            balance = total_income - total_expense

            def build_category_summary(data_dict, total):
                summaries = []
                for (cat_id, cat_name), amount in data_dict.items():
                    percentage = (amount / total * 100) if total > 0 else 0
                    summaries.append(CategorySummary(
                        category_id=cat_id,
                        category_name=cat_name,
                        total=amount,
                        percentage=percentage
                    ))
                summaries.sort(key=lambda x: x.total, reverse=True)
                return summaries

            expense_summary = build_category_summary(expense_by_category, total_expense)
            income_summary = build_category_summary(income_by_category, total_income)

            daily_summaries = [
                DailySummary(
                    date=d,
                    total_income=v["income"],
                    total_expense=v["expense"]
                )
                for d, v in sorted(daily_summary.items())
            ]

            top_expense_category = expense_summary[0] if expense_summary else None
            top_income_category = income_summary[0] if income_summary else None

            top_expense_day = max(daily_summaries, key=lambda x: x.total_expense, default=None)
            top_income_day = max(daily_summaries, key=lambda x: x.total_income, default=None)

            overspending_alert = total_expense > total_income

            result[currency] = SummaryResponse(
                total_income=total_income,
                total_expense=total_expense,
                balance=balance,
                expense_by_category=expense_summary,
                income_by_category=income_summary,
                daily_evolution=daily_summaries,
                top_expense_category=top_expense_category,
                top_income_category=top_income_category,
                top_expense_day=top_expense_day,
                top_income_day=top_income_day,
                overspending_alert=overspending_alert
            )

        return result
