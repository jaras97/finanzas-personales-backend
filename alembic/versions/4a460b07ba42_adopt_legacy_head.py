"""adopt legacy revision 4a460b07ba42 (no-op)

Revision ID: 4a460b07ba42
Revises: 015cdbdf4d58
Create Date: 2025-08-12 00:00:00
"""
from typing import Sequence, Union
from alembic import op  # noqa
import sqlalchemy as sa  # noqa

# revision identifiers, used by Alembic.
revision: str = "4a460b07ba42"
down_revision: Union[str, Sequence[str], None] = "015cdbdf4d58"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # no-op: adoptamos el estado actual de la BD
    pass

def downgrade() -> None:
    pass
