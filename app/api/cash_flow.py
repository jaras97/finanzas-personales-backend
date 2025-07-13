from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select
from datetime import datetime, date
from uuid import UUID
from typing import Optional, Dict
from sqlalchemy.orm import joinedload
from sqlalchemy import not_
from app.database import engine
from app.models.transaction import Transaction
from app.models.saving_account import Currency, SavingAccount
from app.models.enums import TransactionType
from app.core.security import get_current_user_with_subscription_check

router = APIRouter(prefix="/cash-flow", tags=["cash-flow"])

@router.get("/", response_model=Dict[Currency, Dict[str, float]])
def get_cash_flow_summary(
    user_id: UUID = Depends(get_current_user_with_subscription_check),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None)
):
    with Session(engine) as session:
        today = date.today()
        if not start_date:
            start_date = today.replace(day=1)
        if not end_date:
            end_date = today

        result: Dict[Currency, Dict[str, float]] = {}

        for currency in [Currency.COP, Currency.USD, Currency.EUR]:
            query = (
                select(Transaction)
                .join(SavingAccount, Transaction.saving_account_id == SavingAccount.id)
                .where(Transaction.user_id == user_id)
                .where(Transaction.date >= datetime.combine(start_date, datetime.min.time()))
                .where(Transaction.date <= datetime.combine(end_date, datetime.max.time()))
                .where(Transaction.is_cancelled == False)
                .where(Transaction.reversed_transaction_id.is_(None))
                .where(SavingAccount.currency == currency)
               .where(
                    (Transaction.source_type.is_(None)) |
                    not_(Transaction.source_type.in_([
                        "transfer",
                        "investment_yield"
                    ]))
)
                .options(
                    joinedload(Transaction.saving_account),
                )
            )

            transactions = session.exec(query).all()

            total_income = 0.0
            total_expense = 0.0
            total_debt_payments = 0.0

            for tx in transactions:
                if tx.type == TransactionType.income:
                    total_income += tx.amount
                elif tx.type == TransactionType.expense:
                    if tx.source_type == "debt_payment":
                        total_debt_payments += tx.amount
                    else:
                        total_expense += tx.amount

            net_cash_flow = total_income - total_expense - total_debt_payments

            result[currency] = {
                "total_income": total_income,
                "total_expense": total_expense,
                "total_debt_payments": total_debt_payments,
                "net_cash_flow": net_cash_flow
            }

        return result