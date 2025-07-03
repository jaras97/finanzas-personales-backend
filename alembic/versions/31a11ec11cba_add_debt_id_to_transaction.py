"""add debt_id to transaction

Revision ID: 31a11ec11cba
Revises: 3cbfd85a07d2
Create Date: 2025-07-02 14:42:52.630761

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '31a11ec11cba'
down_revision: Union[str, Sequence[str], None] = '3cbfd85a07d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column('transaction', sa.Column('debt_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_transaction_debt_id',
        'transaction',
        'debt',
        ['debt_id'],
        ['id'],
        ondelete='SET NULL'
    )

def downgrade():
    op.drop_constraint('fk_transaction_debt_id', 'transaction', type_='foreignkey')
    op.drop_column('transaction', 'debt_id')
