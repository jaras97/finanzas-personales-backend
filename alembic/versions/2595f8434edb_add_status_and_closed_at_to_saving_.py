"""Add status and closed_at to saving_account

Revision ID: 2595f8434edb
Revises: b751db437c66
Create Date: 2025-07-01 20:14:18.276025

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '2595f8434edb'
down_revision: Union[str, Sequence[str], None] = 'b751db437c66'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('saving_account', sa.Column('status', sa.String(), nullable=True))
    op.add_column('saving_account', sa.Column('closed_at', sa.DateTime(), nullable=True))

def downgrade() -> None:
    op.drop_column('saving_account', 'closed_at')
    op.drop_column('saving_account', 'status')