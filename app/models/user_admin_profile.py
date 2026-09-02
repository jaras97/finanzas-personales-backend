from typing import Optional
from uuid import UUID
from datetime import datetime

from sqlmodel import SQLModel, Field


class UserAdminProfile(SQLModel, table=True):
    """Datos que el ADMIN lleva sobre una persona; el usuario no los ve ni los
    edita. Van en su propia tabla en vez de en `user` para no engordar la tabla
    que se lee en cada request autenticado.
    """

    __tablename__ = "user_admin_profile"

    user_id: UUID = Field(foreign_key="user.id", primary_key=True)
    full_name: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    updated_by: Optional[UUID] = Field(default=None, foreign_key="user.id")
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class UserTag(SQLModel, table=True):
    """Catálogo de etiquetas (paramétrica): prueba, cortesía, moroso..."""

    __tablename__ = "user_tag"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    # Clase de color de la UI, para que el admin distinga de un vistazo.
    color: str = Field(default="slate")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class UserTagLink(SQLModel, table=True):
    """Qué etiquetas tiene cada persona (N a N)."""

    __tablename__ = "user_tag_link"

    user_id: UUID = Field(foreign_key="user.id", primary_key=True)
    tag_id: int = Field(foreign_key="user_tag.id", primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
