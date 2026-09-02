"""Historial de suscripciones, planes, pagos y ficha administrativa.

Lo que estos tests protegen, sobre todo, es la pregunta que antes no se podía
responder: "¿desde cuándo es cliente esta persona?". La tabla `subscription`
reinicia `start_date` en cada renovación, así que el dato se perdía; el
historial existe para que deje de perderse.
"""

import pytest
from sqlalchemy import text

from app.database import engine


@pytest.fixture
def admin(make_user):
    return make_user(role="admin")


def _vencer(user_id: str, dias: int = -5) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE subscription SET end_date = now() + make_interval(days => :d) WHERE user_id = :u"),
            {"d": dias, "u": user_id},
        )


def _ficha(client, admin, user_id):
    res = client.get(f"/admin/users/{user_id}/detail", headers=admin["headers"])
    assert res.status_code == 200, res.text
    return res.json()


class TestHistorial:
    def test_renovar_deja_periodo_y_evento(self, client, admin, make_user):
        u = make_user()
        _vencer(u["id"])

        client.post(f"/subscriptions/admin/renew?user_id={u['id']}&months=2",
                    headers=admin["headers"])

        ficha = _ficha(client, admin, u["id"])
        assert len(ficha["periods"]) == 1
        assert len(ficha["events"]) == 1
        evento = ficha["events"][0]
        assert evento["action"] == "renew"
        assert evento["months"] == 2
        # La bitácora dice QUIÉN lo hizo: es el punto de tenerla.
        assert evento["performed_by_email"] == admin["email"]

    def test_desde_cuando_es_cliente_sobrevive_a_dejar_vencer_y_reactivar(
        self, client, admin, make_user
    ):
        """El caso que motivó todo.

        `subscription.start_date` se reinicia cada vez que se reactiva una
        suscripción vencida, así que en cuanto alguien deja pasar un mes y
        vuelve, se pierde desde cuándo era cliente. El historial lo conserva.
        """
        u = make_user()
        _vencer(u["id"])
        client.post(f"/subscriptions/admin/activate?user_id={u['id']}&months=1",
                    headers=admin["headers"])
        primera = _ficha(client, admin, u["id"])["first_subscribed_at"]

        # Deja vencer y vuelve, tres veces
        for _ in range(3):
            _vencer(u["id"])
            client.post(f"/subscriptions/admin/activate?user_id={u['id']}&months=1",
                        headers=admin["headers"])

        ficha = _ficha(client, admin, u["id"])
        assert ficha["first_subscribed_at"] == primera
        assert len(ficha["periods"]) == 4
        # La suscripción vigente ya perdió el dato: por eso hace falta el historial.
        assert ficha["subscription_start"] != primera

    def test_renovar_vigente_encadena_el_periodo_sin_solaparse(
        self, client, admin, make_user
    ):
        """Un período nuevo debe empezar donde terminaba el anterior; si
        empezara "hoy", el historial mostraría tiempo cubierto dos veces."""
        u = make_user()  # viene con 30 días vigentes
        client.post(f"/subscriptions/admin/renew?user_id={u['id']}&months=1",
                    headers=admin["headers"])

        periodos = _ficha(client, admin, u["id"])["periods"]
        assert len(periodos) == 1
        assert periodos[0]["origin"] == "renew"
        assert periodos[0]["start_date"] > periodos[0]["created_at"]

    def test_eliminar_la_suscripcion_conserva_el_historial(
        self, client, admin, make_user
    ):
        u = make_user()
        _vencer(u["id"])
        client.post(f"/subscriptions/admin/activate?user_id={u['id']}&months=1",
                    headers=admin["headers"])

        client.delete(f"/subscriptions/admin/{u['id']}", headers=admin["headers"])

        ficha = _ficha(client, admin, u["id"])
        assert ficha["subscription_status"] == "none"
        # La persona SÍ estuvo cubierta: eso no se borra.
        assert len(ficha["periods"]) == 1
        assert any(e["action"] == "delete" for e in ficha["events"])


class TestPlanes:
    def test_el_plan_manda_sobre_los_meses_y_copia_su_precio(
        self, client, admin, make_user
    ):
        plan = client.post("/admin/subscription-plans",
                           json={"name": "Anual", "duration_months": 12, "price": 300000},
                           headers=admin["headers"]).json()
        u = make_user()
        _vencer(u["id"])

        client.post(
            f"/subscriptions/admin/activate?user_id={u['id']}&months=1&plan_id={plan['id']}",
            headers=admin["headers"],
        )

        ficha = _ficha(client, admin, u["id"])
        periodo = ficha["periods"][0]
        assert periodo["plan_name"] == "Anual"
        assert periodo["price"] == 300000
        # Lo esencial: manda la duración del plan (12 meses), no el `months=1`
        # que venía en la URL. Sin esto, elegir "Anual" cobraba un año y
        # otorgaba un mes.
        assert ficha["events"][0]["months"] == 12
        with engine.begin() as conn:
            dias = conn.execute(
                text("SELECT EXTRACT(day FROM end_date - now()) FROM subscription WHERE user_id = :u"),
                {"u": u["id"]},
            ).scalar_one()
        assert 358 <= dias <= 361  # 12 * 30 días

    def test_subir_el_precio_del_plan_no_reescribe_lo_ya_cobrado(
        self, client, admin, make_user
    ):
        plan = client.post("/admin/subscription-plans",
                           json={"name": "Mensual", "duration_months": 1, "price": 30000},
                           headers=admin["headers"]).json()
        u = make_user()
        _vencer(u["id"])
        client.post(f"/subscriptions/admin/activate?user_id={u['id']}&plan_id={plan['id']}",
                    headers=admin["headers"])

        client.put(f"/admin/subscription-plans/{plan['id']}", json={"price": 50000},
                   headers=admin["headers"])

        assert _ficha(client, admin, u["id"])["periods"][0]["price"] == 30000

    def test_retirar_un_plan_es_baja_logica(self, client, admin):
        plan = client.post("/admin/subscription-plans",
                           json={"name": "Temporal", "duration_months": 1},
                           headers=admin["headers"]).json()

        client.delete(f"/admin/subscription-plans/{plan['id']}", headers=admin["headers"])

        visibles = client.get("/admin/subscription-plans", headers=admin["headers"]).json()
        assert plan["id"] not in [p["id"] for p in visibles]
        con_inactivos = client.get("/admin/subscription-plans?include_inactive=true",
                                   headers=admin["headers"]).json()
        assert plan["id"] in [p["id"] for p in con_inactivos]

    def test_plan_inexistente_al_activar_da_404(self, client, admin, make_user):
        u = make_user()
        res = client.post(f"/subscriptions/admin/activate?user_id={u['id']}&plan_id=999999",
                          headers=admin["headers"])
        assert res.status_code == 404


