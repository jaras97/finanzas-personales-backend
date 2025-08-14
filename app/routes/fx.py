# app/routes/fx.py
from fastapi import APIRouter, HTTPException, Query
from typing import Literal, Dict, Tuple
import httpx, time

Currency = Literal["COP", "USD", "EUR"]
router = APIRouter(prefix="/fx", tags=["fx"])

# Cache TTL en memoria (clave: (from,to) -> (timestamp, rate))
_CACHE: Dict[Tuple[str, str], Tuple[float, float]] = {}
TTL_SECONDS = 60 * 60 * 12  # 12 horas

async def fetch_rate_exchangerate_host(base: str, target: str) -> float:
    # https://api.exchangerate.host/convert?from=USD&to=COP
    url = f"https://api.exchangerate.host/convert?from={base}&to={target}"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url)
        r.raise_for_status()
        data = r.json()
        if data.get("result") is not None:
            return float(data["result"])
        info = data.get("info", {})
        if info.get("rate") is not None:
            return float(info["rate"])
        raise ValueError("No rate in response")

async def fetch_rate_open_er_api(base: str, target: str) -> float:
    # https://open.er-api.com/v6/latest/USD  -> rates[target]
    url = f"https://open.er-api.com/v6/latest/{base}"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url)
        r.raise_for_status()
        data = r.json()
        rates = data.get("rates", {})
        if data.get("result") == "success" and target in rates:
            return float(rates[target])
        raise ValueError("No rate in response")

@router.get("/rate")
async def get_rate(from_: Currency = Query(..., alias="from"), to: Currency = Query(...)):
    if from_ == to:
        return {"from": from_, "to": to, "rate": 1.0, "source": "identity", "as_of": int(time.time())}

    key = (from_, to)
    now = time.time()
    if key in _CACHE:
        ts, rate = _CACHE[key]
        if now - ts < TTL_SECONDS:
            return {"from": from_, "to": to, "rate": rate, "source": "cache", "as_of": int(ts)}

    # Proveedor primario + fallback
    try:
        rate = await fetch_rate_exchangerate_host(from_, to)
        source = "exchangerate.host"
    except Exception:
        try:
            rate = await fetch_rate_open_er_api(from_, to)
            source = "open.er-api.com"
        except Exception:
            raise HTTPException(status_code=502, detail="No fue posible obtener la tasa de cambio")

    _CACHE[key] = (now, rate)
    return {"from": from_, "to": to, "rate": rate, "source": source, "as_of": int(now)}
