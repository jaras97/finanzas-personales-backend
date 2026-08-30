from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class BudgetCreate(BaseModel):
    category_id: int
    currency: str
    amount: float = Field(..., ge=0)
    # Si se omite, aplica desde el mes en curso. No puede ser un mes que ya
    # pasó -- el versionado existe justo para no reescribir el pasado.
    effective_from: Optional[date] = None


class BudgetProgress(BaseModel):
    """Presupuesto vigente para un mes dado + cuánto se lleva gastado."""

    id: int
    category_id: int
    category_name: str
    currency: str
    amount: float
    effective_from: date
    spent: float
    # spent / amount * 100 -- puede superar 100 si ya se pasó del presupuesto.
    percentage: float
    created_at: datetime

    class Config:
        from_attributes = True
