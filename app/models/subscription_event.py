from typing import Optional
from uuid import UUID
from datetime import datetime

from sqlmodel import SQLModel, Field


class SubscriptionEvent(SQLModel, table=True):
    """Bitácora inmutable: quién hizo qué y cuándo.

    Complementa a `subscription_period` en vez de duplicarlo. Un período dice
    "estuvo cubierto de A a B"; un evento dice "el admin X lo renovó el día D,
    y el vencimiento pasó de A a B". Registra además acciones que NO crean
    período (eliminar una suscripción, cambiar un rol), que son justamente las
    que uno quiere poder auditar después.

    Nada la actualiza ni la borra: solo se inserta.
    """

    __tablename__ = "subscription_event"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)

    # "activate" | "renew" | "delete" | "role_change" | "payment"
    action: str = Field(index=True)

    # Vencimiento antes y después, para poder reconstruir la línea de tiempo
    # aunque el período se haya creado o no.
    end_date_before: Optional[datetime] = None
    end_date_after: Optional[datetime] = None

    months: Optional[int] = None
    plan_id: Optional[int] = Field(default=None, foreign_key="subscription_plan.id")
    detail: Optional[str] = None

    performed_by: Optional[UUID] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
