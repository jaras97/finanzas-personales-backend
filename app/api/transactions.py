from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlmodel import Session, select
from app.database import engine
from app.models.attachment import Attachment
from app.models.category import Category, CategoryType
from app.models.debt import Debt
from app.models.debt_transaction import DebtTransaction, DebtTransactionType
from app.models.enums import TransactionType
from app.models.saving_account import SavingAccount, SavingAccountStatus, SavingAccountType
from app.models.transaction import Transaction
from app.schemas.transaction import RegisterYieldCreate, ReverseRequest, TransactionCreate, TransactionDescriptionUpdate, TransactionRead, TransactionUpdateLimited, TransferCreate
from app.core.security import get_current_user_with_subscription_check
import datetime as dt
from typing import Optional, List
from fastapi import Query
from app.schemas.transaction import TransactionWithCategoryRead
from sqlalchemy.orm import joinedload
from sqlalchemy import func
from app.utils.category_helpers import get_or_create_transfer_category

router = APIRouter(prefix="/transactions", tags=["transactions"])

@router.post("", response_model=TransactionRead)
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
            data["date"] = dt.datetime.utcnow()

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

        now = transfer_data.date or dt.datetime.utcnow()
        transfer_category = get_or_create_transfer_category(session, user_id)

        transfer_group_id = uuid4()

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
            transfer_group_id=transfer_group_id,
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
            transfer_group_id=transfer_group_id,
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
            date=dt.datetime.utcnow(),
            source_type="investment_yield",
        )
        session.add(tx)
        session.commit()
        session.refresh(tx)

        return tx


@router.get("/with-category", response_model=dict)
def list_transactions_with_category(
    user_id: UUID = Depends(get_current_user_with_subscription_check),
    start_date: Optional[dt.datetime] = Query(None, alias="startDate"),
    end_date: Optional[dt.datetime] = Query(None, alias="endDate"),
    category_id: Optional[int] = Query(None, alias="categoryId"),
    type: Optional[TransactionType] = Query(None),
    source: Optional[str] = Query(None),  # ✅ nuevo filtro
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    include_reversals: bool = Query(False)
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

        if not include_reversals:
            query = query.where(Transaction.reversed_transaction_id == None)

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

        # Conteo de comprobantes en UNA sola consulta agrupada para toda la
        # página, en vez de una por fila (N+1).
        page_ids = [t.id for t in transactions]
        counts: dict[int, int] = {}
        if page_ids:
            rows = session.exec(
                select(Attachment.transaction_id, func.count())
                .where(Attachment.transaction_id.in_(page_ids))
                .group_by(Attachment.transaction_id)
            ).all()
            counts = {tx_id: count for tx_id, count in rows}

        items = []
        for t in transactions:
            item = TransactionWithCategoryRead.model_validate(t, from_attributes=True).model_dump()
            item["attachments_count"] = counts.get(t.id, 0)
            items.append(item)

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "totalPages": total_pages
        }
    


