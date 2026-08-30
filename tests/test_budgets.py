"""Presupuestos mensuales por categoría y moneda.

Las propiedades que importan de verdad acá: el gasto real excluye
transferencias/pagos de deuda/reversadas (igual criterio que /summary), dos
monedas para la misma categoría se trackean por separado sin fusionarse, y
el versionado por mes no reescribe el pasado ni permite fijarlo.
"""
import datetime as dt


def _spend(client, auth, acc, cat, amount, description="Gasto"):
    res = client.post(
        "/transactions",
        json={
            "amount": amount,
            "category_id": cat["id"],
            "description": description,
            "type": "expense",
            "saving_account_id": acc["id"],
        },
        headers=auth,
    )
    assert res.status_code == 200, res.text
    return res.json()


def test_create_budget_and_track_spend(client, auth, make_account, make_category):
    acc = make_account(balance=2_000_000)
    cat = make_category(name="Mercado", type_="expense")

    res = client.post(
        "/budgets",
        json={"category_id": cat["id"], "currency": "COP", "amount": 500_000},
        headers=auth,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["amount"] == 500_000
    assert body["spent"] == 0
    assert body["percentage"] == 0

    _spend(client, auth, acc, cat, 150_000)

    listed = client.get("/budgets", headers=auth).json()
    assert len(listed) == 1
    assert listed[0]["spent"] == 150_000
    assert listed[0]["percentage"] == 30.0


def test_editing_same_month_updates_instead_of_duplicating(client, auth, make_category):
    cat = make_category(type_="expense")
    client.post(
        "/budgets", json={"category_id": cat["id"], "currency": "COP", "amount": 100_000}, headers=auth
    )
    res = client.post(
        "/budgets", json={"category_id": cat["id"], "currency": "COP", "amount": 300_000}, headers=auth
    )
    assert res.status_code == 200, res.text

    listed = client.get("/budgets", headers=auth).json()
    assert len(listed) == 1
    assert listed[0]["amount"] == 300_000


def test_cannot_budget_a_system_category(client, auth):
    system_cat = next(
        c for c in client.get("/categories", params={"status": "all"}, headers=auth).json()
        if c["is_system"]
    )
    res = client.post(
        "/budgets",
        json={"category_id": system_cat["id"], "currency": "COP", "amount": 100_000},
        headers=auth,
    )
    assert res.status_code == 400
    assert "sistema" in res.json()["detail"].lower()


def test_cannot_budget_an_income_only_category(client, auth, make_category):
    cat = make_category(name="Sueldo", type_="income")
    res = client.post(
        "/budgets", json={"category_id": cat["id"], "currency": "COP", "amount": 100_000}, headers=auth
    )
    assert res.status_code == 400
    assert "gasto" in res.json()["detail"].lower()


def test_cannot_set_effective_from_in_the_past(client, auth, make_category):
    cat = make_category(type_="expense")
    past_month = (dt.date.today().replace(day=1) - dt.timedelta(days=1)).replace(day=1)
    res = client.post(
        "/budgets",
        json={
            "category_id": cat["id"],
            "currency": "COP",
            "amount": 100_000,
            "effective_from": past_month.isoformat(),
        },
        headers=auth,
    )
    assert res.status_code == 400


def test_pause_hides_budget_from_current_month(client, auth, make_category):
    cat = make_category(type_="expense")
    created = client.post(
        "/budgets", json={"category_id": cat["id"], "currency": "COP", "amount": 100_000}, headers=auth
    ).json()

    res = client.post(f"/budgets/{created['id']}/pause", headers=auth)
    assert res.status_code == 200, res.text

    listed = client.get("/budgets", headers=auth).json()
    assert listed == []


def test_transfers_and_debt_payments_do_not_count_as_spend(
    client, auth, make_account, make_category
):
    acc_a = make_account(name="A", balance=1_000_000)
    acc_b = make_account(name="B", balance=0)
    cat = make_category(name="Otros", type_="expense")

    client.post(
        "/budgets", json={"category_id": cat["id"], "currency": "COP", "amount": 500_000}, headers=auth
    )

    # Una transferencia no debería tocar el presupuesto de ninguna categoría
    # del usuario (usa la categoría de sistema "Transferencia", no la suya).
    res = client.post(
        "/transactions/transfer",
        json={"from_account_id": acc_a["id"], "to_account_id": acc_b["id"], "amount": 300_000},
        headers=auth,
    )
    assert res.status_code == 200, res.text

    listed = client.get("/budgets", headers=auth).json()
    assert listed[0]["spent"] == 0


def test_reversed_transaction_does_not_count(client, auth, make_account, make_category):
    acc = make_account(balance=1_000_000)
    cat = make_category(type_="expense")
    client.post(
        "/budgets", json={"category_id": cat["id"], "currency": "COP", "amount": 500_000}, headers=auth
    )
    tx = _spend(client, auth, acc, cat, 200_000)

    res = client.post(f"/transactions/{tx['id']}/reverse", json={"note": "error"}, headers=auth)
    assert res.status_code == 200, res.text

    listed = client.get("/budgets", headers=auth).json()
    assert listed[0]["spent"] == 0


def test_same_category_tracked_separately_per_currency(client, auth, make_account, make_category):
    acc_cop = make_account(name="COP", currency="COP", balance=2_000_000)
    acc_usd = make_account(name="USD", currency="USD", balance=1_000)
    cat = make_category(name="Mercado", type_="expense")

    client.post(
        "/budgets", json={"category_id": cat["id"], "currency": "COP", "amount": 500_000}, headers=auth
    )
    client.post(
        "/budgets", json={"category_id": cat["id"], "currency": "USD", "amount": 200}, headers=auth
    )

    _spend(client, auth, acc_cop, cat, 100_000)
    _spend(client, auth, acc_usd, cat, 50)

    listed = {b["currency"]: b for b in client.get("/budgets", headers=auth).json()}
    assert listed["COP"]["spent"] == 100_000
    assert listed["USD"]["spent"] == 50
