"""add currency catalog, make saving_account/debt currency user-extensible

Replaces the fixed COP/USD/EUR enum with a `currency` reference table
(ISO-4217 code, name, symbol, decimal digits) plus FKs from
saving_account.currency and debt.currency. No existing row loses data:
debt.currency is converted from the Postgres enum to varchar via a plain
type cast (values stay identical text), saving_account.currency was
already varchar so it's untouched aside from the new FK.

Revision ID: c4a2f9e6d1b3
Revises: f3d9c1a7b8e2
Create Date: 2026-08-22 12:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4a2f9e6d1b3"
down_revision: Union[str, Sequence[str], None] = "f3d9c1a7b8e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SEED_CURRENCIES = [
    ("COP", "Peso colombiano", "$", 0),
    ("USD", "Dólar estadounidense", "$", 2),
    ("EUR", "Euro", "€", 2),
    ("MXN", "Peso mexicano", "$", 2),
    ("ARS", "Peso argentino", "$", 2),
    ("CLP", "Peso chileno", "$", 0),
    ("PEN", "Sol peruano", "S/", 2),
    ("BRL", "Real brasileño", "R$", 2),
    ("GBP", "Libra esterlina", "£", 2),
    ("CAD", "Dólar canadiense", "$", 2),
    ("JPY", "Yen japonés", "¥", 0),
    ("CNY", "Yuan chino", "¥", 2),
    ("CHF", "Franco suizo", "CHF", 2),
    ("AUD", "Dólar australiano", "$", 2),
    ("NZD", "Dólar neozelandés", "$", 2),
    ("INR", "Rupia india", "₹", 2),
    ("KRW", "Won surcoreano", "₩", 0),
    ("SGD", "Dólar de Singapur", "$", 2),
    ("HKD", "Dólar de Hong Kong", "$", 2),
    ("SEK", "Corona sueca", "kr", 2),
    ("NOK", "Corona noruega", "kr", 2),
    ("DKK", "Corona danesa", "kr", 2),
    ("PLN", "Zloty polaco", "zł", 2),
    ("CZK", "Corona checa", "Kč", 2),
    ("TRY", "Lira turca", "₺", 2),
    ("ZAR", "Rand sudafricano", "R", 2),
    ("AED", "Dirham de EAU", "د.إ", 2),
    ("SAR", "Riyal saudí", "﷼", 2),
    ("ILS", "Nuevo shekel israelí", "₪", 2),
    ("THB", "Baht tailandés", "฿", 2),
    ("MYR", "Ringgit malayo", "RM", 2),
    ("IDR", "Rupia indonesia", "Rp", 2),
    ("PHP", "Peso filipino", "₱", 2),
    ("VND", "Dong vietnamita", "₫", 0),
    ("UYU", "Peso uruguayo", "$", 2),
    ("BOB", "Boliviano", "Bs", 2),
    ("PYG", "Guaraní paraguayo", "₲", 0),
    ("CRC", "Colón costarricense", "₡", 2),
    ("GTQ", "Quetzal guatemalteco", "Q", 2),
    ("DOP", "Peso dominicano", "RD$", 2),
    ("PAB", "Balboa panameño", "B/.", 2),
    ("RUB", "Rublo ruso", "₽", 2),
]


def upgrade() -> None:
    # 1) debt.currency: enum -> varchar(3). Cast preserves the exact text
    #    value of every row (the enum's members already ARE their text).
    op.execute("ALTER TABLE debt ALTER COLUMN currency DROP DEFAULT")
    op.execute("ALTER TABLE debt ALTER COLUMN currency TYPE VARCHAR(3) USING currency::text")
    op.execute("ALTER TABLE debt ALTER COLUMN currency SET DEFAULT 'COP'")

    # 2) The Postgres enum type is no longer referenced by any column --
    #    drop it now, before creating the "currency" table below (a table
    #    and an enum type of the same name cannot coexist in one schema).
    op.execute("DROP TYPE IF EXISTS currency")

    # 3) Reference table
    op.create_table(
        "currency",
        sa.Column("code", sa.String(length=3), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("decimal_digits", sa.Integer(), nullable=False, server_default="2"),
    )

    currency_table = sa.table(
        "currency",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("symbol", sa.String),
        sa.column("decimal_digits", sa.Integer),
    )
    op.bulk_insert(
        currency_table,
        [
            {"code": code, "name": name, "symbol": symbol, "decimal_digits": digits}
            for code, name, symbol, digits in SEED_CURRENCIES
        ],
    )

    # 4) Any existing row using a currency outside the seed list (shouldn't
    #    happen -- the old enum only ever allowed COP/USD/EUR) would break
    #    the FK below; normalize defensively instead of failing the deploy.
    op.execute(
        "UPDATE saving_account SET currency = 'COP' WHERE currency IS NULL "
        "OR currency NOT IN (SELECT code FROM currency)"
    )
    op.execute(
        "UPDATE debt SET currency = 'COP' WHERE currency IS NULL "
        "OR currency NOT IN (SELECT code FROM currency)"
    )

    # 5) FKs
    op.create_foreign_key(
        "fk_saving_account_currency", "saving_account", "currency", ["currency"], ["code"]
    )
    op.create_foreign_key("fk_debt_currency", "debt", "currency", ["currency"], ["code"])


def downgrade() -> None:
    op.drop_constraint("fk_debt_currency", "debt", type_="foreignkey")
    op.drop_constraint("fk_saving_account_currency", "saving_account", type_="foreignkey")
    op.drop_table("currency")
    op.execute("CREATE TYPE currency AS ENUM ('COP', 'USD', 'EUR')")
    op.execute("ALTER TABLE debt ALTER COLUMN currency DROP DEFAULT")
    op.execute("ALTER TABLE debt ALTER COLUMN currency TYPE currency USING currency::currency")
    op.execute("ALTER TABLE debt ALTER COLUMN currency SET DEFAULT 'COP'::currency")
