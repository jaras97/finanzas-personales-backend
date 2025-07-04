"""add role to user

Revision ID: 7f229505a8ec
Revises: 3afd63564b8d
Create Date: 2025-07-04 00:16:33.343898

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7f229505a8ec'
down_revision: Union[str, Sequence[str], None] = '3afd63564b8d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('user', sa.Column('role', sa.String(), nullable=False, server_default='user'))

def downgrade() -> None:
    op.drop_column('user', 'role')
