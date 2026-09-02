from sqlmodel import SQLModel, Field
from typing import Optional
from uuid import uuid4, UUID
from datetime import datetime

class User(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(index=True, unique=True)
    hashed_password: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    role: str = Field(default="user")
    # Moneda en la que se muestra el patrimonio neto consolidado (Resumen).
    # No implica que el usuario tenga cuentas en esta moneda.
    report_currency: str = Field(default="COP", foreign_key="currency.code")
    # Se actualiza en cada login. Sirve para que el admin distinga a quien usa
    # la app de quien se registró y nunca volvió; None = nunca ha entrado.
    last_login_at: Optional[datetime] = Field(default=None)