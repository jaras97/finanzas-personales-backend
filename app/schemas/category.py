from typing import List, Literal, Optional
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
    # Nulo = categoría de primer nivel. La validación de que exista, sea del
    # usuario, no sea ya una subcategoría y comparta tipo vive en el endpoint.
    parent_id: Optional[int] = None

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
    parent_id: Optional[int] = None
    # Denormalizado para que los selectores puedan mostrar "Padre › Hija" sin
    # cruzar la lista consigo misma en cada render.
    parent_name: Optional[str] = None
    # Primer nivel = grupo: agrupa pero NO recibe movimientos (invariante I1).
    # Viaja resuelto para que el frontend no tenga que deducirlo de parent_id.
    is_group: bool = False
    # Para un grupo de una sola hoja: su id. Es lo que hace posible que la
    # interfaz muestre "Mascotas" como una línea y aun así sepa dónde registrar.
    default_leaf_id: Optional[int] = None
    # Movimientos asociados. La interfaz lo necesita para saber si al
    # desglosar una categoría hay algo que reubicar, y para no preguntar
    # cuando no hace falta.
    transactions_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class SuggestedCategoriesResult(BaseModel):
    """Resultado de "Añadir categorías sugeridas".

    Se devuelve tanto lo creado como lo omitido para que la UI pueda decir
    "creé 6, ya tenías 7" en vez de un genérico "listo": el usuario necesita
    saber que NO se le duplicó lo que ya tenía.
    """

    created: List[CategoryRead]
    skipped_existing: int


# ---------------------------------------------------------------------------
# Selector de taxonomía
# ---------------------------------------------------------------------------

class TaxonomyItem(BaseModel):
    """Una entrada de la taxonomía, con el estado que tiene EN ESTA cuenta.

    El estado viaja junto al catálogo para que el selector pueda pintarse
    precargado en una sola petición, sin que el frontend tenga que cruzar dos
    listas y adivinar equivalencias de nombres.
    """

    key: str
    name: str
    type: CategoryType
    color: Optional[str] = None
    icon: Optional[str] = None
    core: bool
    # "present" = la tiene activa · "inactive" = la tiene desactivada
    # (marcarla la reactiva) · "absent" = no la tiene (marcarla la crea)
    state: Literal["present", "inactive", "absent"]
    category_id: Optional[int] = None
    transactions: int = 0
    # Con movimientos no se puede desmarcar: desactivarla dejaría agujeros en
    # los reportes. Se informa el porqué en vez de dejar la casilla gris.
    locked: bool = False
    locked_reason: Optional[str] = None
    children: List["TaxonomyItem"] = []


class TaxonomyBlock(BaseModel):
    id: str
    label: str
    items: List[TaxonomyItem]


class TaxonomyRead(BaseModel):
    blocks: List[TaxonomyBlock]


class TaxonomyApply(BaseModel):
    """Conjunto COMPLETO de claves que deben quedar activas.

    Es un estado deseado, no una lista de acciones: el backend calcula qué
    crear, reactivar y desactivar comparándolo con lo que hay. Así el frontend
    no puede pedir una transición incoherente.
    """

    selected: List[str]


class TaxonomyApplyResult(BaseModel):
    created: int
    reactivated: int
    deactivated: int
    # Las que se pidió quitar pero no se pudo, con el motivo. Nunca se falla
    # entero por esto: se aplica el resto y se informa.
    skipped: List[str] = []
