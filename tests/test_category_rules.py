"""Reglas de categorización automática.

Texto-contiene, sin distinguir mayúsculas, sin regex -- v1 deliberadamente
simple. Se evalúan en orden de prioridad ascendente, gana la primera que
matchea. Se usan desde /category-rules/apply (sobre transacciones ya
existentes sin categorizar) y desde el preview de importación de CSV.
"""


def test_create_rule_assigns_incrementing_priority(client, auth, make_category):
    cat = make_category(name="Streaming", type_="expense")
    r1 = client.post("/category-rules", json={"category_id": cat["id"], "match_text": "netflix"}, headers=auth)
    r2 = client.post("/category-rules", json={"category_id": cat["id"], "match_text": "spotify"}, headers=auth)
    assert r1.status_code == 200, r1.text
    assert r2.json()["priority"] > r1.json()["priority"]


def test_list_rules_ordered_by_priority(client, auth, make_category):
    cat = make_category(type_="expense")
    client.post("/category-rules", json={"category_id": cat["id"], "match_text": "b"}, headers=auth)
    client.post("/category-rules", json={"category_id": cat["id"], "match_text": "a"}, headers=auth)
    listed = client.get("/category-rules", headers=auth).json()
    assert [r["match_text"] for r in listed] == ["b", "a"]


def test_update_rule_can_reorder_and_rename(client, auth, make_category):
    cat = make_category(type_="expense")
    rule = client.post(
        "/category-rules", json={"category_id": cat["id"], "match_text": "uber"}, headers=auth
    ).json()
    res = client.put(
        f"/category-rules/{rule['id']}",
        json={"match_text": "uber eats", "priority": 0},
        headers=auth,
    )
    assert res.status_code == 200, res.text
    assert res.json()["match_text"] == "uber eats"
    assert res.json()["priority"] == 0


def test_delete_rule(client, auth, make_category):
    cat = make_category(type_="expense")
    rule = client.post(
        "/category-rules", json={"category_id": cat["id"], "match_text": "uber"}, headers=auth
    ).json()
    res = client.delete(f"/category-rules/{rule['id']}", headers=auth)
    assert res.status_code == 200
    assert client.get("/category-rules", headers=auth).json() == []


def test_first_matching_rule_wins_by_priority(client, auth, make_category):
    general = make_category(name="Transporte", type_="expense")
    specific = make_category(name="Uber", type_="expense")

    # "uber" creada primero -> prioridad menor -> debería ganar aunque
    # "transporte" también matcheara la descripción "Viaje uber centro"
    client.post("/category-rules", json={"category_id": general["id"], "match_text": "viaje"}, headers=auth)
    client.post("/category-rules", json={"category_id": specific["id"], "match_text": "uber"}, headers=auth)

    rules = client.get("/category-rules", headers=auth).json()
    assert rules[0]["match_text"] == "viaje"


def test_apply_rules_updates_existing_uncategorized_transactions(
    client, auth, make_account, make_category
):
    acc = make_account()
    netflix_cat = make_category(name="Streaming", type_="expense")

    # Transacción manual sin categoría explícita -> cae en "Sin categorizar"
    # por defecto en el flujo real solo vía import; acá la forzamos directo
    # apuntando a la categoría de sistema para simular ese estado.
    uncategorized = next(
        c for c in client.get("/categories", params={"status": "all"}, headers=auth).json()
        if c.get("system_key") == "uncategorized"
    )
    tx = client.post(
        "/transactions",
        json={
            "amount": 45900,
            "category_id": uncategorized["id"],
            "description": "Cargo Netflix mensual",
            "type": "expense",
            "saving_account_id": acc["id"],
        },
        headers=auth,
    ).json()

    client.post(
        "/category-rules", json={"category_id": netflix_cat["id"], "match_text": "netflix"}, headers=auth
    )

    res = client.post("/category-rules/apply", headers=auth)
    assert res.status_code == 200, res.text
    assert res.json()["updated"] == 1

    updated = client.get("/transactions/with-category", headers=auth).json()["items"]
    assert updated[0]["id"] == tx["id"]
    assert updated[0]["category"]["id"] == netflix_cat["id"]


