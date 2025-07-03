"""Ensure FKs for debt and accounts in transaction

Revision ID: 918c81e36060
Revises: 31a11ec11cba
Create Date: 2025-07-02 17:46:58.341015

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '918c81e36060'
down_revision: Union[str, Sequence[str], None] = '31a11ec11cba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add missing foreign keys safely without duplicating."""
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_transaction_debt_id'
            ) THEN
                ALTER TABLE transaction
                ADD CONSTRAINT fk_transaction_debt_id FOREIGN KEY (debt_id)
                REFERENCES debt (id) ON DELETE SET NULL;
            END IF;
        END
        $$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_transaction_saving_account_id'
            ) THEN
                ALTER TABLE transaction
                ADD CONSTRAINT fk_transaction_saving_account_id FOREIGN KEY (saving_account_id)
                REFERENCES saving_account (id) ON DELETE SET NULL;
            END IF;
        END
        $$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_transaction_from_account_id'
            ) THEN
                ALTER TABLE transaction
                ADD CONSTRAINT fk_transaction_from_account_id FOREIGN KEY (from_account_id)
                REFERENCES saving_account (id) ON DELETE SET NULL;
            END IF;
        END
        $$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_transaction_to_account_id'
            ) THEN
                ALTER TABLE transaction
                ADD CONSTRAINT fk_transaction_to_account_id FOREIGN KEY (to_account_id)
                REFERENCES saving_account (id) ON DELETE SET NULL;
            END IF;
        END
        $$;
    """)


def downgrade() -> None:
    """Remove added foreign keys if exist."""
    op.execute("ALTER TABLE transaction DROP CONSTRAINT IF EXISTS fk_transaction_to_account_id;")
    op.execute("ALTER TABLE transaction DROP CONSTRAINT IF EXISTS fk_transaction_from_account_id;")
    op.execute("ALTER TABLE transaction DROP CONSTRAINT IF EXISTS fk_transaction_saving_account_id;")
    op.execute("ALTER TABLE transaction DROP CONSTRAINT IF EXISTS fk_transaction_debt_id;")