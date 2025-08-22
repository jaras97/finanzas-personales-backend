# app/api/auth_extra.py (ejemplo)
from datetime import timezone
import datetime
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlmodel import Session, select
from app.database import engine, get_session
from app.models.subscription import Subscription
from app.models.user import User
from app.core.security import get_password_hash, get_current_user
from uuid import uuid4

router = APIRouter(prefix="/auth", tags=["auth"])

# almacenar tokens simple (idealmente en tabla reset_tokens)
RESET_TOKENS: dict[str, str] = {}  # token -> email (solo demo)

class ForgotPwdIn(BaseModel):
    email: EmailStr

@router.post("/forgot-password")
def forgot_password(payload: ForgotPwdIn):
    with Session(engine) as session:
      user = session.exec(select(User).where(User.email == payload.email)).first()
      # No reveles si existe o no
      if user:
        token = str(uuid4())
        RESET_TOKENS[token] = user.email
        # envía email con link a tu frontend: /reset-password?token=...
        # send_email(user.email, token)  # implementa
    return {"detail": "Si el correo existe, se enviaron instrucciones."}

class ResetPwdIn(BaseModel):
    token: str
    new_password: str

@router.post("/reset-password")
def reset_password(payload: ResetPwdIn):
    email = RESET_TOKENS.pop(payload.token, None)
    if not email:
        raise HTTPException(status_code=400, detail="Token inválido o expirado")
    with Session(engine) as session:
      user = session.exec(select(User).where(User.email == email)).first()
      if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
      user.hashed_password = get_password_hash(payload.new_password)
      session.add(user)
      session.commit()
    return {"detail": "Contraseña actualizada"}

class ChangePwdIn(BaseModel):
    current_password: str
    new_password: str

@router.post("/change-password")
def change_password(
    payload: ChangePwdIn,
    user_id = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    user = session.get(User, user_id)
    from app.core.security import verify_password
    if not user or not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Contraseña actual incorrecta")
    user.hashed_password = get_password_hash(payload.new_password)
    session.add(user)
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
