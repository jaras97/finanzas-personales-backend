from logging.config import fileConfig
import os

from sqlalchemy import engine_from_config, pool
from alembic import context
from sqlmodel import SQLModel

# Alembic Config
config = context.config

# ✅ Cargar DATABASE_URL de variables de entorno de forma segura
database_url = os.environ.get("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)

# Configuración de logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Importa tus modelos para autogenerate

from app.models import *  # importa todos tus modelos

target_metadata = SQLModel.metadata

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True  # detecta cambios en tipos de columnas
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()