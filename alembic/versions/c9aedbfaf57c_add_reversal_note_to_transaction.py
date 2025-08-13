"""add reversal_note to transaction

Revision ID: c9aedbfaf57c
Revises: 015cdbdf4d58
Create Date: 2025-08-12 14:49:34.847918

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9aedbfaf57c'
down_revision: Union[str, Sequence[str], None] = '4a460b07ba42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Postgres-safe: idempotente
    op.execute('ALTER TABLE "transaction" ADD COLUMN IF NOT EXISTS reversal_note VARCHAR(500);')

def downgrade():
    op.execute('ALTER TABLE "transaction" DROP COLUMN IF EXISTS reversal_note;')
