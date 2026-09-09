"""Desglose anidado del Resumen y comparación con el período anterior.

Alimenta el drill-down del donut y la tabla comparativa (Fase 3 de
docs/PLAN_CATEGORIAS_V2.md). Las hojas viajan DENTRO de su grupo en la misma
respuesta para que entrar en una categoría sea instantáneo, sin una petición
por clic.

Lo que se protege: que el total del grupo sea exactamente la suma de sus
hojas, que lo no categorizado no se esconda, y que la variación compare
contra el período correcto.
"""

import datetime as dt

import pytest
from sqlalchemy import text

from app.database import engine


def _cualquier_hoja(client, auth):
    cats = client.get("/categories", headers=auth).json()
    return next(c for c in cats if not c["is_group"] and not c["is_system"])


def _hoy():
    return dt.date.today()


def _summary(client, auth, inicio=None, fin=None):
    inicio = inicio or _hoy()
    fin = fin or _hoy()
    res = client.get(
        f"/summary?start_date={inicio}&end_date={fin}&tz=UTC",
        headers=auth,
    )
    assert res.status_code == 200, res.text
    return res.json()["COP"]


def _gastar(client, auth, cuenta, category_id, monto, cuando=None):
    fecha = cuando or dt.datetime.now(dt.timezone.utc)
    res = client.post(
        "/transactions",
        json={"amount": monto, "type": "expense", "description": "x",
              "category_id": category_id, "saving_account_id": cuenta["id"],
              "date": fecha.isoformat()},
        headers=auth,
    )
    assert res.status_code == 200, res.text
    return res.json()


@pytest.fixture
def transporte(client, auth, make_category):
    """Grupo «Transporte» con dos hojas de verdad."""
    make_category(name="Transporte", type_="expense")
    cats = client.get("/categories?status=all", headers=auth).json()
    grupo = next(c for c in cats if c["name"] == "Transporte" and c["is_group"])
    gasolina = client.post(
        "/categories",
        json={"name": "Gasolina", "type": "expense", "parent_id": grupo["id"]},
        headers=auth,
    ).json()
    peajes = client.post(
        "/categories",
        json={"name": "Peajes", "type": "expense", "parent_id": grupo["id"]},
        headers=auth,
    ).json()
    return grupo, gasolina, peajes


class TestAnidado:
    def test_las_hojas_viajan_dentro_de_su_grupo(
        self, client, auth, make_account, transporte
    ):
        grupo, gasolina, peajes = transporte
        cuenta = make_account(balance=1_000_000)
        _gastar(client, auth, cuenta, gasolina["id"], 70_000)
        _gastar(client, auth, cuenta, peajes["id"], 30_000)

        cop = _summary(client, auth)["expense_by_category"]
        fila = next(c for c in cop if c["category_id"] == grupo["id"])

        assert fila["total"] == 100_000
        assert {h["category_name"] for h in fila["children"]} == {"Gasolina", "Peajes"}
        # Las hojas NO aparecen sueltas en el primer nivel
        assert not any(c["category_name"] in ("Gasolina", "Peajes") for c in cop)

    def test_el_total_del_grupo_es_la_suma_exacta_de_sus_hojas(
        self, client, auth, make_account, transporte
    ):
        """Sin «sin desglosar»: un grupo no recibe movimientos, así que su
        total no puede tener nada que no esté en una hoja."""
        grupo, gasolina, peajes = transporte
        cuenta = make_account(balance=1_000_000)
        _gastar(client, auth, cuenta, gasolina["id"], 70_000)
        _gastar(client, auth, cuenta, peajes["id"], 30_000)

        fila = next(
            c for c in _summary(client, auth)["expense_by_category"]
            if c["category_id"] == grupo["id"]
        )

        assert fila["total"] == sum(h["total"] for h in fila["children"])

    def test_el_porcentaje_de_la_hoja_es_dentro_de_su_grupo(
        self, client, auth, make_account, transporte
    ):
        grupo, gasolina, peajes = transporte
        cuenta = make_account(balance=1_000_000)
        _gastar(client, auth, cuenta, gasolina["id"], 75_000)
        _gastar(client, auth, cuenta, peajes["id"], 25_000)

        fila = next(
            c for c in _summary(client, auth)["expense_by_category"]
            if c["category_id"] == grupo["id"]
        )
        por_nombre = {h["category_name"]: h for h in fila["children"]}

        assert por_nombre["Gasolina"]["percentage"] == 75
        assert por_nombre["Peajes"]["percentage"] == 25

    def test_el_color_del_grupo_viaja_en_la_respuesta(
        self, client, auth, make_account, transporte
    ):
        """Para no cruzar con /categories solo para pintar el donut."""
        grupo, gasolina, _ = transporte
        cuenta = make_account(balance=500_000)
        _gastar(client, auth, cuenta, gasolina["id"], 10_000)

        fila = next(
            c for c in _summary(client, auth)["expense_by_category"]
            if c["category_id"] == grupo["id"]
        )
        assert "color" in fila


