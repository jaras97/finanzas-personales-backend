from sqlmodel import SQLModel, Field


class Currency(SQLModel, table=True):
    """Catálogo de monedas soportadas. `code` es el código ISO-4217
    (COP, USD, EUR, ...) y es lo que se guarda en saving_account.currency /
    debt.currency (FK a esta tabla)."""

    __tablename__ = "currency"

    code: str = Field(primary_key=True, max_length=3)
    name: str
    symbol: str
    decimal_digits: int = 2
