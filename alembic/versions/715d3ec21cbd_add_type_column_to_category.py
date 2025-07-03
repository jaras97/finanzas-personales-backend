"""add type column to category

Revision ID: 715d3ec21cbd
Revises: 8101ad4ae469
Create Date: 2025-06-30 21:30:58.297490

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '715d3ec21cbd'
down_revision: Union[str, Sequence[str], None] = '8101ad4ae469'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
