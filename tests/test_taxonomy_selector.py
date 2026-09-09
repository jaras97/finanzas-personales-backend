"""Selector de taxonomía.

Reemplaza al antiguo `POST /categories/suggested`, que creaba doce categorías
de un clic sin avisar. Acá el usuario envía el conjunto completo que quiere
activo y el backend calcula el diff.

Lo que más importa proteger:
  - que sea ATÓMICO (un fallo a medias dejaría categorías huérfanas),
  - que NUNCA quite una categoría con movimientos,
  - que no toque las categorías propias del usuario,
  - y que la ruta no la capture `/categories/{category_id}`.
"""

import datetime as dt

import pytest

from app.utils.default_categories import CORE_CATEGORIES, DEFAULT_SUBCATEGORIES


def _taxonomia(client, auth):
    res = client.get("/categories/taxonomy", headers=auth)
    assert res.status_code == 200, res.text
    return res.json()


def _todos_los_items(tax):
    salida = []
    for b in tax["blocks"]:
        for it in b["items"]:
            salida.append(it)
            salida.extend(it["children"])
    return salida


def _aplicar(client, auth, claves):
    res = client.put("/categories/taxonomy", json={"selected": list(claves)}, headers=auth)
    assert res.status_code == 200, res.text
    return res.json()


class TestLectura:
    def test_devuelve_el_catalogo_completo_agrupado(self, client, auth):
        tax = _taxonomia(client, auth)

        assert [b["id"] for b in tax["blocks"]] == [
            "fijos", "variables", "metas", "ocasionales", "ingresos"
        ]
        items = _todos_los_items(tax)
        assert len(items) == 25 + len(DEFAULT_SUBCATEGORIES)

    def test_marca_como_presentes_las_que_ya_tiene(self, client, auth):
        """El usuario nuevo llega con el núcleo sembrado: debe verse marcado,
        no ofrecérsele crear lo que ya tiene."""
        items = {i["key"]: i for i in _todos_los_items(_taxonomia(client, auth))}

        for c in CORE_CATEGORIES:
            assert items[c.key]["state"] == "present", c.name
        # Ninguna subcategoría se siembra sola
        assert all(
            items[s.key]["state"] == "absent" for s in DEFAULT_SUBCATEGORIES
        )

    def test_reconoce_una_categoria_escrita_sin_tildes(self, client, auth):
        """En producción conviven "Alimentacion" y "Alimentación"."""
        items = {i["key"]: i for i in _todos_los_items(_taxonomia(client, auth))}
        cat_id = items["alimentacion-y-mercados"]["category_id"]
        client.put(
            f"/categories/{cat_id}",
            json={"name": "Alimentacion y Mercados", "type": "expense"},
            headers=auth,
        )

        items = {i["key"]: i for i in _todos_los_items(_taxonomia(client, auth))}

        assert items["alimentacion-y-mercados"]["state"] == "present"


