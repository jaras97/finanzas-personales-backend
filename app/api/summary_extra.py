from fastapi import APIRouter, Depends
from sqlmodel import Session, select, func
from uuid import UUID

from app.database import engine
from app.models.debt import Debt, DebtStatus
from app.models.saving_account import Currency, SavingAccount, SavingAccountType, SavingAccountStatus
from app.core.security import get_current_user_with_subscription_check

router = APIRouter(prefix="/summary-extra", tags=["summary-extra"])

@router.get("/assets-summary")
def get_assets_summary(user_id: UUID = Depends(get_current_user_with_subscription_check)):
    with Session(engine) as session:
        currencies = [Currency.COP, Currency.USD]
        total_savings = {}
        total_investments = {}
        total_assets = {}

        for currency in currencies:
            savings_sum = session.exec(
                select(func.coalesce(func.sum(SavingAccount.balance), 0))
                .where(
                    SavingAccount.user_id == user_id,
                    SavingAccount.status == SavingAccountStatus.active,
                    SavingAccount.type.in_([SavingAccountType.cash, SavingAccountType.bank]),
                    SavingAccount.currency == currency
                )
            ).one()

            investments_sum = session.exec(
                select(func.coalesce(func.sum(SavingAccount.balance), 0))
                .where(
                    SavingAccount.user_id == user_id,
                    SavingAccount.status == SavingAccountStatus.active,
                    SavingAccount.type == SavingAccountType.investment,
                    SavingAccount.currency == currency
                )
            ).one()

            total_savings[currency] = savings_sum
            total_investments[currency] = investments_sum
            total_assets[currency] = savings_sum + investments_sum

        return {
            "total_savings": total_savings,
            "total_investments": total_investments,
            "total_assets": total_assets
        }


@router.get("/liabilities-summary")
def get_liabilities_summary(user_id: UUID = Depends(get_current_user_with_subscription_check)):
    with Session(engine) as session:
        currencies = [Currency.COP, Currency.USD]
        total_liabilities = {}

        for currency in currencies:
            debts = session.exec(
                select(Debt).where(
                    Debt.user_id == user_id,
                    Debt.status == DebtStatus.active,
                    Debt.currency == currency
                )
            ).all()

            total = 0.0
            for debt in debts:
                total_paid = sum(t.amount for t in debt.transactions if t.type == "payment")
                pending = debt.total_amount - total_paid
                if pending > 0:
                    total += pending

            total_liabilities[currency] = total

        return {"total_liabilities": total_liabilities}


@router.get("/net-worth-summary")
def get_net_worth_summary(user_id: UUID = Depends(get_current_user_with_subscription_check)):
    with Session(engine) as session:
        currencies = [Currency.COP, Currency.USD, Currency.EUR]
        summary = {}

        for currency in currencies:
            total_savings = session.exec(
                select(func.coalesce(func.sum(SavingAccount.balance), 0))
                .where(
                    SavingAccount.user_id == user_id,
                    SavingAccount.status == SavingAccountStatus.active,
                    SavingAccount.type.in_([SavingAccountType.cash, SavingAccountType.bank]),
                    SavingAccount.currency == currency
                )
            ).one()

            total_investments = session.exec(
                select(func.coalesce(func.sum(SavingAccount.balance), 0))
                .where(
                    SavingAccount.user_id == user_id,
                    SavingAccount.status == SavingAccountStatus.active,
                    SavingAccount.type == SavingAccountType.investment,
                    SavingAccount.currency == currency
                )
            ).one()

            total_assets = total_savings + total_investments

            debts = session.exec(
                select(Debt).where(
                    Debt.user_id == user_id,
                    Debt.status == DebtStatus.active,
                    Debt.currency == currency
                )
            ).all()

            total_liabilities = 0.0
            for debt in debts:
                total_paid = sum(t.amount for t in debt.transactions if t.type == "payment")
                pending = debt.total_amount - total_paid
                if pending > 0:
                    total_liabilities += pending

            net_worth = total_assets - total_liabilities
            debt_ratio = (total_liabilities / total_assets * 100) if total_assets > 0 else 0

            summary[currency] = {
                "total_assets": total_assets,
                "total_liabilities": total_liabilities,
                "net_worth": net_worth,
                "debt_ratio": debt_ratio
            }

        return summary