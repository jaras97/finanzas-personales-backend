"""Importación de extractos en CSV.

Flujo en dos pasos: sin `column_mapping` el preview solo devuelve una
muestra cruda para que el usuario indique qué columna es cuál; con mapeo,
parsea todas las filas, sugiere "Sin categorizar" (todavía no hay reglas de
categorización) y marca posibles duplicados contra lo que ya existe en esa
cuenta. `confirm` crea de verdad solo las filas que el usuario aprueba.
"""
import io
import json

CSV_BODY = (
    "Fecha,Descripcion,Monto\n"
    "01/08/2026,Compra supermercado,-150000\n"
    "05/08/2026,Pago nomina,2000000\n"
)


def _upload(client, auth, account_id, csv_text, mapping=None, date_format=None, has_header=True):
    files = {"file": ("extracto.csv", io.BytesIO(csv_text.encode("utf-8")), "text/csv")}
    data = {"saving_account_id": str(account_id), "has_header": str(has_header)}
    if mapping is not None:
        data["column_mapping"] = json.dumps(mapping)
    if date_format is not None:
        data["date_format"] = date_format
    return client.post("/transactions/import/preview", files=files, data=data, headers=auth)


def test_inspect_without_mapping_returns_sample(client, auth, make_account):
    acc = make_account()
    res = _upload(client, auth, acc["id"], CSV_BODY)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["mode"] == "inspect"
    assert body["column_count"] == 3
    assert body["sample_rows"][0] == ["Fecha", "Descripcion", "Monto"]
    assert body["saved_profile"] is None


def test_preview_parses_and_suggests_uncategorized(client, auth, make_account):
    acc = make_account()
    mapping = {"date": 0, "description": 1, "amount": 2}
    res = _upload(client, auth, acc["id"], CSV_BODY, mapping=mapping, date_format="%d/%m/%Y")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["mode"] == "review"
    assert body["total_rows"] == 2
    assert body["error_count"] == 0

    expense_row, income_row = body["rows"]
    assert expense_row["type"] == "expense"
    assert expense_row["amount"] == 150000.0
    assert expense_row["date"] == "2026-08-01"
    assert expense_row["category_name"] == "Sin categorizar"
    assert expense_row["include"] is True

    assert income_row["type"] == "income"
    assert income_row["amount"] == 2000000.0


def test_preview_flags_invalid_rows(client, auth, make_account):
    acc = make_account()
    bad_csv = "Fecha,Descripcion,Monto\nno-es-fecha,Algo raro,abc\n"
    mapping = {"date": 0, "description": 1, "amount": 2}
    res = _upload(client, auth, acc["id"], bad_csv, mapping=mapping, date_format="%d/%m/%Y")
    body = res.json()
    assert body["error_count"] == 1
    row = body["rows"][0]
    assert row["include"] is False
    assert "Fecha inválida" in row["error"]
    assert "Monto inválido" in row["error"]


def test_preview_detects_duplicate_against_existing_transaction(
    client, auth, make_account, make_category
):
    acc = make_account()
    cat = make_category(name="Mercado", type_="expense")
    client.post(
        "/transactions",
        json={
            "amount": 150000,
            "category_id": cat["id"],
            "description": "Compra supermercado",
            "type": "expense",
            "saving_account_id": acc["id"],
            "date": "2026-08-02T12:00:00",
        },
        headers=auth,
    )

    mapping = {"date": 0, "description": 1, "amount": 2}
    res = _upload(client, auth, acc["id"], CSV_BODY, mapping=mapping, date_format="%d/%m/%Y")
    body = res.json()
    expense_row = body["rows"][0]
    assert expense_row["is_duplicate"] is True
    assert expense_row["include"] is False
    assert body["duplicate_count"] == 1


def test_confirm_creates_transactions_and_updates_balance(client, auth, make_account, make_category):
    acc = make_account(balance=1_000_000)
    cat = make_category(name="Mercado", type_="expense")

    res = client.post(
        "/transactions/import/confirm",
        json={
            "saving_account_id": acc["id"],
            "rows": [
                {
                    "date": "2026-08-01",
                    "description": "Compra supermercado",
                    "amount": 150000,
                    "type": "expense",
                    "category_id": cat["id"],
                },
                {
                    "date": "2026-08-05",
                    "description": "Pago nomina",
                    "amount": 2000000,
                    "type": "income",
                    "category_id": cat["id"],
                },
            ],
        },
        headers=auth,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["created"] == 2
    assert body["skipped"] == 0

    acc_after = client.get("/saving-accounts", headers=auth).json()
    updated = next(a for a in acc_after if a["id"] == acc["id"])
    assert updated["balance"] == 1_000_000 - 150000 + 2000000

    txs = client.get("/transactions/with-category", headers=auth).json()
    assert txs["total"] == 2


def test_confirm_allows_balance_to_go_negative(client, auth, make_account, make_category):
    """A diferencia de POST /transactions, un import histórico no bloquea por
    fondos insuficientes."""
    acc = make_account(balance=1000)
    cat = make_category(name="Mercado", type_="expense")

    res = client.post(
        "/transactions/import/confirm",
        json={
            "saving_account_id": acc["id"],
            "rows": [
                {
                    "date": "2026-08-01",
                    "description": "Gasto grande",
                    "amount": 50000,
                    "type": "expense",
                    "category_id": cat["id"],
                }
            ],
        },
        headers=auth,
    )
    assert res.status_code == 200, res.text
    assert res.json()["created"] == 1


def test_confirm_skips_row_with_invalid_category(client, auth, make_account):
    acc = make_account(balance=1_000_000)
    res = client.post(
        "/transactions/import/confirm",
        json={
            "saving_account_id": acc["id"],
            "rows": [
                {
                    "date": "2026-08-01",
                    "description": "Algo",
                    "amount": 1000,
                    "type": "expense",
                    "category_id": 999999,
                }
            ],
        },
        headers=auth,
    )
    body = res.json()
    assert body["created"] == 0
    assert body["skipped"] == 1


def test_import_profile_upsert_and_fetch(client, auth, make_account):
    acc = make_account()
    payload = {
        "saving_account_id": acc["id"],
        "column_mapping": {"date": 0, "description": 1, "amount": 2},
        "date_format": "%d/%m/%Y",
        "has_header": True,
    }
    res = client.post("/import-profiles", json=payload, headers=auth)
    assert res.status_code == 200, res.text
    profile_id = res.json()["id"]

    # Guardar de nuevo para la misma cuenta actualiza en vez de duplicar
    payload["date_format"] = "%Y-%m-%d"
    res2 = client.post("/import-profiles", json=payload, headers=auth)
    assert res2.json()["id"] == profile_id
    assert res2.json()["date_format"] == "%Y-%m-%d"

    listed = client.get("/import-profiles", headers=auth).json()
    assert len(listed) == 1

    # Y ese perfil guardado aparece en el siguiente "inspect" de esa cuenta
    inspect = _upload(client, auth, acc["id"], CSV_BODY)
    assert inspect.json()["saved_profile"]["date_format"] == "%Y-%m-%d"
