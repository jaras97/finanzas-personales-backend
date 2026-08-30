from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select, func
from uuid import UUID

from app.database import engine
from app.models.debt import Debt, DebtStatus
from app.models.saving_account import SavingAccount, SavingAccountType, SavingAccountStatus
from app.models.user import User
from app.core.security import get_current_user_with_subscription_check
from app.utils.currency_helpers import get_user_currencies
from app.routes.fx import resolve_rate

router = APIRouter(prefix="/summary-extra", tags=["summary-extra"])

@router.get("/assets-summary")
def get_assets_summary(user_id: UUID = Depends(get_current_user_with_subscription_check)):
    with Session(engine) as session:
        currencies = get_user_currencies(session, user_id)
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
        currencies = get_user_currencies(session, user_id)
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
        currencies = get_user_currencies(session, user_id)
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


@router.get("/net-worth-consolidated")
async def get_net_worth_consolidated(
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    """Patrimonio neto de todas las monedas del usuario, convertido a una
    sola moneda de referencia (`User.report_currency`) usando la tasa de hoy
    -- no es una reconstrucción histórica, es "cuánto tengo ahora mismo en
    total" (ver docs/PENDIENTES.md, Fase 6 del roadmap).

    Si `/fx/rate` falla para alguna moneda (sus dos proveedores externos
    caídos), esa moneda se muestra sin convertir en el `breakdown` y no
    entra en la suma -- degrada con gracia en vez de romper todo el
    endpoint, `degraded=True` avisa al frontend que el total es parcial.
    """
    with Session(engine) as session:
        user = session.get(User, user_id)
        report_currency = user.report_currency if user else "COP"
        per_currency = get_net_worth_summary(user_id)

    total_assets = 0.0
    total_liabilities = 0.0
    degraded = False
    breakdown = []

    for currency, data in per_currency.items():
        if currency == report_currency:
            rate = 1.0
        else:
            try:
                rate = (await resolve_rate(currency, report_currency))["rate"]
            except HTTPException:
                degraded = True
                breakdown.append(
                    {
                        "currency": currency,
                        "original_assets": data["total_assets"],
                        "original_liabilities": data["total_liabilities"],
                        "converted_assets": None,
                        "converted_liabilities": None,
                        "rate_used": None,
                    }
                )
                continue

        converted_assets = data["total_assets"] * rate
        converted_liabilities = data["total_liabilities"] * rate
        total_assets += converted_assets
        total_liabilities += converted_liabilities
        breakdown.append(
            {
                "currency": currency,
                "original_assets": data["total_assets"],
                "original_liabilities": data["total_liabilities"],
                "converted_assets": converted_assets,
                "converted_liabilities": converted_liabilities,
                "rate_used": rate,
            }
        )

    return {
        "report_currency": report_currency,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "net_worth": total_assets - total_liabilities,
        "degraded": degraded,
        "breakdown": breakdown,
    }