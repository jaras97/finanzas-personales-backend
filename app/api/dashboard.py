# app/api/dashboard.py

from fastapi import APIRouter, Depends
from sqlmodel import Session, select, func
from datetime import datetime
from app.database import engine
from app.core.security import get_current_user
from uuid import UUID

from app.models.transaction import Transaction
from app.models.enums import TransactionType
from app.models.saving_account import SavingAccount
from app.models.debt import Debt

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

@router.get("/resumen")
def financial_summary(user_id: UUID = Depends(get_current_user)):
    with Session(engine) as session:
        today = datetime.utcnow()
        month_start = today.replace(day=1)

        ingresos = session.exec(
            select(func.sum(Transaction.amount))
            .where(
                Transaction.user_id == user_id,
                Transaction.type == TransactionType.income,  # corregido
                Transaction.date >= month_start
            )
        ).one() or 0

        egresos = session.exec(
            select(func.sum(Transaction.amount))
            .where(
                Transaction.user_id == user_id,
                Transaction.type == TransactionType.expense,  # corregido
                Transaction.date >= month_start
            )
        ).one() or 0

        ahorro_mensual = ingresos - egresos

        total_ahorros = session.exec(
            select(func.sum(SavingAccount.balance)).where(SavingAccount.user_id == user_id)
        ).one() or 0

        total_deudas = session.exec(
            select(func.sum(Debt.total_amount)).where(Debt.user_id == user_id)
        ).one() or 0

        recomendacion = (
            "Considera mover tu ahorro mensual a una cuenta de ahorro o inversión."
            if ahorro_mensual > 0 else
            "Revisa tus gastos este mes para mejorar tu ahorro."
        )

        return {
            "ingresos_mes": ingresos,
            "egresos_mes": egresos,
            "ahorro_mes": ahorro_mensual,
            "total_ahorros": total_ahorros,
            "total_deudas": total_deudas,
            "recomendacion": recomendacion
        }