# app/schemas/debt.py

from pydantic import BaseModel, Field
from uuid import UUID
from typing import Optional
from datetime import date, datetime

from app.models.debt import DebtKind, DebtStatus


class DebtCreate(BaseModel):
    name: str
    total_amount: float
    interest_rate: float
    due_date: Optional[date] = None
    currency: str = Field(default="COP", max_length=3)
    kind: DebtKind = DebtKind.loan

class DebtRead(DebtCreate):
    id: int
    status: DebtStatus
    currency: str
    transactions_count: Optional[int] = 0

    class Config:
        orm_mode = True 

class DebtPayment(BaseModel):
    amount: float
    saving_account_id: int  # desde qué cuenta se paga
    description: Optional[str] = None
    date: Optional[datetime] = None


class AddChargeRequest(BaseModel):
    amount: float
    description: Optional[str] = "Interés o cargo adicional"
    date: Optional[datetime] = None

class CreditCardPurchaseCreate(BaseModel):
    amount: float
    category_id: int
    description: Optional[str] = None
    date: Optional[datetime] = None
    merchant: Optional[str] = None         # opcional, útil a futuro
    installments: Optional[int] = None