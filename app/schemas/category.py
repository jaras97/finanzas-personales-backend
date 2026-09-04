from typing import List, Optional
from pydantic import BaseModel, ConfigDict, field_validator

from app.models.category import CategoryType
from app.utils.default_categories import PALETTE


def _validar_color(v: Optional[str]) -> Optional[str]:
    """El color es una CLAVE de paleta, no un hex.

    Se valida contra la lista cerrada porque el frontend mapea cada clave a un
    tono con contraste suficiente en tema claro y oscuro: una clave desconocida
    se renderizaría sin color y parecería un bug de estilos.
    """
    if v is None or v == "":
        return None
    if v not in PALETTE:
        raise ValueError(f"Color no admitido. Opciones: {', '.join(PALETTE)}")
    return v


class CategoryCreate(BaseModel):
    name: str
    type: CategoryType
    color: Optional[str] = None
    icon: Optional[str] = None

    _v_color = field_validator("color")(_validar_color)


class CategoryRead(BaseModel):
    id: int
    name: str
    type: CategoryType
    is_active: bool
    is_system: bool     
    system_key: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class SuggestedCategoriesResult(BaseModel):
    """Resultado de "Añadir categorías sugeridas".

    Se devuelve tanto lo creado como lo omitido para que la UI pueda decir
    "creé 6, ya tenías 7" en vez de un genérico "listo": el usuario necesita
    saber que NO se le duplicó lo que ya tenía.
    """

    created: List[CategoryRead]
    skipped_existing: int
