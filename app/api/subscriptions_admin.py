from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from uuid import UUID
from datetime import datetime, timedelta, timezone
from app.database import get_session
from app.schemas.subscription import SubscriptionRead, SubscriptionStatusRead
from app.models.subscription import Subscription
from typing import List

from app.core.security import get_current_admin_user, get_current_user, get_current_user_with_subscription_check

router = APIRouter(prefix="/subscriptions/admin", tags=["admin-subscriptions"])

# ✅ Crear o activar suscripción manualmente para un usuario
@router.post("/activate", response_model=SubscriptionRead)
def activate_subscription_admin(
    user_id: UUID = Query(..., description="ID del usuario al que deseas activar la suscripción"),
    months: int = Query(1, description="Número de meses a activar"),
    session: Session = Depends(get_session),
    admin_user_id: UUID = Depends(get_current_admin_user)
):
    existing = session.exec(
        select(Subscription).where(Subscription.user_id == user_id)
    ).first()

    now = datetime.now(timezone.utc)  # ✅ cambio aquí
    end_date = now + timedelta(days=30 * months)

    if existing:
        if existing.end_date > now:
            raise HTTPException(status_code=400, detail="El usuario ya tiene una suscripción activa.")
        else:
            existing.start_date = now
            existing.end_date = end_date
            session.add(existing)
            session.commit()
            session.refresh(existing)
            return existing

    subscription = Subscription(
        user_id=user_id,
        start_date=now,
        end_date=end_date
    )
    session.add(subscription)
    session.commit()
    session.refresh(subscription)
    return subscription

# ✅ Renovar suscripción manualmente para un usuario
@router.post("/renew", response_model=SubscriptionRead)
def renew_subscription_admin(
    user_id: UUID = Query(..., description="ID del usuario a renovar"),
    months: int = Query(1, description="Número de meses a renovar"),
    session: Session = Depends(get_session),
    admin_user_id: UUID = Depends(get_current_admin_user)
):
    subscription = session.exec(
        select(Subscription).where(Subscription.user_id == user_id)
    ).first()

    if not subscription:
        raise HTTPException(status_code=404, detail="No existe una suscripción para este usuario.")

    now = datetime.now(timezone.utc)  # ✅ cambio aquí
    if subscription.end_date > now:
        subscription.end_date += timedelta(days=30 * months)
    else:
        subscription.start_date = now
        subscription.end_date = now + timedelta(days=30 * months)

    session.add(subscription)
    session.commit()
    session.refresh(subscription)
    return subscription

# ✅ Consultar el estado de suscripción de un usuario específico
@router.get("/{user_id}", response_model=SubscriptionRead)
def get_subscription_admin(
    user_id: UUID,
    session: Session = Depends(get_session),
    admin_user_id: UUID = Depends(get_current_admin_user)
):
    subscription = session.exec(
        select(Subscription).where(Subscription.user_id == user_id)
    ).first()
    if not subscription:
        raise HTTPException(status_code=404, detail="El usuario no tiene una suscripción activa.")
    return subscription

# ✅ Eliminar suscripción de un usuario
@router.delete("/{user_id}")
def delete_subscription_admin(
    user_id: UUID,
    session: Session = Depends(get_session),
    admin_user_id: UUID = Depends(get_current_admin_user)
):
    subscription = session.exec(
        select(Subscription).where(Subscription.user_id == user_id)
    ).first()
    if not subscription:
        raise HTTPException(status_code=404, detail="Suscripción no encontrada para este usuario.")
    session.delete(subscription)
    session.commit()
    return {"detail": "Suscripción eliminada correctamente"}

# ✅ Listar todas las suscripciones
@router.get("", response_model=List[SubscriptionRead])
@router.get("/", response_model=List[SubscriptionRead])
def list_subscriptions_admin(
    session: Session = Depends(get_session),
    admin_user_id: UUID = Depends(get_current_admin_user)
):
    subscriptions = session.exec(select(Subscription)).all()
    return subscriptions

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