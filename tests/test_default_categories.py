"""Taxonomía de categorías sugeridas.

Origen: `docs/Categorias_Finanzas_Egresos_e_Ingresos.pdf`. Se siembra el núcleo
(13) al registrarse y se ofrecen las 25 bajo demanda.

Lo que más importa proteger acá es que la operación sea SOLO ADITIVA: hay
cuentas en producción con años de categorías propias, y este endpoint jamás
debe renombrarlas, fusionarlas ni duplicarlas.
"""

import pytest
from sqlmodel import Session, select

from app.database import engine
from app.models.category import Category
from app.utils.default_categories import CORE_CATEGORIES, DEFAULT_CATEGORIES


def _categorias(client, auth, incluir_inactivas=False):
    res = client.get("/categories", headers=auth)
    assert res.status_code == 200, res.text
    return res.json()


def _nombres(cats):
    return {c["name"].lower() for c in cats}


class TestSiembraAlRegistrarse:
    def test_un_usuario_nuevo_llega_con_el_nucleo(self, client, auth):
        cats = _categorias(client, auth)
        nombres = _nombres(cats)

        for c in CORE_CATEGORIES:
            assert c.name.lower() in nombres, f"falta {c.name}"

    def test_el_nucleo_no_trae_las_opcionales(self, client, auth):
        """El PDF advierte "no saturar al usuario": 25 de golpe es saturación."""
        nombres = _nombres(_categorias(client, auth))
        opcionales = [c for c in DEFAULT_CATEGORIES if not c.core]

        assert opcionales, "el fixture de este test no tiene sentido sin opcionales"
        for c in opcionales:
            assert c.name.lower() not in nombres, f"{c.name} no debería sembrarse"

    def test_las_sembradas_son_del_usuario_no_del_sistema(self, client, auth):
        """Deben poder renombrarse y desactivarse: son sugerencias, no
        infraestructura. Si fueran is_system, la UI las bloquearía."""
        cats = _categorias(client, auth)
        vivienda = next(c for c in cats if c["name"] == "Vivienda")

        assert vivienda["is_system"] is False
        assert vivienda["color"] == "indigo"
        assert vivienda["icon"] == "Home"

    def test_una_categoria_sembrada_se_puede_renombrar(self, client, auth):
        cats = _categorias(client, auth)
        vivienda = next(c for c in cats if c["name"] == "Vivienda")

        res = client.put(
            f"/categories/{vivienda['id']}",
            json={"name": "Casa", "type": "expense", "color": "teal", "icon": "Home"},
            headers=auth,
        )

        assert res.status_code == 200, res.text
        assert res.json()["name"] == "Casa"
        assert res.json()["color"] == "teal"


class TestAnadirSugeridas:
    def test_completa_las_que_faltan_sin_duplicar_las_que_hay(self, client, auth):
        antes = _categorias(client, auth)

        res = client.post("/categories/suggested", headers=auth)

        assert res.status_code == 201, res.text
        data = res.json()
        # El usuario ya tenía el núcleo sembrado al registrarse
        assert data["skipped_existing"] == len(CORE_CATEGORIES)
        assert len(data["created"]) == len(DEFAULT_CATEGORIES) - len(CORE_CATEGORIES)

        despues = _categorias(client, auth)
        assert len(despues) == len(antes) + len(data["created"])
        # Ningún nombre repetido
        nombres = [c["name"].lower() for c in despues]
        assert len(nombres) == len(set(nombres))

    def test_llamarlo_dos_veces_no_crea_nada_la_segunda(self, client, auth):
        client.post("/categories/suggested", headers=auth)
        total = len(_categorias(client, auth))

        res = client.post("/categories/suggested", headers=auth)

        assert res.json()["created"] == []
        assert len(_categorias(client, auth)) == total

    def test_respeta_los_nombres_del_usuario_ignorando_tildes(self, client, auth):
        """En producción conviven "Alimentacion" y "Alimentación": sin
        normalizar, esto le crearía un duplicado a quien ya la tiene."""
        # Borro la sembrada y creo la variante sin tilde, como la escribió un
        # usuario real
        cats = _categorias(client, auth)
        sembrada = next(c for c in cats if c["name"] == "Alimentación y mercados")
        client.delete(f"/categories/{sembrada['id']}", headers=auth)
        client.post("/categories", json={"name": "Alimentacion y Mercados", "type": "expense"}, headers=auth)

        client.post("/categories/suggested", headers=auth)

        finales = [c["name"] for c in _categorias(client, auth)]
        assert "Alimentacion y Mercados" in finales
        assert "Alimentación y mercados" not in finales

    def test_no_toca_las_categorias_propias_del_usuario(self, client, auth):
        """La taxonomía nunca cubrirá "Lotes mutata don Gildardo" -- y no debe
        intentarlo. Lo propio se queda intacto."""
        client.post("/categories", json={"name": "Lotes mutata don Gildardo", "type": "expense"}, headers=auth)

        client.post("/categories/suggested", headers=auth)

        propia = [c for c in _categorias(client, auth) if c["name"] == "Lotes mutata don Gildardo"]
        assert len(propia) == 1
        assert propia[0]["is_system"] is False


class TestColor:
    def test_rechaza_un_color_fuera_de_la_paleta(self, client, auth):
        """Se guarda una CLAVE de paleta, no un hex: un hex no puede verse bien
        en tema claro y oscuro a la vez."""
        res = client.post(
            "/categories",
            json={"name": "Prueba", "type": "expense", "color": "#ff0000"},
            headers=auth,
        )
        assert res.status_code == 422

    def test_acepta_una_clave_valida_y_permite_no_poner_color(self, client, auth):
        con = client.post("/categories", json={"name": "Con color", "type": "expense", "color": "sky"}, headers=auth)
        sin = client.post("/categories", json={"name": "Sin color", "type": "expense"}, headers=auth)

        assert con.status_code == 200, con.text
        assert con.json()["color"] == "sky"
        assert sin.status_code == 200, sin.text
        assert sin.json()["color"] is None


class TestRutas:
    def test_suggested_no_lo_captura_la_ruta_de_id(self, client, auth):
        """`/categories/{category_id}` se declara antes; si algún día alguien
        agrega un POST ahí, "suggested" se interpretaría como un id."""
        res = client.post("/categories/suggested", headers=auth)
        assert res.status_code == 201, res.text
