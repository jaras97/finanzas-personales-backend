"""Autenticación, control de acceso y aislamiento entre usuarios."""
import uuid

import pytest

from app.core import rate_limit


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """El limitador vive en memoria de proceso y persiste entre tests, así que
    se limpia para que un test no haga fallar al siguiente."""
    rate_limit.login_limiter_by_email._attempts.clear()
    rate_limit.login_limiter_by_ip._attempts.clear()
    yield


def test_register_and_login(client):
    email = f"nuevo-{uuid.uuid4().hex[:8]}@test.dev"
    assert client.post(
        "/auth/register", json={"email": email, "password": "ClaveSegura1"}
    ).status_code == 200

    res = client.post(
        "/auth/login", data={"username": email, "password": "ClaveSegura1"}
    )
    assert res.status_code == 200
    assert "access_token" in res.json()


def test_login_sets_httponly_cookie(client, user):
    res = client.post(
        "/auth/login",
        data={"username": user["email"], "password": user["password"]},
    )
    cookie_header = res.headers.get("set-cookie", "")
    assert "access_token=" in cookie_header
    assert "HttpOnly" in cookie_header


def test_cookie_alone_authenticates(client, user):
    """El frontend ya no manda el header Authorization: la cookie debe bastar."""
    client.post(
        "/auth/login",
        data={"username": user["email"], "password": user["password"]},
    )
    res = client.get("/auth/me")  # TestClient conserva las cookies
    assert res.status_code == 200
    assert res.json()["email"] == user["email"]


def test_logout_clears_session(client, user):
    client.post(
        "/auth/login",
        data={"username": user["email"], "password": user["password"]},
    )
    assert client.get("/auth/me").status_code == 200

    client.post("/auth/logout")
    assert client.get("/auth/me").status_code == 401


def test_duplicate_email_is_rejected(client, user):
    res = client.post(
        "/auth/register", json={"email": user["email"], "password": "OtraClave123"}
    )
    assert res.status_code == 400


@pytest.mark.parametrize("password", ["", "corta", "1234567"])
def test_short_passwords_are_rejected(client, password):
    res = client.post(
        "/auth/register",
        json={"email": f"x-{uuid.uuid4().hex[:8]}@test.dev", "password": password},
    )
    assert res.status_code == 422


def test_wrong_password_is_rejected(client, user):
    res = client.post(
        "/auth/login", data={"username": user["email"], "password": "incorrecta"}
    )
    assert res.status_code == 401


def test_login_is_rate_limited_per_email(client, user):
    for _ in range(5):
        client.post(
            "/auth/login", data={"username": user["email"], "password": "mala"}
        )

    blocked = client.post(
        "/auth/login", data={"username": user["email"], "password": "mala"}
    )
    assert blocked.status_code == 429

    # Incluso con la contraseña correcta sigue bloqueado durante la ventana
    still = client.post(
        "/auth/login", data={"username": user["email"], "password": user["password"]}
    )
    assert still.status_code == 429


def test_successful_login_resets_the_limiter(client, user):
    for _ in range(3):
        client.post(
            "/auth/login", data={"username": user["email"], "password": "mala"}
        )
    ok = client.post(
        "/auth/login", data={"username": user["email"], "password": user["password"]}
    )
    assert ok.status_code == 200

    # Tras el acierto, el contador arranca de cero
    for _ in range(4):
        client.post(
            "/auth/login", data={"username": user["email"], "password": "mala"}
        )
    assert client.post(
        "/auth/login", data={"username": user["email"], "password": user["password"]}
    ).status_code == 200


def test_protected_endpoints_reject_anonymous(client):
    for path in [
        "/saving-accounts",
        "/transactions/with-category",
        "/categories",
        "/debts",
        "/recurring-transactions",
        "/currencies",
    ]:
        assert client.get(path).status_code == 401, path


def test_subscription_is_required_for_business_endpoints(client, make_user):
    without = make_user(with_subscription=False)
    res = client.get("/saving-accounts", headers=without["headers"])
    assert res.status_code == 403


def test_change_password_requires_the_current_one(client, user):
    wrong = client.post(
        "/auth/change-password",
        json={"current_password": "nope", "new_password": "NuevaClave123"},
        headers=user["headers"],
    )
    assert wrong.status_code == 400

    ok = client.post(
        "/auth/change-password",
        json={"current_password": user["password"], "new_password": "NuevaClave123"},
        headers=user["headers"],
    )
    assert ok.status_code == 200
    assert client.post(
        "/auth/login", data={"username": user["email"], "password": "NuevaClave123"}
    ).status_code == 200


def test_accounts_are_not_visible_across_users(client, make_user):
    owner = make_user()
    other = make_user()
    client.post(
        "/saving-accounts",
        json={"name": "Privada", "balance": 1.0, "type": "bank", "currency": "COP"},
        headers=owner["headers"],
    )
    assert client.get("/saving-accounts", headers=other["headers"]).json() == []


# --- Panel de administración ------------------------------------------------


def test_admin_endpoints_reject_regular_users(client, user):
    assert client.get("/admin/users", headers=user["headers"]).status_code == 403


def test_admin_can_list_users(client, make_user):
    admin = make_user(role="admin")
    make_user()
    res = client.get("/admin/users", headers=admin["headers"])
    assert res.status_code == 200
    assert res.json()["total"] >= 2


def test_admin_search_filters_by_email(client, make_user):
    admin = make_user(role="admin")
    target = make_user(email="buscable@test.dev")
    res = client.get("/admin/users?search=buscable", headers=admin["headers"]).json()
    assert res["total"] == 1
    assert res["items"][0]["email"] == target["email"]


def test_cannot_remove_the_last_admin(client, make_user):
    """Si se pudiera, nadie volvería a entrar al panel."""
    admin = make_user(role="admin")
    res = client.patch(
        f"/admin/users/{admin['id']}/role",
        json={"role": "user"},
        headers=admin["headers"],
    )
    assert res.status_code == 400


def test_can_demote_admin_when_another_remains(client, make_user):
    first = make_user(role="admin")
    second = make_user(role="admin")
    res = client.patch(
        f"/admin/users/{second['id']}/role",
        json={"role": "user"},
        headers=first["headers"],
    )
    assert res.status_code == 200
    assert res.json()["role"] == "user"


def test_admin_without_subscription_still_has_admin_access(client, make_user):
    """Los administradores son personal, no clientes: no deben quedar fuera
    por no tener suscripción propia."""
    admin = make_user(role="admin", with_subscription=False)
    assert client.get("/admin/users", headers=admin["headers"]).status_code == 200
    assert client.get("/auth/me", headers=admin["headers"]).json()["role"] == "admin"
