"""add subscription table

Revision ID: 3afd63564b8d
Revises: 410f7c2d899f
Create Date: 2025-07-03 23:14:02.313663

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '3afd63564b8d'
down_revision: Union[str, Sequence[str], None] = '410f7c2d899f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Upgrade schema: create subscription table."""
    op.create_table(
        'subscription',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('user_id', postgresql.UUID(), sa.ForeignKey('user.id'), nullable=False),
        sa.Column('start_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

def downgrade() -> None:
    """Downgrade schema: drop subscription table."""
    op.drop_table('subscription')