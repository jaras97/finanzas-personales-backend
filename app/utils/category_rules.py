"""Reglas del modelo grupo/hoja.

Un solo sitio donde vive «esta categoría puede recibir dinero», porque son
cinco endpoints los que tienen que preguntarlo (transacciones, compras con
tarjeta, presupuestos, reglas de categorización y recurrentes) y basta con que
uno se olvide para que la invariante deje de valerse.

Ver docs/PLAN_CATEGORIAS_V2.md — invariantes I1, I2 e I3.
"""

from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlmodel import Session, select

from app.constants.categories import SystemCategoryKey
from app.models.category import Category

NOMBRE_HOJA_POR_DEFECTO = "General"


def es_grupo(categoria: Category) -> bool:
    """Primer nivel = grupo. No recibe dinero; solo agrupa."""
    return categoria.parent_id is None


def hojas_de(session: Session, grupo_id: int, solo_activas: bool = True) -> list[Category]:
    q = select(Category).where(Category.parent_id == grupo_id)
    if solo_activas:
        q = q.where(Category.is_active == True)  # noqa: E712
    return list(session.exec(q).all())


def exigir_hoja(
    session: Session,
    user_id: UUID,
    category_id: Optional[int],
    *,
    que: str = "Una transacción",
) -> Optional[Category]:
    """Devuelve la categoría si es una hoja utilizable; si no, lanza 400/404.

    `que` se usa para que el mensaje diga qué se estaba intentando, en vez de
    un genérico que obligue al usuario a adivinar.
    """
    if category_id is None:
        return None

    categoria = session.exec(
        select(Category).where(Category.id == category_id, Category.user_id == user_id)
    ).first()
    if not categoria:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")

    if es_grupo(categoria):
        hojas = hojas_de(session, categoria.id)
        # Con una sola hoja «General» no se la nombra: el usuario nunca la ve
        # en la interfaz (los grupos de una hoja se muestran colapsados), así
        # que sugerírsela por nombre lo mandaría a buscar algo inexistente.
        nombrables = [h.name for h in hojas if h.name != NOMBRE_HOJA_POR_DEFECTO]
        sugerencia = (
            f" Elige una de sus subcategorías: {', '.join(nombrables[:4])}."
            if nombrables else ""
        )
        raise HTTPException(
            status_code=400,
            detail=(
                f"«{categoria.name}» es un grupo y no recibe movimientos directamente. "
                f"{que} debe ir a una subcategoría.{sugerencia}"
            ),
        )

    if not categoria.is_active:
        raise HTTPException(
            status_code=400,
            detail=f"«{categoria.name}» está desactivada.",
        )

    return categoria


def crear_hoja_por_defecto(
    session: Session, grupo: Category, nombre: str = NOMBRE_HOJA_POR_DEFECTO
) -> Category:
    """Crea la hoja que hace utilizable a un grupo recién nacido (I3).

    La interfaz colapsa un grupo de una sola hoja en una línea, así que el
    usuario que solo quería «Mascotas» nunca ve este segundo nivel.
    """
    hoja = Category(
        name=nombre,
        type=grupo.type,
        user_id=grupo.user_id,
        color=grupo.color,
        parent_id=grupo.id,
        is_system=grupo.is_system,
        is_active=grupo.is_active,
    )
    session.add(hoja)
    return hoja


def tiene_referencias(session: Session, category_id: int) -> bool:
    """¿Algo apunta a esta categoría? Decide si se puede retirar sin dejar
    huecos en los reportes."""
    from app.models.budget import Budget
    from app.models.category_rule import CategoryRule
    from app.models.recurring_transaction import RecurringTransaction
    from app.models.transaction import Transaction

    for modelo in (Transaction, Budget, CategoryRule, RecurringTransaction):
        if session.exec(
            select(modelo).where(modelo.category_id == category_id).limit(1)
        ).first():
            return True
    return False


def nombre_visible(session: Session, categoria: Optional[Category]) -> str:
    """Cómo se llama una categoría de cara al usuario.

    Una hoja «General» que es la única de su grupo NO se muestra como
    «General»: se muestra con el nombre del grupo. Es la contraparte, del lado
    del servidor, del colapso visual que hace la interfaz — sin esto, quien
    creó «Streaming» y nunca lo desglosó vería «General» en la vista previa del
    CSV, en sus reglas y en sus presupuestos.

    Con varias hojas sí se distingue: «Transporte › Gasolina».
    """
    if categoria is None:
        return "(categoría eliminada)"
    if categoria.parent_id is None:
        return categoria.name

    grupo = session.get(Category, categoria.parent_id)
    if grupo is None:
        return categoria.name

    # El grupo Sistema está oculto de la interfaz: prefijar con él daría
    # "Sistema › Sin categorizar", que no le dice nada a nadie.
    if grupo.system_key == SystemCategoryKey.SYSTEM_GROUP.value:
        return categoria.name

    hermanas = hojas_de(session, grupo.id)
    if len(hermanas) <= 1:
        return grupo.name
    return f"{grupo.name} › {categoria.name}"
