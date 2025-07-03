from sqlmodel import Session, select
from fastapi import HTTPException
from app.models.saving_account import SavingAccount

def update_account_balance(session: Session, account_id: int, amount_delta: float):
    account = session.exec(
        select(SavingAccount).where(SavingAccount.id == account_id)
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="Cuenta no encontrada")

    account.balance += amount_delta
    session.add(account)  # Se requiere para que SQLModel registre el cambio