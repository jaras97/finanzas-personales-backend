from enum import Enum

class SystemCategoryKey(str, Enum):
    TRANSFER = "transfer"
    FEES = "fees"
    DEBT_PAYMENT = "debt_payment"
    INTEREST_INCOME = "interest_income"
    UNCATEGORIZED = "uncategorized"
    # Grupo oculto que aloja a las demás de sistema. Existe para que la regla
    # "solo las hojas reciben dinero" no necesite ninguna excepción: sin él,
    # Transferencia y Sin categorizar serían grupos y no podrían recibir nada.
    SYSTEM_GROUP = "system_group"
    # (Opcionales a futuro)
    OPENING_BALANCE = "opening_balance"
    ADJUSTMENT = "adjustment"
