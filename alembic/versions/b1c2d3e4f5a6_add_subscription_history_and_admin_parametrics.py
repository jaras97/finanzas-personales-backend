"""add subscription history, plans, payments and admin parametrics

Hasta ahora la tabla `subscription` guardaba SOLO el estado actual y se
sobrescribía en cada renovación: `start_date` se reiniciaba, así que se perdía
cuándo se suscribió alguien originalmente y qué períodos había tenido. No había
forma de responder "¿desde cuándo es cliente?" ni "¿quién le renovó y cuándo?".

Esta migración agrega el historial y las paramétricas de administración SIN
tocar `subscription`, que es la que decide el acceso en producción: ese camino
se deja intacto a propósito para no arriesgar que alguien quede bloqueado.

  subscription_plan   catálogo de planes (nombre, duración, precio)
  subscription_period tramos de servicio otorgados -> "desde cuándo es cliente"
  subscription_event  bitácora inmutable -> "quién hizo qué y cuándo"
  payment             pagos recibidos (contabilidad del negocio, NO del usuario)
  user_admin_profile  notas/teléfono que lleva el admin
  user_tag/_link      etiquetas para clasificar personas
  user.last_login_at  distinguir quien usa la app de quien nunca entró

Revision ID: b1c2d3e4f5a6
Revises: a8b9c0d1e2f3
Create Date: 2026-09-01 12:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "a8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NUEVAS_TABLAS = [
    "subscription_plan",
    "subscription_period",
    "subscription_event",
    "payment",
    "user_admin_profile",
    "user_tag",
    "user_tag_link",
]


def upgrade() -> None:
    op.create_table(
        "subscription_plan",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("duration_months", sa.Integer(), nullable=False),
        sa.Column("price", sa.Float(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=3), sa.ForeignKey("currency.code"), nullable=False, server_default="COP"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_subscription_plan_name", "subscription_plan", ["name"])

    op.create_table(
        "subscription_period",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("subscription_plan.id"), nullable=True),
        sa.Column("start_date", sa.DateTime(), nullable=False),
        sa.Column("end_date", sa.DateTime(), nullable=False),
        sa.Column("price", sa.Float(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=3), sa.ForeignKey("currency.code"), nullable=False, server_default="COP"),
        sa.Column("origin", sa.String(), nullable=False, server_default="activate"),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_subscription_period_user_id", "subscription_period", ["user_id"])

    op.create_table(
        "subscription_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("end_date_before", sa.DateTime(), nullable=True),
        sa.Column("end_date_after", sa.DateTime(), nullable=True),
        sa.Column("months", sa.Integer(), nullable=True),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("subscription_plan.id"), nullable=True),
        sa.Column("detail", sa.String(), nullable=True),
        sa.Column("performed_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_subscription_event_user_id", "subscription_event", ["user_id"])
    op.create_index("ix_subscription_event_action", "subscription_event", ["action"])
    op.create_index("ix_subscription_event_created_at", "subscription_event", ["created_at"])

    op.create_table(
        "payment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("period_id", sa.Integer(), sa.ForeignKey("subscription_period.id"), nullable=True),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=3), sa.ForeignKey("currency.code"), nullable=False, server_default="COP"),
        sa.Column("method", sa.String(), nullable=False, server_default="transfer"),
        sa.Column("reference", sa.String(), nullable=True),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("paid_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_payment_user_id", "payment", ["user_id"])

    op.create_table(
        "user_admin_profile",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user.id"), primary_key=True),
        sa.Column("full_name", sa.String(), nullable=True),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "user_tag",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("color", sa.String(), nullable=False, server_default="slate"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_user_tag_name", "user_tag", ["name"], unique=True)

    op.create_table(
        "user_tag_link",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user.id"), primary_key=True),
        sa.Column("tag_id", sa.Integer(), sa.ForeignKey("user_tag.id"), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Nullable a propósito: None significa "nunca ha entrado", que es
    # información útil, no un dato faltante que haya que rellenar.
    op.add_column("user", sa.Column("last_login_at", sa.DateTime(), nullable=True))

    # Mismo criterio que f3d9c1a7b8e2: sin RLS, PostgREST expone estas tablas
    # con la anon key. El backend conecta como owner, así que no cambia nada
    # para la app.
    for tabla in NUEVAS_TABLAS:
        op.execute(f'ALTER TABLE IF EXISTS "{tabla}" ENABLE ROW LEVEL SECURITY;')

    # Semilla mínima para que el panel no arranque vacío. Se insertan solo si
    # no hay ningún plan, para que re-aplicar la migración no duplique.
    op.execute(
        """
        INSERT INTO subscription_plan (name, duration_months, price, currency, is_active)
        SELECT * FROM (VALUES
            ('Mensual', 1, 0, 'COP', true),
            ('Trimestral', 3, 0, 'COP', true),
            ('Anual', 12, 0, 'COP', true)
        ) AS v(name, duration_months, price, currency, is_active)
        WHERE NOT EXISTS (SELECT 1 FROM subscription_plan);
        """
    )

    # Backfill del período vigente de quienes YA tienen suscripción. Sin esto,
    # las suscripciones existentes aparecerían "sin historial" hasta su próxima
    # renovación, y "cliente desde" saldría vacío justo para los clientes más
    # antiguos, que es a quienes más importa.
    #
    # Es una RECONSTRUCCIÓN, no historia real: del pasado solo se conoce el
    # período vigente, así que se marca `origin='backfill'` para no hacer pasar
    # por registrado algo que se dedujo. Los períodos anteriores a esta
    # migración se perdieron y no hay forma de recuperarlos.
    op.execute(
        """
        INSERT INTO subscription_period
            (user_id, start_date, end_date, price, currency, origin, note, created_at)
        SELECT s.user_id, s.start_date, s.end_date, 0, 'COP', 'backfill',
               'Período reconstruido al activar el historial; lo anterior no quedó registrado.',
               now()
        FROM subscription s
        WHERE NOT EXISTS (
            SELECT 1 FROM subscription_period p WHERE p.user_id = s.user_id
        );
        """
    )


def downgrade() -> None:
    op.drop_column("user", "last_login_at")
    op.drop_table("user_tag_link")
    op.drop_index("ix_user_tag_name", table_name="user_tag")
    op.drop_table("user_tag")
    op.drop_table("user_admin_profile")
    op.drop_index("ix_payment_user_id", table_name="payment")
    op.drop_table("payment")
    for idx in ("ix_subscription_event_created_at", "ix_subscription_event_action", "ix_subscription_event_user_id"):
        op.drop_index(idx, table_name="subscription_event")
    op.drop_table("subscription_event")
    op.drop_index("ix_subscription_period_user_id", table_name="subscription_period")
    op.drop_table("subscription_period")
    op.drop_index("ix_subscription_plan_name", table_name="subscription_plan")
    op.drop_table("subscription_plan")
