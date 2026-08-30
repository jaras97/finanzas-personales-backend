"""add user.report_currency

Moneda de referencia para el patrimonio neto consolidado (Fase 6 del
roadmap, ver docs/PENDIENTES.md). Todos los usuarios existentes quedan en
"COP" vía `server_default` -- ninguno pierde acceso a la función, solo
empieza con el default más común en la base de usuarios actual.

Revision ID: b3c4d5e6f7a8
Revises: a7b8c9d0e1f2
Create Date: 2026-08-30 15:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column(
            "report_currency",
            sa.String(length=3),
            sa.ForeignKey("currency.code"),
            nullable=False,
            server_default="COP",
        ),
    )


def downgrade() -> None:
    op.drop_column("user", "report_currency")
