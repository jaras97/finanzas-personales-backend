from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlmodel import Session, select
from app.database import engine
from app.models.category import Category
from app.models.enums import TransactionType
from app.models.saving_account import SavingAccount, SavingAccountStatus, SavingAccountType
from app.models.transaction import Transaction
from app.schemas.transaction import RegisterYieldCreate, TransactionCreate, TransactionRead, TransferCreate
from app.core.security import get_current_user, get_current_user_with_subscription_check
from datetime import datetime
from typing import Optional, List
from fastapi import Query
from app.schemas.transaction import TransactionWithCategoryRead
from sqlalchemy.orm import joinedload
from sqlalchemy import func

from app.utils.account_helpers import update_account_balance
from app.utils.category_helpers import get_or_create_transfer_category

router = APIRouter(prefix="/transactions", tags=["transactions"])


from datetime import datetime

@router.post("/", response_model=TransactionRead)
def create_transaction(
    transaction_data: TransactionCreate,
    user_id: UUID = Depends(get_current_user_with_subscription_check)
):
    with Session(engine) as session:
        if transaction_data.amount <= 0:
            raise HTTPException(status_code=400, detail="El monto debe ser mayor a cero.")
        if transaction_data.transaction_fee < 0:
            raise HTTPException(status_code=400, detail="La comisión no puede ser negativa.")

        category = session.exec(
            select(Category).where(
                Category.id == transaction_data.category_id,
                Category.user_id == user_id
            )
        ).first()
        if not category:
            raise HTTPException(status_code=400, detail="Categoría inválida")

        if transaction_data.saving_account_id is None:
            raise HTTPException(status_code=400, detail="Se requiere una cuenta asociada.")

        account = session.exec(
            select(SavingAccount).where(
                SavingAccount.id == transaction_data.saving_account_id,
                SavingAccount.user_id == user_id
            )
        ).first()
        if not account:
            raise HTTPException(status_code=400, detail="Cuenta de ahorro inválida")
        if account.status != SavingAccountStatus.active:
            raise HTTPException(status_code=400, detail="La cuenta no está activa.")

        net_amount = transaction_data.amount
        if transaction_data.type == TransactionType.income:
            net_amount -= transaction_data.transaction_fee
            if net_amount < 0:
                raise HTTPException(status_code=400, detail="La comisión excede el monto de ingreso.")
            account.balance += net_amount
        elif transaction_data.type == TransactionType.expense:
            total_amount = transaction_data.amount + transaction_data.transaction_fee
            if account.balance < total_amount:
                raise HTTPException(status_code=400, detail="Fondos insuficientes para cubrir el gasto y la comisión.")
            account.balance -= total_amount

        session.add(account)

        # ✅ Solución para evitar duplicidad de 'date':
        data = transaction_data.dict()
        if data.get("date") is None:
            data["date"] = datetime.utcnow()

        transaction = Transaction(
            **data,
            user_id=user_id
        )
        session.add(transaction)

        # Registrar transacción de comisión separada si se desea visibilidad en reportes
        if transaction_data.transaction_fee > 0:
            fee_transaction = Transaction(
                user_id=user_id,
                amount=transaction_data.transaction_fee,
                transaction_fee=0.0,
                description=f"Comisión por transacción: {transaction_data.description}",
                type=TransactionType.expense,
                saving_account_id=transaction_data.saving_account_id,
                category_id=transaction_data.category_id,
                date=data["date"]
            )
            session.add(fee_transaction)

        session.commit()
        session.refresh(transaction)
        return transaction
    
