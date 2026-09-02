"""Los pasivos no deben descontar los pagos dos veces.

Al pagar una deuda ocurren DOS cosas (`api/debts.py::pay_debt`):
  1. `debt.total_amount` se decrementa -- ya queda el saldo pendiente.
  2. se crea una `DebtTransaction` de tipo `payment`.

`summary_extra.py` calculaba el pasivo como `total_amount - suma_de_pagos`,
restando los pagos por segunda vez sobre un saldo que ya los descontaba. El
efecto es un pasivo subestimado y, por lo tanto, un patrimonio neto inflado:
en una app de finanzas, un número que se cree y está mal.
"""

import pytest


def _deuda(client, auth, **overrides):
    payload = {
        "name": "Préstamo",
        "total_amount": 1_000_000,
        "interest_rate": 10.0,
        "currency": "COP",
        "kind": "loan",
    }
    payload.update(overrides)
    res = client.post("/debts", json=payload, headers=auth)
    assert res.status_code == 200, res.text
    return res.json()


@pytest.fixture
def deuda_pagada_parcialmente(client, auth, make_account):
    """Deuda de 1.000.000 con 300.000 pagados: el pendiente real es 700.000."""
    cuenta = make_account(balance=5_000_000)
    deuda = _deuda(client, auth)
    res = client.post(
        f"/debts/{deuda['id']}/pay",
        json={"amount": 300_000, "saving_account_id": cuenta["id"]},
        headers=auth,
    )
    assert res.status_code == 200, res.text
    return deuda


def test_liabilities_summary_no_descuenta_el_pago_dos_veces(
    client, auth, deuda_pagada_parcialmente
):
    res = client.get("/summary-extra/liabilities-summary", headers=auth)
    assert res.status_code == 200, res.text

    # Con el bug daba 400.000 (700.000 - 300.000)
    assert res.json()["total_liabilities"]["COP"] == 700_000


def test_net_worth_summary_no_infla_el_patrimonio(
    client, auth, deuda_pagada_parcialmente
):
    res = client.get("/summary-extra/net-worth-summary", headers=auth)
    assert res.status_code == 200, res.text

    cop = res.json()["COP"]
    # Activos: 5.000.000 - 300.000 pagados = 4.700.000. Pasivo real: 700.000.
    assert cop["total_liabilities"] == 700_000
    assert cop["total_assets"] == 4_700_000
    assert cop["net_worth"] == 4_000_000


def test_una_deuda_sin_pagos_no_cambia(client, auth, make_account):
    """Control: sin pagos, ambos cálculos coinciden. Si solo probáramos el
    caso con pagos, quitar el descuento por completo también pasaría."""
    make_account(balance=1_000_000)
    _deuda(client, auth, total_amount=250_000)

    res = client.get("/summary-extra/liabilities-summary", headers=auth)

    assert res.json()["total_liabilities"]["COP"] == 250_000


def test_deuda_totalmente_pagada_deja_pasivo_en_cero(
    client, auth, make_account
):
    cuenta = make_account(balance=5_000_000)
    deuda = _deuda(client, auth, total_amount=400_000)
    client.post(
        f"/debts/{deuda['id']}/pay",
        json={"amount": 400_000, "saving_account_id": cuenta["id"]},
        headers=auth,
    )

    res = client.get("/summary-extra/liabilities-summary", headers=auth)

    assert res.json()["total_liabilities"].get("COP", 0) == 0
