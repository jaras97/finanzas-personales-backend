from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.enums import TransactionType
from app.models.recurring_transaction import RecurrenceFrequency


class RecurringTransactionCreate(BaseModel):
    description: str = Field(..., min_length=1)
    amount: float = Field(..., gt=0)
    type: TransactionType
    category_id: int
    saving_account_id: int
    frequency: RecurrenceFrequency
    # Fecha del primer movimiento. Puede ser pasada: al correr la generación
    # se crearán todas las ocurrencias vencidas hasta hoy.
    next_run: date
    end_date: Optional[date] = None


class RecurringTransactionUpdate(BaseModel):
    description: Optional[str] = Field(None, min_length=1)
    amount: Optional[float] = Field(None, gt=0)
    category_id: Optional[int] = None
    saving_account_id: Optional[int] = None
    frequency: Optional[RecurrenceFrequency] = None
    next_run: Optional[date] = None
    end_date: Optional[date] = None
    is_active: Optional[bool] = None


class RecurringTransactionRead(BaseModel):
    id: int
    description: str
    amount: float
    type: TransactionType
    category_id: int
    saving_account_id: int
    frequency: RecurrenceFrequency
    next_run: date
    end_date: Optional[date] = None
    is_active: bool
    created_at: datetime
    last_run_at: Optional[datetime] = None
    # Resueltos para que la UI no tenga que cruzar endpoints por fila
    category_name: Optional[str] = None
    account_name: Optional[str] = None
    account_currency: Optional[str] = None

    class Config:
        from_attributes = True


class GeneratedItem(BaseModel):
    recurring_id: int
    description: str
    transaction_ids: List[int]
    count: int


class SkippedItem(BaseModel):
    recurring_id: int
    description: str
    reason: str


class RunResult(BaseModel):
    """Resultado de materializar las recurrencias vencidas. Se reporta lo
    omitido además de lo generado: un alquiler que no se pudo cobrar por
    saldo insuficiente es justo lo que el usuario necesita saber."""

    generated: List[GeneratedItem]
    skipped: List[SkippedItem]
    total_created: int
