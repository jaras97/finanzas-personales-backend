from pydantic import BaseModel
from typing import Optional
from datetime import date

class MonthlySummaryCreate(BaseModel):
    year: int
    month: int
    total_income: float
    total_expense: float
    net_savings: float

class MonthlySummaryRead(MonthlySummaryCreate):
    id: int

    class Config:
        from_attributes = True  # Para compatibilidad con SQLModel y Pydantic v2