"""Catálogo de monedas y consistencia de los reportes.

Varios de estos tests existen para que no reaparezcan bugs concretos que ya
se corrigieron una vez (ver docs/ARCHITECTURE.md).
"""


def test_catalog_is_exposed(client, auth):
    res = client.get("/currencies", headers=auth)
    assert res.status_code == 200
    codes = {c["code"] for c in res.json()}
    assert {"COP", "USD", "EUR"} <= codes


def test_currency_carries_its_decimal_digits(client, auth):
    """El frontend usa esto para decidir si mostrar centavos."""
    by_code = {c["code"]: c for c in client.get("/currencies", headers=auth).json()}
    assert by_code["COP"]["decimal_digits"] == 0
    assert by_code["USD"]["decimal_digits"] == 2


def test_unknown_currency_is_rejected_clearly(client, auth):
    """Debe ser un 400 explicable, no un error de integridad crudo."""
    res = client.post(
        "/saving-accounts",
        json={"name": "Inventada", "balance": 0, "type": "bank", "currency": "XYZ"},
        headers=auth,
    )
    assert res.status_code == 400
    assert "XYZ" in res.json()["detail"]


def test_account_can_use_any_catalog_currency(client, auth):
    """Antes solo se admitían COP/USD/EUR por un enum fijo."""
    res = client.post(
        "/saving-accounts",
        json={"name": "Euros", "balance": 100, "type": "bank", "currency": "EUR"},
        headers=auth,
    )
    assert res.status_code == 200
    assert res.json()["currency"] == "EUR"


def test_summaries_cover_every_currency_in_use(client, auth, make_account):
    """Regresión: `assets-summary` omitía EUR mientras `net-worth-summary` lo
    incluía, así que las cifras no cuadraban entre pantallas."""
    make_account(name="En pesos", balance=100_000, currency="COP")
    make_account(name="En dólares", balance=500, currency="USD")
    make_account(name="En euros", balance=300, currency="EUR")

    assets = client.get("/summary-extra/assets-summary", headers=auth).json()
    net_worth = client.get("/summary-extra/net-worth-summary", headers=auth).json()

    assert set(assets["total_assets"]) == {"COP", "USD", "EUR"}
    assert set(net_worth) == set(assets["total_assets"])


def test_summaries_only_report_currencies_the_user_has(client, auth, make_account):
    """Sin cuentas en EUR, no debe aparecer una fila en cero para EUR."""
    make_account(name="Solo pesos", balance=100_000, currency="COP")

    assets = client.get("/summary-extra/assets-summary", headers=auth).json()
    assert set(assets["total_assets"]) == {"COP"}


def test_assets_summary_totals_match_account_balances(client, auth, make_account):
    make_account(name="Banco", balance=100_000, currency="COP", type_="bank")
    make_account(name="Efectivo", balance=50_000, currency="COP", type_="cash")
    make_account(name="Inversión", balance=200_000, currency="COP", type_="investment")

    assets = client.get("/summary-extra/assets-summary", headers=auth).json()
    assert assets["total_savings"]["COP"] == 150_000  # banco + efectivo
    assert assets["total_investments"]["COP"] == 200_000
    assert assets["total_assets"]["COP"] == 350_000


def test_net_worth_subtracts_debts(client, auth, make_account):
    make_account(name="Banco", balance=1_000_000, currency="COP")
    client.post(
        "/debts",
        json={
            "name": "Préstamo",
            "total_amount": 400_000,
            "interest_rate": 0,
            "currency": "COP",
            "kind": "loan",
        },
        headers=auth,
    )

    nw = client.get("/summary-extra/net-worth-summary", headers=auth).json()["COP"]
    assert nw["total_assets"] == 1_000_000
    assert nw["total_liabilities"] == 400_000
    assert nw["net_worth"] == 600_000


def test_summary_separates_income_and_expense(
    client, auth, make_account, make_category
):
    acc = make_account(balance=1_000_000)
    income_cat = make_category(name="Sueldo", type_="income")
    expense_cat = make_category(name="Mercado", type_="expense")

    client.post(
        "/transactions",
        json={
            "description": "Sueldo",
            "amount": 300_000,
            "type": "income",
            "category_id": income_cat["id"],
            "saving_account_id": acc["id"],
        },
        headers=auth,
    )
    client.post(
        "/transactions",
        json={
            "description": "Mercado",
            "amount": 120_000,
            "type": "expense",
            "category_id": expense_cat["id"],
            "saving_account_id": acc["id"],
        },
        headers=auth,
    )

    summary = client.get("/summary", headers=auth).json()["COP"]
    assert summary["total_income"] == 300_000
    assert summary["total_expense"] == 120_000
    assert summary["balance"] == 180_000


def test_transfers_are_excluded_from_summary(client, auth, make_account):
    """Mover plata entre cuentas propias no es ingreso ni gasto."""
    origin = make_account(name="Origen", balance=500_000)
    dest = make_account(name="Destino", balance=0)

    client.post(
        "/transactions/transfer",
        json={
            "amount": 200_000,
            "description": "Traslado",
            "from_account_id": origin["id"],
            "to_account_id": dest["id"],
        },
        headers=auth,
    )

    summary = client.get("/summary", headers=auth).json()["COP"]
    assert summary["total_income"] == 0
    assert summary["total_expense"] == 0
