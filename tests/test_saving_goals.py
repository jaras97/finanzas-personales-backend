"""Metas de ahorro, atadas 1:1 a una SavingAccount completa.

El progreso es simplemente saldo actual / meta, sin trackear aportes vs.
retiros por separado. A lo sumo una meta ACTIVA por cuenta.
"""
import datetime as dt


def test_create_goal_and_progress_tracks_account_balance(client, auth, make_account):
    acc = make_account(balance=300_000)
    res = client.post(
        "/saving-goals",
        json={"saving_account_id": acc["id"], "name": "Viaje a Cartagena", "target_amount": 1_000_000},
        headers=auth,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["current_balance"] == 300_000
    assert body["progress_percent"] == 30.0
    assert body["currency"] == acc["currency"]


def test_cannot_create_second_active_goal_for_same_account(client, auth, make_account):
    acc = make_account()
    client.post(
        "/saving-goals",
        json={"saving_account_id": acc["id"], "name": "Meta 1", "target_amount": 500_000},
        headers=auth,
    )
    res = client.post(
        "/saving-goals",
        json={"saving_account_id": acc["id"], "name": "Meta 2", "target_amount": 500_000},
        headers=auth,
    )
    assert res.status_code == 400


def test_deactivating_a_goal_allows_a_new_one_on_the_same_account(client, auth, make_account):
    acc = make_account()
    goal = client.post(
        "/saving-goals",
        json={"saving_account_id": acc["id"], "name": "Meta 1", "target_amount": 500_000},
        headers=auth,
    ).json()

    client.put(f"/saving-goals/{goal['id']}", json={"is_active": False}, headers=auth)

    res = client.post(
        "/saving-goals",
        json={"saving_account_id": acc["id"], "name": "Meta 2", "target_amount": 700_000},
        headers=auth,
    )
    assert res.status_code == 200, res.text


def test_list_only_returns_active_goals(client, auth, make_account):
    acc = make_account()
    goal = client.post(
        "/saving-goals",
        json={"saving_account_id": acc["id"], "name": "Meta 1", "target_amount": 500_000},
        headers=auth,
    ).json()
    client.put(f"/saving-goals/{goal['id']}", json={"is_active": False}, headers=auth)

    listed = client.get("/saving-goals", headers=auth).json()
    assert listed == []


def test_monthly_savings_needed_with_target_date(client, auth, make_account):
    acc = make_account(balance=200_000)
    today = dt.date.today()
    # 3 meses en el futuro (mismo día, evita bordes de fin de mes en la resta)
    target_month = today.month + 3
    target_year = today.year
    while target_month > 12:
        target_month -= 12
        target_year += 1
    target_date = dt.date(target_year, target_month, 1)

    res = client.post(
        "/saving-goals",
        json={
            "saving_account_id": acc["id"],
            "name": "Fondo emergencia",
            "target_amount": 800_000,
            "target_date": target_date.isoformat(),
        },
        headers=auth,
    )
    body = res.json()
    remaining = 800_000 - 200_000
    assert body["monthly_savings_needed"] == remaining / 3


def test_monthly_savings_needed_is_zero_once_target_reached(client, auth, make_account):
    acc = make_account(balance=1_000_000)
    target_date = (dt.date.today().replace(day=1))
    res = client.post(
        "/saving-goals",
        json={
            "saving_account_id": acc["id"],
            "name": "Meta cumplida",
            "target_amount": 500_000,
            "target_date": target_date.isoformat(),
        },
        headers=auth,
    )
    assert res.json()["monthly_savings_needed"] == 0.0
    assert res.json()["progress_percent"] == 200.0


def test_update_goal_amount_and_delete(client, auth, make_account):
    acc = make_account()
    goal = client.post(
        "/saving-goals",
        json={"saving_account_id": acc["id"], "name": "Meta", "target_amount": 500_000},
        headers=auth,
    ).json()

    updated = client.put(
        f"/saving-goals/{goal['id']}", json={"target_amount": 900_000}, headers=auth
    ).json()
    assert updated["target_amount"] == 900_000

    res = client.delete(f"/saving-goals/{goal['id']}", headers=auth)
    assert res.status_code == 200
    assert client.get("/saving-goals", headers=auth).json() == []


def test_cannot_create_goal_on_inactive_account(client, auth, make_account):
    acc = make_account(balance=0)
    close_res = client.post(f"/saving-accounts/{acc['id']}/close", headers=auth)
    assert close_res.status_code == 200, close_res.text
    res = client.post(
        "/saving-goals",
        json={"saving_account_id": acc["id"], "name": "Meta", "target_amount": 100_000},
        headers=auth,
    )
    assert res.status_code == 400
