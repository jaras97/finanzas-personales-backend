"""add budget table

Metas de gasto mensual por categoría y moneda (ver docs/PENDIENTES.md /
docs/DATA_MODEL.md). Solo agrega una tabla nueva, no toca ninguna fila
existente.

De paso, habilita RLS en `currency` y `recurring_transaction`: la migración
f3d9c1a7b8e2 la activó en las 11 tablas que existían en ese momento, pero
estas dos se crearon después (c4a2f9e6d1b3, d7e4b2c9a015) y quedaron fuera
-- el mismo hueco de PostgREST que esa migración cerró para el resto.

Revision ID: e8f1a2b4c6d3
Revises: d7e4b2c9a015
Create Date: 2026-08-30 12:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e8f1a2b4c6d3"
down_revision: Union[str, Sequence[str], None] = "d7e4b2c9a015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RLS_CATCHUP_TABLES = ["currency", "recurring_transaction"]


def upgrade() -> None:
    op.create_table(
        "budget",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("category.id"), nullable=False),
        sa.Column("currency", sa.String(length=3), sa.ForeignKey("currency.code"), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "user_id", "category_id", "currency", "effective_from",
            name="uq_budget_user_category_currency_month",
        ),
    )
    op.create_index("ix_budget_user_id", "budget", ["user_id"])
    op.create_index("ix_budget_category_id", "budget", ["category_id"])
    op.create_index("ix_budget_effective_from", "budget", ["effective_from"])

    op.execute('ALTER TABLE IF EXISTS "budget" ENABLE ROW LEVEL SECURITY;')
    for table in _RLS_CATCHUP_TABLES:
        op.execute(f'ALTER TABLE IF EXISTS "{table}" ENABLE ROW LEVEL SECURITY;')


def downgrade() -> None:
    for table in _RLS_CATCHUP_TABLES:
        op.execute(f'ALTER TABLE IF EXISTS "{table}" DISABLE ROW LEVEL SECURITY;')

    op.drop_index("ix_budget_effective_from", table_name="budget")
    op.drop_index("ix_budget_category_id", table_name="budget")
    op.drop_index("ix_budget_user_id", table_name="budget")
    op.drop_table("budget")
