import datetime as dt
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlmodel import Session, select
from uuid import UUID
from typing import List

from app.database import engine
from app.models.category import Category, CategoryType
from app.models.debt import Debt, DebtKind
from app.models.debt_transaction import DebtTransaction, DebtTransactionType
from app.models.enums import TransactionType
from app.models.saving_account import SavingAccount
from app.models.transaction import Transaction
from app.schemas.debt import AddChargeRequest, CreditCardPurchaseCreate, DebtCreate, DebtPayment, DebtRead
from app.core.security import get_current_user, get_current_user_with_subscription_check
from app.schemas.debt_transaction import DebtTransactionRead
from app.schemas.transaction import TransactionRead
from app.utils.account_helpers import update_account_balance

router = APIRouter(prefix="/debts", tags=["debts"])

def debt_has_transactions(session: Session, debt_id: int) -> bool:
    tx_exists = session.exec(
        select(Transaction.id).where(Transaction.debt_id == debt_id).limit(1)
    ).first() is not None
    if tx_exists:
        return True
    dtx_exists = session.exec(
        select(DebtTransaction.id).where(DebtTransaction.debt_id == debt_id).limit(1)
    ).first() is not None
    return dtx_exists


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
            tx_count = session.exec(
                select(func.count()).select_from(Transaction).where(Transaction.debt_id == debt.id)
            ).one()
            dtx_count = session.exec(
                select(func.count()).select_from(DebtTransaction).where(DebtTransaction.debt_id == debt.id)
            ).one()
            total_count = (tx_count or 0) + (dtx_count or 0)

            debt_dict = debt.dict()
            debt_dict["transactions_count"] = total_count
            debts_read.append(DebtRead(**debt_dict))

        return debts_read
    
def _normalize_dt(value: dt.date | dt.datetime | str | None) -> dt.datetime:
    """Normaliza a datetime naive en UTC."""
    if value is None:
        return dt.datetime.utcnow()

    if isinstance(value, dt.datetime):
        # Si viene aware, pásalo a UTC y quita tzinfo; si ya es naive, asume UTC
        return value.astimezone(dt.timezone.utc).replace(tzinfo=None) if value.tzinfo else value

    if isinstance(value, dt.date) and not isinstance(value, dt.datetime):
        # Solo fecha → úsala a las 12:00 para evitar desbordes por tz
        return dt.datetime.combine(value, dt.time(12, 0, 0))

    if isinstance(value, str):
        # Acepta ISO con 'Z' o con offset
        s = value.replace("Z", "+00:00")
        try:
            parsed = dt.datetime.fromisoformat(s)
        except ValueError:
            # fallback a YYYY-MM-DD
            parsed = dt.datetime.strptime(value, "%Y-%m-%d")
        return _normalize_dt(parsed)

    raise TypeError(f"Unsupported type for date: {type(value)!r}")
    

@router.put("/{debt_id}", response_model=DebtRead)
def update_debt(debt_id: int, debt_data: DebtCreate, user_id: UUID = Depends(get_current_user_with_subscription_check)):
    with Session(engine) as session:
        debt = session.exec(select(Debt).where(Debt.id == debt_id, Debt.user_id == user_id)).first()
        if not debt:
            raise HTTPException(status_code=404, detail="Deuda no encontrada")

        if debt_has_transactions(session, debt_id):
            if debt_data.currency != debt.currency:
                raise HTTPException(400, "No puedes cambiar la moneda: la deuda tiene movimientos.")
            if debt_data.total_amount != debt.total_amount:
                raise HTTPException(400, "No puedes cambiar el monto total: la deuda tiene movimientos.")

        debt.name = debt_data.name
        debt.interest_rate = debt_data.interest_rate
        debt.due_date = debt_data.due_date
        debt.currency = debt_data.currency
        debt.total_amount = debt_data.total_amount

        session.add(debt); session.commit(); session.refresh(debt)

        tx_count = session.exec(select(func.count()).select_from(Transaction).where(Transaction.debt_id == debt_id)).one()
        dtx_count = session.exec(select(func.count()).select_from(DebtTransaction).where(DebtTransaction.debt_id == debt_id)).one()
        debt_dict = debt.dict(); debt_dict["transactions_count"] = (tx_count or 0) + (dtx_count or 0)
        return DebtRead(**debt_dict)



@router.delete("/{debt_id}")
def delete_debt(debt_id: int, user_id: UUID = Depends(get_current_user_with_subscription_check)):
    with Session(engine) as session:
        debt = session.exec(select(Debt).where(Debt.id == debt_id, Debt.user_id == user_id)).first()
        if not debt:
            raise HTTPException(status_code=404, detail="Deuda no encontrada")

        if debt_has_transactions(session, debt_id):
            raise HTTPException(400, "No puedes eliminar esta deuda porque tiene movimientos asociados.")

        session.delete(debt); session.commit()
        return {"message": "Deuda eliminada correctamente"}

    
