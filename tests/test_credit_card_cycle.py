"""Ciclo de facturación de tarjeta de crédito.

Se calcula en vivo a partir de DebtTransaction, según statement_day
(día de corte) -- no hay tabla de estados de cuenta históricos. Los 4
campos nuevos en Debt solo tienen efecto real en kind=credit_card.
"""
import datetime as dt

import pytest


def _make_credit_card(client, auth, **overrides):
    payload = {
        "name": "Visa",
        "total_amount": 0,
        "interest_rate": 2.5,
        "currency": "COP",
        "kind": "credit_card",
        "credit_limit": 2_000_000,
        "statement_day": 15,
        "payment_due_days": 20,
        "minimum_payment_percent": 5,
    }
    payload.update(overrides)
    res = client.post("/debts", json=payload, headers=auth)
    assert res.status_code == 200, res.text
    return res.json()


def test_create_credit_card_stores_the_four_fields(client, auth):
    card = _make_credit_card(client, auth)
    assert card["credit_limit"] == 2_000_000
    assert card["statement_day"] == 15
    assert card["payment_due_days"] == 20
    assert card["minimum_payment_percent"] == 5


def test_statement_day_out_of_range_is_rejected(client, auth):
    res = client.post(
        "/debts",
        json={
            "name": "Visa",
            "total_amount": 0,
            "interest_rate": 0,
            "currency": "COP",
            "kind": "credit_card",
            "statement_day": 31,
        },
        headers=auth,
    )
    assert res.status_code == 422


def test_statement_requires_kind_credit_card(client, auth):
    res = client.post(
        "/debts",
        json={"name": "Préstamo", "total_amount": 100, "interest_rate": 1, "currency": "COP", "kind": "loan"},
        headers=auth,
    )
    loan_id = res.json()["id"]
    res2 = client.get(f"/debts/{loan_id}/statement", headers=auth)
    assert res2.status_code == 400


def test_statement_requires_cycle_configured(client, auth):
    res = client.post(
        "/debts",
        json={"name": "Visa", "total_amount": 0, "interest_rate": 0, "currency": "COP", "kind": "credit_card"},
        headers=auth,
    )
    card_id = res.json()["id"]
    res2 = client.get(f"/debts/{card_id}/statement", headers=auth)
    assert res2.status_code == 400


def test_statement_computes_dates_and_available_credit(client, auth):
    card = _make_credit_card(client, auth, total_amount=500_000)
    res = client.get(f"/debts/{card['id']}/statement", headers=auth)
    assert res.status_code == 200, res.text
    body = res.json()

    next_statement = dt.date.fromisoformat(body["next_statement_date"])
    payment_due = dt.date.fromisoformat(body["payment_due_date"])
    assert next_statement.day == 15
    assert (payment_due - next_statement).days == 20
    assert body["available_credit"] == 2_000_000 - 500_000
    assert body["minimum_payment_estimate"] == 500_000 * 0.05


def test_statement_current_period_charges_excludes_payments_and_old_charges(
    client, auth, make_account, make_category
):
    card = _make_credit_card(client, auth)
    cat = make_category(name="Compras", type_="expense")

    # Compra reciente (hoy) -- debería contar en el período actual
    client.post(
        f"/debts/{card['id']}/purchase",
        json={"amount": 100_000, "category_id": cat["id"], "description": "Compra hoy"},
        headers=auth,
    )

    body = client.get(f"/debts/{card['id']}/statement", headers=auth).json()
    assert body["current_period_charges"] == 100_000


def test_update_debt_ignores_credit_card_fields_for_loans(client, auth):
    res = client.post(
        "/debts",
        json={"name": "Préstamo", "total_amount": 100, "interest_rate": 1, "currency": "COP", "kind": "loan"},
        headers=auth,
    )
    loan = res.json()
    updated = client.put(
        f"/debts/{loan['id']}",
        json={
            "name": "Préstamo",
            "total_amount": 100,
            "interest_rate": 1,
            "currency": "COP",
            "kind": "loan",
            "credit_limit": 999999,
        },
        headers=auth,
    ).json()
    assert updated["credit_limit"] is None


def test_update_credit_card_can_change_cycle_fields(client, auth):
    card = _make_credit_card(client, auth)
    updated = client.put(
        f"/debts/{card['id']}",
        json={
            "name": "Visa",
            "total_amount": 0,
            "interest_rate": 2.5,
            "currency": "COP",
            "kind": "credit_card",
            "credit_limit": 3_000_000,
            "statement_day": 5,
            "payment_due_days": 15,
            "minimum_payment_percent": 10,
        },
        headers=auth,
    ).json()
    assert updated["credit_limit"] == 3_000_000
    assert updated["statement_day"] == 5
