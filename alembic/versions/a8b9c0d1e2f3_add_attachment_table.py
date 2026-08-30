"""add attachment table

Comprobantes adjuntos a una transacción (foto de recibo, PDF del banco).
El binario vive en Supabase Storage; acá solo queda la ruta y los metadatos.
Solo agrega una tabla nueva.

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-08-30 20:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a8b9c0d1e2f3"
down_revision: Union[str, Sequence[str], None] = "f7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "attachment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column(
            "transaction_id", sa.Integer(), sa.ForeignKey("transaction.id"), nullable=False
        ),
        sa.Column("storage_path", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_attachment_user_id", "attachment", ["user_id"])
    op.create_index("ix_attachment_transaction_id", "attachment", ["transaction_id"])
    op.execute('ALTER TABLE IF EXISTS "attachment" ENABLE ROW LEVEL SECURITY;')


def downgrade() -> None:
    op.drop_index("ix_attachment_transaction_id", table_name="attachment")
    op.drop_index("ix_attachment_user_id", table_name="attachment")
    op.drop_table("attachment")
