"""Generación de movimientos recurrentes.

Las tres propiedades que se prueban aquí (idempotencia, no sobregirar, y el
recorte de fin de mes) son fáciles de romper en un refactor y el daño es
silencioso: plata duplicada o cuentas en negativo sin que nada falle.
"""
import datetime as dt

from app.api.recurring_transactions import _add_months, _advance
from app.models.recurring_transaction import RecurrenceFrequency


def _days_ago(n: int) -> str:
    return (dt.date.today() - dt.timedelta(days=n)).isoformat()


def _balance(client, auth, account_id):
    accounts = client.get("/saving-accounts", headers=auth).json()
    return next(a["balance"] for a in accounts if a["id"] == account_id)


def _make_rule(client, auth, acc, cat, **overrides):
    payload = {
        "description": "Recurrente",
        "amount": 100_000,
        "type": "expense",
        "category_id": cat["id"],
        "saving_account_id": acc["id"],
        "frequency": "monthly",
        "next_run": _days_ago(0),
    }
    payload.update(overrides)
    res = client.post("/recurring-transactions", json=payload, headers=auth)
    assert res.status_code == 200, res.text
    return res.json()


def test_run_generates_every_due_occurrence(client, auth, make_account, make_category):
    acc = make_account(balance=10_000_000)
    cat = make_category(name="Sueldo", type_="income")
    # 45 días atrás, quincenal -> vencen los días 0, 14, 28 y 42
    _make_rule(
        client, auth, acc, cat,
        type="income", amount=1_000_000, frequency="biweekly", next_run=_days_ago(45),
    )

    res = client.post("/recurring-transactions/run", headers=auth).json()
    assert res["total_created"] == 4
    assert _balance(client, auth, acc["id"]) == 10_000_000 + 4_000_000


def test_run_is_idempotent(client, auth, make_account, make_category):
    """Correrlo dos veces seguidas no puede duplicar nada."""
    acc = make_account(balance=10_000_000)
    cat = make_category(name="Sueldo", type_="income")
    _make_rule(
        client, auth, acc, cat,
        type="income", amount=1_000_000, frequency="biweekly", next_run=_days_ago(45),
    )

    first = client.post("/recurring-transactions/run", headers=auth).json()
    balance_after_first = _balance(client, auth, acc["id"])

    second = client.post("/recurring-transactions/run", headers=auth).json()

    assert first["total_created"] == 4
    assert second["total_created"] == 0
    assert _balance(client, auth, acc["id"]) == balance_after_first


def test_run_never_overdraws_the_account(client, auth, make_account, make_category):
    acc = make_account(balance=50_000)
    cat = make_category(type_="expense")
    _make_rule(client, auth, acc, cat, amount=200_000, next_run=_days_ago(1))

    res = client.post("/recurring-transactions/run", headers=auth).json()

    assert res["total_created"] == 0
    assert len(res["skipped"]) == 1
    assert _balance(client, auth, acc["id"]) == 50_000


def test_skipped_rule_stays_pending_for_retry(
    client, auth, make_account, make_category
):
    """Si se omitió por saldo, debe poder generarse cuando haya fondos."""
    acc = make_account(balance=50_000)
    cat = make_category(type_="expense")
    income_cat = make_category(name="Abono", type_="income")
    _make_rule(client, auth, acc, cat, amount=200_000, next_run=_days_ago(1))

    client.post("/recurring-transactions/run", headers=auth)

    # El usuario recarga la cuenta y reintenta
    client.post(
        "/transactions",
        json={
            "description": "Abono",
            "amount": 500_000,
            "type": "income",
            "category_id": income_cat["id"],
            "saving_account_id": acc["id"],
        },
        headers=auth,
    )
    res = client.post("/recurring-transactions/run", headers=auth).json()

    assert res["total_created"] == 1
    assert _balance(client, auth, acc["id"]) == 550_000 - 200_000


def test_paused_rule_does_not_generate(client, auth, make_account, make_category):
    acc = make_account(balance=1_000_000)
    cat = make_category(type_="expense")
    rule = _make_rule(client, auth, acc, cat, next_run=_days_ago(1))

    client.put(
        f"/recurring-transactions/{rule['id']}", json={"is_active": False}, headers=auth
    )
    res = client.post("/recurring-transactions/run", headers=auth).json()

    assert res["total_created"] == 0
    assert _balance(client, auth, acc["id"]) == 1_000_000


