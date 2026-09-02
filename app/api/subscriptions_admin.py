from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from uuid import UUID
from datetime import datetime, timedelta, timezone
from app.database import get_session
from app.schemas.subscription import SubscriptionRead, SubscriptionStatusRead
from app.models.subscription import Subscription
from typing import List

from app.core.security import get_current_admin_user, get_current_user, get_current_user_with_subscription_check
from app.utils.datetime_helpers import as_utc
from app.utils.subscription_history import registrar_evento, registrar_periodo
from app.models.subscription_plan import SubscriptionPlan
from typing import Optional


def _resolver_plan(session: Session, plan_id: Optional[int]) -> Optional[SubscriptionPlan]:
    """Un plan_id inexistente es un error del cliente, no algo a ignorar en
    silencio: si no avisáramos, el período quedaría registrado sin precio y el
    admin creería haberlo cobrado."""
    if plan_id is None:
        return None
    plan = session.get(SubscriptionPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="El plan indicado no existe.")
    return plan

router = APIRouter(prefix="/subscriptions/admin", tags=["admin-subscriptions"])

# ✅ Crear o activar suscripción manualmente para un usuario
@router.post("/activate", response_model=SubscriptionRead)
def activate_subscription_admin(
    user_id: UUID = Query(..., description="ID del usuario al que deseas activar la suscripción"),
    months: int = Query(1, description="Número de meses a activar"),
    plan_id: Optional[int] = Query(None, description="Plan del catálogo; si se envía, su duración manda sobre `months`"),
    note: Optional[str] = Query(None, description="Nota libre que queda en el historial"),
    session: Session = Depends(get_session),
    admin_user_id: UUID = Depends(get_current_admin_user)
):
    plan = _resolver_plan(session, plan_id)
    if plan:
        months = plan.duration_months

    existing = session.exec(
        select(Subscription).where(Subscription.user_id == user_id)
    ).first()

    now = datetime.now(timezone.utc)
    end_date = now + timedelta(days=30 * months)

    if existing:
        # `as_utc` es obligatorio: en producción estas columnas son naive y
        # comparar contra `now` (aware) reventaba con TypeError -> 500. Era la
        # razón por la que reactivar una suscripción vencida fallaba y solo
        # funcionaba borrarla y crearla de cero.
        vigente = as_utc(existing.end_date) > now and existing.is_active
        if vigente:
            raise HTTPException(status_code=400, detail="El usuario ya tiene una suscripción activa.")

        # Se llega acá si está vencida O si está marcada como inactiva. Antes
        # la guarda solo miraba la fecha, así que una suscripción con fecha
        # futura pero is_active=False respondía "ya tiene una suscripción
        # activa" -- mensaje falso y sin salida salvo borrar y recrear.
        anterior = as_utc(existing.end_date)
        existing.start_date = now
        existing.end_date = end_date
        existing.is_active = True  # sin esto, "Reactivar" devolvía 200 y dejaba al usuario bloqueado
        existing.updated_at = now
        session.add(existing)

        registrar_periodo(session, user_id=user_id, start_date=now, end_date=end_date,
                          origin="activate", plan=plan, created_by=admin_user_id, note=note)
        registrar_evento(session, user_id=user_id, action="activate", performed_by=admin_user_id,
                         end_date_before=anterior, end_date_after=end_date, months=months,
                         plan_id=plan.id if plan else None, detail=note)
        session.commit()
        session.refresh(existing)
        return existing

    subscription = Subscription(
        user_id=user_id,
        start_date=now,
        end_date=end_date
    )
    session.add(subscription)

    registrar_periodo(session, user_id=user_id, start_date=now, end_date=end_date,
                      origin="activate", plan=plan, created_by=admin_user_id, note=note)
    registrar_evento(session, user_id=user_id, action="activate", performed_by=admin_user_id,
                     end_date_before=None, end_date_after=end_date, months=months,
                     plan_id=plan.id if plan else None, detail=note)
    session.commit()
    session.refresh(subscription)
    return subscription

# ✅ Renovar suscripción manualmente para un usuario
@router.post("/renew", response_model=SubscriptionRead)
def renew_subscription_admin(
    user_id: UUID = Query(..., description="ID del usuario a renovar"),
    months: int = Query(1, description="Número de meses a renovar"),
    plan_id: Optional[int] = Query(None, description="Plan del catálogo; si se envía, su duración manda sobre `months`"),
    note: Optional[str] = Query(None, description="Nota libre que queda en el historial"),
    session: Session = Depends(get_session),
    admin_user_id: UUID = Depends(get_current_admin_user)
):
    plan = _resolver_plan(session, plan_id)
    if plan:
        months = plan.duration_months

    subscription = session.exec(
        select(Subscription).where(Subscription.user_id == user_id)
    ).first()

    if not subscription:
        raise HTTPException(status_code=404, detail="No existe una suscripción para este usuario.")

    now = datetime.now(timezone.utc)
    fin_actual = as_utc(subscription.end_date)  # ver nota en /activate

    if fin_actual > now:
        # Vigente: se suma el tiempo al vencimiento actual, no se pierde lo que quedaba.
        # El período nuevo arranca donde terminaba el anterior, no hoy: así el
        # historial no muestra dos tramos solapados para el mismo tiempo.
        inicio_periodo = fin_actual
        subscription.end_date = fin_actual + timedelta(days=30 * months)
    else:
        # Vencida: se reinicia desde hoy.
        inicio_periodo = now
        subscription.start_date = now
        subscription.end_date = now + timedelta(days=30 * months)

    # Renovar implica dejarla utilizable: si no, la fecha avanza pero el
    # usuario sigue bloqueado por is_active.
    subscription.is_active = True
    subscription.updated_at = now

    session.add(subscription)
    registrar_periodo(session, user_id=user_id, start_date=inicio_periodo,
                      end_date=subscription.end_date, origin="renew", plan=plan,
                      created_by=admin_user_id, note=note)
    registrar_evento(session, user_id=user_id, action="renew", performed_by=admin_user_id,
                     end_date_before=fin_actual, end_date_after=subscription.end_date,
                     months=months, plan_id=plan.id if plan else None, detail=note)
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

    # El período y los pagos NO se borran: la persona sí estuvo cubierta ese
    # tiempo y sí pagó. Solo se registra la baja.
    registrar_evento(session, user_id=user_id, action="delete", performed_by=admin_user_id,
                     end_date_before=as_utc(subscription.end_date), end_date_after=None,
                     detail="Suscripción eliminada por un administrador")
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

# La ruta GET /subscriptions/admin/me que vivía aquí era inalcanzable: se
# declara después de GET /{user_id}, que la captura primero y falla al
# interpretar "me" como UUID (y además exige admin, cuando el endpoint decía
# ser "mi suscripción"). El equivalente vivo es GET /subscriptions/me, en
# api/subscriptions.py. Se elimina en vez de reordenarla porque estaba
# duplicando ese endpoint.
