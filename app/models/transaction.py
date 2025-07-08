from uuid import UUID
from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.debt import Debt
from app.models.enums import TransactionType
from typing import Optional, TYPE_CHECKING
from app.models.category import Category  # importa la categoría
from sqlmodel import Relationship

from app.models.saving_account import SavingAccount

class Transaction(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id")
    amount: float
    type: TransactionType
    transaction_fee: float = 0.0
    date: datetime = Field(default_factory=datetime.utcnow)
    description: Optional[str] = None
    is_cancelled: bool = Field(default=False)
    reversed_transaction_id: Optional[int] = Field(default=None, foreign_key="transaction.id")
    debt_id: Optional[int] = Field(default=None, foreign_key="debt.id")
    debt: Optional["Debt"] = Relationship(back_populates="transactions")
    source_type: Optional[str] = Field(default=None, nullable=True)
    transfer_group_id: Optional[UUID] = Field(default=None, index=True)
    
    

    # Categoría solo obligatoria en income y expense
    category_id: Optional[int] = Field(default=None, foreign_key="category.id")
    category: Optional["Category"] = Relationship(back_populates="transactions")

    # Cuenta donde entra o sale el dinero (en ingresos y gastos)
    saving_account_id: Optional[int] = Field(default=None, foreign_key="saving_account.id")
    saving_account: Optional[SavingAccount] = Relationship(
    sa_relationship_kwargs={"foreign_keys": "[Transaction.saving_account_id]"}
)

    # NUEVO: cuenta de origen (solo en transferencias)
    from_account_id: Optional[int] = Field(default=None, foreign_key="saving_account.id")

    # NUEVO: cuenta de destino (solo en transferencias)
    to_account_id: Optional[int] = Field(default=None, foreign_key="saving_account.id")

    from_account: Optional[SavingAccount] = Relationship(sa_relationship_kwargs={
        "foreign_keys": "[Transaction.from_account_id]"
    })
    to_account: Optional[SavingAccount] = Relationship(sa_relationship_kwargs={
        "foreign_keys": "[Transaction.to_account_id]"
    })