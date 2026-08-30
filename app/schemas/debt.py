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
    # Solo aplican cuando kind=credit_card -- se ignoran en préstamos.
    credit_limit: Optional[float] = None
    statement_day: Optional[int] = Field(default=None, ge=1, le=28)
    payment_due_days: Optional[int] = Field(default=None, ge=1)
    minimum_payment_percent: Optional[float] = Field(default=None, ge=0, le=100)

class DebtRead(DebtCreate):
    id: int
    status: DebtStatus
    currency: str
    transactions_count: Optional[int] = 0

    class Config:
        orm_mode = True


class DebtStatementRead(BaseModel):
    next_statement_date: date
    payment_due_date: date
    current_period_charges: float
    minimum_payment_estimate: Optional[float] = None
    available_credit: Optional[float] = None

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