"""add kind field to debt

Revision ID: 410f7c2d899f
Revises: d9bac7ffa2f7
Create Date: 2025-07-03 13:28:23.684720

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '410f7c2d899f'
down_revision: Union[str, Sequence[str], None] = 'd9bac7ffa2f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column('debt', sa.Column('kind', sa.String(), nullable=True))

    # establecer valor por defecto 'loan' a registros existentes
    op.execute("UPDATE debt SET kind = 'loan' WHERE kind IS NULL;")

    # ahora establecer non-nullable
    op.alter_column('debt', 'kind', nullable=False)

def downgrade():
    op.drop_column('debt', 'kind')