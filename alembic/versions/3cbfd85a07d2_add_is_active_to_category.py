"""Add is_active to Category

Revision ID: 3cbfd85a07d2
Revises: 857815e4b162
Create Date: 2025-07-02 13:15:07.236060

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3cbfd85a07d2'
down_revision: Union[str, Sequence[str], None] = '857815e4b162'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column('category', sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'))

def downgrade():
    op.drop_column('category', 'is_active')
