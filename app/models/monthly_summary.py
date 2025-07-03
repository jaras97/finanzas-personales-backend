# app/models/monthly_summary.py

from sqlmodel import SQLModel, Field
from uuid import UUID
from typing import Optional
from datetime import date

class MonthlySummary(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id")
    month: int  # 1-12
    year: int
    total_income: float
    total_expense: float
    net_saving: float  # income - expenses
    suggestion: Optional[str] = None  # Texto con recomendación (ahorrar, abonar a deuda, invertir, etc.)