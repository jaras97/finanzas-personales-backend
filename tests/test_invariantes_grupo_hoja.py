"""Invariantes del modelo grupo/hoja.

El primer nivel es un GRUPO y nunca recibe dinero; las transacciones,
presupuestos, reglas y recurrentes van siempre a una HOJA. Ver
docs/PLAN_CATEGORIAS_V2.md.

Si una de estas se rompe, el sistema empieza a dar números que no cuadran:
son el contrato del que se deriva todo lo demás (rollup del resumen,
presupuesto derivado, reglas de importación).
"""

import datetime as dt

import pytest


def _cats(client, auth, status="active"):
    res = client.get(f"/categories?status={status}", headers=auth)
    assert res.status_code == 200, res.text
    return res.json()


def _grupo(client, auth, nombre):
    return next(c for c in _cats(client, auth, "all") if c["name"] == nombre and c["is_group"])


@pytest.fixture
def grupo_y_hoja(client, auth, make_category):
    """Crea "Taller" y devuelve (grupo, hoja General)."""
    hoja = make_category(name="Taller", type_="expense")
    grupo = _grupo(client, auth, "Taller")
    return grupo, hoja


class TestFormaDelArbol:
    def test_crear_una_categoria_crea_grupo_y_hoja(self, client, auth, grupo_y_hoja):
        grupo, hoja = grupo_y_hoja
        assert grupo["is_group"] is True
        assert grupo["parent_id"] is None
        assert hoja["parent_id"] == grupo["id"]
        assert hoja["name"] == "General"
        # El grupo dice dónde registrar: sin esto la interfaz no podría
        # colapsarlo en una sola línea.
        assert grupo["default_leaf_id"] == hoja["id"]

    def test_las_de_sistema_son_hojas_de_un_grupo_oculto(self, client, auth):
        cats = _cats(client, auth, "all")
        sistema = [c for c in cats if c["is_system"]]
        grupo = next(c for c in sistema if c["name"] == "Sistema")

        operativas = [c for c in sistema if c["name"] != "Sistema"]
        assert operativas, "deberían existir Transferencia, Sin categorizar, etc."
        for c in operativas:
            assert c["parent_id"] == grupo["id"], f"{c['name']} quedó fuera del grupo Sistema"

    def test_ningun_grupo_queda_sin_hojas(self, client, auth, make_category):
        make_category(name="Taller")
        cats = _cats(client, auth, "all")
        con_padre = {c["parent_id"] for c in cats if c["parent_id"]}

        for g in [c for c in cats if c["is_group"] and c["is_active"]]:
            assert g["id"] in con_padre, f"«{g['name']}» quedó sin ninguna hoja"

    def test_agregar_una_hoja_real_retira_la_General_sin_usar(
        self, client, auth, grupo_y_hoja
    ):
        """Si no, cada grupo quedaría como «General + lo que importa»."""
        grupo, _ = grupo_y_hoja
        client.post(
            "/categories",
            json={"name": "Repuestos", "type": "expense", "parent_id": grupo["id"]},
            headers=auth,
        )

        hojas = [c["name"] for c in _cats(client, auth) if c["parent_id"] == grupo["id"]]
        assert hojas == ["Repuestos"]

    def test_la_General_con_movimientos_no_se_retira(
        self, client, auth, make_account, grupo_y_hoja
    ):
        grupo, hoja = grupo_y_hoja
        cuenta = make_account(balance=500_000)
        client.post(
            "/transactions",
            json={"amount": 10_000, "type": "expense", "description": "x",
                  "category_id": hoja["id"], "saving_account_id": cuenta["id"],
                  "date": dt.datetime.now(dt.timezone.utc).isoformat()},
            headers=auth,
        )

        client.post(
            "/categories",
            json={"name": "Repuestos", "type": "expense", "parent_id": grupo["id"]},
            headers=auth,
        )

        hojas = sorted(c["name"] for c in _cats(client, auth) if c["parent_id"] == grupo["id"])
        assert hojas == ["General", "Repuestos"]


class TestI1_SoloLasHojasReciben:
    def _crear_tx(self, client, auth, cuenta, category_id):
        return client.post(
            "/transactions",
            json={"amount": 25_000, "type": "expense", "description": "prueba",
                  "category_id": category_id, "saving_account_id": cuenta["id"],
                  "date": dt.datetime.now(dt.timezone.utc).isoformat()},
            headers=auth,
        )

    def test_una_transaccion_a_un_grupo_se_rechaza(
        self, client, auth, make_account, grupo_y_hoja
    ):
        grupo, _ = grupo_y_hoja
        cuenta = make_account(balance=500_000)

        res = self._crear_tx(client, auth, cuenta, grupo["id"])

        assert res.status_code == 400
        assert "grupo" in res.json()["detail"]
        # El mensaje tiene que decir a dónde ir, no solo que está mal
        assert "subcategoría" in res.json()["detail"]

    def test_a_la_hoja_sí_se_permite(self, client, auth, make_account, grupo_y_hoja):
        """Control: sin esto, rechazarlo todo pasaría el test anterior."""
        _, hoja = grupo_y_hoja
        cuenta = make_account(balance=500_000)

        res = self._crear_tx(client, auth, cuenta, hoja["id"])

        assert res.status_code == 200, res.text

    def test_una_regla_a_un_grupo_se_rechaza(self, client, auth, grupo_y_hoja):
        """Crítico de cara a la importación bancaria: una regla ambigua
        archiva mal a escala."""
        grupo, _ = grupo_y_hoja
        res = client.post(
            "/category-rules",
            json={"category_id": grupo["id"], "match_text": "taller"},
            headers=auth,
        )
        assert res.status_code == 400
        assert "grupo" in res.json()["detail"]

    def test_un_recurrente_a_un_grupo_se_rechaza(
        self, client, auth, make_account, grupo_y_hoja
    ):
        grupo, _ = grupo_y_hoja
        cuenta = make_account(balance=500_000)
        res = client.post(
            "/recurring-transactions",
            json={"description": "arriendo", "amount": 100_000, "type": "expense",
                  "category_id": grupo["id"], "saving_account_id": cuenta["id"],
                  "frequency": "monthly",
                  "next_run": dt.date.today().isoformat()},
            headers=auth,
        )
        assert res.status_code == 400
        assert "grupo" in res.json()["detail"]


