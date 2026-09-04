"""add parent_id to category (subcategorías)

Segundo nivel de categorías, siguiendo la recomendación 1 del PDF de taxonomía
("Categoría Padre > Subcategoría, para no saturar al usuario").

Nullable y sin backfill: todas las categorías existentes quedan como de primer
nivel, que es exactamente lo que son. Nadie tiene que reorganizar nada, y una
app que nunca use subcategorías se comporta igual que antes.

La profundidad máxima (2 niveles) NO se impone con una constraint de base:
requeriría un trigger o un CHECK con subconsulta. Se valida en
`api/categories.py`, que es el único camino por el que se crean categorías.

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-09-04 10:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, Sequence[str], None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("category", sa.Column("parent_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_category_parent_id", "category", "category", ["parent_id"], ["id"]
    )
    op.create_index("ix_category_parent_id", "category", ["parent_id"])


def downgrade() -> None:
    op.drop_index("ix_category_parent_id", table_name="category")
    op.drop_constraint("fk_category_parent_id", "category", type_="foreignkey")
    op.drop_column("category", "parent_id")
