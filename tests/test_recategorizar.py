"""Higiene de categorías: pendientes, edición y recategorización masiva.

Fase 4 de docs/PLAN_CATEGORIAS_V2.md. Lo que se prueba aquí, en orden de
importancia:

1. Que la invariante I1 (solo las hojas reciben dinero) también se cumpla al
   EDITAR, no solo al crear. Era un agujero real: `PATCH /transactions/{id}`
   validaba el tipo de la categoría pero no que fuera hoja.
2. Que «sin clasificar» signifique lo mismo en todas partes, aunque en la base
   sean dos estados distintos (`category_id IS NULL` y la hoja de sistema
   «Sin categorizar» que usa la importación de CSV).
3. Que la operación masiva aplique lo aplicable en vez de abortar entera, y
   que no pueda tocar los movimientos de otra cuenta.
"""

import datetime as dt

import pytest
from sqlalchemy import text

from app.database import engine


def _hoja_sistema_sin_categorizar(client, auth):
    cats = client.get("/categories?status=all", headers=auth).json()
    return next(c for c in cats if c["name"] == "Sin categorizar")


def _tx_sin_categoria(
    user_id: str,
    account_id: int,
    *,
    tipo="expense",
    monto=1000.0,
    cancelada=False,
    reversa_de=None,
    source_type=None,
) -> int:
    """Inserta un movimiento con `category_id NULL`.

    Va por SQL directo porque `POST /transactions` exige categoría desde hace
    tiempo: este estado solo existe en datos anteriores a esa regla, que es
    justo lo que la bandeja de pendientes tiene que saber recoger.

    Los tres modificadores existen para construir el caso que de verdad pone a
    prueba el filtro de elegibilidad: sin categoría **y** intocable a la vez.
    Por la vía de la API ese estado es inalcanzable.
    """
    with engine.begin() as conn:
        return conn.execute(
            text(
                """
                INSERT INTO transaction
                    (user_id, amount, type, transaction_fee, date, description,
                     is_cancelled, saving_account_id, reversed_transaction_id,
                     source_type)
                VALUES (:u, :a, :t, 0, :d, 'Legado sin categoría', :cancel, :c,
                        :rev, :src)
                RETURNING id
                """
            ),
            {
                "u": user_id, "a": monto, "t": tipo, "d": dt.datetime.utcnow(),
                "c": account_id, "cancel": cancelada, "rev": reversa_de,
                "src": source_type,
            },
        ).scalar_one()


@pytest.fixture
def cuenta(make_account):
    return make_account(name="Bancolombia", balance=5_000_000.0)


class TestEditarRespetaLasHojas:
    def test_no_se_puede_mover_un_movimiento_a_un_grupo(
        self, client, auth, make_category, cuenta
    ):
        hoja = make_category(name="Taller", type_="expense")
        grupo = make_category.group(name="Taller", type_="expense")

        tx = client.post(
            "/transactions",
            json={
                "amount": 1000,
                "type": "expense",
                "category_id": hoja["id"],
                "saving_account_id": cuenta["id"],
                "description": "Cambio de aceite",
            },
            headers=auth,
        ).json()

        res = client.patch(
            f"/transactions/{tx['id']}",
            json={"category_id": grupo["id"]},
            headers=auth,
        )
        assert res.status_code == 400, res.text
        assert "grupo" in res.json()["detail"].lower()

        # Y el movimiento se queda donde estaba.
        actual = client.get("/transactions/with-category", headers=auth).json()["items"]
        assert next(t for t in actual if t["id"] == tx["id"])["category"]["id"] == hoja["id"]

    def test_no_se_puede_mover_un_egreso_a_una_categoria_de_ingreso(
        self, client, auth, make_category, cuenta
    ):
        gasto = make_category(name="Taller", type_="expense")
        ingreso = make_category(name="Bonificaciones", type_="income")

        tx = client.post(
            "/transactions",
            json={
                "amount": 1000,
                "type": "expense",
                "category_id": gasto["id"],
                "saving_account_id": cuenta["id"],
            },
            headers=auth,
        ).json()

        res = client.patch(
            f"/transactions/{tx['id']}",
            json={"category_id": ingreso["id"]},
            headers=auth,
        )
        assert res.status_code == 400, res.text
        detalle = res.json()["detail"]
        assert "egresos" in detalle
        # Nombra el GRUPO, no la hoja «General»: es el único nombre que el
        # usuario ha visto en su pantalla.
        assert "Bonificaciones" in detalle, detalle
        assert "General" not in detalle


