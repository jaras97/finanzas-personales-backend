"""add saving_goal table

Meta de ahorro atada 1:1 a una SavingAccount (Fase 8 del roadmap, ver
docs/PENDIENTES.md). Índice único parcial: a lo sumo una meta ACTIVA por
cuenta a la vez -- metas viejas inactivas no cuentan, así que reemplazar
una meta abandonada por una nueva en la misma cuenta no queda bloqueado.
Solo agrega una tabla nueva, no toca ninguna fila existente.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-08-30 17:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, Sequence[str], None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "saving_goal",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column(
            "saving_account_id",
            sa.Integer(),
            sa.ForeignKey("saving_account.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("target_amount", sa.Float(), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_saving_goal_user_id", "saving_goal", ["user_id"])
    op.create_index("ix_saving_goal_saving_account_id", "saving_goal", ["saving_account_id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_saving_goal_active_account "
        "ON saving_goal (saving_account_id) WHERE is_active = true;"
    )
    op.execute('ALTER TABLE IF EXISTS "saving_goal" ENABLE ROW LEVEL SECURITY;')


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_saving_goal_active_account;")
    op.drop_index("ix_saving_goal_saving_account_id", table_name="saving_goal")
    op.drop_index("ix_saving_goal_user_id", table_name="saving_goal")
    op.drop_table("saving_goal")
