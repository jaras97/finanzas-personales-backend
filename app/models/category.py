from sqlalchemy import UniqueConstraint
from sqlmodel import  SQLModel, Field
from typing import Optional
from uuid import UUID
from typing import List, TYPE_CHECKING
from enum import Enum
from sqlmodel import Relationship
if TYPE_CHECKING:
    from app.models.transaction import Transaction

class CategoryType(str, Enum):
    income = "income"
    expense = "expense"
    both = "both"

class Category(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("user_id", "system_key", name="uq_category_user_system_key"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    type: CategoryType = Field(default=CategoryType.expense)  # Nuevo campo
    user_id: UUID = Field(foreign_key="user.id")
    is_active: bool = Field(default=True)

    is_system: bool = Field(default=False, index=True)
    system_key: Optional[str] = Field(default=None, index=True)

    transactions: List["Transaction"] = Relationship(back_populates="category")