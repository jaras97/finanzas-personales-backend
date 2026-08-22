"""add recurring_transaction table

Plantillas de movimientos que se repiten (nómina, arriendo, suscripciones).
Solo agrega una tabla nueva: no toca ni migra ninguna fila existente.

Revision ID: d7e4b2c9a015
Revises: c4a2f9e6d1b3
Create Date: 2026-08-22 13:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d7e4b2c9a015"
down_revision: Union[str, Sequence[str], None] = "c4a2f9e6d1b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "recurring_transaction",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        # El tipo reutiliza el enum existente transactiontype (income/expense/
        # transfer). create_type=False: el tipo ya existe en la base, no hay
        # que volver a crearlo.
        sa.Column(
            "type",
            postgresql.ENUM(
                "income", "expense", "transfer", name="transactiontype", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("category.id"), nullable=False),
        sa.Column(
            "saving_account_id",
            sa.Integer(),
            sa.ForeignKey("saving_account.id"),
            nullable=False,
        ),
        sa.Column("frequency", sa.String(length=20), nullable=False),
        sa.Column("next_run", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_recurring_transaction_user_id", "recurring_transaction", ["user_id"]
    )
    op.create_index(
        "ix_recurring_transaction_next_run", "recurring_transaction", ["next_run"]
    )


def downgrade() -> None:
    op.drop_index("ix_recurring_transaction_next_run", table_name="recurring_transaction")
    op.drop_index("ix_recurring_transaction_user_id", table_name="recurring_transaction")
    op.drop_table("recurring_transaction")
