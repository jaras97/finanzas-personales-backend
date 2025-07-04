from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlmodel import Session, select
from uuid import UUID
from typing import List

from app.database import engine
from app.models.debt import Debt, DebtKind
from app.models.debt_transaction import DebtTransaction, DebtTransactionType
from app.models.enums import TransactionType
from app.models.saving_account import SavingAccount
from app.models.transaction import Transaction
from app.schemas.debt import AddChargeRequest, DebtCreate, DebtPayment, DebtRead
from app.core.security import get_current_user, get_current_user_with_subscription_check
from app.schemas.debt_transaction import DebtTransactionRead
from app.schemas.transaction import TransactionRead
from app.utils.account_helpers import update_account_balance

router = APIRouter(prefix="/debts", tags=["debts"])


@router.post("/", response_model=DebtRead)
def create_debt(
    debt_data: DebtCreate,
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    with Session(engine) as session:
        new_debt = Debt(**debt_data.dict(), user_id=user_id)
        session.add(new_debt)
        session.commit()
        session.refresh(new_debt)
        return new_debt


@router.get("/", response_model=List[DebtRead])
def get_debts(user_id: UUID = Depends(get_current_user_with_subscription_check)):
    with Session(engine) as session:
        debts = session.exec(select(Debt).where(Debt.user_id == user_id)).all()
        debts_read = []

        for debt in debts:
            # Calculamos el conteo de transacciones sin traer todas las transacciones
            transactions_count = session.exec(
                select(func.count()).select_from(Transaction).where(Transaction.debt_id == debt.id)
            ).one()

            # Mapeamos manualmente para incluir transactions_count
            debt_dict = debt.dict()
            debt_dict["transactions_count"] = transactions_count
            debts_read.append(DebtRead(**debt_dict))

        return debts_read
    

@router.put("/{debt_id}", response_model=DebtRead)
def update_debt(
    debt_id: int,
    debt_data: DebtCreate,
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    user_id = UUID(user_id)
    with Session(engine) as session:
        debt = session.exec(
            select(Debt).where(Debt.id == debt_id, Debt.user_id == user_id)
        ).first()

        if not debt:
            raise HTTPException(status_code=404, detail="Deuda no encontrada")

        # Verificar si la deuda tiene transacciones asociadas
        transactions_exist = session.exec(
            select(Transaction).where(Transaction.debt_id == debt_id)
        ).first() is not None

        if transactions_exist:
            # Bloquear edición de currency si hay transacciones
            if debt_data.currency != debt.currency:
                raise HTTPException(
                    status_code=400,
                    detail="No puedes cambiar la moneda de la deuda porque tiene transacciones asociadas."
                )
            # Bloquear edición de total_amount si hay transacciones
            if debt_data.total_amount != debt.total_amount:
                raise HTTPException(
                    status_code=400,
                    detail="No puedes cambiar el monto total de la deuda porque tiene transacciones asociadas."
                )

        # Permitir cambios seguros
        debt.name = debt_data.name
        debt.interest_rate = debt_data.interest_rate
        debt.due_date = debt_data.due_date
        debt.currency = debt_data.currency  # Se mantiene igual o se actualiza si no hay transacciones
        debt.total_amount = debt_data.total_amount  # Igual

        session.add(debt)
        session.commit()
        session.refresh(debt)

        # ✅ Calcular transactions_count de forma consistente
        transactions_count = session.exec(
            select(func.count()).select_from(Transaction).where(Transaction.debt_id == debt_id)
        ).one()

        # ✅ Retornar de forma compatible con DebtRead
        debt_dict = debt.dict()
        debt_dict["transactions_count"] = transactions_count
        return DebtRead(**debt_dict)


@router.delete("/{debt_id}")
def delete_debt(
    debt_id: int,
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    user_id = UUID(user_id)
    with Session(engine) as session:
        debt = session.exec(
            select(Debt).where(Debt.id == debt_id, Debt.user_id == user_id)
        ).first()

        if not debt:
            raise HTTPException(status_code=404, detail="Deuda no encontrada")
        if debt.total_amount > 0:
            raise HTTPException(
                status_code=400,
                detail="No puedes eliminar una deuda con saldo pendiente."
            )

        session.delete(debt)
        session.commit()
        return {"message": "Deuda eliminada correctamente"}
    
@router.post("/{debt_id}/pay", response_model=TransactionRead)
def pay_debt(
    debt_id: int,
    payment: DebtPayment,
    user_id: UUID = Depends(get_current_user_with_subscription_check)
):
    user_id = UUID(user_id)
    if payment.amount <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser mayor a cero.")

    with Session(engine) as session:
        # Validar la deuda
        debt = session.exec(
            select(Debt).where(Debt.id == debt_id, Debt.user_id == user_id)
        ).first()
        if not debt:
            raise HTTPException(status_code=404, detail="Deuda no encontrada")

        # Validar la cuenta
        account = session.exec(
            select(SavingAccount).where(
                SavingAccount.id == payment.saving_account_id,
                SavingAccount.user_id == user_id
            )
        ).first()
        if not account:
            raise HTTPException(status_code=400, detail="Cuenta inválida")
        
        if account.currency != debt.currency:
            raise HTTPException(
                status_code=400,
                detail="No puedes pagar una deuda con una cuenta de distinta moneda en este momento."
            )

        if account.balance < payment.amount:
            raise HTTPException(status_code=400, detail="Saldo insuficiente")

        # Crear transacción
        tx = Transaction(
            user_id=user_id,
            amount=payment.amount,
            type=TransactionType.expense,
            saving_account_id=payment.saving_account_id,
            date=payment.date or datetime.utcnow(),
            description=payment.description or f"Pago de deuda: {debt.name}",
            debt_id=debt.id,
            source_type="debt_payment",
        )
        session.add(tx)

        debt_tx = DebtTransaction(
        user_id=user_id,
        debt_id=debt.id,
        amount=payment.amount,
        type=DebtTransactionType.payment,
        description=payment.description or f"Pago de deuda: {debt.name}",
        date=payment.date or datetime.utcnow()
        )
        session.add(debt_tx)

        # Actualizar balance de la cuenta
        update_account_balance(session, payment.saving_account_id, -payment.amount)

        # Reducir el monto de la deuda
        debt.total_amount -= payment.amount
        if debt.total_amount <= 0.01:  # margen de tolerancia
            debt.total_amount = 0.0
            debt.status = "closed"
        session.add(debt)

        session.commit()
        session.refresh(tx)
        return tx
    
@router.post("/{debt_id}/add-charge", response_model=DebtRead)
def add_charge_to_debt(
    debt_id: int,
    data: AddChargeRequest,
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    user_id = UUID(user_id)
    with Session(engine) as session:
        debt = session.get(Debt, debt_id)

        if not debt or debt.user_id != user_id:
            raise HTTPException(status_code=404, detail="Deuda no encontrada")
        
        if debt.status != "active":
            raise HTTPException(status_code=400, detail="La deuda no está activa")

        if data.amount <= 0:
            raise HTTPException(status_code=400, detail="El monto debe ser positivo")

        # Incrementar saldo pendiente
        debt.total_amount += data.amount
        session.add(debt)

        # Registrar transacción asociada
        charge_tx = DebtTransaction(
            user_id=user_id,
            debt_id=debt_id,
            amount=data.amount,
            type="interest_charge",
            description=data.description,
            date=data.date or datetime.utcnow(),
        )
        session.add(charge_tx)

        session.commit()
        session.refresh(debt)

        return debt
    
@router.get("/{debt_id}/transactions", response_model=List[DebtTransactionRead])
def get_debt_transactions(
    debt_id: int,
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    user_id = UUID(user_id)
    with Session(engine) as session:
        debt = session.get(Debt, debt_id)
        if not debt or debt.user_id != user_id:
            raise HTTPException(status_code=404, detail="Deuda no encontrada")
        
        transactions = session.exec(
            select(DebtTransaction)
            .where(DebtTransaction.debt_id == debt_id, DebtTransaction.user_id == user_id)
            .order_by(DebtTransaction.date.desc())
        ).all()

        return transactions
    
@router.post("/{debt_id}/purchase", response_model=TransactionRead)
def register_credit_card_purchase(
    debt_id: int,
    purchase: AddChargeRequest,  # reutiliza schema (amount, description, date)
    user_id: UUID = Depends(get_current_user_with_subscription_check)
):
    user_id = UUID(user_id)
    if purchase.amount <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser positivo.")

    with Session(engine) as session:
        debt = session.get(Debt, debt_id)

        if not debt or debt.user_id != user_id:
            raise HTTPException(status_code=404, detail="Deuda no encontrada")
        
        if debt.status != "active":
            raise HTTPException(status_code=400, detail="La deuda no está activa")

        if debt.kind != DebtKind.credit_card:
            raise HTTPException(status_code=400, detail="Solo puedes registrar compras en deudas de tipo tarjeta de crédito.")

        # Incrementa saldo de la deuda
        debt.total_amount += purchase.amount
        session.add(debt)

        # Crea transacción tipo expense con debt_id
        tx = Transaction(
            user_id=user_id,
            amount=purchase.amount,
            type=TransactionType.expense,
            date=purchase.date or datetime.utcnow(),
            description=purchase.description or f"Compra con tarjeta: {debt.name}",
            debt_id=debt.id,
            source_type="credit_card_purchase"
        )
        session.add(tx)

        # También registra en DebtTransaction como 'extra_charge'
        debt_tx = DebtTransaction(
            user_id=user_id,
            debt_id=debt.id,
            amount=purchase.amount,
            type=DebtTransactionType.extra_charge,
            description=purchase.description or f"Compra con tarjeta: {debt.name}",
            date=purchase.date or datetime.utcnow()
        )
        session.add(debt_tx)

        session.commit()
        session.refresh(tx)

        return tx