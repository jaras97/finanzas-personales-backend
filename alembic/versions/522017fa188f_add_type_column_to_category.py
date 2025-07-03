"""add type column to category

Revision ID: 522017fa188f
Revises: 715d3ec21cbd
Create Date: 2025-06-30 21:33:17.671789

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '522017fa188f'
down_revision: Union[str, Sequence[str], None] = '715d3ec21cbd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'category',
        sa.Column('type', sa.String(length=20), nullable=False, server_default='expense')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('category', 'type')