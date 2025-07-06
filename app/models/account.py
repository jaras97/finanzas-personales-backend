from sqlmodel import SQLModel, Field
from uuid import UUID, uuid4
from typing import Optional

class Account(SQLModel, table=True):
    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id")
    name: str
    type: str  # savings, checking, cash, etc.
    balance: float