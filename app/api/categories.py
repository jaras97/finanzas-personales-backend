# app/api/categories.py

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select, func

from app.database import engine
from app.models.category import Category, CategoryType
from app.models.transaction import Transaction
from app.schemas.category import CategoryCreate, CategoryRead, SuggestedCategoriesResult
from app.utils.category_helpers import sembrar_categorias_sugeridas
from app.utils.default_categories import DEFAULT_CATEGORIES
from app.core.security import get_current_user_with_subscription_check

def _validar_padre(
    session: Session,
    user_id: UUID,
    parent_id: Optional[int],
    tipo: CategoryType,
    *,
    hija_id: Optional[int] = None,
) -> Optional[Category]:
    """Comprueba que `parent_id` sea un padre válido y lo devuelve.

    Las cuatro reglas, y por qué cada una:

    - **Existe y es del usuario.** Sin esto, un id ajeno colgaría una categoría
      del árbol de otra persona.
    - **El padre no puede ser ya una subcategoría.** La jerarquía es de dos
      niveles a propósito (recomendación del PDF); permitir tres convertiría
      cada reporte en un recorrido de árbol.
    - **Mismo tipo.** Una subcategoría de egreso dentro de un padre de ingreso
      haría que los totales del padre mezclaran signos.
    - **No puede ser ella misma, ni una de sus propias hijas.** Es lo que
      evita un ciclo, que colgaría cualquier consulta recursiva.
    """
    if parent_id is None:
        return None

    padre = session.exec(
        select(Category).where(Category.id == parent_id, Category.user_id == user_id)
    ).first()
    if not padre:
        raise HTTPException(status_code=404, detail="La categoría padre no existe.")

    if hija_id is not None and padre.id == hija_id:
        raise HTTPException(
            status_code=400, detail="Una categoría no puede ser su propia subcategoría."
        )

    if padre.parent_id is not None:
        raise HTTPException(
            status_code=400,
            detail=f"«{padre.name}» ya es una subcategoría. Solo se admiten dos niveles.",
        )

    if hija_id is not None:
        tiene_hijas = session.exec(
            select(Category).where(Category.parent_id == hija_id)
        ).first()
        if tiene_hijas:
            raise HTTPException(
                status_code=400,
                detail="Esta categoría tiene subcategorías: no puede convertirse en una.",
            )

    # `both` (Transferencia y similares) convive con cualquiera; el resto debe
    # coincidir para que los totales del padre no mezclen ingresos con egresos.
    if CategoryType.both not in (padre.type, tipo) and padre.type != tipo:
        raise HTTPException(
            status_code=400,
            detail=f"«{padre.name}» es de tipo {padre.type.value} y esta categoría es de tipo {tipo.value}.",
        )

    return padre


def _con_padre(session: Session, categoria: Category) -> dict:
    """Serializa una categoría añadiendo el nombre del padre."""
    datos = CategoryRead.model_validate(categoria).model_dump()
    if categoria.parent_id:
        padre = session.get(Category, categoria.parent_id)
        datos["parent_name"] = padre.name if padre else None
    return datos



router = APIRouter(prefix="/categories", tags=["categories"])

