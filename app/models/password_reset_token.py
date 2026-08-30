from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlmodel import Field, SQLModel


class PasswordResetToken(SQLModel, table=True):
    """Token de restablecimiento de contraseña.

    Reemplaza el dict en memoria `RESET_TOKENS`, que se perdía en cada
    deploy (un usuario que pedía el enlace justo antes de un despliegue
    quedaba con un enlace muerto) y no habría funcionado con más de una
    instancia del backend.

    Mismo criterio que `RefreshToken`: se guarda el SHA-256, nunca el valor
    crudo, y las filas usadas se conservan para que un reuso se distinga de
    un token inexistente.
    """

    __tablename__ = "password_reset_token"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    token_hash: str = Field(index=True, unique=True)
    expires_at: datetime
    used_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
