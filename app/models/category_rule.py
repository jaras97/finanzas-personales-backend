from typing import Optional
from uuid import UUID

from sqlmodel import Field, SQLModel


class CategoryRule(SQLModel, table=True):
    """Regla de categorización automática: si la descripción de una
    transacción CONTIENE `match_text` (comparación en minúsculas, sin
    regex -- v1 deliberadamente simple), se sugiere `category_id`.

    Se evalúan en orden de `priority` ascendente, gana la primera que
    matchea (orden manual explícito, no "la más específica gana" -- ver
    docs/PENDIENTES.md, Fase 5 del roadmap). Reutilizada desde la
    importación de CSV y desde el endpoint `apply` sobre transacciones ya
    existentes sin categorizar.
    """

    __tablename__ = "category_rule"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    category_id: int = Field(foreign_key="category.id")
    match_text: str
    priority: int = Field(default=0, index=True)
    is_active: bool = Field(default=True)