class TestI2_PresupuestoDerivado:
    def test_un_presupuesto_a_un_grupo_se_rechaza(self, client, auth, grupo_y_hoja):
        grupo, _ = grupo_y_hoja
        res = client.post(
            "/budgets",
            json={"category_id": grupo["id"], "amount": 100_000, "currency": "COP",
                  "month": dt.date.today().strftime("%Y-%m")},
            headers=auth,
        )
        assert res.status_code == 400
        assert "grupo" in res.json()["detail"]

    def test_el_gasto_de_una_hoja_no_se_cuenta_dos_veces(
        self, client, auth, make_account, grupo_y_hoja
    ):
        """El bug que este modelo mata: antes, presupuestar el padre y la hija
        hacía que los mismos pesos contaran en ambos presupuestos."""
        grupo, _ = grupo_y_hoja
        cuenta = make_account(balance=1_000_000)
        # Dos hojas de verdad: la "General" desaparece al crear la primera real
        # (ver test_agregar_una_hoja_real_retira_la_General_sin_usar).
        repuestos = client.post(
            "/categories",
            json={"name": "Repuestos", "type": "expense", "parent_id": grupo["id"]},
            headers=auth,
        ).json()
        pintura = client.post(
            "/categories",
            json={"name": "Pintura", "type": "expense", "parent_id": grupo["id"]},
            headers=auth,
        ).json()
        otra = repuestos
        hoja = pintura
        mes = dt.date.today().strftime("%Y-%m")
        for cid in (hoja["id"], otra["id"]):
            client.post("/budgets",
                        json={"category_id": cid, "amount": 200_000, "currency": "COP", "month": mes},
                        headers=auth)
        client.post(
            "/transactions",
            json={"amount": 50_000, "type": "expense", "description": "x",
                  "category_id": otra["id"], "saving_account_id": cuenta["id"],
                  "date": dt.datetime.now(dt.timezone.utc).isoformat()},
            headers=auth,
        )

        respuesta = client.get(f"/budgets?month={mes}", headers=auth).json()
        presupuestos = respuesta["items"]
        gastado = {b["category_id"]: b["spent"] for b in presupuestos}

        assert gastado[otra["id"]] == 50_000
        # La hermana no hereda el gasto de nadie
        assert gastado[hoja["id"]] == 0
        # Y el total no infla: 50.000 una sola vez
        assert sum(gastado.values()) == 50_000

        # El grupo es DERIVADO: suma exacta de sus hojas, ni una vez más.
        grupo_fila = next(g for g in respuesta["groups"] if g["category_id"] == grupo["id"])
        assert grupo_fila["amount"] == 400_000   # 200.000 + 200.000
        assert grupo_fila["spent"] == 50_000
        assert grupo_fila["leaf_count"] == 2


class TestI3_UnGrupoSiempreTieneHojas:
    def test_no_se_puede_quitar_la_ultima_hoja(self, client, auth, grupo_y_hoja):
        _, hoja = grupo_y_hoja

        res = client.delete(f"/categories/{hoja['id']}", headers=auth)

        assert res.status_code == 400
        assert "única subcategoría" in res.json()["detail"]

    def test_quitar_el_grupo_arrastra_a_sus_hojas(self, client, auth, grupo_y_hoja):
        """Es lo que el usuario quiere decir: no usa esa categoría."""
        grupo, hoja = grupo_y_hoja

        res = client.delete(f"/categories/{grupo['id']}", headers=auth)

        assert res.status_code == 200, res.text
        cats = {c["id"]: c for c in _cats(client, auth, "all")}
        assert cats[grupo["id"]]["is_active"] is False
        assert cats[hoja["id"]]["is_active"] is False

    def test_no_se_quita_un_grupo_con_movimientos(
        self, client, auth, make_account, grupo_y_hoja
    ):
        grupo, hoja = grupo_y_hoja
        cuenta = make_account(balance=500_000)
        client.post(
            "/transactions",
            json={"amount": 10_000, "type": "expense", "description": "x",
                  "category_id": hoja["id"], "saving_account_id": cuenta["id"],
                  "date": dt.datetime.now(dt.timezone.utc).isoformat()},
            headers=auth,
        )

        res = client.delete(f"/categories/{grupo['id']}", headers=auth)

        assert res.status_code == 400
        assert "movimientos" in res.json()["detail"]

    def test_una_hoja_no_puede_subir_a_primer_nivel(self, client, auth, grupo_y_hoja):
        """Se convertiría en un grupo sin hojas."""
        _, hoja = grupo_y_hoja

        res = client.put(
            f"/categories/{hoja['id']}",
            json={"name": "General", "type": "expense", "parent_id": None},
            headers=auth,
        )

        assert res.status_code == 400
        assert "necesita un grupo" in res.json()["detail"]
