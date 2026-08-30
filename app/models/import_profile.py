from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import Column, JSON, UniqueConstraint
from sqlmodel import Field, SQLModel


class ImportProfile(SQLModel, table=True):
    """Mapeo de columnas de CSV recordado por cuenta, para no volver a
    pedirlo cada vez que el usuario importa un extracto de la misma cuenta
    (ver docs/PENDIENTES.md, Fase 4 del roadmap de presupuestos/features).

    `column_mapping` guarda índices de columna (0-based), no nombres de
    encabezado -- el CSV puede no tener encabezado, o tenerlo repetido.
    """

    __tablename__ = "import_profile"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "saving_account_id", name="uq_import_profile_user_account"
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    saving_account_id: int = Field(foreign_key="saving_account.id", index=True)
    column_mapping: dict = Field(sa_column=Column(JSON))
    date_format: str
    has_header: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
