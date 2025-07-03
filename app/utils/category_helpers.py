from uuid import UUID
from sqlmodel import Session, select
from app.models.category import Category


def get_or_create_transfer_category(session: Session, user_id: UUID) -> Category:
    category = session.exec(
        select(Category).where(
            Category.user_id == user_id,
            Category.name == "Transferencia"
        )
    ).first()

    if not category:
        category = Category(
            user_id=user_id,
            name="Transferencia",
            icon="🔁",
            color="#888"
        )
        session.add(category)
        session.commit()
        session.refresh(category)
    
    return category


def create_base_categories(user_id: UUID, session: Session):
    base_categories = [
        {"name": "Rendimientos", "type": "income"},
        {"name": "Comisiones", "type": "expense"},
        {"name": "Transferencia", "type": "both"},
        {"name": "Pago de Deuda", "type": "expense"},
    ]
    for cat in base_categories:
        existing = session.exec(
            select(Category).where(Category.user_id == user_id, Category.name == cat["name"])
        ).first()
        if not existing:
            session.add(Category(name=cat["name"], type=cat["type"], user_id=user_id))