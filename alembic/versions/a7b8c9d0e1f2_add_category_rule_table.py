"""add category_rule table

Reglas de categorización automática: si la descripción de una transacción
contiene `match_text` (sin distinguir mayúsculas), se sugiere `category_id`.
Fase 5 del roadmap de presupuestos/features, ver docs/PENDIENTES.md. Solo
agrega una tabla nueva, no toca ninguna fila existente.

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
Create Date: 2026-08-30 14:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "category_rule",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("category.id"), nullable=False),
        sa.Column("match_text", sa.String(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_category_rule_user_id", "category_rule", ["user_id"])
    op.create_index("ix_category_rule_priority", "category_rule", ["priority"])
    op.execute('ALTER TABLE IF EXISTS "category_rule" ENABLE ROW LEVEL SECURITY;')


def downgrade() -> None:
    op.drop_index("ix_category_rule_priority", table_name="category_rule")
    op.drop_index("ix_category_rule_user_id", table_name="category_rule")
    op.drop_table("category_rule")
