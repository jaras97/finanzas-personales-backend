from enum import Enum

class SystemCategoryKey(str, Enum):
    TRANSFER = "transfer"
    FEES = "fees"
    DEBT_PAYMENT = "debt_payment"
    INTEREST_INCOME = "interest_income"
    # (Opcionales a futuro)
    OPENING_BALANCE = "opening_balance"
    ADJUSTMENT = "adjustment"
