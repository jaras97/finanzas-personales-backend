# app/models/debt.py

from enum import Enum
from sqlmodel import Relationship, SQLModel, Field
from uuid import UUID
from typing import List, Optional
from datetime import date

from app.models.saving_account import Currency
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.transaction import Transaction

class DebtStatus(str, Enum):
    active = "active"
    closed = "closed"

class DebtKind(str, Enum):
    loan = "loan"
    credit_card = "credit_card"

class Debt(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id")
    name: str  # Ej: "Préstamo Bancolombia", "Tarjeta Visa"
    total_amount: float  # Monto total adeudado
    interest_rate: float  # En porcentaje anual
    due_date: Optional[date] = None  # Fecha de vencimiento
    status: DebtStatus = Field(default=DebtStatus.active)  # Estado de la deuda
    currency: Currency = Field(default=Currency.COP)
    transactions: List["Transaction"] = Relationship(back_populates="debt")
    kind: DebtKind = Field(default=DebtKind.loan)