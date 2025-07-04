# app/api/subscriptions.py

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from uuid import UUID
from datetime import datetime, timezone
from app.database import get_session
from app.schemas.subscription import SubscriptionStatusRead
from app.models.subscription import Subscription
from app.core.security import get_current_user

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])

@router.get("/me", response_model=SubscriptionStatusRead)
def get_my_subscription(
    session: Session = Depends(get_session),
    user_id: UUID = Depends(get_current_user)
):
    subscription = session.exec(
        select(Subscription).where(Subscription.user_id == user_id)
    ).first()

    if not subscription:
        raise HTTPException(status_code=404, detail="No tienes una suscripción activa.")

    now = datetime.now(timezone.utc)
    status = "expired" if subscription.end_date < now else "active"

    return {
        **subscription.dict(),
        "status": status
    }