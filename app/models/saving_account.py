# app/models/saving_account.py

from sqlmodel import SQLModel, Field
from uuid import UUID
from typing import Optional
from enum import Enum
from datetime import datetime

class SavingAccountStatus(str, Enum):
    active = "active"
    closed = "closed"

class SavingAccountType(str, Enum):
    cash = "cash"
    bank = "bank"
    investment = "investment"

class Currency(str, Enum):
    COP = "COP"
    USD = "USD"
    EUR = "EUR"

class SavingAccount(SQLModel, table=True):
    __tablename__ = "saving_account"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id")
    name: str
    type: SavingAccountType
    balance: float = 0.0
    currency: Currency = Field(default=Currency.COP)

    status: SavingAccountStatus = Field(default=SavingAccountStatus.active)
    closed_at: Optional[datetime] = None