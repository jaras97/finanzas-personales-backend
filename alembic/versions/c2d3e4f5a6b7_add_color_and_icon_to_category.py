"""add color and icon to category

Dos columnas nullable para que cada categoría pueda tener identidad visual
propia, siguiendo la recomendación 3 del PDF de taxonomía
(`docs/Categorias_Finanzas_Egresos_e_Ingresos.pdf`).

Arregla además un defecto existente: los colores de los gráficos se asignaban
por POSICIÓN (`TOKEN_COLORS[i % n]` en DonutByCategory), así que una categoría
cambiaba de color de un mes a otro según su ranking de gasto, y comparar dos
períodos de un vistazo engañaba.

Deliberadamente NO rellena nada. Las filas existentes quedan con `NULL`, y el
frontend deriva su color de un hash estable del nombre: eso corrige el color
saltarín para TODAS las categorías -- también las creadas antes de esta
migración -- sin tocar una sola fila ni obligar a nadie a elegir colores.

`color` guarda una clave de paleta ("sky", "emerald"...), no un hex: un hex
fijo no puede verse bien en tema claro y oscuro a la vez.

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-09-04 09:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("category", sa.Column("color", sa.String(length=20), nullable=True))
    op.add_column("category", sa.Column("icon", sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column("category", "icon")
    op.drop_column("category", "color")