class TestContadorDePendientes:
    def test_cuenta_las_dos_formas_de_sin_clasificar(
        self, client, auth, user, cuenta
    ):
        _tx_sin_categoria(user["id"], cuenta["id"])
        sistema = _hoja_sistema_sin_categorizar(client, auth)
        client.post(
            "/transactions",
            json={
                "amount": 2000,
                "type": "expense",
                "category_id": sistema["id"],
                "saving_account_id": cuenta["id"],
                "description": "Importado del banco",
            },
            headers=auth,
        )

        res = client.get("/transactions/uncategorized/count", headers=auth)
        assert res.status_code == 200, res.text
        assert res.json()["count"] == 2

    def test_no_cuenta_lo_que_el_usuario_no_puede_arreglar(
        self, client, auth, user, cuenta
    ):
        """Sin categoría pero intocable no es un pendiente.

        Contarlos mandaría al usuario a una bandeja que nunca podría vaciar:
        la edición rechaza los tres casos, así que por muchas veces que abra el
        aviso el número no bajaría.
        """
        arreglable = _tx_sin_categoria(user["id"], cuenta["id"])
        original = _tx_sin_categoria(user["id"], cuenta["id"])

        _tx_sin_categoria(user["id"], cuenta["id"], cancelada=True)
        _tx_sin_categoria(user["id"], cuenta["id"], reversa_de=original)
        _tx_sin_categoria(user["id"], cuenta["id"], source_type="transfer")
        # Una transferencia vieja, de antes de que existiera `source_type`:
        # el tipo es lo único que la delata, y la edición la rechaza por eso.
        _tx_sin_categoria(user["id"], cuenta["id"], tipo="transfer")

        res = client.get("/transactions/uncategorized/count", headers=auth)
        assert res.json()["count"] == 2, "solo los dos editables son pendientes"

        # Y el listado tiene que decir lo mismo que el contador.
        ids = [
            t["id"]
            for t in client.get(
                "/transactions/with-category",
                params={"uncategorized": "true"},
                headers=auth,
            ).json()["items"]
        ]
        assert sorted(ids) == sorted([arreglable, original])

    def test_el_listado_devuelve_exactamente_lo_contado(
        self, client, auth, user, cuenta
    ):
        for _ in range(3):
            _tx_sin_categoria(user["id"], cuenta["id"])

        listado = client.get(
            "/transactions/with-category",
            params={"uncategorized": "true"},
            headers=auth,
        )
        assert listado.status_code == 200, listado.text
        cuenta_total = client.get(
            "/transactions/uncategorized/count", headers=auth
        ).json()["count"]
        assert listado.json()["total"] == cuenta_total == 3

    def test_el_contador_ignora_el_rango_de_fechas(self, client, auth, user, cuenta):
        """Un pendiente de hace un año tiene que seguir avisando hoy."""
        tx_id = _tx_sin_categoria(user["id"], cuenta["id"])
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE transaction SET date = :d WHERE id = :i"),
                {"d": dt.datetime.utcnow() - dt.timedelta(days=400), "i": tx_id},
            )
        assert client.get("/transactions/uncategorized/count", headers=auth).json()["count"] == 1


