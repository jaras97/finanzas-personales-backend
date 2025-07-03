# app/api/categories.py

from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select, func
from app.database import engine
from app.models.category import Category, CategoryType
from app.models.transaction import Transaction
from app.schemas.category import CategoryCreate, CategoryRead
from app.core.security import get_current_user

router = APIRouter(prefix="/categories", tags=["categories"])


@router.post("/", response_model=CategoryRead)
def create_category(
    category_data: CategoryCreate,
    user_id: UUID = Depends(get_current_user)
):
    with Session(engine) as session:
        exists = session.exec(
            select(Category).where(
                Category.name == category_data.name,
                Category.user_id == user_id,
                Category.is_active == True
            )
        ).first()
        if exists:
            raise HTTPException(status_code=400, detail="Categoría ya existe")
        category = Category(**category_data.dict(), user_id=user_id)
        session.add(category)
        session.commit()
        session.refresh(category)
        return category


@router.get("/", response_model=list[CategoryRead])
def list_categories(
    user_id: UUID = Depends(get_current_user),
    type: Optional[CategoryType] = Query(None),
    status: Optional[str] = Query("active"),  # "active", "inactive", "all"
):
    with Session(engine) as session:
        query = select(Category).where(Category.user_id == user_id)
        if type:
            query = query.where(
                (Category.type == type) | (Category.type == CategoryType.both)
            )
        if status == "active":
            query = query.where(Category.is_active == True)
        elif status == "inactive":
            query = query.where(Category.is_active == False)
        # if "all", no filtro adicional

        categories = session.exec(query).all()
        return categories


@router.put("/{category_id}", response_model=CategoryRead)
def update_category(
    category_id: int,
    category_data: CategoryCreate,
    user_id: UUID = Depends(get_current_user)
):
    with Session(engine) as session:
        category = session.exec(
            select(Category).where(
                Category.id == category_id,
                Category.user_id == user_id
            )
        ).first()

        if not category:
            raise HTTPException(status_code=404, detail="Categoría no encontrada")

        # 🚩 Si quiere cambiar el tipo, verificar si tiene transacciones
        if category.type != category_data.type:
            has_transactions = session.exec(
                select(Transaction).where(
                    Transaction.category_id == category.id,
                    Transaction.user_id == user_id
                )
            ).first()
            if has_transactions:
                raise HTTPException(
                    status_code=400,
                    detail="No puedes cambiar el tipo de esta categoría porque tiene transacciones asociadas."
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
    user_id: UUID = Depends(get_current_user)
):
    with Session(engine) as session:
        category = session.exec(
            select(Category).where(
                Category.id == category_id,
                Category.user_id == user_id,
                Category.is_active == True
            )
        ).first()

        if not category:
            raise HTTPException(status_code=404, detail="Categoría no encontrada")

        # 🚩 Validar que no existan transacciones asociadas
        tx_count = session.exec(
            select(func.count(Transaction.id))
            .where(Transaction.category_id == category_id)
        ).first()

        if tx_count > 0:
            raise HTTPException(
                status_code=400,
                detail="No puedes eliminar una categoría con transacciones asociadas. Puedes desactivarla si deseas ocultarla."
            )

        # Eliminar o desactivar según prefieras:
        # Opción 1: Soft delete
        category.is_active = False
        session.add(category)
        session.commit()
        return {"message": "Categoría desactivada correctamente"}

        # Opción 2: Hard delete si no hay transacciones
        # session.delete(category)
        # session.commit()
        # return {"message": "Categoría eliminada correctamente"}


@router.put("/{category_id}/reactivate", response_model=CategoryRead)
def reactivate_category(
    category_id: int,
    user_id: UUID = Depends(get_current_user)
):
    with Session(engine) as session:
        category = session.exec(
            select(Category).where(
                Category.id == category_id,
                Category.user_id == user_id,
                Category.is_active == False
            )
        ).first()

        if not category:
            raise HTTPException(status_code=404, detail="Categoría no encontrada o ya activa")

        category.is_active = True
        session.add(category)
        session.commit()
        session.refresh(category)
        return category