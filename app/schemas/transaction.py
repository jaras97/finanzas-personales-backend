from uuid import UUID
from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime
from app.models.enums import TransactionType
from app.schemas.category import CategoryRead
from app.schemas.saving_account import SavingAccountRead
from app.schemas.debt import DebtRead  # 🚩 asegúrate de tener este import

class TransactionCreate(BaseModel):
    amount: float
    category_id: Optional[int] = None
    description: Optional[str] = None
    type: TransactionType
    saving_account_id: Optional[int] = None
    transaction_fee: float = 0.0
    date: Optional[datetime] = None

class TransactionRead(TransactionCreate):
    id: int
    date: datetime
    transaction_fee: Optional[float] = None
    is_cancelled: bool
    reversed_transaction_id: Optional[int] = None
    debt_id: Optional[int] = None
    source_type: Optional[str] = None
    transfer_group_id: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)

class TransactionWithCategoryRead(TransactionRead):
    category: Optional[CategoryRead] = None
    saving_account: Optional[SavingAccountRead] = None
    from_account: Optional[SavingAccountRead] = None
    to_account: Optional[SavingAccountRead] = None
    debt: Optional[DebtRead] = None  # 🚩 reemplaza debt_name por objeto completo

    model_config = ConfigDict(from_attributes=True)

class TransferCreate(BaseModel):
    amount: float
    description: Optional[str] = None
    from_account_id: int
    to_account_id: int
    transaction_fee: float = 0.0
    exchange_rate: Optional[float] = None

class RegisterYieldCreate(BaseModel):
    amount: float
    description: Optional[str] = "Rendimiento de inversión"