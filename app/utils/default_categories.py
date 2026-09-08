"""Taxonomía de categorías que se ofrece a los usuarios.

Origen: `docs/Categorias_Finanzas_Egresos_e_Ingresos.pdf`, contrastado el
2026-09-03 contra las 2.008 transacciones de producción: el 92% de los
movimientos reales ya caía en esta estructura, aunque cada usuario la había
reinventado con sus propios nombres.

Dos criterios para el NÚCLEO (`core=True`), que es lo único que se siembra
automáticamente a un usuario nuevo:

1. Volumen real medido (Ocio 306 movimientos, Comida fuera 226, Alimentación
   158, Transporte 127...).
2. Universalidad, aunque el volumen sea cero: *Servicios Públicos* y
   *Suscripciones Digitales* casi no aparecían, pero las paga todo el mundo, y
   su ausencia es justo lo que empuja a inventar nombres sueltos.

El resto (`core=False`) NO se siembra: el propio PDF advierte "no saturar al
usuario", y 19 categorías de egreso en una lista plana son su propia forma de
saturación para quien registra tres gastos al mes. Se ofrecen bajo demanda
desde `POST /categories/suggested`.

Estas categorías NO son `is_system`: el usuario puede renombrarlas, cambiarles
el color o desactivarlas. Las de sistema (Transferencia, Sin categorizar...)
son operativas y viven en `category_helpers.py`.

`color` guarda una CLAVE de paleta, no un hex: el frontend la resuelve a un
tono que funcione en tema claro y oscuro. Un hex fijo se vería mal en uno de
los dos.
"""

import re
import unicodedata
from typing import List, NamedTuple, Optional

from app.models.category import CategoryType


