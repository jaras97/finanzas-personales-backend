"""Subcategorías (dos niveles).

Recomendación 1 del PDF de taxonomía: "Categoría Padre > Subcategoría, para no
saturar al usuario". Lo que estos tests protegen es que la jerarquía no se
pueda corromper (ciclos, tres niveles, tipos mezclados) y que el rollup a
padre sea correcto, porque de él dependen el resumen y los presupuestos.
"""

import datetime as dt

import pytest


def _crear(client, auth, nombre, tipo="expense", parent_id=None):
    payload = {"name": nombre, "type": tipo}
    if parent_id is not None:
        payload["parent_id"] = parent_id
    return client.post("/categories", json=payload, headers=auth)


@pytest.fixture
def transporte(client, auth):
    """La taxonomía sembrada ya trae "Transporte" de primer nivel."""
    cats = client.get("/categories", headers=auth).json()
    return next(c for c in cats if c["name"] == "Transporte")


class TestJerarquiaValida:
    def test_crear_una_subcategoria(self, client, auth, transporte):
        res = _crear(client, auth, "Gasolina", parent_id=transporte["id"])

        assert res.status_code == 200, res.text
        assert res.json()["parent_id"] == transporte["id"]
        assert res.json()["parent_name"] == "Transporte"

    def test_el_mismo_nombre_puede_existir_bajo_padres_distintos(
        self, client, auth, transporte
    ):
        """El sentido de la jerarquía: "Transporte › Gasolina" y
        "Viajes › Gasolina" son cosas distintas."""
        viajes = _crear(client, auth, "Viajes").json()

        a = _crear(client, auth, "Gasolina", parent_id=transporte["id"])
        b = _crear(client, auth, "Gasolina", parent_id=viajes["id"])

        assert a.status_code == 200, a.text
        assert b.status_code == 200, b.text

    def test_no_se_puede_repetir_el_nombre_bajo_el_mismo_padre(
        self, client, auth, transporte
    ):
        _crear(client, auth, "Gasolina", parent_id=transporte["id"])

        res = _crear(client, auth, "Gasolina", parent_id=transporte["id"])

        assert res.status_code == 400
        assert "nombre" in res.json()["detail"].lower()

    def test_el_listado_pone_cada_hija_junto_a_su_padre(
        self, client, auth, transporte
    ):
        _crear(client, auth, "Gasolina", parent_id=transporte["id"])
        cats = client.get("/categories", headers=auth).json()

        nombres = [c["name"] for c in cats]
        assert nombres.index("Gasolina") == nombres.index("Transporte") + 1


class TestJerarquiaInvalida:
    def test_rechaza_un_tercer_nivel(self, client, auth, transporte):
        gasolina = _crear(client, auth, "Gasolina", parent_id=transporte["id"]).json()

        res = _crear(client, auth, "Corriente", parent_id=gasolina["id"])

        assert res.status_code == 400
        assert "dos niveles" in res.json()["detail"]

    def test_rechaza_mezclar_tipos(self, client, auth, transporte):
        res = _crear(client, auth, "Reembolso gasolina", tipo="income", parent_id=transporte["id"])

        assert res.status_code == 400
        assert "tipo" in res.json()["detail"].lower()

    def test_rechaza_un_padre_inexistente(self, client, auth):
        res = _crear(client, auth, "Huérfana", parent_id=999999)
        assert res.status_code == 404

    def test_rechaza_un_padre_de_otro_usuario(self, client, auth, make_user):
        otro = make_user()
        ajena = client.post(
            "/categories", json={"name": "Ajena", "type": "expense"}, headers=otro["headers"]
        ).json()

        res = _crear(client, auth, "Mía", parent_id=ajena["id"])

        assert res.status_code == 404

    def test_una_categoria_no_puede_ser_su_propia_madre(self, client, auth, transporte):
        res = client.put(
            f"/categories/{transporte['id']}",
            json={"name": "Transporte", "type": "expense", "parent_id": transporte["id"]},
            headers=auth,
        )
        assert res.status_code == 400

    def test_un_padre_con_hijas_no_puede_volverse_subcategoria(
        self, client, auth, transporte
    ):
        """Sería un ciclo de tres niveles por la puerta de atrás."""
        _crear(client, auth, "Gasolina", parent_id=transporte["id"])
        otra = _crear(client, auth, "Movilidad").json()

        res = client.put(
            f"/categories/{transporte['id']}",
            json={"name": "Transporte", "type": "expense", "parent_id": otra["id"]},
            headers=auth,
        )

        assert res.status_code == 400
        assert "subcategorías" in res.json()["detail"]


