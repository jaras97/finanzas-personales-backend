"""add is_cancelled and reversed_transaction_id to transaction

Revision ID: b751db437c66
Revises: c4c25a529b09
Create Date: 2025-07-01 19:56:06.625075

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b751db437c66'
down_revision: Union[str, Sequence[str], None] = 'c4c25a529b09'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('transaction', sa.Column('is_cancelled', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('transaction', sa.Column('reversed_transaction_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_transaction_reversed_transaction_id',
        'transaction',
        'transaction',
        ['reversed_transaction_id'],
        ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    op.drop_constraint('fk_transaction_reversed_transaction_id', 'transaction', type_='foreignkey')
    op.drop_column('transaction', 'reversed_transaction_id')
    op.drop_column('transaction', 'is_cancelled')