def test_future_rule_does_not_generate_yet(client, auth, make_account, make_category):
    acc = make_account(balance=1_000_000)
    cat = make_category(type_="expense")
    tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    _make_rule(client, auth, acc, cat, next_run=tomorrow)

    res = client.post("/recurring-transactions/run", headers=auth).json()
    assert res["total_created"] == 0


def test_end_date_stops_generation(client, auth, make_account, make_category):
    acc = make_account(balance=10_000_000)
    cat = make_category(name="Sueldo", type_="income")
    # Empieza hace 45 días pero termina hace 20 -> solo las de los días 0 y 14
    _make_rule(
        client, auth, acc, cat,
        type="income", amount=1_000_000, frequency="biweekly",
        next_run=_days_ago(45), end_date=_days_ago(20),
    )

    res = client.post("/recurring-transactions/run", headers=auth).json()
    assert res["total_created"] == 2


def test_deleting_rule_keeps_generated_transactions(
    client, auth, make_account, make_category
):
    acc = make_account(balance=1_000_000)
    cat = make_category(type_="expense")
    rule = _make_rule(client, auth, acc, cat, amount=10_000, next_run=_days_ago(1))
    client.post("/recurring-transactions/run", headers=auth)

    before = client.get("/transactions/with-category", headers=auth).json()["total"]
    client.delete(f"/recurring-transactions/{rule['id']}", headers=auth)
    after = client.get("/transactions/with-category", headers=auth).json()["total"]

    assert before == after > 0


def test_rule_rejects_category_of_wrong_type(
    client, auth, make_account, make_category
):
    acc = make_account()
    income_cat = make_category(name="Sueldo", type_="income")
    res = client.post(
        "/recurring-transactions",
        json={
            "description": "Tipo cruzado",
            "amount": 1_000,
            "type": "expense",
            "category_id": income_cat["id"],
            "saving_account_id": acc["id"],
            "frequency": "monthly",
            "next_run": _days_ago(0),
        },
        headers=auth,
    )
    assert res.status_code == 400


def test_rules_are_scoped_per_user(client, make_user, make_account, make_category):
    owner = make_user()
    other = make_user()
    acc = client.post(
        "/saving-accounts",
        json={"name": "A", "balance": 100.0, "type": "bank", "currency": "COP"},
        headers=owner["headers"],
    ).json()
    cat = client.post(
        "/categories", json={"name": "C", "type": "expense"}, headers=owner["headers"]
    ).json()
    client.post(
        "/recurring-transactions",
        json={
            "description": "Privada",
            "amount": 10,
            "type": "expense",
            "category_id": cat["id"],
            "saving_account_id": acc["id"],
            "frequency": "monthly",
            "next_run": _days_ago(0),
        },
        headers=owner["headers"],
    )

    assert client.get("/recurring-transactions", headers=other["headers"]).json() == []


# --- Aritmética de fechas (unitario, sin base de datos) ---------------------


def test_add_months_clamps_to_last_valid_day():
    # El 31 de enero + 1 mes debe caer en febrero, no desbordarse a marzo
    assert _add_months(dt.date(2026, 1, 31), 1) == dt.date(2026, 2, 28)
    assert _add_months(dt.date(2024, 1, 31), 1) == dt.date(2024, 2, 29)  # bisiesto
    assert _add_months(dt.date(2026, 3, 31), 1) == dt.date(2026, 4, 30)


def test_add_months_crosses_year_boundary():
    assert _add_months(dt.date(2026, 12, 15), 1) == dt.date(2027, 1, 15)
    assert _add_months(dt.date(2026, 6, 10), 12) == dt.date(2027, 6, 10)


def test_advance_matches_each_frequency():
    d = dt.date(2026, 3, 10)
    assert _advance(d, RecurrenceFrequency.weekly) == dt.date(2026, 3, 17)
    assert _advance(d, RecurrenceFrequency.biweekly) == dt.date(2026, 3, 24)
    assert _advance(d, RecurrenceFrequency.monthly) == dt.date(2026, 4, 10)
    assert _advance(d, RecurrenceFrequency.yearly) == dt.date(2027, 3, 10)
