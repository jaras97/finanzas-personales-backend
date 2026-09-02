from typing import Optional
from datetime import datetime

from sqlmodel import SQLModel, Field


class SubscriptionPlan(SQLModel, table=True):
    """Catálogo de planes (paramétrica editable por el admin).

    Existe para dejar de escribir "meses" a mano en cada activación: el admin
    define una vez "Mensual / 1 mes / 30.000 COP" y luego solo elige el plan.
    El precio se copia al período y al pago en el momento de usarlo, así que
    cambiar el precio del plan no reescribe la historia ya registrada.
    """

    __tablename__ = "subscription_plan"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    duration_months: int
    price: float = 0
    currency: str = Field(default="COP", foreign_key="currency.code", max_length=3)
    # Baja lógica: un plan retirado no debe desaparecer, porque los períodos y
    # pagos históricos lo referencian.
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
