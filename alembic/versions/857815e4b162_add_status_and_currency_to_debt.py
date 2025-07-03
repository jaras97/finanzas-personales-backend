"""Add status and currency to Debt

Revision ID: 857815e4b162
Revises: 2595f8434edb
Create Date: 2025-07-01 23:52:47.630831

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '857815e4b162'
down_revision: Union[str, Sequence[str], None] = '2595f8434edb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column('debt', sa.Column('status', sa.Enum('active', 'closed', name='debtstatus'), nullable=False, server_default='active'))
    op.add_column('debt', sa.Column('currency', sa.Enum('COP', 'USD', 'EUR', name='currency'), nullable=False, server_default='COP'))

def downgrade():
    op.drop_column('debt', 'status')
    op.drop_column('debt', 'currency')
    op.execute('DROP TYPE debtstatus')
    op.execute('DROP TYPE currency')