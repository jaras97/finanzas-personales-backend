from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr


class AdminUserRead(BaseModel):
    """Un usuario visto desde el panel de administración, con el estado de su
    suscripción resuelto (para no obligar al frontend a cruzar dos endpoints)."""

    id: UUID
    email: EmailStr
    role: str
    created_at: datetime
    subscription_status: Literal["none", "active", "expired", "inactive"]
    subscription_start: Optional[datetime] = None
    subscription_end: Optional[datetime] = None

    class Config:
        from_attributes = True


class AdminUsersPage(BaseModel):
    items: List[AdminUserRead]
    total: int
    page: int
    page_size: int
    total_pages: int


class RoleUpdate(BaseModel):
    role: Literal["user", "admin"]
