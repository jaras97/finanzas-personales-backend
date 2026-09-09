"""categorias: modelo grupo/hoja

Convierte el árbol de categorías al modelo en el que **el primer nivel nunca
recibe dinero**: las transacciones, presupuestos, reglas y recurrentes apuntan
siempre a una hoja. Ver docs/PLAN_CATEGORIAS_V2.md para el porqué.

Después de esta migración, para cada usuario:

  - Toda categoría de primer nivel es un GRUPO con al menos una hoja.
  - Ninguna transacción, presupuesto, regla ni recurrente apunta a un grupo.
  - Las categorías de sistema (Transferencia, Sin categorizar, Comisiones,
    Pago de Deuda, Rendimientos) son hojas de un grupo oculto `Sistema`, para
    que la regla no necesite excepciones.

Dos formas de convertir, según el caso:

  a) Categoría SIN hijas (la mayoría). Se crea un grupo encima y se recuelga la
     fila existente debajo, renombrada a «General». **No se toca ni una
     transacción**: la fila conserva su id, así que todas las referencias
     siguen siendo válidas. Es el camino barato y el que aplica al 95%.

  b) Categoría CON hijas y con referencias propias (p. ej. `Salario`, que tenía
     movimientos propios además de subcategorías). La fila pasa a ser el grupo
     y se crea una hoja «General» a la que se mueven sus referencias.

Es reversible: `downgrade` deshace la jerarquía dejando todo en primer nivel.

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-09-09 09:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, Sequence[str], None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tablas que apuntan a una categoría y que, por tanto, hay que mover cuando una
# categoría deja de ser hoja. Si algún día se agrega otra, va acá.
REFERENCIAS = ("transaction", "budget", "category_rule", "recurring_transaction")

NOMBRE_HOJA_POR_DEFECTO = "General"


def _mover_referencias(conn, desde: int, hacia: int) -> int:
    total = 0
    for tabla in REFERENCIAS:
        res = conn.execute(
            sa.text(f"UPDATE {tabla} SET category_id = :hacia WHERE category_id = :desde"),
            {"hacia": hacia, "desde": desde},
        )
        total += res.rowcount or 0
    return total


def _tiene_referencias(conn, category_id: int) -> bool:
    for tabla in REFERENCIAS:
        n = conn.execute(
            sa.text(f"SELECT 1 FROM {tabla} WHERE category_id = :c LIMIT 1"),
            {"c": category_id},
        ).first()
        if n:
            return True
    return False


def upgrade() -> None:
    conn = op.get_bind()

    # --- 1. Grupo Sistema por usuario ------------------------------------
    conn.execute(
        sa.text(
            """
            INSERT INTO category (name, type, user_id, is_active, is_system, system_key, color)
            SELECT 'Sistema', 'both', u.id, true, true, 'system_group', 'slate'
            FROM "user" u
            WHERE EXISTS (
                -- Solo para quien TIENE categorías de sistema que alojar: si no,
                -- el grupo nacería vacío y violaría la invariante I3.
                SELECT 1 FROM category c
                WHERE c.user_id = u.id AND c.is_system
                  AND c.system_key IS DISTINCT FROM 'system_group'
              )
              AND NOT EXISTS (
                SELECT 1 FROM category c
                WHERE c.user_id = u.id AND c.system_key = 'system_group'
              )
            """
        )
    )

    # Las de sistema pasan a ser hojas de ese grupo.
    conn.execute(
        sa.text(
            """
            UPDATE category c
            SET parent_id = g.id
            FROM category g
            WHERE g.user_id = c.user_id
              AND g.system_key = 'system_group'
              AND c.is_system
              AND c.system_key IS DISTINCT FROM 'system_group'
              AND c.parent_id IS NULL
            """
        )
    )

    # --- 2. Categorías del usuario ---------------------------------------
    raices = conn.execute(
        sa.text(
            """
            SELECT id, name, type, user_id, is_active, color, icon
            FROM category
            WHERE parent_id IS NULL AND NOT is_system
            ORDER BY id
            """
        )
    ).all()

    for fila in raices:
        hijas = conn.execute(
            sa.text("SELECT count(*) FROM category WHERE parent_id = :p"),
            {"p": fila.id},
        ).scalar_one()

        if hijas == 0:
            # (a) Sin hijas: grupo nuevo encima, la fila existente baja a hoja.
            #     Ninguna referencia cambia porque la fila conserva su id.
            grupo_id = conn.execute(
                sa.text(
                    """
                    INSERT INTO category (name, type, user_id, is_active, is_system, color, icon)
                    VALUES (:n, :t, :u, :a, false, :c, :i)
                    RETURNING id
                    """
                ),
                {
                    "n": fila.name, "t": fila.type, "u": fila.user_id,
                    "a": fila.is_active, "c": fila.color, "i": fila.icon,
                },
            ).scalar_one()
            conn.execute(
                sa.text(
                    "UPDATE category SET parent_id = :g, name = :n, icon = NULL WHERE id = :c"
                ),
                {"g": grupo_id, "n": NOMBRE_HOJA_POR_DEFECTO, "c": fila.id},
            )
        elif _tiene_referencias(conn, fila.id):
            # (b) Con hijas Y con movimientos propios: la fila queda como grupo
            #     y sus referencias se mudan a una hoja «General».
            hoja_id = conn.execute(
                sa.text(
                    """
                    INSERT INTO category (name, type, user_id, is_active, is_system, color, parent_id)
                    VALUES (:n, :t, :u, true, false, :c, :p)
                    RETURNING id
                    """
                ),
                {
                    "n": NOMBRE_HOJA_POR_DEFECTO, "t": fila.type,
                    "u": fila.user_id, "c": fila.color, "p": fila.id,
                },
            ).scalar_one()
            _mover_referencias(conn, fila.id, hoja_id)
        # else: con hijas y sin referencias propias -> ya es un grupo válido.

    # --- 3. Comprobaciones: abortan la migración si algo quedó mal --------
    for tabla in REFERENCIAS:
        colgadas = conn.execute(
            sa.text(
                f"""
                SELECT count(*) FROM {tabla} r
                JOIN category c ON c.id = r.category_id
                WHERE c.parent_id IS NULL
                """
            )
        ).scalar_one()
        assert colgadas == 0, f"{tabla}: {colgadas} filas siguen apuntando a un grupo"

    sin_hojas = conn.execute(
        sa.text(
            """
            SELECT count(*) FROM category g
            WHERE g.parent_id IS NULL
              AND NOT EXISTS (SELECT 1 FROM category h WHERE h.parent_id = g.id)
            """
        )
    ).scalar_one()
    assert sin_hojas == 0, f"{sin_hojas} grupos quedaron sin ninguna hoja"

    tres_niveles = conn.execute(
        sa.text(
            """
            SELECT count(*) FROM category h
            JOIN category p ON p.id = h.parent_id
            WHERE p.parent_id IS NOT NULL
            """
        )
    ).scalar_one()
    assert tres_niveles == 0, f"{tres_niveles} categorías quedaron en un tercer nivel"


def downgrade() -> None:
    """Deshace la jerarquía: todo vuelve a primer nivel.

    Las hojas «General» recuperan el nombre de su grupo antes de que el grupo
    desaparezca, para no dejar al usuario con una lista de categorías llamadas
    todas «General».
    """
    conn = op.get_bind()

    conn.execute(
        sa.text(
            """
            UPDATE category h
            SET name = p.name, icon = p.icon
            FROM category p
            WHERE p.id = h.parent_id
              AND h.name = :general
              AND NOT p.is_system
              AND (SELECT count(*) FROM category x WHERE x.parent_id = p.id) = 1
            """
        ),
        {"general": NOMBRE_HOJA_POR_DEFECTO},
    )

    # Las hojas suben a primer nivel y los grupos vacíos se eliminan.
    conn.execute(sa.text("UPDATE category SET parent_id = NULL"))
    conn.execute(
        sa.text(
            """
            DELETE FROM category
            WHERE system_key = 'system_group'
               OR (NOT is_system
                   AND NOT EXISTS (SELECT 1 FROM transaction t WHERE t.category_id = category.id)
                   AND NOT EXISTS (SELECT 1 FROM budget b WHERE b.category_id = category.id)
                   AND NOT EXISTS (SELECT 1 FROM category_rule r WHERE r.category_id = category.id)
                   AND NOT EXISTS (SELECT 1 FROM recurring_transaction rt WHERE rt.category_id = category.id)
                   AND name IN (SELECT name FROM category c2
                                WHERE c2.user_id = category.user_id AND c2.id <> category.id))
            """
        )
    )
