from sqlmodel import Session
from app.database import engine
from sqlalchemy import text

with Session(engine) as session:
    session.execute(text("DROP SCHEMA public CASCADE"))
    session.execute(text("CREATE SCHEMA public"))
    session.commit()

print("✅ Base de datos reseteada correctamente (todas las tablas eliminadas).")