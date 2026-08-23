"""Transferencias entre cuentas (incluida conversión de moneda) y deudas."""


def _balances(client, auth):
    return {a["id"]: a["balance"] for a in client.get("/saving-accounts", headers=auth).json()}


# --- Transferencias ---------------------------------------------------------


def test_transfer_same_currency_moves_the_amount(client, auth, make_account):
    origin = make_account(name="Origen", balance=500_000)
    dest = make_account(name="Destino", balance=0)

    res = client.post(
        "/transactions/transfer",
        json={
            "amount": 200_000,
            "description": "Traslado",
            "from_account_id": origin["id"],
            "to_account_id": dest["id"],
        },
        headers=auth,
    )
    assert res.status_code == 200, res.text

    b = _balances(client, auth)
    assert b[origin["id"]] == 300_000
    assert b[dest["id"]] == 200_000


def test_transfer_applies_exchange_rate(client, auth, make_account):
    """Cross-currency: sale el monto original, entra el convertido."""
    cop = make_account(name="COP", balance=1_000_000, currency="COP")
    usd = make_account(name="USD", balance=0, currency="USD")

    res = client.post(
        "/transactions/transfer",
        json={
            "amount": 400_000,
            "description": "COP a USD",
            "from_account_id": cop["id"],
            "to_account_id": usd["id"],
            "exchange_rate": 0.00025,
        },
        headers=auth,
    )
    assert res.status_code == 200, res.text

    b = _balances(client, auth)
    assert b[cop["id"]] == 600_000
    assert b[usd["id"]] == 100.0  # 400.000 * 0,00025


def test_cross_currency_transfer_requires_a_rate(client, auth, make_account):
    cop = make_account(name="COP", balance=1_000_000, currency="COP")
    usd = make_account(name="USD", balance=0, currency="USD")

    res = client.post(
        "/transactions/transfer",
        json={
            "amount": 100_000,
            "description": "Sin tasa",
            "from_account_id": cop["id"],
            "to_account_id": usd["id"],
        },
        headers=auth,
    )
    assert res.status_code == 400
    assert _balances(client, auth)[cop["id"]] == 1_000_000


def test_transfer_fee_is_charged_to_origin(client, auth, make_account):
    origin = make_account(name="Origen", balance=500_000)
    dest = make_account(name="Destino", balance=0)

    client.post(
        "/transactions/transfer",
        json={
            "amount": 100_000,
            "transaction_fee": 5_000,
            "description": "Con comisión",
            "from_account_id": origin["id"],
            "to_account_id": dest["id"],
        },
        headers=auth,
    )

    b = _balances(client, auth)
    assert b[origin["id"]] == 395_000  # 100.000 + 5.000 de comisión
    assert b[dest["id"]] == 100_000  # el destino recibe íntegro


def test_transfer_beyond_balance_is_rejected(client, auth, make_account):
    origin = make_account(name="Origen", balance=50_000)
    dest = make_account(name="Destino", balance=0)

    res = client.post(
        "/transactions/transfer",
        json={
            "amount": 100_000,
            "description": "Sin fondos",
            "from_account_id": origin["id"],
            "to_account_id": dest["id"],
        },
        headers=auth,
    )
    assert res.status_code == 400
    b = _balances(client, auth)
    assert b[origin["id"]] == 50_000 and b[dest["id"]] == 0


def test_transfer_to_same_account_is_rejected(client, auth, make_account):
    acc = make_account(balance=100_000)
    res = client.post(
        "/transactions/transfer",
        json={
            "amount": 1_000,
            "description": "A sí misma",
            "from_account_id": acc["id"],
            "to_account_id": acc["id"],
        },
        headers=auth,
    )
    assert res.status_code == 400


# --- Deudas -----------------------------------------------------------------


def _make_debt(client, auth, **overrides):
    payload = {
        "name": "Préstamo",
        "total_amount": 1_000_000,
        "interest_rate": 10.0,
        "currency": "COP",
        "kind": "loan",
    }
    payload.update(overrides)
    res = client.post("/debts", json=payload, headers=auth)
    assert res.status_code == 200, res.text
    return res.json()


