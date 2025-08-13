"""add category system

Revision ID: a1489a79a521
Revises: c9aedbfaf57c
Create Date: 2025-08-12 16:45:11.389275

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1489a79a521'
down_revision: Union[str, Sequence[str], None] = 'c9aedbfaf57c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column("category", sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("category", sa.Column("system_key", sa.String(length=64), nullable=True))
    op.create_index("ix_category_is_system", "category", ["is_system"])
    op.create_index("ix_category_system_key", "category", ["system_key"])
    op.create_unique_constraint("uq_category_user_system_key", "category", ["user_id", "system_key"])
    # quita server_default si quieres
    op.alter_column("category", "is_system", server_default=None)

def downgrade():
    op.drop_constraint("uq_category_user_system_key", "category", type_="unique")
    op.drop_index("ix_category_system_key", table_name="category")
    op.drop_index("ix_category_is_system", table_name="category")
    op.drop_column("category", "system_key")
    op.drop_column("category", "is_system")