@router.patch("/{transaction_id}", response_model=TransactionRead)
def update_transaction_limited(
    transaction_id: int,
    data: TransactionUpdateLimited,
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    if data.description is None and data.category_id is None and data.date is None:
        raise HTTPException(status_code=400, detail="Nada para actualizar.")

    with Session(engine) as session:
        tx = session.exec(
            select(Transaction).where(
                Transaction.id == transaction_id,
                Transaction.user_id == user_id
            )
        ).first()

        if not tx:
            raise HTTPException(status_code=404, detail="Transacción no encontrada")

        # Reglas de elegibilidad (como ya las tienes)
        if tx.is_cancelled:
            raise HTTPException(status_code=400, detail="No se puede editar una transacción cancelada")
        if tx.reversed_transaction_id:
            raise HTTPException(status_code=400, detail="No se puede editar una transacción de reversa")
        if tx.source_type is not None:
            raise HTTPException(status_code=400, detail="No se puede editar una transacción generada automáticamente")
        if tx.type not in [TransactionType.income, TransactionType.expense]:
            raise HTTPException(status_code=400, detail="Solo puedes editar ingresos o egresos")

        # Validar categoría (si viene)
        if data.category_id is not None:
            category = session.exec(
                select(Category).where(
                    Category.id == data.category_id,
                    Category.user_id == user_id,
                    Category.is_active == True
                )
            ).first()
            if not category:
                raise HTTPException(status_code=400, detail="Categoría inválida")

            if not (
                (category.type == CategoryType.both) or
                (category.type == CategoryType.income and tx.type == TransactionType.income) or
                (category.type == CategoryType.expense and tx.type == TransactionType.expense)
            ):
                raise HTTPException(status_code=400, detail="La categoría no coincide con el tipo de la transacción")

            tx.category_id = data.category_id

        # Descripción (si viene)
        if data.description is not None:
            tx.description = data.description.strip()

        # Fecha (si viene)
        if data.date is not None:
            new_dt = data.date
            # Si viene con zona horaria (p.ej. ISO con Z), convertir a UTC y strip tz
            if new_dt.tzinfo is not None:
                new_dt = new_dt.astimezone(dt.timezone.utc).replace(tzinfo=None)
            # Si viene naive la guardamos tal cual (asumiendo UTC naive en tu DB)
            tx.date = new_dt

        session.add(tx)
        session.commit()
        session.refresh(tx)
        return TransactionRead.model_validate(tx, from_attributes=True)



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

        # --- Transferencias: se borra el GRUPO completo -------------------
        # Las 2 patas llevan `saving_account_id` (su propia cuenta) Y
        # `from_account_id`/`to_account_id`. Tratarlas como movimiento simple
        # revertía la cuenta de esa pata dos veces y dejaba la otra pata viva
        # con su efecto de saldo aplicado -- el patrimonio del usuario crecía
        # de la nada. Se revierte cada cuenta exactamente una vez y se borran
        # ambas filas.
        #
        # La comisión de la transferencia NO se toca: es una fila aparte, sin
        # `transfer_group_id` (dárselo rompería `mergeTransferPairs` en el
        # frontend, que solo fusiona cuando el grupo tiene exactamente 2
        # filas). Además es correcto: la plata se reubicó y eso se revierte,
        # pero el banco sí cobró la comisión y ese gasto ocurrió de verdad.
        if transaction.source_type == "transfer" and transaction.transfer_group_id:
            legs = session.exec(
                select(Transaction).where(
                    Transaction.user_id == user_id,
                    Transaction.transfer_group_id == transaction.transfer_group_id,
                    Transaction.source_type == "transfer",
                )
            ).all()

            for leg in legs:
                if leg.saving_account_id is None:
                    continue
                account = session.get(SavingAccount, leg.saving_account_id)
                if not account:
                    continue
                if leg.type == TransactionType.income:
                    account.balance -= leg.amount
                else:
                    account.balance += leg.amount
                session.add(account)

            for leg in legs:
                session.delete(leg)

            session.commit()
            return {"message": "Transferencia eliminada correctamente"}

        # --- Movimiento simple (ingreso/egreso de una sola cuenta) --------
        if transaction.type in [TransactionType.income, TransactionType.expense]:
            if transaction.saving_account_id is not None:
                account = session.get(SavingAccount, transaction.saving_account_id)
                if account:
                    if transaction.type == TransactionType.income:
                        account.balance -= transaction.amount
                    elif transaction.type == TransactionType.expense:
                        account.balance += transaction.amount
                    session.add(account)

        session.delete(transaction)
        session.commit()

        return {"message": "Transacción eliminada correctamente"}
    



def _build_reversal_description(original: Transaction, note: Optional[str]) -> str:
    base = f"Reversión de transacción #{original.id}: {original.description or ''}".strip()
    return f"{base} | Nota: {note}" if note else base

@router.post("/{transaction_id}/reverse", response_model=TransactionRead)
def reverse_transaction(
    transaction_id: int,
    data: ReverseRequest,  # {"note": "..."}
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

        transactions_to_reverse = [tx]

        # Si es transferencia emparejada, agregamos la complementaria
        if tx.transfer_group_id:
            complementary_tx = session.exec(
                select(Transaction).where(
                    Transaction.transfer_group_id == tx.transfer_group_id,
                    Transaction.id != tx.id,
                    Transaction.user_id == user_id,
                    Transaction.is_cancelled == False
                )
            ).first()
            if complementary_tx:
                if complementary_tx.is_cancelled:
                    raise HTTPException(status_code=400, detail="La transacción complementaria de la transferencia ya está cancelada.")
                transactions_to_reverse.append(complementary_tx)

        reversed_transactions = []

        for t in transactions_to_reverse:
            inverse_type = TransactionType.expense if t.type == TransactionType.income else TransactionType.income
            inverse_amount = t.amount

            reversed_tx = Transaction(
                user_id=user_id,
                amount=inverse_amount,
                type=inverse_type,
                transaction_fee=0.0,
                description=_build_reversal_description(t, data.note),
                date=dt.datetime.utcnow(),
                category_id=t.category_id,
                saving_account_id=t.saving_account_id,
                from_account_id=t.from_account_id,
                to_account_id=t.to_account_id,
                transfer_group_id=t.transfer_group_id,
                reversed_transaction_id=t.id,
                reversal_note=data.note,
                # 👇 NUEVO: si venía de TC, conservamos debt_id y marcamos el source
                debt_id=t.debt_id if t.source_type == "credit_card_purchase" else t.debt_id,
                source_type="credit_card_purchase_reversal" if t.source_type == "credit_card_purchase" else None,
            )

            # Ajustar balances de cuenta (solo si existía saving_account_id)
            if t.saving_account_id:
                account = session.exec(
                    select(SavingAccount).where(
                        SavingAccount.id == t.saving_account_id,
                        SavingAccount.user_id == user_id
                    )
                ).first()
                if account:
                    if inverse_type == TransactionType.income:
                        account.balance += inverse_amount
                    else:
                        if account.balance < inverse_amount:
                            raise HTTPException(status_code=400, detail=f"Fondos insuficientes en la cuenta {account.name} para reversar.")
                        account.balance -= inverse_amount
                    session.add(account)

            # 👇 NUEVO: si era compra con TC, ajustamos la deuda
            if t.debt_id and t.source_type == "credit_card_purchase":
                debt = session.exec(
                    select(Debt).where(Debt.id == t.debt_id, Debt.user_id == user_id)
                ).first()
                if not debt:
                    raise HTTPException(status_code=400, detail="Deuda asociada no encontrada.")

                # La compra subió la deuda; su reversa la baja
                debt.total_amount = (debt.total_amount or 0) - inverse_amount
                session.add(debt)

                # (Opcional) Registrar un movimiento en el ledger de la deuda:
                # try:
                #     from app.models.debt_transaction import DebtTransaction, DebtTransactionType
                session.add(DebtTransaction(
                    user_id=user_id,
                    debt_id=debt.id,
                    amount=inverse_amount,  # positivo, pero tipo "charge_reversal"
                    type=DebtTransactionType.charge_reversal if hasattr(DebtTransactionType, "charge_reversal") else DebtTransactionType.extra_charge,
                    description=_build_reversal_description(t, data.note),
                    date=reversed_tx.date,
                ))
                # except Exception:
                #     # Si no existe el enum/tipo, puedes omitir el asiento o guardar un extra_charge negativo:
                #     pass

            # Marcar original como cancelada y guardar nota
            t.is_cancelled = True
            t.reversal_note = data.note
            session.add(t)

            # Guardar reversa
            session.add(reversed_tx)
            session.commit()
            session.refresh(reversed_tx)

            reversed_transactions.append(reversed_tx)

        return TransactionRead.model_validate(reversed_transactions[0], from_attributes=True)
    



