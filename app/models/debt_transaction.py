# app/models/debt_transaction.py

from enum import Enum
from sqlmodel import SQLModel, Field
from uuid import UUID
from typing import Optional
from datetime import datetime

class DebtTransactionType(str, Enum):
    payment = "payment"
    interest_charge = "interest_charge"
    extra_charge = "extra_charge"

class DebtTransaction(SQLModel, table=True):
    __tablename__ = "debt_transaction"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id")
    debt_id: int = Field(foreign_key="debt.id")
    amount: float
    type: DebtTransactionType
    description: Optional[str] = None
    date: datetime = Field(default_factory=datetime.utcnow)