@router.post("", response_model=CategoryRead)
@router.post("/", response_model=CategoryRead)
def create_category(
    category_data: CategoryCreate,
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    """
    Crea categorías del usuario. Las categorías creadas por el usuario
    nunca son de sistema (is_system=False, system_key=None).
    """
    with Session(engine) as session:
        _validar_padre(session, user_id, category_data.parent_id, category_data.type)

        # La unicidad es POR PADRE, no global: el sentido de la jerarquía es
        # que "Transporte › Gasolina" y "Viajes › Gasolina" puedan convivir.
        exists = session.exec(
            select(Category).where(
                Category.name == category_data.name,
                Category.user_id == user_id,
                Category.is_active == True,
                Category.parent_id.is_(None)
                if category_data.parent_id is None
                else Category.parent_id == category_data.parent_id,
            )
        ).first()
        if exists:
            raise HTTPException(
                status_code=400,
                detail="Ya existe una categoría con ese nombre en ese nivel.",
            )

        category = Category(
            **category_data.model_dump(),
            user_id=user_id,
            is_system=False,   # 👈 garantizamos que no sea de sistema
            system_key=None,   # 👈 sin clave de sistema
        )
        session.add(category)
        session.commit()
        session.refresh(category)
        return _con_padre(session, category)

@router.get("", response_model=list[CategoryRead])
@router.get("/", response_model=list[CategoryRead])
def list_categories(
    user_id: UUID = Depends(get_current_user_with_subscription_check),
    type: Optional[CategoryType] = Query(None),
    status: Optional[str] = Query("active"),  # "active", "inactive", "all"
):
    """
    Lista categorías del usuario, con filtros por tipo y estado.
    """
    with Session(engine) as session:
        query = select(Category).where(Category.user_id == user_id)

        if type:
            query = query.where((Category.type == type) | (Category.type == CategoryType.both))

        if status == "active":
            query = query.where(Category.is_active == True)
        elif status == "inactive":
            query = query.where(Category.is_active == False)
        # if "all": sin filtro extra

        categories = session.exec(query).all()

        # Nombre del padre resuelto en UNA consulta, no una por fila: la lista
        # se pide en cada formulario que tenga selector de categoría.
        nombres = {
            c.id: c.name
            for c in session.exec(
                select(Category).where(Category.user_id == user_id)
            ).all()
        }
        salida = []
        for c in categories:
            datos = CategoryRead.model_validate(c).model_dump()
            datos["parent_name"] = nombres.get(c.parent_id) if c.parent_id else None
            salida.append(datos)

        # Padres antes que hijas, y cada hija junto a su padre: así cualquier
        # selector que solo itere la lista ya sale agrupado sin ordenar nada.
        salida.sort(key=lambda d: (d["parent_name"] or d["name"], d["parent_id"] is not None, d["name"]))
        return salida


@router.put("/{category_id}", response_model=CategoryRead)
def update_category(
    category_id: int,
    category_data: CategoryCreate,
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    """
    Actualiza nombre/tipo de una categoría.
    - Si es de sistema: solo permite renombrar (bloquea cambio de tipo).
    - Si no es de sistema: permite cambiar nombre y tipo, pero no si ya tiene transacciones (para tipo).
    """
    with Session(engine) as session:
        category = session.exec(
            select(Category).where(Category.id == category_id, Category.user_id == user_id)
        ).first()

        if not category:
            raise HTTPException(status_code=404, detail="Categoría no encontrada")

        if category.is_system:
            # 🚫 No permitir cambiar el tipo de categorías del sistema
            if category_data.type != category.type:
                raise HTTPException(
                    status_code=400,
                    detail="No puedes cambiar el tipo de una categoría del sistema.",
                )
            # ✔️ Permitir renombrar
            category.name = category_data.name
        else:
            # Si quiere cambiar el tipo y ya tiene transacciones, bloquear
            if category.type != category_data.type:
                has_transactions = session.exec(
                    select(Transaction).where(
                        Transaction.category_id == category.id,
                        Transaction.user_id == user_id,
                    )
                ).first()
                if has_transactions:
                    raise HTTPException(
                        status_code=400,
                        detail="No puedes cambiar el tipo de esta categoría porque tiene transacciones asociadas.",
                    )
            category.name = category_data.name
            category.type = category_data.type

        # El color y el icono se pueden cambiar SIEMPRE, incluso en las de
        # sistema: son presentación, no comportamiento. Lo que se bloquea de
        # una categoría de sistema es su tipo, porque de él dependen las
        # transferencias y los pagos de deuda.
        category.color = category_data.color
        category.icon = category_data.icon

        # Mover de padre (o sacar al primer nivel). Las de sistema se quedan
        # siempre en el primer nivel: colgarlas de otra rompería los flujos que
        # las buscan por system_key.
        if not category.is_system:
            _validar_padre(
                session, user_id, category_data.parent_id, category.type,
                hija_id=category.id,
            )
            category.parent_id = category_data.parent_id

        session.add(category)
        session.commit()
        session.refresh(category)
        return _con_padre(session, category)


@router.delete("/{category_id}")
def delete_category(
    category_id: int,
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    """
    Desactiva una categoría (soft delete).
    - 🚫 No permite desactivar categorías de sistema.
    - 🚫 No permite desactivar si tiene transacciones asociadas (para evitar agujeros en reportes).
    """
    with Session(engine) as session:
        category = session.exec(
            select(Category).where(
                Category.id == category_id,
                Category.user_id == user_id,
                Category.is_active == True,
            )
        ).first()

        if not category:
            raise HTTPException(status_code=404, detail="Categoría no encontrada")

        # 🚫 Bloquear desactivación de categorías de sistema
        if category.is_system:
            raise HTTPException(
                status_code=400,
                detail="No puedes desactivar una categoría del sistema.",
            )

        # 🚫 Bloquear si tiene transacciones asociadas
        tx_count = session.exec(
            select(func.count(Transaction.id)).where(Transaction.category_id == category_id)
        ).one()
        if tx_count and tx_count > 0:
            raise HTTPException(
                status_code=400,
                detail="No puedes desactivar una categoría con transacciones asociadas.",
            )

        # Soft delete
        # Desactivar un padre dejaría a sus hijas colgando de algo invisible:
        # seguirían apareciendo en los selectores pero sin su contexto. Se
        # bloquea en vez de cascada para que la acción sea reversible.
        hijas_activas = session.exec(
            select(Category).where(
                Category.parent_id == category.id,
                Category.is_active == True,  # noqa: E712
            )
        ).all()
        if hijas_activas:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"«{category.name}» tiene {len(hijas_activas)} "
                    f"{'subcategoría activa' if len(hijas_activas) == 1 else 'subcategorías activas'}. "
                    "Desactívalas primero o muévelas a otra categoría."
                ),
            )

        category.is_active = False
        session.add(category)
        session.commit()
        return {"message": "Categoría desactivada correctamente"}


@router.put("/{category_id}/reactivate", response_model=CategoryRead)
def reactivate_category(
    category_id: int,
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    """
    Reactiva una categoría previamente desactivada.
    """
    with Session(engine) as session:
        category = session.exec(
            select(Category).where(
                Category.id == category_id,
                Category.user_id == user_id,
                Category.is_active == False,
            )
        ).first()

        if not category:
            raise HTTPException(status_code=404, detail="Categoría no encontrada o ya activa")

        category.is_active = True
        session.add(category)
        session.commit()
        session.refresh(category)
        return category


@router.post("/suggested", response_model=SuggestedCategoriesResult, status_code=201)
def add_suggested_categories(
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    """Añade las categorías de la taxonomía sugerida que al usuario le falten.

    Opt-in a propósito, y solo aditivo: no renombra, no fusiona y no desactiva
    nada. A alguien que ya curó 29 categorías propias, inyectarle 25 genéricas
    de golpe le haría daño; que lo pida quien lo quiera.

    La comparación ignora tildes y mayúsculas, porque en producción ya conviven
    "Alimentacion", "Alimentación" y "Alimentación y mercados": sin eso, esto
    crearía duplicados de lo que la persona ya tiene.

    Ofrece las 25 completas (no solo el núcleo): quien pulsa el botón está
    pidiendo explícitamente el catálogo, no un arranque mínimo.
    """
    with Session(engine) as session:
        creadas = sembrar_categorias_sugeridas(user_id, session, solo_nucleo=False)
        session.commit()
        for c in creadas:
            session.refresh(c)

        return SuggestedCategoriesResult(
            created=[CategoryRead.model_validate(c) for c in creadas],
            skipped_existing=len(DEFAULT_CATEGORIES) - len(creadas),
        )