class TestPagos:
    def test_registrar_pago_suma_al_total_y_queda_en_bitacora(
        self, client, admin, make_user
    ):
        u = make_user()
        res = client.post(f"/admin/users/{u['id']}/payments",
                          json={"amount": 30000, "method": "transfer", "reference": "ABC-1"},
                          headers=admin["headers"])
        assert res.status_code == 201, res.text

        ficha = res.json()
        assert ficha["total_paid"] == 30000
        assert ficha["payments"][0]["reference"] == "ABC-1"
        assert any(e["action"] == "payment" for e in ficha["events"])

    def test_borrar_un_pago_deja_rastro(self, client, admin, make_user):
        u = make_user()
        ficha = client.post(f"/admin/users/{u['id']}/payments", json={"amount": 30000},
                            headers=admin["headers"]).json()
        pago_id = ficha["payments"][0]["id"]

        client.delete(f"/admin/users/{u['id']}/payments/{pago_id}", headers=admin["headers"])

        final = _ficha(client, admin, u["id"])
        assert final["total_paid"] == 0
        assert sum(1 for e in final["events"] if e["action"] == "payment") == 2

    def test_no_se_puede_colgar_un_pago_de_otro_usuario(
        self, client, admin, make_user
    ):
        a, b = make_user(), make_user()
        _vencer(a["id"])
        client.post(f"/subscriptions/admin/activate?user_id={a['id']}", headers=admin["headers"])
        periodo_de_a = _ficha(client, admin, a["id"])["periods"][0]["id"]

        res = client.post(f"/admin/users/{b['id']}/payments",
                          json={"amount": 1000, "period_id": periodo_de_a},
                          headers=admin["headers"])
        assert res.status_code == 404


class TestFichaYEtiquetas:
    def test_notas_y_etiquetas(self, client, admin, make_user):
        u = make_user()
        tag = client.post("/admin/tags", json={"name": "Cortesía", "color": "emerald"},
                          headers=admin["headers"]).json()

        client.put(f"/admin/users/{u['id']}/profile",
                   json={"full_name": "Ana Pérez", "phone": "300", "notes": "Paga puntual"},
                   headers=admin["headers"])
        ficha = client.put(f"/admin/users/{u['id']}/tags", json={"tag_ids": [tag["id"]]},
                           headers=admin["headers"]).json()

        assert ficha["full_name"] == "Ana Pérez"
        assert ficha["notes"] == "Paga puntual"
        assert [t["name"] for t in ficha["tags"]] == ["Cortesía"]

    def test_borrar_una_etiqueta_en_uso_no_rompe(self, client, admin, make_user):
        u = make_user()
        tag = client.post("/admin/tags", json={"name": "Prueba"},
                          headers=admin["headers"]).json()
        client.put(f"/admin/users/{u['id']}/tags", json={"tag_ids": [tag["id"]]},
                   headers=admin["headers"])

        res = client.delete(f"/admin/tags/{tag['id']}", headers=admin["headers"])

        assert res.status_code == 200
        assert _ficha(client, admin, u["id"])["tags"] == []

    def test_etiquetas_duplicadas_se_rechazan(self, client, admin):
        client.post("/admin/tags", json={"name": "Moroso"}, headers=admin["headers"])
        res = client.post("/admin/tags", json={"name": "moroso"}, headers=admin["headers"])
        assert res.status_code == 400


class TestMetricas:
    def test_registra_el_ultimo_acceso(self, client, admin, make_user):
        u = make_user()  # make_user hace login, así que ya entró una vez
        metrics = _ficha(client, admin, u["id"])["metrics"]
        assert metrics["has_ever_logged_in"] is True
        assert metrics["days_since_last_login"] == 0

    def test_cuenta_la_actividad_real(self, client, admin, user, make_account):
        # `make_account` crea siempre para el usuario del fixture `user`.
        make_account(name="Bancolombia")
        metrics = _ficha(client, admin, user["id"])["metrics"]
        assert metrics["accounts"] == 1
        assert metrics["transactions"] == 0


class TestAcceso:
    def test_un_usuario_normal_no_ve_la_ficha_de_nadie(self, client, user, make_user):
        otro = make_user()
        res = client.get(f"/admin/users/{otro['id']}/detail", headers=user["headers"])
        assert res.status_code == 403

    def test_un_usuario_normal_no_puede_crear_planes(self, client, user):
        res = client.post("/admin/subscription-plans",
                          json={"name": "Gratis", "duration_months": 1},
                          headers=user["headers"])
        assert res.status_code == 403
