"""Historial de suscripciones, planes, pagos y ficha administrativa.

Todo aquí exige rol admin. Es el panel con el que se lleva el registro de las
personas: quién es cliente desde cuándo, qué se le cobró, quién le renovó y
si de verdad usa la app.
"""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select, func

from app.database import get_session
from app.core.security import get_current_admin_user
from app.models.user import User
from app.models.subscription import Subscription
from app.models.subscription_plan import SubscriptionPlan
from app.models.subscription_period import SubscriptionPeriod
from app.models.subscription_event import SubscriptionEvent
from app.models.payment import Payment
from app.models.user_admin_profile import UserAdminProfile, UserTag, UserTagLink
from app.models.transaction import Transaction
from app.models.saving_account import SavingAccount
from app.models.debt import Debt
from app.schemas.admin_records import (
    PlanCreate, PlanUpdate, PlanRead,
    TagCreate, TagRead, TagAssign,
    PeriodRead, EventRead,
    PaymentCreate, PaymentRead,
    ProfileUpdate, UserMetrics, AdminUserDetail,
)
from app.utils.datetime_helpers import as_utc
from app.utils.subscription_history import registrar_evento

router = APIRouter(prefix="/admin", tags=["admin-records"])


# ===========================================================================
# Planes (paramétrica)
# ===========================================================================
@router.get("/subscription-plans", response_model=List[PlanRead])
def listar_planes(
    include_inactive: bool = Query(False),
    session: Session = Depends(get_session),
    admin_user_id: UUID = Depends(get_current_admin_user),
):
    q = select(SubscriptionPlan)
    if not include_inactive:
        q = q.where(SubscriptionPlan.is_active == True)  # noqa: E712
    return session.exec(q.order_by(SubscriptionPlan.duration_months)).all()


@router.post("/subscription-plans", response_model=PlanRead, status_code=201)
def crear_plan(
    data: PlanCreate,
    session: Session = Depends(get_session),
    admin_user_id: UUID = Depends(get_current_admin_user),
):
    plan = SubscriptionPlan(**data.model_dump())
    session.add(plan)
    session.commit()
    session.refresh(plan)
    return plan


