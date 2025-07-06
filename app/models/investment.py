from sqlmodel import SQLModel, Field
from uuid import UUID, uuid4
from typing import Optional

class Investment(SQLModel, table=True):
    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id")
    name: str
    type: str  # stock, fund, crypto
    invested_amount: float
    current_value: float