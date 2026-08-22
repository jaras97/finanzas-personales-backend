"""In-memory rate limiting for auth endpoints.

Same pattern already used elsewhere in this codebase (the password-reset
token store in auth_extra.py, the FX rate cache): a plain in-process dict.
That means limits reset on deploy/restart and aren't shared across the two
Fly machines -- acceptable for slowing down brute force on a small app, not
a guarantee. If this app ever needs a real guarantee, move this to Redis.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from fastapi import HTTPException, Request, status


class SlidingWindowRateLimiter:
    def __init__(self, max_attempts: int, window_seconds: int):
        self.max_attempts = max_attempts
        self.window = timedelta(seconds=window_seconds)
        self._attempts: Dict[str, List[datetime]] = defaultdict(list)

    def _prune(self, key: str, now: datetime) -> List[datetime]:
        cutoff = now - self.window
        kept = [t for t in self._attempts[key] if t > cutoff]
        self._attempts[key] = kept
        return kept

    def check(self, key: str) -> None:
        now = datetime.now(timezone.utc)
        if len(self._prune(key, now)) >= self.max_attempts:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Demasiados intentos. Espera unos minutos e inténtalo de nuevo.",
            )

    def record_failure(self, key: str) -> None:
        self._attempts[key].append(datetime.now(timezone.utc))

    def reset(self, key: str) -> None:
        self._attempts.pop(key, None)


# Dos límites independientes: por correo (protege esa cuenta puntual de
# fuerza bruta) y por IP (protege contra un mismo origen probando muchos
# correos). Cualquiera de los dos que se agote bloquea el intento.
login_limiter_by_email = SlidingWindowRateLimiter(max_attempts=5, window_seconds=15 * 60)
login_limiter_by_ip = SlidingWindowRateLimiter(max_attempts=20, window_seconds=15 * 60)


def get_client_ip(request: Request) -> str:
    # Fly's edge sets Fly-Client-IP; fall back to the standard proxy header,
    # then the raw connection (only meaningful when not behind a proxy).
    fly_ip = request.headers.get("Fly-Client-IP")
    if fly_ip:
        return fly_ip
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
