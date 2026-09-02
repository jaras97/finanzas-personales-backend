"""Depósito y retiro directos sobre una cuenta.

El retiro archivaba su transacción como `source_type="account_deposit"`
(copiado del endpoint de depósito), así que un retiro quedaba registrado como
depósito y cualquier filtro por origen los mezclaba.
"""


def _transacciones(client, auth):
    res = client.get("/transactions/with-category", headers=auth)
    assert res.status_code == 200, res.text
    return res.json()["items"]


def test_el_retiro_se_archiva_como_retiro(client, auth, make_account):
    cuenta = make_account(balance=1_000_000)

    res = client.post(
        f"/saving-accounts/{cuenta['id']}/withdraw",
        json={"amount": 200_000},
        headers=auth,
    )
    assert res.status_code == 200, res.text

    tx = _transacciones(client, auth)[0]
    assert tx["source_type"] == "account_withdraw"
    assert tx["type"] == "expense"


def test_el_deposito_sigue_archivandose_como_deposito(client, auth, make_account):
    """Control: sin esto, renombrar ambos a lo mismo pasaría el test anterior."""
    cuenta = make_account(balance=100_000)

    res = client.post(
        f"/saving-accounts/{cuenta['id']}/deposit",
        json={"amount": 50_000},
        headers=auth,
    )
    assert res.status_code == 200, res.text

    tx = _transacciones(client, auth)[0]
    assert tx["source_type"] == "account_deposit"
    assert tx["type"] == "income"


def test_los_saldos_se_mueven_en_la_direccion_correcta(client, auth, make_account):
    cuenta = make_account(balance=1_000_000)

    client.post(f"/saving-accounts/{cuenta['id']}/withdraw",
                json={"amount": 300_000}, headers=auth)
    client.post(f"/saving-accounts/{cuenta['id']}/deposit",
                json={"amount": 100_000}, headers=auth)

    cuentas = client.get("/saving-accounts", headers=auth).json()
    saldo = next(c for c in cuentas if c["id"] == cuenta["id"])["balance"]
    assert saldo == 800_000
