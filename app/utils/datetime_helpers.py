"""Utilidades de fecha/hora.

Existe por un caso real: las columnas `timestamp` de producción son
**without time zone** mientras que en local son **with time zone** (drift de
esquema documentado en docs/PENDIENTES.md). Eso hace que el mismo código lea
datetimes *naive* en producción y *aware* en local, y comparar unos con otros
lanza `TypeError: can't compare offset-naive and offset-aware datetimes`.

El síntoma no es un fallo de validación sino un 500 seco, y solo en producción,
que es la peor combinación posible. Ya había dos copias de esta normalización
(`api/subscriptions.py` y `api/admin_users.py`); centralizarla evita que un
tercer sitio se olvide, que es exactamente lo que había pasado con
`api/subscriptions_admin.py`.
"""

from datetime import datetime, timezone


def as_utc(dt: datetime) -> datetime:
    """Devuelve `dt` como datetime *aware* en UTC.

    Un valor naive se asume UTC: es lo que la app escribe siempre
    (`datetime.now(timezone.utc)` / `utcnow`), así que la suposición es
    correcta para los datos existentes.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
