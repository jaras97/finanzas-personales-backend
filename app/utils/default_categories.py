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

from typing import List, NamedTuple

from app.models.category import CategoryType


class DefaultCategory(NamedTuple):
    name: str
    type: CategoryType
    color: str
    icon: str
    core: bool
    block: str


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

CORE_CATEGORIES = [c for c in DEFAULT_CATEGORIES if c.core]
