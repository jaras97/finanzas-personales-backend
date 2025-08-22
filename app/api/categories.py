# app/api/categories.py

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select, func

from app.database import engine
from app.models.category import Category, CategoryType
from app.models.transaction import Transaction
from app.schemas.category import CategoryCreate, CategoryRead
from app.core.security import get_current_user_with_subscription_check

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
        exists = session.exec(
            select(Category).where(
                Category.name == category_data.name,
                Category.user_id == user_id,
                Category.is_active == True,
            )
        ).first()
        if exists:
            raise HTTPException(status_code=400, detail="Categoría ya existe")

        category = Category(
            **category_data.model_dump(),
            user_id=user_id,
            is_system=False,   # 👈 garantizamos que no sea de sistema
            system_key=None,   # 👈 sin clave de sistema
        )
        session.add(category)
        session.commit()
        session.refresh(category)
        return category

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
        return categories


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

        session.add(category)
        session.commit()
        session.refresh(category)
        return category


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
