"""add transaction_fee to transaction and currency to saving_account

Revision ID: c4c25a529b09
Revises: 522017fa188f
Create Date: 2025-07-01 19:23:15.710782

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4c25a529b09'
down_revision: Union[str, Sequence[str], None] = '522017fa188f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column('saving_account', sa.Column('status', sa.String(), nullable=True))
    op.add_column('saving_account', sa.Column('closed_at', sa.DateTime(), nullable=True))

def downgrade():
    op.drop_column('saving_account', 'closed_at')
    op.drop_column('saving_account', 'status')