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
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    type: CategoryType = Field(default=CategoryType.expense)  # Nuevo campo
    user_id: UUID = Field(foreign_key="user.id")
    is_active: bool = Field(default=True)
    transactions: List["Transaction"] = Relationship(back_populates="category")