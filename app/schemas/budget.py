from datetime import date, datetime
from typing import List, Optional

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
    # Jerarquía, para que la interfaz agrupe sin cruzar con /categories.
    parent_id: Optional[int] = None
    parent_name: Optional[str] = None

    class Config:
        from_attributes = True


class BudgetGroup(BaseModel):
    """Total de un GRUPO: la suma de los presupuestos de sus hojas.

    Es derivado, no una fila de `budget`. Esa es toda la diferencia con el
    modelo anterior: cuando el grupo podía tener presupuesto propio *además*
    del de sus hojas, no había forma de decir si los 500k del padre incluían a
    las hijas o se sumaban, y los mismos pesos contaban dos veces.

    Por eso la interfaz lo muestra con candado y sin campo editable.
    """

    category_id: int
    category_name: str
    currency: str
    amount: float
    spent: float
    percentage: float
    # Cuántas hojas suyas tienen presupuesto; sirve para plegar el grupo de
    # una sola hoja en una línea.
    leaf_count: int


class BudgetsResponse(BaseModel):
    groups: List[BudgetGroup]
    items: List[BudgetProgress]
