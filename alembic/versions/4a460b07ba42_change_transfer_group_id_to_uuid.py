"""Change transfer_group_id to UUID

Revision ID: 4a460b07ba42
Revises: 80e3a1fc69bf
Create Date: 2025-07-07 23:48:59.359042

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '4a460b07ba42'
down_revision: Union[str, Sequence[str], None] = '80e3a1fc69bf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.alter_column(
        'transaction',
        'transfer_group_id',
        type_=postgresql.UUID(),
        postgresql_using="transfer_group_id::uuid"
    )

def downgrade():
    op.alter_column(
        'transaction',
        'transfer_group_id',
        type_=sa.String(),
        postgresql_using="transfer_group_id::text"
    )