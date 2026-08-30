"""Comprobantes adjuntos a transacciones.

El almacenamiento se mockea: la suite no debe depender de Supabase ni de la
red. Lo que se prueba es la lógica propia -- validación de tipo y tamaño,
propiedad de la transacción, y que la ruta en el bucket se construya del
lado del servidor y no con el nombre que manda el cliente.
"""
import io
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _fake_storage():
    """Evita llamadas reales a Supabase en todos los tests del módulo."""
    with patch("app.api.attachments.upload_file") as upload, patch(
        "app.api.attachments.delete_file"
    ) as delete, patch(
        "app.api.attachments.create_signed_url", return_value="https://signed.example/x"
    ):
        yield {"upload": upload, "delete": delete}


@pytest.fixture
def transaction(client, auth, make_account, make_category):
    acc = make_account(balance=1_000_000)
    cat = make_category(type_="expense")
    return client.post(
        "/transactions",
        json={
            "amount": 50_000,
            "category_id": cat["id"],
            "description": "Compra",
            "type": "expense",
            "saving_account_id": acc["id"],
        },
        headers=auth,
    ).json()


def _upload(client, auth, tx_id, *, name="recibo.jpg", content=b"fake-bytes", ctype="image/jpeg"):
    return client.post(
        f"/transactions/{tx_id}/attachments",
        files={"file": (name, io.BytesIO(content), ctype)},
        headers=auth,
    )


def test_upload_and_list_attachment(client, auth, transaction):
    res = _upload(client, auth, transaction["id"])
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["filename"] == "recibo.jpg"
    assert body["content_type"] == "image/jpeg"
    assert body["url"] == "https://signed.example/x"

    listed = client.get(f"/transactions/{transaction['id']}/attachments", headers=auth).json()
    assert len(listed) == 1
    assert listed[0]["id"] == body["id"]


def test_storage_path_is_server_built_and_scoped_to_the_user(
    client, auth, transaction, _fake_storage, user
):
    # Nombre malicioso: no debe poder escaparse de su carpeta.
    _upload(client, auth, transaction["id"], name="../../otro-usuario/robado.jpg")

    path = _fake_storage["upload"].call_args[0][0]
    assert path.startswith(f"{user['id']}/{transaction['id']}/")
    assert ".." not in path


def test_rejects_disallowed_content_type(client, auth, transaction):
    res = _upload(client, auth, transaction["id"], name="virus.exe", ctype="application/x-msdownload")
    assert res.status_code == 400
    assert "Formato no admitido" in res.json()["detail"]


def test_rejects_file_over_the_size_limit(client, auth, transaction):
    huge = b"x" * (5 * 1024 * 1024 + 1)
    res = _upload(client, auth, transaction["id"], content=huge)
    assert res.status_code == 400
    assert "límite" in res.json()["detail"]


def test_rejects_empty_file(client, auth, transaction):
    res = _upload(client, auth, transaction["id"], content=b"")
    assert res.status_code == 400


def test_cannot_attach_to_someone_elses_transaction(client, auth, transaction, make_user):
    other = make_user()
    res = client.post(
        f"/transactions/{transaction['id']}/attachments",
        files={"file": ("recibo.jpg", io.BytesIO(b"bytes"), "image/jpeg")},
        headers=other["headers"],
    )
    assert res.status_code == 404


def test_cannot_list_someone_elses_attachments(client, auth, transaction, make_user):
    _upload(client, auth, transaction["id"])
    other = make_user()
    res = client.get(
        f"/transactions/{transaction['id']}/attachments", headers=other["headers"]
    )
    assert res.status_code == 404


def test_cannot_delete_someone_elses_attachment(client, auth, transaction, make_user):
    created = _upload(client, auth, transaction["id"]).json()
    other = make_user()
    res = client.delete(f"/attachments/{created['id']}", headers=other["headers"])
    assert res.status_code == 404


def test_delete_removes_row_and_file(client, auth, transaction, _fake_storage):
    created = _upload(client, auth, transaction["id"]).json()

    res = client.delete(f"/attachments/{created['id']}", headers=auth)
    assert res.status_code == 200
    _fake_storage["delete"].assert_called_once()

    listed = client.get(f"/transactions/{transaction['id']}/attachments", headers=auth).json()
    assert listed == []


def test_enforces_max_attachments_per_transaction(client, auth, transaction):
    for _ in range(5):
        assert _upload(client, auth, transaction["id"]).status_code == 200

    res = _upload(client, auth, transaction["id"])
    assert res.status_code == 400
    assert "Máximo" in res.json()["detail"]


def test_pdf_is_accepted(client, auth, transaction):
    res = _upload(
        client, auth, transaction["id"], name="extracto.pdf", ctype="application/pdf"
    )
    assert res.status_code == 200


def test_transaction_list_exposes_attachments_count(client, auth, transaction):
    listed = client.get("/transactions/with-category", headers=auth).json()["items"]
    assert next(t for t in listed if t["id"] == transaction["id"])["attachments_count"] == 0

    _upload(client, auth, transaction["id"])
    _upload(client, auth, transaction["id"], name="segundo.pdf", ctype="application/pdf")

    listed = client.get("/transactions/with-category", headers=auth).json()["items"]
    assert next(t for t in listed if t["id"] == transaction["id"])["attachments_count"] == 2


def test_attachment_works_on_a_transfer_leg(client, auth, make_account):
    a = make_account(name="A", balance=1_000_000)
    b = make_account(name="B", balance=0)
    client.post(
        "/transactions/transfer",
        json={"from_account_id": a["id"], "to_account_id": b["id"], "amount": 100_000},
        headers=auth,
    )
    legs = client.get(
        "/transactions/with-category", params={"page_size": 50}, headers=auth
    ).json()["items"]
    expense_leg = next(
        t for t in legs if t["source_type"] == "transfer" and t["type"] == "expense"
    )

    res = _upload(client, auth, expense_leg["id"])
    assert res.status_code == 200, res.text