@router.post("/transfer", response_model=List[TransactionRead])
def create_transfer(
    transfer_data: TransferCreate,
    user_id: UUID = Depends(get_current_user_with_subscription_check)
):
    
    if transfer_data.from_account_id == transfer_data.to_account_id:
        raise HTTPException(status_code=400, detail="No se puede transferir a la misma cuenta.")
    if transfer_data.amount <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser mayor a cero.")
    if transfer_data.transaction_fee < 0:
        raise HTTPException(status_code=400, detail="La comisión no puede ser negativa.")

    with Session(engine) as session:
        from_account = session.get(SavingAccount, transfer_data.from_account_id)
        to_account = session.get(SavingAccount, transfer_data.to_account_id)

        if not from_account or from_account.user_id != user_id:
            raise HTTPException(status_code=400, detail="Cuenta de origen inválida")
        if not to_account or to_account.user_id != user_id:
            raise HTTPException(status_code=400, detail="Cuenta de destino inválida")
        if from_account.status != SavingAccountStatus.active:
            raise HTTPException(status_code=400, detail="La cuenta origen no está activa.")
        if to_account.status != SavingAccountStatus.active:
            raise HTTPException(status_code=400, detail="La cuenta destino no está activa.")

        # 🚩 Validar y aplicar tasa de conversión si las monedas son diferentes
        if from_account.currency != to_account.currency:
            if transfer_data.exchange_rate is None or transfer_data.exchange_rate <= 0:
                raise HTTPException(
                    status_code=400,
                    detail="Debes proporcionar una tasa de conversión válida para transferencias entre monedas diferentes."
                )
            converted_amount = transfer_data.amount * transfer_data.exchange_rate
        else:
            converted_amount = transfer_data.amount

        total_deduction = transfer_data.amount + transfer_data.transaction_fee
        if from_account.balance < total_deduction:
            raise HTTPException(status_code=400, detail="Fondos insuficientes en la cuenta de origen para cubrir la transferencia y la comisión.")

        now = datetime.utcnow()
        transfer_category = get_or_create_transfer_category(session, user_id)

        # Transacción de egreso
        from_tx = Transaction(
            user_id=user_id,
            amount=transfer_data.amount,
            transaction_fee=transfer_data.transaction_fee,
            type=TransactionType.expense,
            description=transfer_data.description or "Transferencia de salida",
            from_account_id=transfer_data.from_account_id,
            to_account_id=transfer_data.to_account_id,
            saving_account_id=transfer_data.from_account_id,
            date=now,
            category_id=transfer_category.id,
            source_type="transfer",
        )

        # Transacción de ingreso
        to_tx = Transaction(
            user_id=user_id,
            amount=converted_amount,
            transaction_fee=0.0,
            type=TransactionType.income,
            description=transfer_data.description or "Transferencia recibida",
            from_account_id=transfer_data.from_account_id,
            to_account_id=transfer_data.to_account_id,
            saving_account_id=transfer_data.to_account_id,
            date=now,
            category_id=transfer_category.id,
            source_type="transfer",
        )

        # Actualizar balances
        from_account.balance -= total_deduction
        to_account.balance += converted_amount

        session.add_all([from_tx, to_tx, from_account, to_account])

        # Registrar transacción de comisión separada si se desea trazabilidad
        if transfer_data.transaction_fee > 0:
            fee_tx = Transaction(
                user_id=user_id,
                amount=transfer_data.transaction_fee,
                transaction_fee=0.0,
                type=TransactionType.expense,
                description="Comisión por transferencia",
                saving_account_id=transfer_data.from_account_id,
                category_id=transfer_category.id,
                date=now
            )
            session.add(fee_tx)

        session.commit()
        session.refresh(from_tx)
        session.refresh(to_tx)

        return [from_tx, to_tx]
    
@router.post("/register-yield/{account_id}", response_model=TransactionRead)
def register_yield(
    account_id: int,
    data: RegisterYieldCreate,
    user_id: UUID = Depends(get_current_user_with_subscription_check)
):
 
    with Session(engine) as session:
        if data.amount <= 0:
            raise HTTPException(status_code=400, detail="El monto debe ser positivo.")

        account = session.get(SavingAccount, account_id)
        if not account or account.user_id != user_id:
            raise HTTPException(status_code=404, detail="Cuenta no encontrada")
        if account.status != SavingAccountStatus.active:
            raise HTTPException(status_code=400, detail="La cuenta no está activa.")
        if account.type != SavingAccountType.investment:
            raise HTTPException(
                status_code=400,
                detail="Solo puedes registrar rendimientos en cuentas de tipo inversión."
            )

        account.balance += data.amount
        session.add(account)

        tx = Transaction(
            user_id=user_id,
            amount=data.amount,
            transaction_fee=0.0,
            description=data.description,
            type=TransactionType.income,
            saving_account_id=account_id,
            date=datetime.utcnow(),
            source_type="investment_yield",
        )
        session.add(tx)
        session.commit()
        session.refresh(tx)

        return tx


