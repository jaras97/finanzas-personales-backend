# app/api/auth_extra.py
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlmodel import Session, select
from app.core.config import FRONTEND_URL, PASSWORD_RESET_EXPIRE_MINUTES
from app.core.email import send_password_reset_email
from app.database import engine, get_session
from app.models.password_reset_token import PasswordResetToken
from app.models.subscription import Subscription
from app.models.user import User
from app.core.security import get_password_hash, get_current_user
from app.schemas.user import MIN_PASSWORD_LENGTH

router = APIRouter(prefix="/auth", tags=["auth"])


class ForgotPwdIn(BaseModel):
    email: EmailStr


@router.post("/forgot-password")
def forgot_password(payload: ForgotPwdIn):
    """Emite un enlace de restablecimiento y lo envía por correo.

    Responde siempre lo mismo, exista o no la cuenta: si la respuesta
    cambiara, este endpoint se convertiría en un detector de qué correos
    están registrados. Por lo mismo no se propaga un fallo de envío.
    """
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == payload.email)).first()
        if user:
            # Invalida enlaces anteriores: pedir uno nuevo debe dejar sin
            # efecto al viejo, si no cada solicitud amplía la ventana de
            # ataque en vez de reemplazarla.
            previous = session.exec(
                select(PasswordResetToken).where(
                    PasswordResetToken.user_id == user.id,
                    PasswordResetToken.used_at == None,  # noqa: E711
                )
            ).all()
            now = datetime.utcnow()
            for old in previous:
                old.used_at = now
                session.add(old)

            raw_token = secrets.token_urlsafe(48)
            session.add(
                PasswordResetToken(
                    user_id=user.id,
                    token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
                    expires_at=now + timedelta(minutes=PASSWORD_RESET_EXPIRE_MINUTES),
                )
            )
            session.commit()

            send_password_reset_email(
                to=user.email,
                reset_url=f"{FRONTEND_URL}/auth/reset-password?token={raw_token}",
                expire_minutes=PASSWORD_RESET_EXPIRE_MINUTES,
            )

    return {"detail": "Si el correo existe, se enviaron instrucciones."}


class ResetPwdIn(BaseModel):
    token: str
    new_password: str = Field(..., min_length=MIN_PASSWORD_LENGTH)


@router.post("/reset-password")
def reset_password(payload: ResetPwdIn):
    from app.core.security import revoke_all_refresh_tokens

    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()

    with Session(engine) as session:
        record = session.exec(
            select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
        ).first()

        if not record or record.used_at is not None:
            raise HTTPException(status_code=400, detail="Token inválido o expirado")
        if record.expires_at < datetime.utcnow():
            raise HTTPException(status_code=400, detail="Token inválido o expirado")

        user = session.get(User, record.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        user.hashed_password = get_password_hash(payload.new_password)
        record.used_at = datetime.utcnow()
        # Quien recupera la contraseña normalmente lo hace porque perdió el
        # control de la cuenta: cerrar las sesiones abiertas es parte de
        # recuperarla.
        revoke_all_refresh_tokens(session, user.id)
        session.add_all([user, record])
        session.commit()

    return {"detail": "Contraseña actualizada"}

class ChangePwdIn(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=MIN_PASSWORD_LENGTH)

@router.post("/change-password")
def change_password(
    payload: ChangePwdIn,
    user_id = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    user = session.get(User, user_id)
    from app.core.security import revoke_all_refresh_tokens, verify_password
    if not user or not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Contraseña actual incorrecta")
    user.hashed_password = get_password_hash(payload.new_password)
    session.add(user)
    # Cambiar la contraseña cierra las sesiones renovables: si alguien más
    # tenía acceso, este es el momento en que lo pierde.
    revoke_all_refresh_tokens(session, user.id)
    session.commit()
    return {"detail": "Contraseña actualizada"}


class SubscriptionState(BaseModel):
    state: str  # 'active' | 'none' | 'inactive' | 'expired'
    end_date: Optional[datetime] = None

@router.get("/subscription-status", response_model=SubscriptionState)
def subscription_status(user_id=Depends(get_current_user), session: Session = Depends(get_session)):
    user = session.get(User, user_id)
    if not user:
        return {"state": "none"}

    sub = session.exec(
        select(Subscription)
        .where(Subscription.user_id == user.id)
        .order_by(Subscription.end_date.desc())
    ).first()

    if not sub:
        return {"state": "none"}

    end_date = sub.end_date
    if end_date and end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=timezone.utc)

    expired = end_date and end_date < datetime.now(timezone.utc)
    if expired:
        return {"state": "expired", "end_date": end_date}

    if not sub.is_active:
        return {"state": "inactive", "end_date": end_date}

    return {"state": "active", "end_date": end_date}