class TestBajaDeUnPadre:
    def test_no_deja_desactivar_un_padre_con_hijas_activas(
        self, client, auth, transporte
    ):
        _crear(client, auth, "Gasolina", parent_id=transporte["id"])

        res = client.delete(f"/categories/{transporte['id']}", headers=auth)

        assert res.status_code == 400
        assert "subcategoría activa" in res.json()["detail"]

    def test_se_puede_desactivar_tras_quitar_las_hijas(self, client, auth, transporte):
        gasolina = _crear(client, auth, "Gasolina", parent_id=transporte["id"]).json()
        client.delete(f"/categories/{gasolina['id']}", headers=auth)

        res = client.delete(f"/categories/{transporte['id']}", headers=auth)

        assert res.status_code == 200, res.text


class TestRollup:
    def _gastar(self, client, auth, cuenta, categoria_id, monto):
        return client.post(
            "/transactions",
            json={
                "amount": monto,
                "type": "expense",
                "description": "compra",
                "category_id": categoria_id,
                "saving_account_id": cuenta["id"],
                "date": dt.datetime.now(dt.timezone.utc).isoformat(),
            },
            headers=auth,
        )

    def test_el_resumen_suma_la_subcategoria_al_padre(
        self, client, auth, make_account, transporte
    ):
        """Sin esto la jerarquía no reduce nada: el resumen mostraría 25 hojas
        en vez de las 8 categorías reconocibles que se buscaban."""
        cuenta = make_account(balance=1_000_000)
        gasolina = _crear(client, auth, "Gasolina", parent_id=transporte["id"]).json()

        self._gastar(client, auth, cuenta, transporte["id"], 30_000)
        self._gastar(client, auth, cuenta, gasolina["id"], 70_000)

        hoy = dt.date.today()
        res = client.get(
            f"/summary?startDate={hoy}T00:00:00Z&endDate={hoy}T23:59:59Z&tz=UTC",
            headers=auth,
        )
        assert res.status_code == 200, res.text
        cop = res.json()["COP"]["expense_by_category"]

        transporte_row = [c for c in cop if c["category_name"] == "Transporte"]
        assert len(transporte_row) == 1, "la subcategoría debería sumarse al padre"
        assert transporte_row[0]["total"] == 100_000
        assert not any(c["category_name"] == "Gasolina" for c in cop)

    def test_el_presupuesto_del_padre_incluye_a_las_hijas(
        self, client, auth, make_account, transporte
    ):
        """Ignorarlas mostraría plata disponible que ya se gastó."""
        cuenta = make_account(balance=1_000_000)
        gasolina = _crear(client, auth, "Gasolina", parent_id=transporte["id"]).json()
        hoy = dt.date.today()
        client.post(
            "/budgets",
            json={
                "category_id": transporte["id"],
                "amount": 200_000,
                "currency": "COP",
                "month": hoy.strftime("%Y-%m"),
            },
            headers=auth,
        )

        self._gastar(client, auth, cuenta, gasolina["id"], 70_000)

        presupuestos = client.get(f"/budgets?month={hoy.strftime('%Y-%m')}", headers=auth).json()
        b = next(x for x in presupuestos if x["category_id"] == transporte["id"])
        assert b["spent"] == 70_000
