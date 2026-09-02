from typing import Optional
from uuid import UUID
from datetime import datetime

from sqlmodel import SQLModel, Field


class SubscriptionPeriod(SQLModel, table=True):
    """Un tramo de servicio efectivamente otorgado a una persona.

    Responde "¿desde cuándo es cliente y qué meses estuvo cubierto?", que la
    tabla `subscription` no puede responder: esa guarda solo el estado actual y
    se sobrescribe en cada renovación, perdiendo el pasado.

    Es un registro histórico, NO la fuente de verdad del acceso: quien decide
    si alguien entra sigue siendo `subscription`. Se mantiene así a propósito
    para no tocar la ruta de autorización de producción.
    """

    __tablename__ = "subscription_period"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    plan_id: Optional[int] = Field(default=None, foreign_key="subscription_plan.id")

    start_date: datetime
    end_date: datetime

    # Precio copiado del plan al momento de otorgarlo (ver nota en el plan).
    price: float = 0
    currency: str = Field(default="COP", foreign_key="currency.code", max_length=3)

    # "activate" | "renew". Distingue reactivar de extender sin tener que
    # deducirlo comparando fechas.
    origin: str = Field(default="activate")
    note: Optional[str] = None

    created_by: Optional[UUID] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
