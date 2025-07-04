from sqlmodel import SQLModel, Session, create_engine
import os
from dotenv import load_dotenv

load_dotenv()  # Carga las variables de entorno

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL, echo=True)  # echo=True imprime las queries

def create_db_and_tables():
    from app.models.user import User  # importar los modelos
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session