def test_paying_debt_reduces_both_debt_and_account(client, auth, make_account):
    acc = make_account(balance=500_000)
    debt = _make_debt(client, auth)

    res = client.post(
        f"/debts/{debt['id']}/pay",
        json={"amount": 300_000, "saving_account_id": acc["id"]},
        headers=auth,
    )
    assert res.status_code == 200, res.text

    assert _balances(client, auth)[acc["id"]] == 200_000
    remaining = next(d for d in client.get("/debts", headers=auth).json() if d["id"] == debt["id"])
    assert remaining["total_amount"] == 700_000


def test_payment_cannot_exceed_the_debt(client, auth, make_account):
    acc = make_account(balance=5_000_000)
    debt = _make_debt(client, auth, total_amount=100_000)

    res = client.post(
        f"/debts/{debt['id']}/pay",
        json={"amount": 500_000, "saving_account_id": acc["id"]},
        headers=auth,
    )
    assert res.status_code == 400
    assert _balances(client, auth)[acc["id"]] == 5_000_000


def test_payment_requires_matching_currency(client, auth, make_account):
    usd_account = make_account(name="USD", balance=1_000, currency="USD")
    cop_debt = _make_debt(client, auth, currency="COP")

    res = client.post(
        f"/debts/{cop_debt['id']}/pay",
        json={"amount": 100, "saving_account_id": usd_account["id"]},
        headers=auth,
    )
    assert res.status_code == 400


def test_loan_closes_itself_when_fully_paid(client, auth, make_account):
    acc = make_account(balance=1_000_000)
    debt = _make_debt(client, auth, total_amount=200_000, kind="loan")

    client.post(
        f"/debts/{debt['id']}/pay",
        json={"amount": 200_000, "saving_account_id": acc["id"]},
        headers=auth,
    )

    updated = next(d for d in client.get("/debts", headers=auth).json() if d["id"] == debt["id"])
    assert updated["total_amount"] == 0
    assert updated["status"] == "closed"


def test_credit_card_stays_open_at_zero(client, auth, make_account):
    """A diferencia de un préstamo, una tarjeta en cero sigue usándose."""
    acc = make_account(balance=1_000_000)
    card = _make_debt(client, auth, name="Visa", total_amount=200_000, kind="credit_card")

    client.post(
        f"/debts/{card['id']}/pay",
        json={"amount": 200_000, "saving_account_id": acc["id"]},
        headers=auth,
    )

    updated = next(d for d in client.get("/debts", headers=auth).json() if d["id"] == card["id"])
    assert updated["total_amount"] == 0
    assert updated["status"] == "active"


def test_card_purchase_increases_debt_without_touching_accounts(
    client, auth, make_account, make_category
):
    acc = make_account(balance=500_000)
    card = _make_debt(client, auth, name="Visa", total_amount=0, kind="credit_card")
    cat = make_category(type_="expense")

    res = client.post(
        f"/debts/{card['id']}/purchase",
        json={"amount": 80_000, "category_id": cat["id"], "description": "Compra"},
        headers=auth,
    )
    assert res.status_code == 200, res.text

    # La cuenta bancaria no se toca: solo sube el saldo de la tarjeta
    assert _balances(client, auth)[acc["id"]] == 500_000
    updated = next(d for d in client.get("/debts", headers=auth).json() if d["id"] == card["id"])
    assert updated["total_amount"] == 80_000


def test_purchases_are_rejected_on_loans(client, auth, make_category):
    loan = _make_debt(client, auth, kind="loan")
    cat = make_category(type_="expense")
    res = client.post(
        f"/debts/{loan['id']}/purchase",
        json={"amount": 1_000, "category_id": cat["id"], "description": "No aplica"},
        headers=auth,
    )
    assert res.status_code == 400


def test_debt_with_movements_cannot_be_deleted(client, auth, make_account):
    acc = make_account(balance=1_000_000)
    debt = _make_debt(client, auth, total_amount=500_000)
    client.post(
        f"/debts/{debt['id']}/pay",
        json={"amount": 100_000, "saving_account_id": acc["id"]},
        headers=auth,
    )

    assert client.delete(f"/debts/{debt['id']}", headers=auth).status_code == 400
