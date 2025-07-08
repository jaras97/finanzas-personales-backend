"""add transfer_group_id to transactions

Revision ID: 80e3a1fc69bf
Revises: 7f229505a8ec
Create Date: 2025-07-07 23:42:48.111702

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '80e3a1fc69bf'
down_revision: Union[str, Sequence[str], None] = '7f229505a8ec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column('transaction', sa.Column('transfer_group_id', sa.String(length=36), nullable=True))


def downgrade():
    op.drop_column('transaction', 'transfer_group_id')