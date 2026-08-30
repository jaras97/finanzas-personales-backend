from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AttachmentRead(BaseModel):
    id: int
    transaction_id: int
    filename: str
    content_type: str
    size_bytes: int
    created_at: datetime
    # URL firmada de corta duración; None si el almacenamiento no responde.
    url: Optional[str] = None

    class Config:
        from_attributes = True
