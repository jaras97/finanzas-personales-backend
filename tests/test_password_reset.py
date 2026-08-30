"""Restablecimiento de contraseña.

El token vive en la base (antes era un dict en memoria que se perdía en
cada deploy). Lo que se prueba acá: que el token sirva una sola vez, que
pedir uno nuevo invalide el anterior, que no se filtre qué correos existen,
y que recuperar la contraseña cierre las sesiones abiertas.
"""
import hashlib
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlmodel import select

from app.models.password_reset_token import PasswordResetToken


def _request_reset(client, email):
    """Dispara el flujo y devuelve el token CRUDO capturado del correo."""
    captured = {}

    def _fake_send(to, reset_url, expire_minutes):
        captured["url"] = reset_url
        captured["to"] = to
        return True

    with patch("app.api.auth_extra.send_password_reset_email", side_effect=_fake_send):
        res = client.post("/auth/forgot-password", json={"email": email})
    assert res.status_code == 200, res.text
    if "url" not in captured:
        return None
    return captured["url"].split("token=")[1]


def test_forgot_password_response_is_identical_for_unknown_emails(client, make_user):
    user = make_user()
    known = client.post("/auth/forgot-password", json={"email": user["email"]})
    unknown = client.post("/auth/forgot-password", json={"email": "nadie@test.dev"})

    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()


def test_no_email_is_sent_for_an_unknown_address(client):
    assert _request_reset(client, "nadie@test.dev") is None


def test_reset_with_valid_token_changes_the_password(client, make_user):
    user = make_user()
    token = _request_reset(client, user["email"])
    assert token

    res = client.post(
        "/auth/reset-password", json={"token": token, "new_password": "ClaveNueva123!"}
    )
    assert res.status_code == 200, res.text

    # La contraseña vieja ya no sirve y la nueva sí.
    old = client.post(
        "/auth/login",
        data={"username": user["email"], "password": user["password"]},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert old.status_code == 401

    new = client.post(
        "/auth/login",
        data={"username": user["email"], "password": "ClaveNueva123!"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert new.status_code == 200


def test_token_cannot_be_used_twice(client, make_user):
    user = make_user()
    token = _request_reset(client, user["email"])

    first = client.post(
        "/auth/reset-password", json={"token": token, "new_password": "ClaveNueva123!"}
    )
    assert first.status_code == 200

    second = client.post(
        "/auth/reset-password", json={"token": token, "new_password": "OtraClave456!"}
    )
    assert second.status_code == 400


def test_requesting_a_new_link_invalidates_the_previous_one(client, make_user):
    user = make_user()
    first_token = _request_reset(client, user["email"])
    second_token = _request_reset(client, user["email"])
    assert first_token != second_token

    stale = client.post(
        "/auth/reset-password", json={"token": first_token, "new_password": "ClaveNueva123!"}
    )
    assert stale.status_code == 400

    fresh = client.post(
        "/auth/reset-password", json={"token": second_token, "new_password": "ClaveNueva123!"}
    )
    assert fresh.status_code == 200


def test_expired_token_is_rejected(client, make_user, session):
    user = make_user()
    token = _request_reset(client, user["email"])

    record = session.exec(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == hashlib.sha256(token.encode()).hexdigest()
        )
    ).first()
    record.expires_at = datetime.utcnow() - timedelta(minutes=1)
    session.add(record)
    session.commit()

    res = client.post(
        "/auth/reset-password", json={"token": token, "new_password": "ClaveNueva123!"}
    )
    assert res.status_code == 400


def test_garbage_token_is_rejected(client):
    res = client.post(
        "/auth/reset-password", json={"token": "inventado", "new_password": "ClaveNueva123!"}
    )
    assert res.status_code == 400


def test_reset_revokes_open_sessions(client, make_user):
    user = make_user()
    client.cookies.clear()
    login = client.post(
        "/auth/login",
        data={"username": user["email"], "password": user["password"]},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    refresh_cookie = login.cookies["refresh_token"]

    token = _request_reset(client, user["email"])
    client.post("/auth/reset-password", json={"token": token, "new_password": "ClaveNueva123!"})

    client.cookies.clear()
    client.cookies.set("refresh_token", refresh_cookie)
    assert client.post("/auth/refresh").status_code == 401


def test_short_password_is_rejected(client, make_user):
    user = make_user()
    token = _request_reset(client, user["email"])
    res = client.post("/auth/reset-password", json={"token": token, "new_password": "corta"})
    assert res.status_code == 422