class TestSinCategorizar:
    def test_lo_no_categorizado_aparece_como_fila_propia(
        self, client, auth, make_account
    ):
        """Esconderlo convertiría el desglose en una media verdad.

        La API ya no deja crear una transacción sin categoría, así que se
        inserta a mano: es el caso REAL de producción, donde 51 movimientos
        antiguos quedaron con `category_id` nulo.
        """
        cuenta = make_account(balance=500_000)
        tx = _gastar(client, auth, cuenta,
                     _cualquier_hoja(client, auth)["id"], 40_000)
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE transaction SET category_id = NULL WHERE id = :i"),
                {"i": tx["id"]},
            )

        cop = _summary(client, auth)["expense_by_category"]
        fila = [c for c in cop if c["category_name"] == "Sin categorizar"]

        assert len(fila) == 1
        assert fila[0]["total"] == 40_000
        assert fila[0]["category_id"] == 0

    def test_no_se_muestra_bajo_el_grupo_Sistema(self, client, auth, make_account):
        """El grupo Sistema está oculto: «Sistema › Sin categorizar» no le
        dice nada a nadie."""
        cuenta = make_account(balance=500_000)
        cats = client.get("/categories?status=all", headers=auth).json()
        sin_cat = next(c for c in cats if c["name"] == "Sin categorizar")
        _gastar(client, auth, cuenta, sin_cat["id"], 25_000)

        cop = _summary(client, auth)["expense_by_category"]

        assert not any(c["category_name"] == "Sistema" for c in cop)
        assert any(c["category_name"] == "Sin categorizar" for c in cop)


class TestComparacion:
    def test_compara_contra_el_mes_anterior_cuando_el_rango_es_un_mes(
        self, client, auth, make_account, transporte
    ):
        _, gasolina, _ = transporte
        cuenta = make_account(balance=2_000_000)
        hoy = _hoy()
        primero = hoy.replace(day=1)
        # El PRIMER día del mes pasado, a propósito: cae dentro del mes
        # anterior pero FUERA de la ventana "mismos N días hacia atrás".
        # Si el código comparara por duración en vez de por mes de calendario,
        # este gasto no se contaría y el test lo detectaría.
        primero_mes_pasado = (primero - dt.timedelta(days=1)).replace(day=1)

        _gastar(client, auth, cuenta, gasolina["id"], 100_000,
                dt.datetime.combine(primero_mes_pasado, dt.time(12), dt.timezone.utc))
        _gastar(client, auth, cuenta, gasolina["id"], 150_000,
                dt.datetime.combine(primero, dt.time(12), dt.timezone.utc))

        import calendar
        ultimo = hoy.replace(day=calendar.monthrange(hoy.year, hoy.month)[1])
        cop = _summary(client, auth, primero, ultimo)["expense_by_category"]
        hoja = next(
            h for c in cop for h in c["children"] if h["category_name"] == "Gasolina"
        )

        assert hoja["previous_total"] == 100_000
        assert hoja["delta_percentage"] == 50.0   # de 100k a 150k

    def test_sin_base_de_comparacion_la_variacion_es_nula(
        self, client, auth, make_account, transporte
    ):
        """Un «+∞%» no informa: se devuelve None y la interfaz muestra un guion."""
        _, gasolina, _ = transporte
        cuenta = make_account(balance=500_000)
        _gastar(client, auth, cuenta, gasolina["id"], 50_000)

        cop = _summary(client, auth)["expense_by_category"]
        hoja = next(
            h for c in cop for h in c["children"] if h["category_name"] == "Gasolina"
        )

        assert hoja["previous_total"] == 0
        assert hoja["delta_percentage"] is None
