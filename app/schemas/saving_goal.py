from datetime import date
from typing import Optional

from pydantic import BaseModel


class SavingGoalCreate(BaseModel):
    saving_account_id: int
    name: str
    target_amount: float
    target_date: Optional[date] = None


class SavingGoalUpdate(BaseModel):
    name: Optional[str] = None
    target_amount: Optional[float] = None
    target_date: Optional[date] = None
    is_active: Optional[bool] = None


class SavingGoalRead(BaseModel):
    id: int
    saving_account_id: int
    account_name: str
    currency: str
    name: str
    target_amount: float
    target_date: Optional[date] = None
    is_active: bool
    current_balance: float
    progress_percent: float
    monthly_savings_needed: Optional[float] = None

    class Config:
        from_attributes = True
