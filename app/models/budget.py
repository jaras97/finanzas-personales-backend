from datetime import date, datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class Budget(SQLModel, table=True):
    """Meta de gasto mensual para una categoría, en una moneda específica.

    El monto está versionado por `effective_from` en vez de ser un solo valor
    "actual": editar el presupuesto hoy no debe reescribir cómo le fue al
    usuario en un mes que ya pasó. Resolver "cuál era el presupuesto de esta
    categoría para tal mes" es "la fila más reciente con
    effective_from <= ese mes" -- a diferencia de RecurringTransaction, un
    presupuesto no necesita generar filas por adelantado, porque es solo una
    meta, no un movimiento real que haya que materializar.

    Por categoría *y* moneda: una categoría puede tener gastos en más de una
    moneda (ej. "Mercado" pagado a veces desde una cuenta COP, a veces desde
    una cuenta USD), y fusionarlos en un solo número sin conversión sería
    incorrecto -- mismo criterio que ya usa el resto de la app (Resumen,
    flujo de caja) al reportar todo en silos por moneda.

    `amount = 0` se interpreta como "presupuesto pausado desde este mes", no
    como "meta de cero" -- evita un estado adicional (`is_active`) para algo
    que ya es expresable con el propio versionado.
    """

    __tablename__ = "budget"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "category_id", "currency", "effective_from",
            name="uq_budget_user_category_currency_month",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    category_id: int = Field(foreign_key="category.id", index=True)
    currency: str = Field(foreign_key="currency.code", max_length=3)
    amount: float
    effective_from: date = Field(index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