def test_apply_rules_is_noop_without_rules(client, auth):
    res = client.post("/category-rules/apply", headers=auth)
    assert res.json()["updated"] == 0


def test_inactive_rule_is_not_applied(client, auth, make_account, make_category):
    acc = make_account()
    cat = make_category(name="Streaming", type_="expense")
    uncategorized = next(
        c for c in client.get("/categories", params={"status": "all"}, headers=auth).json()
        if c.get("system_key") == "uncategorized"
    )
    client.post(
        "/transactions",
        json={
            "amount": 1000,
            "category_id": uncategorized["id"],
            "description": "Netflix",
            "type": "expense",
            "saving_account_id": acc["id"],
        },
        headers=auth,
    )
    rule = client.post(
        "/category-rules", json={"category_id": cat["id"], "match_text": "netflix"}, headers=auth
    ).json()
    client.put(f"/category-rules/{rule['id']}", json={"is_active": False}, headers=auth)

    res = client.post("/category-rules/apply", headers=auth)
    assert res.json()["updated"] == 0


def test_apply_rules_also_covers_transactions_with_null_category(
    client, auth, make_account, make_category, session
):
    """«Sin categorizar» son DOS estados y `apply` solo cubría uno.

    Los movimientos manuales anteriores a que la categoría fuera obligatoria
    tienen `category_id IS NULL`; el import de CSV, en cambio, deja lo suyo en
    la hoja de sistema. `apply` miraba solo la hoja, así que crear una regla y
    pulsar «aplicar a existentes» no tocaba los manuales viejos -- que son
    justo los que llenan la bandeja de pendientes -- sin ningún error visible.

    Ese estado solo se alcanza por SQL directo: la API ya exige categoría.
    """
    from sqlalchemy import text

    acc = make_account()
    destino = make_category(name="Domicilios", type_="expense")
    otra = make_category(name="Otra cosa", type_="expense")

    tx = client.post(
        "/transactions",
        json={
            "amount": 32000,
            "category_id": otra["id"],
            "description": "RAPPI*BOGOTA 4471",
            "type": "expense",
            "saving_account_id": acc["id"],
        },
        headers=auth,
    ).json()

    session.execute(
        text("UPDATE transaction SET category_id = NULL WHERE id = :id"), {"id": tx["id"]}
    )
    session.commit()

    client.post(
        "/category-rules",
        json={"category_id": destino["id"], "match_text": "rappi"},
        headers=auth,
    )

    res = client.post("/category-rules/apply", headers=auth)
    assert res.status_code == 200, res.text
    assert res.json()["updated"] == 1

    items = client.get("/transactions/with-category", headers=auth).json()["items"]
    actualizada = next(i for i in items if i["id"] == tx["id"])
    assert actualizada["category"]["id"] == destino["id"]


def test_apply_rules_does_not_touch_already_categorized(
    client, auth, make_account, make_category
):
    """El contrapeso del test anterior: ensanchar el filtro no puede llevarse
    por delante lo que el usuario ya clasificó a mano."""
    acc = make_account()
    elegida = make_category(name="Mercado", type_="expense")
    destino = make_category(name="Domicilios", type_="expense")

    tx = client.post(
        "/transactions",
        json={
            "amount": 32000,
            "category_id": elegida["id"],
            "description": "RAPPI*BOGOTA 4471",
            "type": "expense",
            "saving_account_id": acc["id"],
        },
        headers=auth,
    ).json()

    client.post(
        "/category-rules",
        json={"category_id": destino["id"], "match_text": "rappi"},
        headers=auth,
    )

    assert client.post("/category-rules/apply", headers=auth).json()["updated"] == 0

    items = client.get("/transactions/with-category", headers=auth).json()["items"]
    actualizada = next(i for i in items if i["id"] == tx["id"])
    assert actualizada["category"]["id"] == elegida["id"]
