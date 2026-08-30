"""Renovación de sesión con refresh token.

Lo que de verdad importa acá: que el refresh rote (un token usado no sirve
dos veces), que logout y cambio de contraseña revoquen de verdad, y que el
refresh token nunca viaje en el body de la respuesta.
"""


def _login(client, email, password="TestPass123!"):
    return client.post(
        "/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


def test_login_sets_both_cookies_and_never_leaks_refresh_in_body(client, make_user):
    user = make_user()
    client.cookies.clear()
    res = _login(client, user["email"])
    assert res.status_code == 200, res.text

    assert "access_token" in res.cookies
    assert "refresh_token" in res.cookies
    # El refresh token solo debe existir como cookie httpOnly.
    assert "refresh_token" not in res.json()


def test_refresh_issues_a_new_access_token(client, make_user):
    user = make_user()
    client.cookies.clear()
    _login(client, user["email"])

    res = client.post("/auth/refresh")
    assert res.status_code == 200, res.text
    assert res.json()["access_token"]


def test_refresh_rotates_the_token_so_the_old_one_stops_working(client, make_user):
    user = make_user()
    client.cookies.clear()
    login = _login(client, user["email"])
    original_refresh = login.cookies["refresh_token"]

    first = client.post("/auth/refresh")
    assert first.status_code == 200

    # Reusar el token viejo (el que ya rotó) debe fallar.
    client.cookies.clear()
    client.cookies.set("refresh_token", original_refresh)
    replay = client.post("/auth/refresh")
    assert replay.status_code == 401


def test_refresh_without_cookie_is_401(client):
    client.cookies.clear()
    res = client.post("/auth/refresh")
    assert res.status_code == 401


def test_refresh_with_garbage_token_is_401(client):
    client.cookies.clear()
    client.cookies.set("refresh_token", "no-es-un-token-real")
    res = client.post("/auth/refresh")
    assert res.status_code == 401


def test_logout_revokes_the_refresh_token(client, make_user):
    user = make_user()
    client.cookies.clear()
    login = _login(client, user["email"])
    refresh_cookie = login.cookies["refresh_token"]

    assert client.post("/auth/logout").status_code == 200

    # Aunque el navegador conservara la cookie, ya no debe servir.
    client.cookies.clear()
    client.cookies.set("refresh_token", refresh_cookie)
    assert client.post("/auth/refresh").status_code == 401


def test_changing_password_revokes_existing_sessions(client, make_user):
    user = make_user()
    client.cookies.clear()
    login = _login(client, user["email"])
    refresh_cookie = login.cookies["refresh_token"]

    res = client.post(
        "/auth/change-password",
        json={"current_password": user["password"], "new_password": "NuevaClave456!"},
        headers=user["headers"],
    )
    assert res.status_code == 200, res.text

    client.cookies.clear()
    client.cookies.set("refresh_token", refresh_cookie)
    assert client.post("/auth/refresh").status_code == 401


def test_refreshed_access_token_actually_works(client, make_user):
    user = make_user()
    client.cookies.clear()
    _login(client, user["email"])

    refreshed = client.post("/auth/refresh")
    new_access = refreshed.json()["access_token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {new_access}"})
    assert me.status_code == 200
    assert me.json()["email"] == user["email"]
