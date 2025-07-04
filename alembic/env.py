import sys
import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
from sqlmodel import SQLModel
from app.models import *  # importa tus modelos aquí

# ✅ Agregar load_dotenv
from dotenv import load_dotenv
load_dotenv()

# ✅ Agregar DATABASE_URL
DATABASE_URL = os.getenv("DATABASE_URL")

# Configuración Alembic
config = context.config
fileConfig(config.config_file_name)

# ✅ Inyectar DATABASE_URL dinámicamente en la config
if DATABASE_URL:
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
else:
    raise Exception("DATABASE_URL no está definida. Verifica tu .env")

# Aquí le pasamos los metadatos
target_metadata = SQLModel.metadata

def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()