@router.post("/{debt_id}/pay", response_model=TransactionRead)
def pay_debt(debt_id: int, payment: DebtPayment, user_id: UUID = Depends(get_current_user_with_subscription_check)):
    if payment.amount <= 0:
        raise HTTPException(400, "El monto debe ser mayor a cero.")

    with Session(engine) as session:
        debt = session.exec(select(Debt).where(Debt.id == debt_id, Debt.user_id == user_id)).first()
        if not debt:
            raise HTTPException(404, "Deuda no encontrada")
        
        EPS = 0.01
        if payment.amount - debt.total_amount > EPS:
            raise HTTPException(
                status_code=400,
                detail=f"El monto a pagar ({payment.amount}) excede el saldo pendiente ({debt.total_amount}).",
            )

        account = session.exec(select(SavingAccount).where(SavingAccount.id == payment.saving_account_id, SavingAccount.user_id == user_id)).first()
        if not account:
            raise HTTPException(400, "Cuenta inválida")
        if account.status != "active":
            raise HTTPException(400, "No puedes pagar con una cuenta cerrada.")
        if account.currency != debt.currency:
            raise HTTPException(400, "Monedas distintas entre cuenta y deuda.")
        if account.balance < payment.amount:
            raise HTTPException(400, "Saldo insuficiente")

        tx = Transaction(
            user_id=user_id, amount=payment.amount, type=TransactionType.expense,
            saving_account_id=payment.saving_account_id, date=payment.date or dt.datetime.utcnow(),
            description=payment.description or f"Pago de deuda: {debt.name}", debt_id=debt.id, source_type="debt_payment",
        )
        session.add(tx)
        session.add(DebtTransaction(
            user_id=user_id, debt_id=debt.id, amount=payment.amount,
            type=DebtTransactionType.payment, description=payment.description or f"Pago de deuda: {debt.name}",
            date=payment.date or dt.datetime.utcnow(),
        ))

        update_account_balance(session, payment.saving_account_id, -payment.amount)

        debt.total_amount -= payment.amount
        if debt.total_amount <= 0.01:
            debt.total_amount = 0.0
            # ✅ Solo préstamos se auto-cierran; tarjetas quedan activas
            if debt.kind == DebtKind.loan:
                debt.status = "closed"
        session.add(debt)

        session.commit(); session.refresh(tx)
        return tx

    
@router.post("/{debt_id}/add-charge", response_model=DebtRead)
def add_charge_to_debt(
    debt_id: int,
    data: AddChargeRequest,
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
   
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
            date=data.date or dt.datetime.utcnow(),
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
    purchase: CreditCardPurchaseCreate,
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    if purchase.amount <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser positivo.")

    with Session(engine) as session:
        debt = session.get(Debt, debt_id)
        if not debt or debt.user_id != user_id:
            raise HTTPException(status_code=404, detail="Deuda no encontrada")
        if debt.status != "active":
            raise HTTPException(status_code=400, detail="La deuda no está activa")
        if debt.kind != DebtKind.credit_card:
            raise HTTPException(
                status_code=400,
                detail="Solo puedes registrar compras en deudas de tipo tarjeta de crédito."
            )

        # Validar categoría (propiedad, activa y de gasto/both)
        category = session.exec(
            select(Category).where(
                Category.id == purchase.category_id,
                Category.user_id == user_id,
                Category.is_active == True
            )
        ).first()
        if not category:
            raise HTTPException(status_code=400, detail="Categoría inválida")
        if category.type not in (CategoryType.expense, CategoryType.both):
            raise HTTPException(status_code=400, detail="La categoría no es de gasto")

        tx_date = _normalize_dt(purchase.date)

        print("tx_date:", tx_date)

        # 1) Incrementar saldo pendiente de la deuda
        debt.total_amount += purchase.amount
        session.add(debt)

        # 2) Registrar gasto categorizado en el libro mayor
        tx = Transaction(
            user_id=user_id,
            amount=purchase.amount,
            type=TransactionType.expense,
            date=tx_date,
            description=purchase.description or f"Compra con tarjeta: {debt.name}",
            category_id=purchase.category_id,     # ✅ ahora queda categorizada
            saving_account_id=None,               # explícito: no afecta cuenta de ahorro
            debt_id=debt.id,
            source_type="credit_card_purchase",
        )
        session.add(tx)

        # 3) Asiento en subledger de la deuda
        debt_tx = DebtTransaction(
            user_id=user_id,
            debt_id=debt.id,
            amount=purchase.amount,
            type=DebtTransactionType.extra_charge,
            description=tx.description,
            date=tx_date,
        )
        session.add(debt_tx)

        session.commit()
        session.refresh(tx)
        return tx
    
@router.post("/{debt_id}/close")
def close_debt(debt_id: int, user_id: UUID = Depends(get_current_user_with_subscription_check)):
    with Session(engine) as session:
        debt = session.exec(select(Debt).where(Debt.id == debt_id, Debt.user_id == user_id)).first()
        if not debt:
            raise HTTPException(404, "Deuda no encontrada")
        if debt.total_amount != 0:
            raise HTTPException(400, "Solo puedes cerrar deudas con saldo 0.")
        if debt.status == "closed":
            raise HTTPException(400, "La deuda ya está cerrada.")

        debt.status = "closed"; session.add(debt); session.commit()
        return {"message": "Deuda cerrada correctamente."}

@router.post("/{debt_id}/reopen")
def reopen_debt(debt_id: int, user_id: UUID = Depends(get_current_user_with_subscription_check)):
    with Session(engine) as session:
        debt = session.exec(select(Debt).where(Debt.id == debt_id, Debt.user_id == user_id)).first()
        if not debt:
            raise HTTPException(404, "Deuda no encontrada")
        if debt.status != "closed":
            raise HTTPException(400, "La deuda no está cerrada.")

        debt.status = "active"; session.add(debt); session.commit()
        return {"message": "Deuda reabierta correctamente."}