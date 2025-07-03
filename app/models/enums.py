from enum import Enum

class TransactionType(str, Enum):
    income = "income"
    expense = "expense"
    transfer = "transfer"