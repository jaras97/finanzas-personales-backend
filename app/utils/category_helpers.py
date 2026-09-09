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


def get_or_create_system_group(session: Session, user_id: UUID) -> Category:
    """Grupo oculto que aloja a las categorías operativas.

    Existe para que la invariante «solo las hojas reciben dinero» no necesite
    excepciones: sin él, Transferencia y Sin categorizar serían grupos de
    primer nivel y no podrían recibir los movimientos que sí reciben.

    Es de tipo `both` a propósito: dentro conviven Rendimientos (ingreso) y
    Comisiones (egreso), y un padre `both` admite hojas de cualquier tipo.
    """
    grupo = session.exec(
        select(Category).where(
            Category.user_id == user_id,
            Category.system_key == SystemCategoryKey.SYSTEM_GROUP.value,
        )
    ).first()
    if grupo:
        return grupo

    grupo = Category(
        user_id=user_id,
        name="Sistema",
        type=CategoryType.both,
        is_system=True,
        system_key=SystemCategoryKey.SYSTEM_GROUP.value,
        is_active=True,
        color="slate",
    )
    session.add(grupo)
    session.commit()
    session.refresh(grupo)
    return grupo


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
    grupo = get_or_create_system_group(session, user_id)

    if cat:
        # Datos anteriores al modelo grupo/hoja: si quedó en primer nivel, se
        # recuelga. Así una cuenta vieja converge sin migración aparte.
        if cat.parent_id is None:
            cat.parent_id = grupo.id
            session.add(cat)
            session.commit()
            session.refresh(cat)
        return cat

    # Intentar adoptar por nombre (compatibilidad con datos existentes)
    adopted = _adopt_by_name_if_exists(session, user_id, default_name, type_, key)
    if adopted:
        if adopted.parent_id is None:
            adopted.parent_id = grupo.id
            session.add(adopted)
            session.commit()
            session.refresh(adopted)
        return adopted

    # Crear nueva, ya como hoja del grupo Sistema
    cat = Category(
        user_id=user_id,
        name=default_name,
        type=type_,
        is_system=True,
        system_key=key.value,
        is_active=True,
        parent_id=grupo.id,
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


def get_or_create_uncategorized_category(session: Session, user_id: UUID) -> Category:
    """Categoría de sistema donde caen las filas de una importación de CSV
    que ninguna regla de categorización (aún no implementadas) sabe resolver.
    """
    return get_or_create_system_category(
        session=session,
        user_id=user_id,
        key=SystemCategoryKey.UNCATEGORIZED,
        default_name="Sin categorizar",
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
    get_or_create_system_category(
        session, user_id,
        key=SystemCategoryKey.UNCATEGORIZED,
        default_name="Sin categorizar",
        type_=CategoryType.both,
    )

    # Núcleo de la taxonomía sugerida (13 categorías). Sin esto el usuario
    # nuevo llega a una lista vacía y termina inventando nombres sueltos
    # ("Bedo, gastos .", "Max", nombres de banco) -- medido en producción.
    # Es idempotente: si ya las tiene, no crea nada.
    sembrar_categorias_sugeridas(user_id, session, solo_nucleo=True)


# ---------------------------------------------------------------------------
# Taxonomía sugerida (NO son categorías de sistema: el usuario las controla)
# ---------------------------------------------------------------------------

def _normalizar(nombre: str) -> str:
    """Compara nombres ignorando tildes, mayúsculas y puntuación.

    Necesario porque la gente ya escribió "Alimentacion", "Alimentación" y
    "Alimentación y mercados": sin normalizar, ofrecerle la taxonomía a un
    usuario existente le crearía duplicados de lo que ya tiene.
    """
    import re
    import unicodedata

    base = unicodedata.normalize("NFKD", nombre.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", base).strip()


def sembrar_categorias_sugeridas(
    user_id: UUID,
    session: Session,
    *,
    solo_nucleo: bool = True,
) -> list[Category]:
    """Crea las categorías de la taxonomía que al usuario le FALTAN.

    Nunca renombra, fusiona ni desactiva nada de lo que ya tenga: solo añade lo
    que no está. Por eso es seguro llamarla sobre una cuenta con años de uso.

    `solo_nucleo=True` (registro de un usuario nuevo) siembra las 13
    recomendadas; `False` (botón "Añadir sugeridas") ofrece las 25.

    No hace commit: lo hace quien llama.
    """
    from app.utils.category_rules import crear_hoja_por_defecto
    from app.utils.default_categories import CORE_CATEGORIES, DEFAULT_CATEGORIES

    candidatas = CORE_CATEGORIES if solo_nucleo else DEFAULT_CATEGORIES

    existentes = session.exec(
        select(Category).where(Category.user_id == user_id)
    ).all()
    ya_tiene = {_normalizar(c.name) for c in existentes}

    creadas: list[Category] = []
    for cand in candidatas:
        if _normalizar(cand.name) in ya_tiene:
            continue
        nueva = Category(
            name=cand.name,
            type=cand.type,
            user_id=user_id,
            color=cand.color,
            icon=cand.icon,
            # is_system=False a propósito: son sugerencias, no infraestructura.
            # El usuario puede renombrarlas, recolorearlas o desactivarlas.
        )
        session.add(nueva)
        # Nace como grupo, y un grupo sin hojas no recibe nada (I3). La hoja
        # "General" es donde caen los movimientos mientras el usuario no
        # desglose; la interfaz colapsa ese caso en una sola línea.
        session.flush()
        crear_hoja_por_defecto(session, nueva)
        creadas.append(nueva)
        # Se agrega al set para que dos candidatas que normalizan igual no se
        # dupliquen entre sí dentro de la misma llamada.
        ya_tiene.add(_normalizar(cand.name))

    return creadas