@router.get("/with-category", response_model=dict)
def list_transactions_with_category(
    user_id: UUID = Depends(get_current_user_with_subscription_check),
    start_date: Optional[datetime] = Query(None, alias="startDate"),
    end_date: Optional[datetime] = Query(None, alias="endDate"),
    category_id: Optional[int] = Query(None, alias="categoryId"),
    type: Optional[TransactionType] = Query(None),
    source: Optional[str] = Query(None),  # ✅ nuevo filtro
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    with Session(engine) as session:
        query = select(Transaction).where(Transaction.user_id == user_id)

        if start_date:
            query = query.where(Transaction.date >= start_date)
        if end_date:
            query = query.where(Transaction.date <= end_date)
        if category_id:
            query = query.where(Transaction.category_id == category_id)
        if type in ["income", "expense", "transfer"]:
            query = query.where(Transaction.type == type)

        # ✅ Filtro por fuente
        if source == "account":
            query = query.where(Transaction.debt_id == None)
        elif source == "credit_card":
            query = query.where(Transaction.debt_id != None)

        query = query.options(
            joinedload(Transaction.category),
            joinedload(Transaction.from_account),
            joinedload(Transaction.to_account),
            joinedload(Transaction.debt),
            joinedload(Transaction.saving_account)
        ).order_by(Transaction.date.desc())

        total = session.exec(select(func.count()).select_from(query.subquery())).one()

        transactions = session.exec(
            query.offset((page - 1) * page_size).limit(page_size)
        ).all()

        total_pages = max(1, (total + page_size - 1) // page_size)

        return {
            "items": [
                TransactionWithCategoryRead.model_validate(t, from_attributes=True).model_dump()
                for t in transactions
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
            "totalPages": total_pages
        }
    
@router.put("/{transaction_id}", response_model=TransactionRead)
def update_transaction(
    transaction_id: int,
    transaction_data: TransactionCreate,
    user_id: UUID = Depends(get_current_user_with_subscription_check)
):
    with Session(engine) as session:
        transaction = session.exec(
            select(Transaction).where(
                Transaction.id == transaction_id,
                Transaction.user_id == user_id
            )
        ).first()

        if not transaction:
            raise HTTPException(status_code=404, detail="Transacción no encontrada")
        
        if transaction.is_cancelled:
            raise HTTPException(status_code=400, detail="No se puede editar una transacción cancelada")

        # 🚩 Bloquear edición si es reversa
        if transaction.reversed_transaction_id:
            raise HTTPException(status_code=400, detail="No se puede editar una transacción de reversa")

        if transaction.source_type is not None:
            raise HTTPException(status_code=400, detail="No se puede editar una transacción generada automáticamente")
        # Validar categoría
        category = session.exec(
            select(Category).where(
                Category.id == transaction_data.category_id,
                Category.user_id == user_id
            )
        ).first()

        if not category:
            raise HTTPException(status_code=400, detail="Categoría inválida")

        # Validar nueva cuenta
        new_account = None
        if transaction_data.saving_account_id is not None:
            new_account = session.exec(
                select(SavingAccount).where(
                    SavingAccount.id == transaction_data.saving_account_id,
                    SavingAccount.user_id == user_id
                )
            ).first()
            if not new_account:
                raise HTTPException(status_code=400, detail="Cuenta de ahorro inválida")

        # Revertir balance de la cuenta anterior
        if transaction.saving_account_id is not None:
            previous_account = session.get(SavingAccount, transaction.saving_account_id)
            if previous_account:
                if transaction.type == TransactionType.income:
                    previous_account.balance -= transaction.amount
                elif transaction.type == TransactionType.expense:
                    previous_account.balance += transaction.amount
                session.add(previous_account)

        # Aplicar balance a la nueva cuenta
        if new_account is not None:
            if transaction_data.type == TransactionType.income:
                new_account.balance += transaction_data.amount
            elif transaction_data.type == TransactionType.expense:
                new_account.balance -= transaction_data.amount
            session.add(new_account)

        # Actualizar transacción
        transaction.amount = transaction_data.amount
        transaction.category_id = transaction_data.category_id
        transaction.description = transaction_data.description
        transaction.type = transaction_data.type
        # transaction.date = transaction_data.date
        transaction.saving_account_id = transaction_data.saving_account_id

        session.add(transaction)
        session.commit()
        session.refresh(transaction)
        return transaction


@router.delete("/{transaction_id}")
def delete_transaction(
    transaction_id: int,
    user_id: UUID = Depends(get_current_user_with_subscription_check)
):
    with Session(engine) as session:
        transaction = session.exec(
            select(Transaction).where(
                Transaction.id == transaction_id,
                Transaction.user_id == user_id
            )
        ).first()

        if not transaction:
            raise HTTPException(status_code=404, detail="Transacción no encontrada")

        # Ajuste de balances antes de eliminar
        if transaction.type in [TransactionType.income, TransactionType.expense]:
            if transaction.saving_account_id is not None:
                account = session.get(SavingAccount, transaction.saving_account_id)
                if account:
                    if transaction.type == TransactionType.income:
                        account.balance -= transaction.amount
                    elif transaction.type == TransactionType.expense:
                        account.balance += transaction.amount
                    session.add(account)

        # Si es transferencia, ajustar ambas cuentas
        if transaction.from_account_id and transaction.to_account_id:
            from_account = session.get(SavingAccount, transaction.from_account_id)
            to_account = session.get(SavingAccount, transaction.to_account_id)
            if from_account and to_account:
                # Se asume que las transferencias se crean como:
                # - salida: expense en cuenta origen
                # - entrada: income en cuenta destino
                if transaction.type == TransactionType.expense:
                    from_account.balance += transaction.amount  # Revertir egreso
                elif transaction.type == TransactionType.income:
                    to_account.balance -= transaction.amount   # Revertir ingreso
                session.add_all([from_account, to_account])

        # Eliminar transacción
        session.delete(transaction)
        session.commit()

        return {"message": "Transacción eliminada correctamente"}
    
@router.post("/{transaction_id}/reverse", response_model=TransactionRead)
def reverse_transaction(
    transaction_id: int,
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    with Session(engine) as session:
        tx = session.exec(
            select(Transaction).where(
                Transaction.id == transaction_id,
                Transaction.user_id == user_id
            )
        ).first()

        if not tx:
            raise HTTPException(status_code=404, detail="Transacción no encontrada.")

        if tx.is_cancelled:
            raise HTTPException(status_code=400, detail="Esta transacción ya está cancelada.")
        
        if tx.reversed_transaction_id:
            raise HTTPException(status_code=400, detail="Esta transacción es una reversa y no puede ser reversada nuevamente.")

        if tx.type not in [TransactionType.income, TransactionType.expense]:
            raise HTTPException(status_code=400, detail="Solo se pueden revertir ingresos o gastos.")

        # Generar transacción inversa
        inverse_type = TransactionType.expense if tx.type == TransactionType.income else TransactionType.income
        inverse_amount = tx.amount

        reversed_tx = Transaction(
            user_id=user_id,
            amount=inverse_amount,
            type=inverse_type,
            transaction_fee=0.0,
            description=f"Reversión de transacción #{tx.id}: {tx.description}",
            date=datetime.utcnow(),
            category_id=tx.category_id,
            saving_account_id=tx.saving_account_id,
            from_account_id=tx.from_account_id,
            to_account_id=tx.to_account_id,
            reversed_transaction_id=tx.id
        )

        # Ajustar balances
        if tx.saving_account_id:
            account = session.exec(
                select(SavingAccount).where(
                    SavingAccount.id == tx.saving_account_id,
                    SavingAccount.user_id == user_id
                )
            ).first()
            if account:
                if inverse_type == TransactionType.income:
                    account.balance += inverse_amount
                else:
                    if account.balance < inverse_amount:
                        raise HTTPException(status_code=400, detail="Fondos insuficientes para reversar.")
                    account.balance -= inverse_amount
                session.add(account)

        # Marcar como cancelada
        tx.is_cancelled = True
        session.add(tx)

        # Guardar reversa
        session.add(reversed_tx)
        session.commit()
        session.refresh(reversed_tx)

        return reversed_tx