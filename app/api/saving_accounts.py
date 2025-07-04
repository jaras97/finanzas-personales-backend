from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from uuid import UUID
from typing import List

from app.database import engine
from app.models.saving_account import SavingAccount, SavingAccountStatus
from app.schemas.saving_account import SavingAccountCreate, SavingAccountDeposit, SavingAccountRead, SavingAccountWithdraw
from app.core.security import get_current_user, get_current_user_with_subscription_check
from app.schemas.transaction import TransactionWithCategoryRead
from sqlalchemy.orm import joinedload

from app.models.transaction import Transaction
from app.models.enums import TransactionType
from datetime import datetime

router = APIRouter(prefix="/saving-accounts", tags=["saving_accounts"])


@router.post("/", response_model=SavingAccountRead)
def create_saving_account(
    account_data: SavingAccountCreate,
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    with Session(engine) as session:
        existing = session.exec(
            select(SavingAccount).where(
                SavingAccount.user_id == user_id,
                SavingAccount.name == account_data.name
            )
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Ya tienes una cuenta con este nombre.")
        
        new_account = SavingAccount(**account_data.dict(), user_id=user_id)
        session.add(new_account)
        session.commit()
        session.refresh(new_account)
        return new_account


@router.get("/", response_model=List[SavingAccountRead])
def list_saving_accounts(user_id: UUID = Depends(get_current_user_with_subscription_check)):
    with Session(engine) as session:
        accounts = session.exec(
            select(SavingAccount).where(SavingAccount.user_id == user_id)
        ).all()
        return accounts


@router.put("/{account_id}", response_model=SavingAccountRead)
def update_saving_account(
    account_id: int,
    account_data: SavingAccountCreate,
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    with Session(engine) as session:
        account = session.exec(
            select(SavingAccount).where(SavingAccount.id == account_id, SavingAccount.user_id == user_id)
        ).first()

        if not account:
            raise HTTPException(status_code=404, detail="Cuenta de ahorro no encontrada")

        account.name = account_data.name
        account.balance = account_data.balance
        account.type = account_data.type

        session.add(account)
        session.commit()
        session.refresh(account)
        return account


from sqlalchemy.exc import IntegrityError

@router.delete("/{account_id}")
def delete_saving_account(
    account_id: int,
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    with Session(engine) as session:
        account = session.exec(
            select(SavingAccount).where(
                SavingAccount.id == account_id,
                SavingAccount.user_id == user_id
            )
        ).first()

        if not account:
            raise HTTPException(status_code=404, detail="Cuenta de ahorro no encontrada")

        try:
            session.delete(account)
            session.commit()
            return {"message": "Cuenta de ahorro eliminada correctamente"}
        except IntegrityError:
            session.rollback()
            raise HTTPException(
                status_code=400,
                detail="No puedes eliminar esta cuenta porque tiene transacciones asociadas."
            )
    


@router.post("/{account_id}/withdraw", response_model=SavingAccountRead)
def withdraw_from_saving_account(
    account_id: int,
    withdraw_data: SavingAccountWithdraw,
    user_id: UUID = Depends(get_current_user_with_subscription_check)
):
    user_id = UUID(user_id)
    with Session(engine) as session:
        account = session.get(SavingAccount, account_id)

        if not account or account.user_id != user_id:
            raise HTTPException(status_code=404, detail="Cuenta no encontrada")

        if withdraw_data.amount > account.balance:
            raise HTTPException(status_code=400, detail="Fondos insuficientes")

        # 1. Actualizar el balance
        account.balance -= withdraw_data.amount
        session.add(account)

        # 2. Registrar la transacción
        transaction = Transaction(
            user_id=user_id,
            amount=withdraw_data.amount,
            type=TransactionType.expense,
            description=f"Retiro desde cuenta de ahorro: {account.name}",
            date=datetime.utcnow(),
            category_id=None,  # O crea una categoría genérica 'Ahorros' si prefieres
            saving_account_id=account.id,
            source_type="account_deposit",
        )
        session.add(transaction)

        # 3. Guardar todo
        session.commit()
        session.refresh(account)

        return account
    
@router.post("/{account_id}/deposit")
def deposit_to_saving_account(
    account_id: int,
    data: SavingAccountDeposit,
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    with Session(engine) as session:
        account = session.get(SavingAccount, account_id)
        if not account or account.user_id != UUID(user_id):
            raise HTTPException(status_code=404, detail="Cuenta no encontrada")

        account.balance += data.amount
        session.add(account)

        # 👉 Registrar transacción
        transaction = Transaction(
            user_id=user_id,
            amount=data.amount,
            type=TransactionType.income,
            description=data.description or f"Depósito a {account.name}",
            date=datetime.utcnow(),
            category_id=None,  # Puedes crear una categoría fija tipo "Transferencia Interna"
            saving_account_id=account.id,
            source_type="account_deposit",  
        )
        session.add(transaction)

        session.commit()
        return {"message": "Depósito exitoso", "nuevo_balance": account.balance}
    
@router.post("/{account_id}/close")
def close_saving_account(
    account_id: int,
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    with Session(engine) as session:
        account = session.exec(
            select(SavingAccount).where(
                SavingAccount.id == account_id,
                SavingAccount.user_id == user_id
            )
        ).first()

        if not account:
            raise HTTPException(status_code=404, detail="Cuenta no encontrada.")

        if account.balance != 0:
            raise HTTPException(
                status_code=400,
                detail="No puedes cerrar esta cuenta hasta que el saldo sea cero."
            )

        account.status = SavingAccountStatus.closed
        account.closed_at = datetime.utcnow()
        session.add(account)
        session.commit()

        return {"message": "Cuenta cerrada correctamente."}
    


@router.get("/{account_id}/transactions", response_model=List[TransactionWithCategoryRead])
def get_account_transactions(
    account_id: int,
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    with Session(engine) as session:
        account = session.exec(
            select(SavingAccount).where(
                SavingAccount.id == account_id,
                SavingAccount.user_id == user_id
            )
        ).first()

        if not account:
            raise HTTPException(status_code=404, detail="Cuenta no encontrada")

        transactions = session.exec(
            select(Transaction)
            .where(Transaction.saving_account_id == account_id)
            .options(
                joinedload(Transaction.category),
                joinedload(Transaction.from_account),
                joinedload(Transaction.to_account),
                joinedload(Transaction.debt),
                joinedload(Transaction.saving_account),
            )
            .order_by(Transaction.date.desc())
        ).all()

        return [
            TransactionWithCategoryRead.model_validate(t, from_attributes=True)
            for t in transactions
        ]