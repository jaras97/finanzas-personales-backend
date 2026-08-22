"""enable row level security on all public tables

Supabase's PostgREST API is always reachable at the project URL regardless of
whether the app uses the Supabase SDK. Without RLS, anyone holding the
project's anon/service key can read, edit, or delete every row via that API,
bypassing this backend entirely. The backend itself connects as the table
owner (DATABASE_URL), so owners are exempt from RLS by default and this
migration does not change any application behavior -- it only removes
PostgREST's (anon/authenticated role) implicit access, which is exactly the
"Row-Level Security is not enabled" warning Supabase's dashboard reports for
every one of these tables.

Revision ID: f3d9c1a7b8e2
Revises: a1489a79a521
Create Date: 2026-08-22 00:00:00
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3d9c1a7b8e2"
down_revision: Union[str, Sequence[str], None] = "a1489a79a521"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = [
    "user",
    "category",
    "saving_account",
    "debt",
    "debt_transaction",
    "transaction",
    "subscription",
    "account",
    "investment",
    "monthlysummary",
    "alembic_version",
]


def upgrade() -> None:
    for table in TABLES:
        op.execute(f'ALTER TABLE IF EXISTS "{table}" ENABLE ROW LEVEL SECURITY;')


def downgrade() -> None:
    for table in TABLES:
        op.execute(f'ALTER TABLE IF EXISTS "{table}" DISABLE ROW LEVEL SECURITY;')
