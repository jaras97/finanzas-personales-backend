# app/schemas/summary.py

from pydantic import BaseModel
from typing import List, Optional
from datetime import date

class CategorySummary(BaseModel):
    """Una línea del desglose por categoría.

    Las líneas de primer nivel son GRUPOS y su `total` es la suma de sus
    hojas — nunca hay un «sin desglosar», porque un grupo no recibe
    movimientos (invariante I1). El detalle viaja en `children` para que el
    drill-down del Resumen sea instantáneo, sin una petición por clic.
    """

    category_id: int
    category_name: str
    total: float
    percentage: float
    # Identidad visual, para no tener que cruzar con /categories al pintar.
    color: Optional[str] = None
    icon: Optional[str] = None
    # Comparación con el período anterior. `delta_percentage` es None cuando
    # no hay base (antes no se gastó nada ahí): un "+∞%" no informa.
    previous_total: float = 0.0
    delta_percentage: Optional[float] = None
    children: List["CategorySummary"] = []

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