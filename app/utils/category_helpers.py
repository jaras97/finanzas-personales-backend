from uuid import UUID
from sqlmodel import Session, select
from typing import Optional

from app.models.category import Category, CategoryType
from app.constants.categories import SystemCategoryKey

def _adopt_by_name_if_exists(
    session: Session,
    user_id: UUID,
    name: str,
    type_: CategoryType,
    key: SystemCategoryKey,
) -> Optional[Category]:
    """
    Si el usuario ya tiene una categoría con ese NOMBRE (sin system_key),
    la adoptamos como de sistema (is_system=True, system_key=key).
    """
    existing = session.exec(
        select(Category).where(
            Category.user_id == user_id,
            Category.name == name,
            Category.system_key == None,  # aún no es de sistema
        )
    ).first()

    if existing:
        existing.is_system = True
        existing.system_key = key.value
        # Ajusta tipo si es necesario; si prefieres no tocarlo, comenta la línea:
        existing.type = existing.type or type_
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing
    return None


def get_or_create_system_category(
    session: Session,
    user_id: UUID,
    *,
    key: SystemCategoryKey,
    default_name: str,
    type_: CategoryType,
) -> Category:
    """
    Busca por system_key, si no existe intenta adoptar por nombre,
    si tampoco, crea nueva. Idempotente por (user_id, system_key) UNIQUE.
    """
    cat = session.exec(
        select(Category).where(
            Category.user_id == user_id,
            Category.system_key == key.value,
        )
    ).first()
    if cat:
        return cat

    # Intentar adoptar por nombre (compatibilidad con datos existentes)
    adopted = _adopt_by_name_if_exists(session, user_id, default_name, type_, key)
    if adopted:
        return adopted

    # Crear nueva
    cat = Category(
        user_id=user_id,
        name=default_name,
        type=type_,
        is_system=True,
        system_key=key.value,
        is_active=True,
    )
    session.add(cat)
    session.commit()
    session.refresh(cat)
    return cat


def get_or_create_transfer_category(session: Session, user_id: UUID) -> Category:
    # En adelante usamos system_key en lugar de nombre
    return get_or_create_system_category(
        session=session,
        user_id=user_id,
        key=SystemCategoryKey.TRANSFER,
        default_name="Transferencia",
        type_=CategoryType.both,
    )


def create_base_categories(user_id: UUID, session: Session) -> None:
    """
    Crea/adopta las categorías base del sistema para un usuario nuevo.
    Idempotente (seguro si se llama varias veces).
    """
    get_or_create_system_category(
        session, user_id,
        key=SystemCategoryKey.INTEREST_INCOME,
        default_name="Rendimientos",
        type_=CategoryType.income,
    )
    get_or_create_system_category(
        session, user_id,
        key=SystemCategoryKey.FEES,
        default_name="Comisiones",
        type_=CategoryType.expense,
    )
    get_or_create_system_category(
        session, user_id,
        key=SystemCategoryKey.TRANSFER,
        default_name="Transferencia",
        type_=CategoryType.both,
    )
    get_or_create_system_category(
        session, user_id,
        key=SystemCategoryKey.DEBT_PAYMENT,
        default_name="Pago de Deuda",
        type_=CategoryType.expense,
    )