class TestAplicar:
    def test_crea_solo_lo_que_falta(self, client, auth):
        tax = _taxonomia(client, auth)
        actuales = [i["key"] for i in _todos_los_items(tax) if i["state"] == "present"]

        res = _aplicar(client, auth, actuales + ["vivienda/arriendo", "vivienda/hipoteca"])

        assert res["created"] == 2
        assert res["deactivated"] == 0

    def test_desmarcar_desactiva_y_es_reversible(self, client, auth):
        tax = _taxonomia(client, auth)
        presentes = [i["key"] for i in _todos_los_items(tax) if i["state"] == "present"]
        sin_mascotas = [k for k in presentes if k != "suscripciones-digitales"]

        r1 = _aplicar(client, auth, sin_mascotas)
        assert r1["deactivated"] == 1

        items = {i["key"]: i for i in _todos_los_items(_taxonomia(client, auth))}
        assert items["suscripciones-digitales"]["state"] == "inactive"

        # Volver a marcarla la reactiva: no se creó una duplicada
        r2 = _aplicar(client, auth, presentes)
        assert r2["reactivated"] == 1
        assert r2["created"] == 0

    def test_nunca_quita_una_categoria_con_movimientos(
        self, client, auth, make_account
    ):
        """La propiedad de seguridad del selector."""
        cuenta = make_account(balance=1_000_000)
        items = {i["key"]: i for i in _todos_los_items(_taxonomia(client, auth))}
        grupo_id = items["transporte"]["category_id"]
        # El movimiento va a una HOJA: el grupo no los recibe (I1). El selector
        # tiene que bloquear igualmente el grupo, porque quitarlo arrastraría
        # una hoja con movimientos.
        cats = client.get("/categories?status=all", headers=auth).json()
        hoja = next(c for c in cats if c["parent_id"] == grupo_id and c["is_active"])
        client.post(
            "/transactions",
            json={
                "amount": 50_000, "type": "expense", "description": "taxi",
                "category_id": hoja["id"], "saving_account_id": cuenta["id"],
                "date": dt.datetime.now(dt.timezone.utc).isoformat(),
            },
            headers=auth,
        )

        res = _aplicar(client, auth, [])  # desmarcar TODO

        assert res["deactivated"] >= 1
        assert any("Transporte" in s for s in res["skipped"])
        items = {i["key"]: i for i in _todos_los_items(_taxonomia(client, auth))}
        assert items["transporte"]["state"] == "present"
        assert items["transporte"]["locked"] is True
        assert "movimiento" in items["transporte"]["locked_reason"]

    def test_una_hija_sin_su_padre_no_se_crea_huerfana(self, client, auth):
        tax = _taxonomia(client, auth)
        presentes = [i["key"] for i in _todos_los_items(tax) if i["state"] == "present"]
        # "Mascotas" no está en el núcleo, así que su hija no tiene dónde colgarse
        sin_padre = [k for k in presentes] + ["mascotas/veterinario"]

        res = _aplicar(client, auth, sin_padre)

        assert res["created"] == 0
        assert any("Mascotas" in s for s in res["skipped"])

    def test_crea_padre_e_hija_en_la_misma_pasada(self, client, auth):
        tax = _taxonomia(client, auth)
        presentes = [i["key"] for i in _todos_los_items(tax) if i["state"] == "present"]

        res = _aplicar(client, auth, presentes + ["mascotas", "mascotas/veterinario"])

        assert res["created"] == 2
        assert res["skipped"] == []
        items = {i["key"]: i for i in _todos_los_items(_taxonomia(client, auth))}
        assert items["mascotas/veterinario"]["state"] == "present"

    def test_no_toca_las_categorias_propias_del_usuario(self, client, auth):
        """La taxonomía nunca cubrirá "Lotes mutata don Gildardo"."""
        propia = client.post(
            "/categories", json={"name": "Lotes mutata don Gildardo", "type": "expense"},
            headers=auth,
        ).json()

        _aplicar(client, auth, [])  # desmarcar todo

        cats = client.get("/categories?status=all", headers=auth).json()
        mia = next(c for c in cats if c["id"] == propia["id"])
        assert mia["is_active"] is True

    def test_las_de_sistema_quedan_fuera_del_alcance(self, client, auth):
        """Desmarcar todo no toca Transferencia, Sin categorizar, etc.

        Ojo con lo que este test prueba de verdad: las de sistema sobreviven
        porque **no están en la taxonomía**, así que el selector nunca las
        encuentra. El guardia `existente.is_system` del endpoint es defensivo y
        hoy inalcanzable -- quitarlo no hace fallar ningún test, y así lo
        confirmó una mutación. Se deja como red por si algún día una entrada de
        la taxonomía coincidiera de nombre con una de sistema.
        """
        _aplicar(client, auth, [])

        cats = client.get("/categories?status=all", headers=auth).json()
        sistema = [c for c in cats if c["is_system"]]
        assert sistema and all(c["is_active"] for c in sistema)


class TestRutas:
    def test_taxonomy_no_lo_captura_la_ruta_de_id(self, client, auth):
        """`PUT /categories/{category_id}` se declara ANTES que este endpoint.
        Es el mismo patrón que dejó inalcanzable a /subscriptions/admin/me."""
        res = client.put("/categories/taxonomy", json={"selected": []}, headers=auth)
        assert res.status_code == 200, res.text

    def test_requiere_autenticacion(self, client):
        assert client.get("/categories/taxonomy").status_code == 401
        assert client.put("/categories/taxonomy", json={"selected": []}).status_code == 401
