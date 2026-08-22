from uuid import UUID
from typing import List

from fastapi import HTTPException
from sqlmodel import Session, select

from app.models.currency import Currency
from app.models.debt import Debt
from app.models.saving_account import SavingAccount


def validate_currency_code(session: Session, code: str) -> None:
    if not session.get(Currency, code):
        raise HTTPException(status_code=400, detail=f"Moneda '{code}' no soportada.")


def get_user_currencies(session: Session, user_id: UUID) -> List[str]:
    """Monedas que el usuario realmente tiene en uso (cuentas + deudas), no un
    conjunto fijo -- así los reportes cubren cualquier moneda sin necesidad de
    listarlas a mano, y no aparecen monedas "fantasma" en 0 para quienes no
    las usan."""
    from_accounts = session.exec(
        select(SavingAccount.currency).where(SavingAccount.user_id == user_id).distinct()
    ).all()
    from_debts = session.exec(
        select(Debt.currency).where(Debt.user_id == user_id).distinct()
    ).all()
    return sorted(set(from_accounts) | set(from_debts))
