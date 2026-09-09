"""Reorganiza las categorías de mateojaras@gmail.com según la taxonomía.

Operación puntual, pedida el 2026-09-08. Se ejecuta DENTRO de la máquina de
Fly, que es donde vive DATABASE_URL:

    fly ssh console -a personal-finances-backend -C "python scripts/reorganizar_categorias_mateo.py"

Qué hace, en este orden (importa: las bajas liberan los nombres que heredan
las categorías reales):

  1. Desactiva 18 categorías sin un solo movimiento -- las que creó el antiguo
     botón "Categorías sugeridas" y nunca se usaron. Es baja LÓGICA
     (is_active=false): se reactivan desde la app en un clic.
  2. Renombra 11 categorías reales a su nombre de la taxonomía, conservando
     sus transacciones, y les pone color e icono.
  3. Convierte 6 en subcategorías bajo su padre correspondiente.

Cuatro categorías vacías sobreviven a propósito (217 Compras personales,
226 Negocios y ventas, 224 Regalos y fechas especiales, 218 Ropa y cuidado
personal): son el padre de una que sí tiene movimientos y sin ellas la hija
no tendría dónde colgarse.

No se borra ni una fila y ninguna transacción cambia de categoría: solo cambia
cómo se llaman y cómo se agrupan las categorías que ya tenían.

Aborta sin escribir nada si cualquier comprobación falla.
"""

import os

import psycopg2

UID = "1c31702d-1061-4cf9-83df-d53a569648f6"  # mateojaras@gmail.com

BAJAS = [221, 210, 214, 220, 212, 215, 223, 225, 222,
         213, 227, 229, 230, 211, 209, 216, 228, 219]

PADRES_QUE_SOBREVIVEN = [217, 226, 224, 218]

# id -> (nombre nuevo, color, icono)
RENOMBRAR = {
    21:  ("Entretenimiento y ocio", "violet", "Ticket"),
    65:  ("Comida fuera y domicilios", "orange", "UtensilsCrossed"),
    23:  ("Alimentación y mercados", "lime", "ShoppingCart"),
    22:  ("Transporte", "sky", "Car"),
    44:  ("Otros ingresos", "amber", "Sparkles"),
    40:  ("Salud y bienestar", "rose", "HeartPulse"),
    61:  ("Deudas y créditos", "red", "CreditCard"),
    43:  ("Vivienda", "indigo", "Home"),
    60:  ("Inversiones", "teal", "TrendingUp"),
    62:  ("Salario", "emerald", "Briefcase"),
    64:  ("Educación y capacitación", "indigo", "GraduationCap"),
}

# id -> (padre_id, nombre nuevo, color)
SUBCATEGORIAS = {
    42:  (217, "Tecnología", "pink"),
    41:  (226, "Encargos USA", "teal"),
    76:  (62,  "Liquidación", "emerald"),
    63:  (218, "Vestuario y calzado", "pink"),
    66:  (62,  "Cesantías", "emerald"),
    123: (224, "Donación", "fuchsia"),
}


def main() -> None:
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    objetivo = BAJAS + PADRES_QUE_SOBREVIVEN + list(RENOMBRAR) + list(SUBCATEGORIAS)

    # Cinturón 1: ninguna fila de otro usuario.
    cur.execute(
        "SELECT count(*) FROM category WHERE id = ANY(%s) AND user_id <> %s",
        (objetivo, UID),
    )
    ajenas = cur.fetchone()[0]
    assert ajenas == 0, f"ABORTA: {ajenas} de esos ids no son de este usuario"

    # Cinturón 2: nada que se desactive puede tener movimientos.
    cur.execute(
        "SELECT c.id, c.name FROM category c JOIN transaction t ON t.category_id = c.id "
        "WHERE c.id = ANY(%s) GROUP BY c.id, c.name",
        (BAJAS,),
    )
    con_movimientos = cur.fetchall()
    assert not con_movimientos, f"ABORTA: tienen movimientos: {con_movimientos}"

    cur.execute(
        "UPDATE category SET is_active = false WHERE id = ANY(%s) AND user_id = %s",
        (BAJAS, UID),
    )
    bajas = cur.rowcount

    cur.execute(
        "UPDATE category SET is_active = true WHERE id = ANY(%s) AND user_id = %s",
        (PADRES_QUE_SOBREVIVEN, UID),
    )

    renombradas = 0
    for cid, (nombre, color, icono) in RENOMBRAR.items():
        cur.execute(
            "UPDATE category SET name = %s, color = %s, icon = %s, "
            "parent_id = NULL, is_active = true WHERE id = %s AND user_id = %s",
            (nombre, color, icono, cid, UID),
        )
        renombradas += cur.rowcount

    subcategorias = 0
    for cid, (padre, nombre, color) in SUBCATEGORIAS.items():
        cur.execute(
            "UPDATE category SET name = %s, parent_id = %s, color = %s, "
            "is_active = true WHERE id = %s AND user_id = %s",
            (nombre, padre, color, cid, UID),
        )
        subcategorias += cur.rowcount

    # --- Comprobaciones antes de confirmar --------------------------------
    comprobaciones = [
        ("un tercer nivel",
         "SELECT count(*) FROM category h JOIN category p ON p.id = h.parent_id "
         "WHERE h.user_id = %s AND p.parent_id IS NOT NULL"),
        ("una subcategoría colgando de un padre inactivo",
         "SELECT count(*) FROM category h JOIN category p ON p.id = h.parent_id "
         "WHERE h.user_id = %s AND NOT p.is_active"),
        ("una subcategoría con tipo distinto al de su padre",
         "SELECT count(*) FROM category h JOIN category p ON p.id = h.parent_id "
         "WHERE h.user_id = %s AND h.type <> p.type "
         "AND h.type <> 'both' AND p.type <> 'both'"),
    ]
    for descripcion, sql in comprobaciones:
        cur.execute(sql, (UID,))
        n = cur.fetchone()[0]
        assert n == 0, f"ABORTA: quedó {descripcion} ({n})"

    cur.execute(
        "SELECT lower(name), coalesce(parent_id, 0), count(*) FROM category "
        "WHERE user_id = %s AND is_active GROUP BY 1, 2 HAVING count(*) > 1",
        (UID,),
    )
    duplicados = cur.fetchall()
    assert not duplicados, f"ABORTA: nombres repetidos en el mismo nivel: {duplicados}"

    cur.execute("SELECT count(*) FROM transaction WHERE user_id = %s", (UID,))
    total_tx = cur.fetchone()[0]
    cur.execute(
        "SELECT count(*) FROM transaction WHERE user_id = %s AND category_id IS NULL",
        (UID,),
    )
    sin_categoria = cur.fetchone()[0]

    conn.commit()

    print(f"OK  desactivadas={bajas}  renombradas={renombradas}  subcategorias={subcategorias}")
    print(f"    transacciones={total_tx}  sin categoría={sin_categoria}")


if __name__ == "__main__":
    main()
