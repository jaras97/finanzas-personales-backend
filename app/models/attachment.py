from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlmodel import Field, SQLModel


class Attachment(SQLModel, table=True):
    """Comprobante adjunto a una transacción (foto de recibo, PDF del banco).

    Se adjunta a una `Transaction`, no a un grupo de transferencia: en una
    transferencia el comprobante se cuelga de la pata de salida, que es
    justamente la fila que el usuario ve en Transacciones tras la fusión de
    pares (`mergeTransferPairs`).

    El archivo vive en Supabase Storage; acá solo queda la ruta. Se guarda
    `storage_path` completo (incluye el `user_id`) para que borrar la fila
    permita borrar el binario sin tener que reconstruir la ruta.
    """

    __tablename__ = "attachment"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    transaction_id: int = Field(foreign_key="transaction.id", index=True)
    storage_path: str
    filename: str
    content_type: str
    size_bytes: int
    created_at: datetime = Field(default_factory=datetime.utcnow)
