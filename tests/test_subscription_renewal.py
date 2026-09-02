"""Renovación y reactivación de suscripciones desde el panel de admin.

Contexto del bug que motivó estos tests (2026-09-01): en producción no se podía
renovar ni reactivar una suscripción vencida -- devolvía 500 -- y el único
rodeo era borrarla y crear una nueva.

Concurrían dos defectos independientes:

1. Las columnas `start_date`/`end_date` son `timestamp WITHOUT time zone` en
   producción (drift de esquema; en local son WITH time zone). Eso hace que se
   lean como datetimes *naive*, y `activate`/`renew` los comparaban contra
   `datetime.now(timezone.utc)` (aware) -> TypeError -> 500. Las rutas de
   lectura ya normalizaban la zona; estas dos se habían quedado fuera.

2. Ni `activate` ni `renew` ponían `is_active = True`, y la guarda de
   "ya tiene una suscripción activa" solo miraba la fecha. Una suscripción con
   fecha futura pero `is_active=False` respondía con ese mensaje -- falso,
   porque el usuario estaba bloqueado -- y quedaba sin salida.

`columnas_naive` replica el esquema de producción a propósito: sin él estos
tests pasarían en local aun con el bug presente.
"""

import pytest
from sqlalchemy import text

from app.database import engine


@pytest.fixture
def columnas_naive():
    """Deja subscription.start_date/end_date como en producción y lo revierte."""
    def cambiar(tipo: str, usando: str) -> None:
        with engine.begin() as conn:
            for col in ("start_date", "end_date"):
                conn.execute(
                    text(f"ALTER TABLE subscription ALTER COLUMN {col} TYPE {tipo} USING {col} {usando}")
                )

    cambiar("timestamp without time zone", "AT TIME ZONE 'UTC'")
    yield
    cambiar("timestamp with time zone", "AT TIME ZONE 'UTC'")


def _fijar_suscripcion(user_id: str, *, dias_fin: int, is_active: bool = True) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE subscription SET end_date = now() + make_interval(days => :d), "
                "is_active = :a WHERE user_id = :u"
            ),
            {"d": dias_fin, "a": is_active, "u": user_id},
        )


def _estado(conn, user_id: str):
    return conn.execute(
        text("SELECT is_active, end_date > now() AS vigente FROM subscription WHERE user_id = :u"),
        {"u": user_id},
    ).one()


@pytest.fixture
def admin(make_user):
    return make_user(role="admin")


class TestRenovarVencida:
    def test_reactivar_vencida_deja_la_suscripcion_utilizable(
        self, client, admin, make_user, columnas_naive
    ):
        victima = make_user()
        _fijar_suscripcion(victima["id"], dias_fin=-5)

        res = client.post(
            f"/subscriptions/admin/activate?user_id={victima['id']}&months=1",
            headers=admin["headers"],
        )

        assert res.status_code == 200, res.text
        assert res.json()["is_active"] is True
        with engine.begin() as conn:
            fila = _estado(conn, victima["id"])
        assert fila.is_active is True
        assert fila.vigente is True

    def test_renovar_vencida_reinicia_desde_hoy(
        self, client, admin, make_user, columnas_naive
    ):
        victima = make_user()
        _fijar_suscripcion(victima["id"], dias_fin=-5)

        res = client.post(
            f"/subscriptions/admin/renew?user_id={victima['id']}&months=1",
            headers=admin["headers"],
        )

        assert res.status_code == 200, res.text
        with engine.begin() as conn:
            fila = _estado(conn, victima["id"])
        assert fila.vigente is True
        assert fila.is_active is True

    def test_el_usuario_recupera_el_acceso_tras_reactivar(
        self, client, admin, make_user, columnas_naive
    ):
        """La prueba que de verdad importa: que deje de estar bloqueado."""
        victima = make_user()
        _fijar_suscripcion(victima["id"], dias_fin=-5)
        assert client.get("/saving-accounts", headers=victima["headers"]).status_code == 403

        client.post(
            f"/subscriptions/admin/activate?user_id={victima['id']}&months=1",
            headers=admin["headers"],
        )

        assert client.get("/saving-accounts", headers=victima["headers"]).status_code == 200


class TestSuscripcionInactiva:
    def test_reactivar_inactiva_con_fecha_futura_no_miente_con_un_400(
        self, client, admin, make_user, columnas_naive
    ):
        """Antes respondía "ya tiene una suscripción activa" y no había salida."""
        victima = make_user()
        _fijar_suscripcion(victima["id"], dias_fin=20, is_active=False)

        res = client.post(
            f"/subscriptions/admin/activate?user_id={victima['id']}&months=1",
            headers=admin["headers"],
        )

        assert res.status_code == 200, res.text
        assert res.json()["is_active"] is True

    def test_renovar_inactiva_la_vuelve_utilizable(
        self, client, admin, make_user, columnas_naive
    ):
        victima = make_user()
        _fijar_suscripcion(victima["id"], dias_fin=20, is_active=False)

        res = client.post(
            f"/subscriptions/admin/renew?user_id={victima['id']}&months=1",
            headers=admin["headers"],
        )

        assert res.status_code == 200, res.text
        assert res.json()["is_active"] is True


class TestNoSeRompeLoQueYaFuncionaba:
    def test_reactivar_una_vigente_y_activa_sigue_rechazandose(
        self, client, admin, make_user, columnas_naive
    ):
        """Control: si no, "arreglar" quitando la guarda pasaría los demás tests."""
        victima = make_user()
        _fijar_suscripcion(victima["id"], dias_fin=20, is_active=True)

        res = client.post(
            f"/subscriptions/admin/activate?user_id={victima['id']}&months=1",
            headers=admin["headers"],
        )

        assert res.status_code == 400
        assert "activa" in res.json()["detail"]

    def test_renovar_una_vigente_suma_al_vencimiento_actual(
        self, client, admin, make_user, columnas_naive
    ):
        victima = make_user()
        _fijar_suscripcion(victima["id"], dias_fin=20, is_active=True)

        res = client.post(
            f"/subscriptions/admin/renew?user_id={victima['id']}&months=1",
            headers=admin["headers"],
        )

        assert res.status_code == 200, res.text
        with engine.begin() as conn:
            dias = conn.execute(
                text("SELECT EXTRACT(day FROM end_date - now()) FROM subscription WHERE user_id = :u"),
                {"u": victima["id"]},
            ).scalar_one()
        # 20 restantes + 30 del mes renovado; no se pierde lo que quedaba
        assert 48 <= dias <= 50
