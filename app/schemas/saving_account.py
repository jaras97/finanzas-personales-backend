# app/schemas/saving_account.py

from datetime import datetime
from pydantic import BaseModel
from uuid import UUID
from typing import Optional
from app.models.saving_account import SavingAccountStatus, SavingAccountType, Currency
from pydantic import Field
from typing import Annotated

class SavingAccountCreate(BaseModel):
    name: str
    type: SavingAccountType
    balance: float
    currency: Optional[Currency] = Currency.COP

class SavingAccountRead(SavingAccountCreate):
    id: int
    status: SavingAccountStatus
    closed_at: Optional[datetime] = None

class SavingAccountWithdraw(BaseModel):
    amount: float = Field(..., gt=0, description="Monto a retirar")

class SavingAccountDeposit(BaseModel):
    amount: Annotated[float, Field(gt=0, description="Monto a depositar")]
    description: Optional[str] = None

class SavingAccountUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None