class TestRecategorizacionMasiva:
    def test_asigna_a_varios_de_una_vez(self, client, auth, user, cuenta, make_category):
        hoja = make_category(name="Taller", type_="expense")
        ids = [_tx_sin_categoria(user["id"], cuenta["id"]) for _ in range(4)]

        res = client.patch(
            "/transactions/bulk-category",
            json={"transaction_ids": ids, "category_id": hoja["id"]},
            headers=auth,
        )
        assert res.status_code == 200, res.text
        assert res.json() == {"updated": 4, "skipped": []}
        assert client.get("/transactions/uncategorized/count", headers=auth).json()["count"] == 0

    def test_aplica_lo_aplicable_y_explica_lo_que_no(
        self, client, auth, user, cuenta, make_category
    ):
        """Un inelegible entre veinte no puede tumbar los otros diecinueve."""
        hoja = make_category(name="Taller", type_="expense")
        buenas = [_tx_sin_categoria(user["id"], cuenta["id"]) for _ in range(2)]

        ingreso = _tx_sin_categoria(user["id"], cuenta["id"], tipo="income")

        res = client.patch(
            "/transactions/bulk-category",
            json={"transaction_ids": buenas + [ingreso], "category_id": hoja["id"]},
            headers=auth,
        )
        assert res.status_code == 200, res.text
        cuerpo = res.json()
        assert cuerpo["updated"] == 2
        assert [s["id"] for s in cuerpo["skipped"]] == [ingreso]
        motivo = cuerpo["skipped"][0]["reason"]
        assert "no admite ingresos" in motivo
        assert "Taller" in motivo and "General" not in motivo, motivo

    def test_no_toca_los_movimientos_de_otra_cuenta(
        self, client, make_user, make_category, make_account, user, cuenta
    ):
        """El id de otro usuario se reporta como no encontrado, no se aplica."""
        otro = make_user()
        ajena = _tx_sin_categoria(otro["id"], cuenta["id"])

        hoja = make_category(name="Taller", type_="expense")
        propia = _tx_sin_categoria(user["id"], cuenta["id"])

        res = client.patch(
            "/transactions/bulk-category",
            json={"transaction_ids": [propia, ajena], "category_id": hoja["id"]},
            headers=user["headers"],
        )
        assert res.status_code == 200, res.text
        cuerpo = res.json()
        assert cuerpo["updated"] == 1
        assert cuerpo["skipped"] == [{"id": ajena, "reason": "No encontrado"}]

        with engine.begin() as conn:
            sigue = conn.execute(
                text("SELECT category_id FROM transaction WHERE id = :i"), {"i": ajena}
            ).scalar_one()
        assert sigue is None

    def test_rechaza_un_grupo_como_destino(
        self, client, auth, user, cuenta, make_category
    ):
        make_category(name="Taller", type_="expense")
        grupo = make_category.group(name="Taller", type_="expense")
        ids = [_tx_sin_categoria(user["id"], cuenta["id"])]

        res = client.patch(
            "/transactions/bulk-category",
            json={"transaction_ids": ids, "category_id": grupo["id"]},
            headers=auth,
        )
        assert res.status_code == 400, res.text
        assert "grupo" in res.json()["detail"].lower()

    def test_rechaza_una_lista_vacia(self, client, auth, make_category):
        hoja = make_category(name="Taller", type_="expense")
        res = client.patch(
            "/transactions/bulk-category",
            json={"transaction_ids": [], "category_id": hoja["id"]},
            headers=auth,
        )
        assert res.status_code == 400, res.text


class TestResumenNoDuplicaSinCategorizar:
    def test_una_sola_fila_aunque_haya_de_las_dos_formas(
        self, client, auth, user, cuenta
    ):
        """El bug que destapó la Fase 4.

        `category_id IS NULL` y la hoja de sistema son el mismo estado para el
        usuario, pero el desglose los contaba como dos categorías distintas y
        pintaba DOS filas llamadas «Sin categorizar», indistinguibles entre sí.
        """
        _tx_sin_categoria(user["id"], cuenta["id"], monto=1000.0)
        sistema = _hoja_sistema_sin_categorizar(client, auth)
        client.post(
            "/transactions",
            json={
                "amount": 3000,
                "type": "expense",
                "category_id": sistema["id"],
                "saving_account_id": cuenta["id"],
            },
            headers=auth,
        )

        # Hoy en UTC y `tz=UTC`, no `date.today()`: los movimientos se sellan
        # con `utcnow()`, así que mezclar husos deja el test fallando solo de
        # noche en UTC-5. Ver el mismo comentario en test_summary_desglose.
        hoy = dt.datetime.now(dt.timezone.utc).date()
        res = client.get(
            "/summary",
            params={
                "start_date": hoy.replace(day=1).isoformat(),
                "end_date": hoy.isoformat(),
                "tz": "UTC",
            },
            headers=auth,
        )
        assert res.status_code == 200, res.text
        gastos = res.json()["COP"]["expense_by_category"]
        sin_cat = [c for c in gastos if c["category_name"] == "Sin categorizar"]
        assert len(sin_cat) == 1, [c["category_name"] for c in gastos]
        assert sin_cat[0]["total"] == pytest.approx(4000.0)
