from sqlmodel import Session, select
from app.database import engine
from app.models.user import User
from app.models.category import Category

BASE_CATEGORIES = [
    {"name": "Rendimientos", "type": "income"},
    {"name": "Comisiones", "type": "expense"},
    {"name": "Transferencia", "type": "both"},
    {"name": "Pago de Deuda", "type": "expense"},
]

def backfill_categories():
    with Session(engine) as session:
        users = session.exec(select(User)).all()
        for user in users:
            for cat in BASE_CATEGORIES:
                existing = session.exec(
                    select(Category).where(Category.user_id == user.id, Category.name == cat["name"])
                ).first()
                if not existing:
                    new_cat = Category(
                        name=cat["name"],
                        type=cat["type"],
                        user_id=user.id,
                    )
                    session.add(new_cat)
                    print(f"✅ Creada categoría {cat['name']} para usuario {user.email}")
        session.commit()
    print("🎉 Backfill completado.")

if __name__ == "__main__":
    backfill_categories()