@router.put("/subscription-plans/{plan_id}", response_model=PlanRead)
def editar_plan(
    plan_id: int,
    data: PlanUpdate,
    session: Session = Depends(get_session),
    admin_user_id: UUID = Depends(get_current_admin_user),
):
    plan = session.get(SubscriptionPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan no encontrado")
    for campo, valor in data.model_dump(exclude_unset=True).items():
        setattr(plan, campo, valor)
    plan.updated_at = datetime.now(timezone.utc)
    session.add(plan)
    session.commit()
    session.refresh(plan)
    return plan


@router.delete("/subscription-plans/{plan_id}")
def retirar_plan(
    plan_id: int,
    session: Session = Depends(get_session),
    admin_user_id: UUID = Depends(get_current_admin_user),
):
    """Baja lógica, nunca física: los períodos y pagos ya registrados apuntan a
    este plan y borrarlo dejaría el historial sin poder explicar qué se cobró."""
    plan = session.get(SubscriptionPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan no encontrado")
    plan.is_active = False
    plan.updated_at = datetime.now(timezone.utc)
    session.add(plan)
    session.commit()
    return {"detail": "Plan retirado del catálogo. El historial que lo usa se conserva."}


# ===========================================================================
# Etiquetas (paramétrica)
# ===========================================================================
@router.get("/tags", response_model=List[TagRead])
def listar_etiquetas(
    session: Session = Depends(get_session),
    admin_user_id: UUID = Depends(get_current_admin_user),
):
    return session.exec(select(UserTag).order_by(UserTag.name)).all()


@router.post("/tags", response_model=TagRead, status_code=201)
def crear_etiqueta(
    data: TagCreate,
    session: Session = Depends(get_session),
    admin_user_id: UUID = Depends(get_current_admin_user),
):
    existente = session.exec(
        select(UserTag).where(func.lower(UserTag.name) == data.name.strip().lower())
    ).first()
    if existente:
        raise HTTPException(status_code=400, detail="Ya existe una etiqueta con ese nombre.")
    tag = UserTag(name=data.name.strip(), color=data.color)
    session.add(tag)
    session.commit()
    session.refresh(tag)
    return tag


@router.delete("/tags/{tag_id}")
def borrar_etiqueta(
    tag_id: int,
    session: Session = Depends(get_session),
    admin_user_id: UUID = Depends(get_current_admin_user),
):
    tag = session.get(UserTag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Etiqueta no encontrada")
    # Se quitan primero las asignaciones: si no, la FK impide el borrado y el
    # admin recibe un 500 en vez de una acción que simplemente funciona.
    for enlace in session.exec(select(UserTagLink).where(UserTagLink.tag_id == tag_id)).all():
        session.delete(enlace)
    # flush explícito: sin él SQLAlchemy podía emitir el DELETE de la etiqueta
    # antes que el de sus enlaces y Postgres rechazaba por la foreign key.
    session.flush()
    session.delete(tag)
    session.commit()
    return {"detail": "Etiqueta eliminada"}


# ===========================================================================
# Ficha de una persona
# ===========================================================================
def _emails(session: Session, ids: set) -> dict:
    """Resuelve los correos de los admins que actuaron, en UNA consulta.
    Hacerlo por fila convertía la ficha en N+1 sobre la tabla de usuarios."""
    ids = {i for i in ids if i}
    if not ids:
        return {}
    filas = session.exec(select(User.id, User.email).where(User.id.in_(ids))).all()
    return {i: e for i, e in filas}


def _estado_suscripcion(sub: Optional[Subscription]) -> str:
    if not sub:
        return "none"
    if as_utc(sub.end_date) < datetime.now(timezone.utc):
        return "expired"
    if not sub.is_active:
        return "inactive"
    return "active"


@router.get("/users/{user_id}/detail", response_model=AdminUserDetail)
def ficha_usuario(
    user_id: UUID,
    session: Session = Depends(get_session),
    admin_user_id: UUID = Depends(get_current_admin_user),
):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    sub = session.exec(
        select(Subscription).where(Subscription.user_id == user_id)
        .order_by(Subscription.end_date.desc())
    ).first()

    periodos = session.exec(
        select(SubscriptionPeriod).where(SubscriptionPeriod.user_id == user_id)
        .order_by(SubscriptionPeriod.start_date.desc())
    ).all()
    eventos = session.exec(
        select(SubscriptionEvent).where(SubscriptionEvent.user_id == user_id)
        .order_by(SubscriptionEvent.created_at.desc())
    ).all()
    pagos = session.exec(
        select(Payment).where(Payment.user_id == user_id).order_by(Payment.paid_at.desc())
    ).all()

    correos = _emails(
        session,
        {p.created_by for p in periodos} | {e.performed_by for e in eventos} | {p.created_by for p in pagos},
    )
    planes = {
        p.id: p.name
        for p in session.exec(select(SubscriptionPlan)).all()
    }

    perfil = session.get(UserAdminProfile, user_id)
    etiquetas = session.exec(
        select(UserTag).join(UserTagLink, UserTagLink.tag_id == UserTag.id)
        .where(UserTagLink.user_id == user_id).order_by(UserTag.name)
    ).all()

    def _contar(modelo) -> int:
        return session.exec(
            select(func.count()).select_from(modelo).where(modelo.user_id == user_id)
        ).one() or 0

    ultimo = as_utc(user.last_login_at) if user.last_login_at else None
    metrics = UserMetrics(
        last_login_at=ultimo,
        transactions=_contar(Transaction),
        accounts=_contar(SavingAccount),
        debts=_contar(Debt),
        days_since_last_login=(datetime.now(timezone.utc) - ultimo).days if ultimo else None,
        has_ever_logged_in=ultimo is not None,
    )

    # Se suma sin convertir monedas a propósito: mezclar COP y USD en un solo
    # número daría una cifra falsa. Si algún día hay varias monedas en juego,
    # esto debe pasar a un desglose por moneda.
    total_pagado = sum(p.amount for p in pagos)

    return AdminUserDetail(
        id=user.id,
        email=user.email,
        role=user.role,
        created_at=user.created_at,
        subscription_status=_estado_suscripcion(sub),
        subscription_start=sub.start_date if sub else None,
        subscription_end=sub.end_date if sub else None,
        full_name=perfil.full_name if perfil else None,
        phone=perfil.phone if perfil else None,
        notes=perfil.notes if perfil else None,
        tags=[TagRead.model_validate(t) for t in etiquetas],
        metrics=metrics,
        periods=[
            PeriodRead(
                id=p.id, start_date=p.start_date, end_date=p.end_date, price=p.price,
                currency=p.currency, origin=p.origin, note=p.note,
                plan_name=planes.get(p.plan_id), created_at=p.created_at,
                created_by_email=correos.get(p.created_by),
            ) for p in periodos
        ],
        events=[
            EventRead(
                id=e.id, action=e.action, end_date_before=e.end_date_before,
                end_date_after=e.end_date_after, months=e.months, detail=e.detail,
                created_at=e.created_at, performed_by_email=correos.get(e.performed_by),
            ) for e in eventos
        ],
        payments=[
            PaymentRead(
                id=p.id, amount=p.amount, currency=p.currency, method=p.method,
                reference=p.reference, note=p.note, paid_at=p.paid_at,
                created_at=p.created_at, created_by_email=correos.get(p.created_by),
            ) for p in pagos
        ],
        total_paid=total_pagado,
        # El período más antiguo es la respuesta a "¿desde cuándo es cliente?",
        # que `subscription.start_date` no puede dar porque se reinicia en cada
        # renovación.
        first_subscribed_at=periodos[-1].start_date if periodos else None,
    )


@router.put("/users/{user_id}/profile", response_model=AdminUserDetail)
def editar_ficha(
    user_id: UUID,
    data: ProfileUpdate,
    session: Session = Depends(get_session),
    admin_user_id: UUID = Depends(get_current_admin_user),
):
    if not session.get(User, user_id):
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    perfil = session.get(UserAdminProfile, user_id) or UserAdminProfile(user_id=user_id)
    for campo, valor in data.model_dump(exclude_unset=True).items():
        setattr(perfil, campo, valor)
    perfil.updated_by = admin_user_id
    perfil.updated_at = datetime.now(timezone.utc)
    session.add(perfil)
    session.commit()
    return ficha_usuario(user_id, session, admin_user_id)


@router.put("/users/{user_id}/tags", response_model=AdminUserDetail)
def asignar_etiquetas(
    user_id: UUID,
    data: TagAssign,
    session: Session = Depends(get_session),
    admin_user_id: UUID = Depends(get_current_admin_user),
):
    """Reemplaza el conjunto completo de etiquetas de la persona."""
    if not session.get(User, user_id):
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    validos = {
        t.id for t in session.exec(select(UserTag).where(UserTag.id.in_(data.tag_ids))).all()
    } if data.tag_ids else set()
    desconocidos = set(data.tag_ids) - validos
    if desconocidos:
        raise HTTPException(status_code=404, detail=f"Etiquetas inexistentes: {sorted(desconocidos)}")

    for enlace in session.exec(select(UserTagLink).where(UserTagLink.user_id == user_id)).all():
        session.delete(enlace)
    for tag_id in validos:
        session.add(UserTagLink(user_id=user_id, tag_id=tag_id))
    session.commit()
    return ficha_usuario(user_id, session, admin_user_id)


@router.post("/users/{user_id}/payments", response_model=AdminUserDetail, status_code=201)
def registrar_pago(
    user_id: UUID,
    data: PaymentCreate,
    session: Session = Depends(get_session),
    admin_user_id: UUID = Depends(get_current_admin_user),
):
    if not session.get(User, user_id):
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if data.period_id is not None:
        periodo = session.get(SubscriptionPeriod, data.period_id)
        if not periodo or periodo.user_id != user_id:
            raise HTTPException(status_code=404, detail="El período indicado no es de este usuario.")

    pago = Payment(
        user_id=user_id,
        period_id=data.period_id,
        amount=data.amount,
        currency=data.currency,
        method=data.method,
        reference=data.reference,
        note=data.note,
        paid_at=data.paid_at or datetime.now(timezone.utc),
        created_by=admin_user_id,
        created_at=datetime.now(timezone.utc),
    )
    session.add(pago)
    registrar_evento(
        session, user_id=user_id, action="payment", performed_by=admin_user_id,
        detail=f"Pago registrado: {data.amount:,.0f} {data.currency} ({data.method})",
    )
    session.commit()
    return ficha_usuario(user_id, session, admin_user_id)


@router.delete("/users/{user_id}/payments/{payment_id}")
def borrar_pago(
    user_id: UUID,
    payment_id: int,
    session: Session = Depends(get_session),
    admin_user_id: UUID = Depends(get_current_admin_user),
):
    pago = session.get(Payment, payment_id)
    if not pago or pago.user_id != user_id:
        raise HTTPException(status_code=404, detail="Pago no encontrado para este usuario.")
    registrar_evento(
        session, user_id=user_id, action="payment", performed_by=admin_user_id,
        detail=f"Pago ELIMINADO: {pago.amount:,.0f} {pago.currency}",
    )
    session.delete(pago)
    session.commit()
    return {"detail": "Pago eliminado"}
