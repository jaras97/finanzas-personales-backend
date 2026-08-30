from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlmodel import Field, SQLModel


class RefreshToken(SQLModel, table=True):
    """Token de renovación de sesión.

    Se guarda el SHA-256 del token, nunca el valor crudo: si la base se
    filtrara, los hashes no sirven para autenticarse. Es un valor aleatorio
    de alta entropía (`secrets.token_urlsafe`), así que sha256 alcanza --
    bcrypt existe para contraseñas de baja entropía, acá solo estorbaría.

    Rotación: cada uso revoca el token y emite uno nuevo. Si alguien roba un
    token y lo usa, el legítimo deja de funcionar en su siguiente intento --
    el usuario nota la expulsión en vez de compartir sesión en silencio.
    """

    __tablename__ = "refresh_token"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    token_hash: str = Field(index=True, unique=True)
    expires_at: datetime
    revoked_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
