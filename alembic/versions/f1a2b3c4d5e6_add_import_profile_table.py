"""add import_profile table

Recuerda el mapeo de columnas de un CSV por cuenta, para no volver a
pedirlo en cada importación de la misma cuenta (Fase 4 del roadmap de
presupuestos/features, ver docs/PENDIENTES.md). Solo agrega una tabla
nueva, no toca ninguna fila existente.

Revision ID: f1a2b3c4d5e6
Revises: e8f1a2b4c6d3
Create Date: 2026-08-30 13:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "e8f1a2b4c6d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "import_profile",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column(
            "saving_account_id",
            sa.Integer(),
            sa.ForeignKey("saving_account.id"),
            nullable=False,
        ),
        sa.Column("column_mapping", sa.JSON(), nullable=False),
        sa.Column("date_format", sa.String(), nullable=False),
        sa.Column("has_header", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "user_id", "saving_account_id", name="uq_import_profile_user_account"
        ),
    )
    op.create_index("ix_import_profile_user_id", "import_profile", ["user_id"])
    op.create_index(
        "ix_import_profile_saving_account_id", "import_profile", ["saving_account_id"]
    )
    op.execute('ALTER TABLE IF EXISTS "import_profile" ENABLE ROW LEVEL SECURITY;')


def downgrade() -> None:
    op.drop_index("ix_import_profile_saving_account_id", table_name="import_profile")
    op.drop_index("ix_import_profile_user_id", table_name="import_profile")
    op.drop_table("import_profile")
