"""Patrimonio neto consolidado en una moneda de referencia.

`User.report_currency` default "COP". La conversión usa la tasa de HOY
(`/fx/rate`, mockeada acá para no depender de red), nunca una tasa
histórica por transacción -- documentado como aproximación, no
reconstrucción exacta.
"""
from unittest.mock import AsyncMock, patch


def test_report_currency_defaults_to_cop_and_can_be_changed(client, auth):
    me = client.get("/auth/me", headers=auth).json()
    assert me["report_currency"] == "COP"

    res = client.patch("/account/preferences", json={"report_currency": "USD"}, headers=auth)
    assert res.status_code == 200, res.text
    assert res.json()["report_currency"] == "USD"

    me2 = client.get("/auth/me", headers=auth).json()
    assert me2["report_currency"] == "USD"


def test_cannot_set_unsupported_currency(client, auth):
    res = client.patch("/account/preferences", json={"report_currency": "ZZZ"}, headers=auth)
    assert res.status_code == 400


def test_consolidated_same_currency_as_report_needs_no_conversion(
    client, auth, make_account
):
    make_account(balance=1_000_000, currency="COP")
    res = client.get("/summary-extra/net-worth-consolidated", headers=auth)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["report_currency"] == "COP"
    assert body["total_assets"] == 1_000_000
    assert body["degraded"] is False
    assert body["breakdown"][0]["rate_used"] == 1.0


def test_consolidated_converts_other_currencies_with_mocked_rate(
    client, auth, make_account
):
    make_account(name="COP", balance=1_000_000, currency="COP")
    make_account(name="USD", balance=100, currency="USD")

    with patch("app.api.summary_extra.resolve_rate", new=AsyncMock(return_value={"rate": 4000.0})):
        res = client.get("/summary-extra/net-worth-consolidated", headers=auth)

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total_assets"] == 1_000_000 + 100 * 4000.0
    assert body["degraded"] is False
    usd_row = next(b for b in body["breakdown"] if b["currency"] == "USD")
    assert usd_row["rate_used"] == 4000.0
    assert usd_row["converted_assets"] == 400_000.0


def test_consolidated_degrades_gracefully_when_fx_fails(client, auth, make_account):
    from fastapi import HTTPException

    make_account(name="COP", balance=1_000_000, currency="COP")
    make_account(name="USD", balance=100, currency="USD")

    async def _boom(*args, **kwargs):
        raise HTTPException(status_code=502, detail="No fue posible obtener la tasa de cambio")

    with patch("app.api.summary_extra.resolve_rate", new=_boom):
        res = client.get("/summary-extra/net-worth-consolidated", headers=auth)

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["degraded"] is True
    # El total solo refleja lo que sí se pudo convertir (COP, 1:1)
    assert body["total_assets"] == 1_000_000
    usd_row = next(b for b in body["breakdown"] if b["currency"] == "USD")
    assert usd_row["rate_used"] is None
    assert usd_row["converted_assets"] is None
    assert usd_row["original_assets"] == 100
