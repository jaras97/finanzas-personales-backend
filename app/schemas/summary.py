# app/schemas/summary.py

from pydantic import BaseModel
from typing import List, Optional
from datetime import date

class CategorySummary(BaseModel):
    category_id: int
    category_name: str
    total: float
    percentage: float

class DailySummary(BaseModel):
    date: date
    total_income: float
    total_expense: float

class SummaryResponse(BaseModel):
    total_income: float
    total_expense: float
    balance: float
    expense_by_category: List[CategorySummary]
    income_by_category: List[CategorySummary]
    daily_evolution: List[DailySummary]
    top_expense_category: Optional[CategorySummary] = None
    top_income_category: Optional[CategorySummary] = None
    top_expense_day: Optional[DailySummary] = None
    top_income_day: Optional[DailySummary] = None
    overspending_alert: bool