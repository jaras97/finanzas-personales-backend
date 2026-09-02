from typing import Optional
from uuid import UUID
from datetime import datetime

from sqlmodel import SQLModel, Field


class Payment(SQLModel, table=True):
    """Pago recibido de una persona por su suscripción.

    Es contabilidad del negocio (tuya), no de las finanzas personales del
    usuario: no aparece en Resumen ni toca ninguna cuenta ni saldo de la app.
    Va deliberadamente en su propia tabla para que nunca se mezcle con
    `transaction`, que es del usuario final.
    """

    __tablename__ = "payment"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    # Se enlaza al período que este pago cubrió, cuando se registró junto con él.
    period_id: Optional[int] = Field(default=None, foreign_key="subscription_period.id")

    amount: float
    currency: str = Field(default="COP", foreign_key="currency.code", max_length=3)
    # "cash" | "transfer" | "card" | "other" -- texto libre a propósito: son
    # los medios de pago de un negocio pequeño y no vale un catálogo aparte.
    method: str = Field(default="transfer")
    reference: Optional[str] = None
    note: Optional[str] = None

    paid_at: datetime
    created_by: Optional[UUID] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
