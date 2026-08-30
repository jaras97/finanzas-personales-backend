"""Borrado de transferencias.

Una transferencia son 2 filas que comparten `transfer_group_id`, y AMBAS
llevan `saving_account_id` + `from_account_id`/`to_account_id`. Borrar una
pata tiene que revertir la transferencia completa (las dos cuentas, las dos
filas), no media.
"""


def _balances(client, auth):
    return {a["name"]: a["balance"] for a in client.get("/saving-accounts", headers=auth).json()}


def test_deleting_a_transfer_leg_reverts_the_whole_transfer(client, auth, make_account):
    make_account(name="Origen", balance=1_000_000)
    make_account(name="Destino", balance=0)
    accounts = {a["name"]: a["id"] for a in client.get("/saving-accounts", headers=auth).json()}

    res = client.post(
        "/transactions/transfer",
        json={
            "from_account_id": accounts["Origen"],
            "to_account_id": accounts["Destino"],
            "amount": 300_000,
        },
        headers=auth,
    )
    assert res.status_code == 200, res.text

    after_transfer = _balances(client, auth)
    assert after_transfer["Origen"] == 700_000
    assert after_transfer["Destino"] == 300_000

    legs = client.get(
        "/transactions/with-category", params={"page_size": 50}, headers=auth
    ).json()["items"]
    transfer_legs = [t for t in legs if t["source_type"] == "transfer"]
    assert len(transfer_legs) == 2
    expense_leg = next(t for t in transfer_legs if t["type"] == "expense")

    res = client.delete(f"/transactions/{expense_leg['id']}", headers=auth)
    assert res.status_code == 200, res.text

    # Los saldos deben volver EXACTAMENTE a como estaban antes de transferir.
    after_delete = _balances(client, auth)
    assert after_delete["Origen"] == 1_000_000, (
        f"Origen quedó en {after_delete['Origen']}, se esperaba 1.000.000 "
        "(doble reversión si es 1.300.000)"
    )
    assert after_delete["Destino"] == 0, (
        f"Destino quedó en {after_delete['Destino']}, se esperaba 0 "
        "(pata huérfana si sigue en 300.000)"
    )

    # Y ninguna de las dos patas debe sobrevivir.
    remaining = client.get(
        "/transactions/with-category", params={"page_size": 50}, headers=auth
    ).json()["items"]
    assert [t for t in remaining if t["source_type"] == "transfer"] == []


def test_deleting_the_income_leg_also_reverts_the_whole_transfer(client, auth, make_account):
    make_account(name="Origen", balance=1_000_000)
    make_account(name="Destino", balance=0)
    accounts = {a["name"]: a["id"] for a in client.get("/saving-accounts", headers=auth).json()}

    client.post(
        "/transactions/transfer",
        json={
            "from_account_id": accounts["Origen"],
            "to_account_id": accounts["Destino"],
            "amount": 250_000,
        },
        headers=auth,
    )

    legs = client.get(
        "/transactions/with-category", params={"page_size": 50}, headers=auth
    ).json()["items"]
    income_leg = next(
        t for t in legs if t["source_type"] == "transfer" and t["type"] == "income"
    )

    res = client.delete(f"/transactions/{income_leg['id']}", headers=auth)
    assert res.status_code == 200, res.text

    after = _balances(client, auth)
    assert after["Origen"] == 1_000_000
    assert after["Destino"] == 0


def test_deleting_a_plain_expense_still_works(client, auth, make_account, make_category):
    acc = make_account(name="Cuenta", balance=500_000)
    cat = make_category(type_="expense")
    tx = client.post(
        "/transactions",
        json={
            "amount": 50_000,
            "category_id": cat["id"],
            "description": "Gasto normal",
            "type": "expense",
            "saving_account_id": acc["id"],
        },
        headers=auth,
    ).json()

    assert _balances(client, auth)["Cuenta"] == 450_000
    client.delete(f"/transactions/{tx['id']}", headers=auth)
    assert _balances(client, auth)["Cuenta"] == 500_000
