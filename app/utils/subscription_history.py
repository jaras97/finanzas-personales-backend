"""Escritura del historial de suscripciones.

Centralizado en un módulo para que ningún endpoint pueda "olvidarse" de dejar
rastro: exactamente el tipo de omisión que causó el bug de renovación de
2026-09-01, donde una de las cuatro copias de una comparación se quedó atrás.

Regla que sostiene todo esto: el historial NUNCA decide el acceso. Quien manda
sigue siendo la tabla `subscription`. Si algo aquí fallara, el usuario podría
quedarse sin registro histórico, pero jamás sin acceso.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlmodel import Session

from app.models.subscription_event import SubscriptionEvent
from app.models.subscription_period import SubscriptionPeriod
from app.models.subscription_plan import SubscriptionPlan


def registrar_evento(
    session: Session,
    *,
    user_id: UUID,
    action: str,
    performed_by: Optional[UUID] = None,
    end_date_before: Optional[datetime] = None,
    end_date_after: Optional[datetime] = None,
    months: Optional[int] = None,
    plan_id: Optional[int] = None,
    detail: Optional[str] = None,
) -> SubscriptionEvent:
    """Añade una entrada a la bitácora. No hace commit: lo hace quien llama,
    para que el evento y el cambio que describe entren en la misma transacción
    y no puedan quedar desincronizados."""
    evento = SubscriptionEvent(
        user_id=user_id,
        action=action,
        performed_by=performed_by,
        end_date_before=end_date_before,
        end_date_after=end_date_after,
        months=months,
        plan_id=plan_id,
        detail=detail,
        created_at=datetime.now(timezone.utc),
    )
    session.add(evento)
    return evento


def registrar_periodo(
    session: Session,
    *,
    user_id: UUID,
    start_date: datetime,
    end_date: datetime,
    origin: str,
    plan: Optional[SubscriptionPlan] = None,
    created_by: Optional[UUID] = None,
    note: Optional[str] = None,
) -> SubscriptionPeriod:
    """Registra un tramo de servicio otorgado.

    El precio y la moneda se COPIAN del plan en este momento: si mañana subes
    el precio del plan, lo ya otorgado conserva lo que costó entonces.
    """
    periodo = SubscriptionPeriod(
        user_id=user_id,
        plan_id=plan.id if plan else None,
        start_date=start_date,
        end_date=end_date,
        price=plan.price if plan else 0,
        currency=plan.currency if plan else "COP",
        origin=origin,
        note=note,
        created_by=created_by,
        created_at=datetime.now(timezone.utc),
    )
    session.add(periodo)
    return periodo
