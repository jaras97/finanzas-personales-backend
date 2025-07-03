"""add source_type to transactions

Revision ID: d9bac7ffa2f7
Revises: 918c81e36060
Create Date: 2025-07-02 23:12:46.788077

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd9bac7ffa2f7'
down_revision: Union[str, Sequence[str], None] = '918c81e36060'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    pass

def downgrade():
   pass