from sqlmodel import Session
from app.database import engine
from sqlalchemy import text

with Session(engine) as session:
    session.execute(text("DROP TABLE IF EXISTS savingaccount CASCADE"))
    session.commit()

print("Tabla 'savingaccount' eliminada correctamente con CASCADE.")