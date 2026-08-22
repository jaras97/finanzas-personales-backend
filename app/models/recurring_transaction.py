from datetime import date, datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from sqlmodel import Field, SQLModel

from app.models.enums import TransactionType


class RecurrenceFrequency(str, Enum):
    weekly = "weekly"
    biweekly = "biweekly"
    monthly = "monthly"
    yearly = "yearly"


class RecurringTransaction(SQLModel, table=True):
    """Plantilla de un movimiento que se repite (nómina, arriendo,
    suscripciones). No es un movimiento en sí: al vencer genera filas reales
    en `transaction` mediante POST /recurring-transactions/run.

    `next_run` es la fecha del próximo movimiento pendiente de generar y es
    lo que hace idempotente la generación: solo se avanza cuando la fila
    correspondiente ya se creó, dentro de la misma transacción de base de
    datos.
    """

    __tablename__ = "recurring_transaction"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)

    description: str
    amount: float
    type: TransactionType
    category_id: int = Field(foreign_key="category.id")
    saving_account_id: int = Field(foreign_key="saving_account.id")

    # Texto plano, no un enum de Postgres: los enums de PG en este proyecto ya
    # han causado drift entre entornos y migraciones dolorosas (ver la de
    # monedas). La validación de valores vive en los schemas Pydantic
    # (RecurrenceFrequency), que es donde entra la data del usuario.
    frequency: str = Field(max_length=20)
    next_run: date = Field(index=True)
    # Opcional: si se define, no se generan movimientos después de esta fecha.
    end_date: Optional[date] = None

    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_run_at: Optional[datetime] = None
