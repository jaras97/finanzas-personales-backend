import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from sqlmodel import Session, select
from app.core.config import (
    SECRET_KEY,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
)
from app.database import engine, get_session
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.models.subscription import Subscription

# Manejo de contraseñas
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ACCESS_TOKEN_COOKIE_NAME = "access_token"
REFRESH_TOKEN_COOKIE_NAME = "refresh_token"

# auto_error=False: no rechaza la request solo porque falte el header
# Authorization -- get_token() abajo intenta la cookie httpOnly antes de
# rechazar. El esquema se mantiene para que Swagger/Postman sigan pudiendo
# autenticar por header como hasta ahora.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def get_token(request: Request, header_token: Optional[str] = Depends(oauth2_scheme)) -> str:
    if header_token:
        return header_token
    cookie_token = request.cookies.get(ACCESS_TOKEN_COOKIE_NAME)
    if cookie_token:
        return cookie_token
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")

# Funciones de seguridad
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def _hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def issue_refresh_token(session: Session, user_id: UUID) -> str:
    """Crea un refresh token nuevo y devuelve el valor CRUDO (lo único que
    se le entrega al cliente). En la base solo queda su hash."""
    raw_token = secrets.token_urlsafe(48)
    session.add(
        RefreshToken(
            user_id=user_id,
            token_hash=_hash_refresh_token(raw_token),
            expires_at=datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        )
    )
    return raw_token


def consume_refresh_token(session: Session, raw_token: str) -> Optional[UUID]:
    """Valida y ROTA un refresh token: si es válido lo revoca y devuelve el
    `user_id` para que el llamador emita uno nuevo. Devuelve `None` si no
    existe, ya fue usado/revocado, o expiró."""
    record = session.exec(
        select(RefreshToken).where(RefreshToken.token_hash == _hash_refresh_token(raw_token))
    ).first()

    if not record or record.revoked_at is not None:
        return None

    expires_at = record.expires_at
    if expires_at.tzinfo is not None:
        expires_at = expires_at.astimezone(timezone.utc).replace(tzinfo=None)
    if expires_at < datetime.utcnow():
        return None

    record.revoked_at = datetime.utcnow()
    session.add(record)
    return record.user_id


def revoke_all_refresh_tokens(session: Session, user_id: UUID) -> None:
    """Cierra todas las sesiones renovables del usuario (logout, o cambio de
    contraseña: si alguien te robó la clave, cambiarla debe echarlo)."""
    tokens = session.exec(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id, RefreshToken.revoked_at == None  # noqa: E711
        )
    ).all()
    now = datetime.utcnow()
    for token in tokens:
        token.revoked_at = now
        session.add(token)


def get_current_user(token: str = Depends(get_token)) -> UUID:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id_str: str = payload.get("sub")
        if user_id_str is None:
            raise HTTPException(status_code=401, detail="Token inválido")
        user_id = UUID(user_id_str)
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido")

    return user_id

def get_current_user_with_subscription_check(token: str = Depends(get_token)) -> UUID:
    user_id = get_current_user(token)

    with Session(engine) as session:
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=401, detail="Usuario no encontrado")

        subscription = session.exec(
            select(Subscription)
            .where(Subscription.user_id == user.id)
            .order_by(Subscription.end_date.desc())
        ).first()

        # 🚩 Bloquear si el usuario NO tiene suscripción
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes una suscripción activa. Por favor suscríbete para continuar."
            )

        # 🚩 Bloquear si la suscripción está inactiva
        if not subscription.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tu suscripción está inactiva. Por favor contacta al administrador para activarla."
            )

        # ✅ CORRECCIÓN: Asegurar que end_date sea timezone-aware
        end_date = subscription.end_date
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)

        # 🚩 Bloquear si la suscripción está vencida
        if end_date < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tu suscripción ha expirado. Por favor renueva para continuar."
            )

    return user.id

def get_current_admin_user(
    token: str = Depends(get_token),
    session: Session = Depends(get_session)
) -> UUID:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
        
        user = session.exec(select(User).where(User.id == user_id)).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

        if user.role != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No autorizado, se requiere rol de administrador")

        return user.id

    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")