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
    """Con el modelo grupo/hoja esto cambió de sentido.

    Antes se BLOQUEABA desactivar un padre con hijas activas. Ahora quitar un
    grupo las arrastra: para el usuario «Transporte» es una categoría, no un
    árbol que deba desmontar a mano. Lo que sí se bloquea es quitar algo con
    movimientos, y eso vive en test_invariantes_grupo_hoja.py (I3).
    """

    def test_quitar_el_grupo_se_lleva_sus_hojas(self, client, auth, transporte):
        gasolina = _crear(client, auth, "Gasolina", parent_id=transporte["id"]).json()

        res = client.delete(f"/categories/{transporte['id']}", headers=auth)

        assert res.status_code == 200, res.text
        cats = {c["id"]: c for c in client.get("/categories?status=all", headers=auth).json()}
        assert cats[transporte["id"]]["is_active"] is False
        assert cats[gasolina["id"]]["is_active"] is False


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
        # Los movimientos van a HOJAS (I1): el grupo no los recibe. Lo que se
        # comprueba es que el resumen los sume bajo el grupo.
        gasolina = _crear(client, auth, "Gasolina", parent_id=transporte["id"]).json()
        peajes = _crear(client, auth, "Peajes", parent_id=transporte["id"]).json()

        self._gastar(client, auth, cuenta, peajes["id"], 30_000)
        self._gastar(client, auth, cuenta, gasolina["id"], 70_000)

        # UTC, no local: el resumen se pide con tz=UTC y los movimientos se
        # crean con now(timezone.utc). Mezclar husos hacía fallar el test de
        # noche, cuando la fecha local y la UTC ya no coinciden.
        hoy = dt.datetime.now(dt.timezone.utc).date()
        res = client.get(
            f"/summary?start_date={hoy}&end_date={hoy}&tz=UTC",
            headers=auth,
        )
        assert res.status_code == 200, res.text
        cop = res.json()["COP"]["expense_by_category"]

        transporte_row = [c for c in cop if c["category_name"] == "Transporte"]
        assert len(transporte_row) == 1, "la subcategoría debería sumarse al padre"
        assert transporte_row[0]["total"] == 100_000
        assert not any(c["category_name"] in ("Gasolina", "Peajes") for c in cop)

    # test_el_presupuesto_del_padre_incluye_a_las_hijas se eliminó el
    # 2026-09-09: un grupo ya no PUEDE tener presupuesto propio (I2), su total
    # es derivado de sus hojas. Lo cubre
    # test_invariantes_grupo_hoja.py::TestI2::test_el_gasto_de_una_hoja_no_se_cuenta_dos_veces,
    # que además verifica que no haya doble conteo.
