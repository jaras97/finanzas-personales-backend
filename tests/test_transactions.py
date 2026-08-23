"""Efectos en saldo de las transacciones.

Es la lógica con más riesgo del proyecto: un error aquí no lanza excepción,
solo deja mal la plata del usuario.
"""


def _balance(client, auth, account_id):
    accounts = client.get("/saving-accounts", headers=auth).json()
    return next(a["balance"] for a in accounts if a["id"] == account_id)


def test_expense_debits_account(client, auth, make_account, make_category):
    acc = make_account(balance=100_000)
    cat = make_category(type_="expense")

    res = client.post(
        "/transactions",
        json={
            "description": "Mercado",
            "amount": 30_000,
            "type": "expense",
            "category_id": cat["id"],
            "saving_account_id": acc["id"],
        },
        headers=auth,
    )
    assert res.status_code == 200, res.text
    assert _balance(client, auth, acc["id"]) == 70_000


def test_income_credits_account(client, auth, make_account, make_category):
    acc = make_account(balance=100_000)
    cat = make_category(name="Sueldo", type_="income")

    res = client.post(
        "/transactions",
        json={
            "description": "Pago",
            "amount": 50_000,
            "type": "income",
            "category_id": cat["id"],
            "saving_account_id": acc["id"],
        },
        headers=auth,
    )
    assert res.status_code == 200, res.text
    assert _balance(client, auth, acc["id"]) == 150_000


def test_expense_beyond_balance_is_rejected(client, auth, make_account, make_category):
    acc = make_account(balance=10_000)
    cat = make_category(type_="expense")

    res = client.post(
        "/transactions",
        json={
            "description": "Muy caro",
            "amount": 50_000,
            "type": "expense",
            "category_id": cat["id"],
            "saving_account_id": acc["id"],
        },
        headers=auth,
    )
    assert res.status_code == 400
    # Lo importante no es el mensaje sino que la cuenta quedó intacta
    assert _balance(client, auth, acc["id"]) == 10_000


def test_expense_fee_is_debited_on_top_of_amount(
    client, auth, make_account, make_category
):
    acc = make_account(balance=100_000)
    cat = make_category(type_="expense")

    res = client.post(
        "/transactions",
        json={
            "description": "Con comisión",
            "amount": 30_000,
            "transaction_fee": 5_000,
            "type": "expense",
            "category_id": cat["id"],
            "saving_account_id": acc["id"],
        },
        headers=auth,
    )
    assert res.status_code == 200, res.text
    assert _balance(client, auth, acc["id"]) == 65_000


def test_income_fee_is_deducted_from_amount(client, auth, make_account, make_category):
    acc = make_account(balance=0)
    cat = make_category(name="Sueldo", type_="income")

    res = client.post(
        "/transactions",
        json={
            "description": "Ingreso con comisión",
            "amount": 10_000,
            "transaction_fee": 1_000,
            "type": "income",
            "category_id": cat["id"],
            "saving_account_id": acc["id"],
        },
        headers=auth,
    )
    assert res.status_code == 200, res.text
    # Se acredita neto (10.000 - 1.000), no el bruto
    assert _balance(client, auth, acc["id"]) == 9_000


def test_closed_account_rejects_transactions(
    client, auth, make_account, make_category
):
    acc = make_account(balance=0)
    client.post(f"/saving-accounts/{acc['id']}/close", headers=auth)
    cat = make_category(name="Sueldo", type_="income")

    res = client.post(
        "/transactions",
        json={
            "description": "A cuenta cerrada",
            "amount": 1_000,
            "type": "income",
            "category_id": cat["id"],
            "saving_account_id": acc["id"],
        },
        headers=auth,
    )
    assert res.status_code == 400


def test_transaction_requires_own_account(
    client, make_user, make_account, make_category
):
    """Una cuenta ajena no debe ser utilizable aunque se conozca su id."""
    victim = make_user()
    victim_acc = client.post(
        "/saving-accounts",
        json={"name": "Ajena", "balance": 500_000, "type": "bank", "currency": "COP"},
        headers=victim["headers"],
    ).json()

    attacker = make_user()
    attacker_cat = client.post(
        "/categories", json={"name": "X", "type": "expense"}, headers=attacker["headers"]
    ).json()

    res = client.post(
        "/transactions",
        json={
            "description": "Gasto sobre cuenta ajena",
            "amount": 1_000,
            "type": "expense",
            "category_id": attacker_cat["id"],
            "saving_account_id": victim_acc["id"],
        },
        headers=attacker["headers"],
    )
    assert res.status_code == 400

    remaining = next(
        a["balance"]
        for a in client.get("/saving-accounts", headers=victim["headers"]).json()
        if a["id"] == victim_acc["id"]
    )
    assert remaining == 500_000


def test_reversal_restores_balance(client, auth, make_account, make_category):
    acc = make_account(balance=100_000)
    cat = make_category(type_="expense")

    tx = client.post(
        "/transactions",
        json={
            "description": "A reversar",
            "amount": 40_000,
            "type": "expense",
            "category_id": cat["id"],
            "saving_account_id": acc["id"],
        },
        headers=auth,
    ).json()
    assert _balance(client, auth, acc["id"]) == 60_000

    res = client.post(
        f"/transactions/{tx['id']}/reverse",
        json={"note": "Cobro duplicado"},
        headers=auth,
    )
    assert res.status_code == 200, res.text
    assert _balance(client, auth, acc["id"]) == 100_000


def test_transaction_cannot_be_reversed_twice(
    client, auth, make_account, make_category
):
    acc = make_account(balance=100_000)
    cat = make_category(type_="expense")
    tx = client.post(
        "/transactions",
        json={
            "description": "Doble reversa",
            "amount": 10_000,
            "type": "expense",
            "category_id": cat["id"],
            "saving_account_id": acc["id"],
        },
        headers=auth,
    ).json()

    first = client.post(
        f"/transactions/{tx['id']}/reverse", json={"note": "a"}, headers=auth
    )
    assert first.status_code == 200
    second = client.post(
        f"/transactions/{tx['id']}/reverse", json={"note": "b"}, headers=auth
    )
    assert second.status_code == 400
    # El saldo solo se restituyó una vez
    assert _balance(client, auth, acc["id"]) == 100_000
