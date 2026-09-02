from datetime import datetime, timezone
from math import ceil
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlmodel import Session, select

from app.core.security import get_current_admin_user
from app.database import get_session
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.admin import AdminUserRead, AdminUsersPage, RoleUpdate
from app.utils.datetime_helpers import as_utc

router = APIRouter(prefix="/admin/users", tags=["admin-users"])


def _subscription_status(sub: Optional[Subscription]) -> str:
    """Misma prioridad que usa el frontend (useSubscriptionStatus): la fecha de
    vencimiento manda sobre is_active."""
    if not sub:
        return "none"
    if as_utc(sub.end_date) < datetime.now(timezone.utc):
        return "expired"
    if not sub.is_active:
        return "inactive"
    return "active"


def _to_read(user: User, sub: Optional[Subscription]) -> AdminUserRead:
    return AdminUserRead(
        id=user.id,
        email=user.email,
        role=user.role,
        created_at=user.created_at,
        subscription_status=_subscription_status(sub),
        subscription_start=sub.start_date if sub else None,
        subscription_end=sub.end_date if sub else None,
    )


def _latest_subscription(session: Session, user_id: UUID) -> Optional[Subscription]:
    return session.exec(
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .order_by(Subscription.end_date.desc())
    ).first()


@router.get("", response_model=AdminUsersPage)
@router.get("/", response_model=AdminUsersPage)
def list_users(
    search: Optional[str] = Query(None, description="Filtra por coincidencia parcial de correo"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    session: Session = Depends(get_session),
    admin_user_id: UUID = Depends(get_current_admin_user),
):
    base = select(User)
    count_q = select(func.count()).select_from(User)
    if search:
        pattern = f"%{search.strip().lower()}%"
        base = base.where(func.lower(User.email).like(pattern))
        count_q = count_q.where(func.lower(User.email).like(pattern))

    total = session.exec(count_q).one() or 0
    users = session.exec(
        base.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()

    items = [_to_read(u, _latest_subscription(session, u.id)) for u in users]

    return AdminUsersPage(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=ceil(total / page_size) if total else 0,
    )


@router.patch("/{user_id}/role", response_model=AdminUserRead)
def update_user_role(
    user_id: UUID,
    payload: RoleUpdate,
    session: Session = Depends(get_session),
    admin_user_id: UUID = Depends(get_current_admin_user),
):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if user.role == payload.role:
        return _to_read(user, _latest_subscription(session, user.id))

    # Nunca dejar el sistema sin ningún administrador: si este cambio quita el
    # último rol admin que queda, no hay forma de volver a entrar al panel.
    if user.role == "admin" and payload.role != "admin":
        remaining_admins = session.exec(
            select(func.count()).select_from(User).where(User.role == "admin", User.id != user_id)
        ).one() or 0
        if remaining_admins == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No puedes quitar el último administrador: quedarías sin acceso al panel.",
            )

    user.role = payload.role
    session.add(user)
    session.commit()
    session.refresh(user)
    return _to_read(user, _latest_subscription(session, user.id))