def _slug(nombre: str) -> str:
    base = unicodedata.normalize("NFKD", nombre.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", base).strip("-")


class DefaultCategory(NamedTuple):
    name: str
    type: CategoryType
    color: str
    icon: str
    core: bool
    block: str
    # Nombre del padre dentro de esta misma taxonomía. None = primer nivel.
    parent: Optional[str] = None

    @property
    def key(self) -> str:
        """Identificador estable para el selector.

        Se deriva del nombre normalizado, no de un id de base de datos: el
        frontend necesita poder marcar "Vivienda" antes de que exista ninguna
        fila, y el backend tiene que reconocerla después por el mismo nombre.
        """
        base = _slug(self.name)
        return f"{_slug(self.parent)}/{base}" if self.parent else base


# Claves de paleta admitidas. El frontend (lib/categoryStyle.ts) mapea cada una
# a un color con contraste suficiente en ambos temas.
PALETTE = [
    "sky", "emerald", "amber", "rose", "violet", "teal", "orange",
    "indigo", "lime", "pink", "cyan", "fuchsia", "red", "slate",
]

E = CategoryType.expense
I = CategoryType.income

DEFAULT_CATEGORIES: List[DefaultCategory] = [
    # --- 1.1 Gastos fijos y necesidades básicas ---------------------------
    DefaultCategory("Vivienda", E, "indigo", "Home", True, "fijos"),
    DefaultCategory("Servicios públicos", E, "cyan", "Zap", True, "fijos"),
    DefaultCategory("Alimentación y mercados", E, "lime", "ShoppingCart", True, "fijos"),
    DefaultCategory("Transporte", E, "sky", "Car", True, "fijos"),
    DefaultCategory("Salud y bienestar", E, "rose", "HeartPulse", True, "fijos"),
    DefaultCategory("Educación y capacitación", E, "indigo", "GraduationCap", False, "fijos"),
    DefaultCategory("Mascotas", E, "orange", "PawPrint", False, "fijos"),

    # --- 1.2 Gastos variables y estilo de vida ----------------------------
    DefaultCategory("Comida fuera y domicilios", E, "orange", "UtensilsCrossed", True, "variables"),
    DefaultCategory("Entretenimiento y ocio", E, "violet", "Ticket", True, "variables"),
    DefaultCategory("Suscripciones digitales", E, "fuchsia", "Repeat", True, "variables"),
    DefaultCategory("Compras personales", E, "pink", "ShoppingBag", True, "variables"),
    DefaultCategory("Ropa y cuidado personal", E, "pink", "Shirt", False, "variables"),
    DefaultCategory("Viajes y vacaciones", E, "cyan", "Plane", False, "variables"),

    # --- 1.3 Metas, ahorro e inversión ------------------------------------
    DefaultCategory("Deudas y créditos", E, "red", "CreditCard", True, "metas"),
    DefaultCategory("Ahorro", E, "emerald", "PiggyBank", False, "metas"),
    DefaultCategory("Inversiones", E, "teal", "TrendingUp", False, "metas"),

    # --- 1.4 Gastos ocasionales e imprevistos -----------------------------
    DefaultCategory("Imprevistos", E, "red", "TriangleAlert", False, "ocasionales"),
    DefaultCategory("Regalos y fechas especiales", E, "fuchsia", "Gift", False, "ocasionales"),
    DefaultCategory("Impuestos y trámites", E, "slate", "Landmark", False, "ocasionales"),

    # --- 2 Ingresos --------------------------------------------------------
    DefaultCategory("Salario", I, "emerald", "Briefcase", True, "ingresos"),
    DefaultCategory("Negocios y ventas", I, "teal", "Store", True, "ingresos"),
    DefaultCategory("Otros ingresos", I, "amber", "Sparkles", True, "ingresos"),
    DefaultCategory("Trabajo independiente", I, "lime", "Laptop", False, "ingresos"),
    DefaultCategory("Plataformas y servicios", I, "sky", "Smartphone", False, "ingresos"),
    DefaultCategory("Rentas", I, "violet", "Building2", False, "ingresos"),
]

# ---------------------------------------------------------------------------
# Segundo nivel
# ---------------------------------------------------------------------------
# Salen de los "Ejemplos" que el PDF lista bajo cada categoría. Ahí eran
# ilustraciones; acá se convierten en subcategorías opcionales que el usuario
# elige una por una en el selector.
#
# NINGUNA se siembra automáticamente: son 70 y sembrarlas convertiría la lista
# de categorías en el muro que la jerarquía venía a evitar. Existen para quien
# quiera ese detalle y lo pida marcándolas.
#
# Se evitan nombres de marca ("Netflix", "Spotify"): envejecen mal y no son
# categorías, son proveedores. El color y el tipo se heredan del padre.
SUBCATEGORIAS: dict[str, List[str]] = {
    "Vivienda": ["Arriendo", "Hipoteca", "Administración", "Mantenimiento del hogar"],
    "Servicios públicos": ["Energía", "Agua", "Gas", "Internet", "Telefonía"],
    "Alimentación y mercados": ["Mercado", "Artículos de aseo"],
    "Transporte": ["Gasolina", "Transporte público", "Peajes", "Seguros y trámites", "Mantenimiento del vehículo"],
    "Salud y bienestar": ["Medicamentos", "Citas médicas", "Seguro médico"],
    "Educación y capacitación": ["Matrículas y mensualidades", "Cursos y certificaciones", "Libros y materiales"],
    "Mascotas": ["Alimento", "Veterinario", "Accesorios y guardería"],

    "Comida fuera y domicilios": ["Restaurantes", "Domicilios", "Café y snacks"],
    "Entretenimiento y ocio": ["Cine y eventos", "Salidas", "Parques y planes"],
    "Suscripciones digitales": ["Streaming", "Almacenamiento en la nube", "Licencias y apps"],
    "Compras personales": ["Tecnología", "Hogar y decoración", "Hobbies"],
    "Ropa y cuidado personal": ["Vestuario y calzado", "Peluquería y estética", "Gimnasio"],
    "Viajes y vacaciones": ["Tiquetes", "Hospedaje", "Tours y actividades"],

    "Deudas y créditos": ["Tarjeta de crédito", "Préstamos"],
    "Ahorro": ["Fondo de emergencia", "Metas de ahorro"],
    "Inversiones": ["Portafolio", "Finca raíz"],

    "Imprevistos": ["Reparaciones", "Emergencias médicas"],
    "Regalos y fechas especiales": ["Cumpleaños", "Navidad y fin de año"],
    "Impuestos y trámites": ["Renta", "Vehículo", "Predial"],

    "Salario": ["Nómina", "Primas y bonificaciones"],
    "Trabajo independiente": ["Honorarios", "Asesorías"],
    "Negocios y ventas": ["Ventas", "Comisiones"],
    "Plataformas y servicios": ["Domicilios y entregas", "Transporte de pasajeros"],
    "Rentas": ["Arriendos cobrados", "Dividendos y rendimientos"],
    "Otros ingresos": ["Reembolsos", "Premios y subsidios", "Venta de usados"],
}


def _expandir_subcategorias() -> List[DefaultCategory]:
    """Construye el segundo nivel heredando tipo, color y bloque del padre.

    Se genera en vez de escribirse a mano para que un cambio de color o de
    bloque en el padre no deje a sus hijas desalineadas.
    """
    por_nombre = {c.name: c for c in DEFAULT_CATEGORIES}
    salida: List[DefaultCategory] = []
    for nombre_padre, hijas in SUBCATEGORIAS.items():
        padre = por_nombre[nombre_padre]  # KeyError a propósito si se renombra un padre
        for hija in hijas:
            salida.append(
                DefaultCategory(
                    name=hija,
                    type=padre.type,
                    color=padre.color,
                    icon="",  # heredan el icono del padre en la interfaz
                    core=False,  # nunca se siembran solas
                    block=padre.block,
                    parent=nombre_padre,
                )
            )
    return salida


DEFAULT_SUBCATEGORIES: List[DefaultCategory] = _expandir_subcategorias()

# Taxonomía completa, padres y luego sus hijas.
FULL_TAXONOMY: List[DefaultCategory] = DEFAULT_CATEGORIES + DEFAULT_SUBCATEGORIES

CORE_CATEGORIES = [c for c in DEFAULT_CATEGORIES if c.core]

# Etiquetas de los bloques, en el orden del PDF.
BLOCK_LABELS: List[tuple[str, str]] = [
    ("fijos", "Gastos fijos y necesidades básicas"),
    ("variables", "Gastos variables y estilo de vida"),
    ("metas", "Metas, ahorro e inversión"),
    ("ocasionales", "Gastos ocasionales e imprevistos"),
    ("ingresos", "Ingresos"),
]
