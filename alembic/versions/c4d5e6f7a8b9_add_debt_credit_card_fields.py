"""add credit card cycle fields to debt

Cupo, día de corte, días para pagar y % de pago mínimo -- solo aplican a
deudas kind=credit_card, quedan NULL en préstamos (Fase 7 del roadmap, ver
docs/PENDIENTES.md). No toca ninguna fila existente.

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-08-30 16:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, Sequence[str], None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("debt", sa.Column("credit_limit", sa.Float(), nullable=True))
    op.add_column("debt", sa.Column("statement_day", sa.Integer(), nullable=True))
    op.add_column("debt", sa.Column("payment_due_days", sa.Integer(), nullable=True))
    op.add_column("debt", sa.Column("minimum_payment_percent", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("debt", "minimum_payment_percent")
    op.drop_column("debt", "payment_due_days")
    op.drop_column("debt", "statement_day")
    op.drop_column("debt", "credit_limit")
