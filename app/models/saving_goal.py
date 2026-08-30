from datetime import date, datetime
from typing import Optional
from uuid import UUID

from sqlmodel import Field, SQLModel


class SavingGoal(SQLModel, table=True):
    """Meta de ahorro atada 1:1 a una SavingAccount completa -- "esta cuenta
    ES mi fondo para el viaje" (ver docs/PENDIENTES.md, Fase 8 del roadmap).
    Nada de "sobres" compartiendo el saldo de una cuenta: si alguien quiere
    varias metas, crea varias cuentas. El progreso es simplemente
    `saving_account.balance / target_amount` en el momento de consultar, sin
    trackear aportes/retiros por separado.

    A lo sumo una meta ACTIVA por cuenta (ver índice único parcial en la
    migración) -- una cuenta puede tener metas viejas inactivas (abandonadas
    o reemplazadas) sin que eso bloquee crear una nueva.
    """

    __tablename__ = "saving_goal"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    saving_account_id: int = Field(foreign_key="saving_account.id", index=True)
    name: str
    target_amount: float
    target_date: Optional[date] = None
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
