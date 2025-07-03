# app/schemas/debt_transaction.py

from uuid import UUID
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class DebtTransactionRead(BaseModel):
    id: int
    debt_id: int
    user_id: UUID
    amount: float
    type: str
    description: Optional[str] = None
    date: datetime

    class Config:
        orm_mode = True