"""Almacenamiento de archivos en Supabase Storage.

Se usa la API REST con `httpx` (ya es dependencia) en vez del SDK de
Supabase: son tres llamadas (subir, firmar, borrar) y evita otra
dependencia.

El bucket debe ser PRIVADO. Los archivos no se sirven por URL pública sino
por URL firmada de corta duración, que se genera al momento de listar: un
comprobante puede tener el monto, el banco y el nombre del usuario, así que
una URL pública y permanente sería una filtración esperando a pasar.
"""
import logging
from typing import Optional

import httpx
from fastapi import HTTPException

from app.core.config import (
    SUPABASE_SERVICE_KEY,
    SUPABASE_STORAGE_BUCKET,
    SUPABASE_URL,
)

logger = logging.getLogger(__name__)

SIGNED_URL_EXPIRES_IN = 60 * 60  # 1 hora


def is_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)


def _require_config() -> None:
    if not is_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "El almacenamiento de archivos no está configurado. "
                "Faltan SUPABASE_URL y/o SUPABASE_SERVICE_KEY."
            ),
        )


def _headers() -> dict:
    return {"Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}


def upload_file(path: str, content: bytes, content_type: str) -> None:
    """Sube un archivo. Lanza HTTPException si falla -- a diferencia del
    correo, acá no se puede degradar en silencio: el usuario cree que
    adjuntó su comprobante y tiene que ser verdad."""
    _require_config()
    try:
        response = httpx.post(
            f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_STORAGE_BUCKET}/{path}",
            headers={**_headers(), "Content-Type": content_type},
            content=content,
            timeout=30,
        )
        response.raise_for_status()
    except httpx.HTTPError:
        logger.exception("Fallo subiendo archivo a %s", path)
        raise HTTPException(status_code=502, detail="No se pudo guardar el archivo.")


def create_signed_url(path: str) -> Optional[str]:
    """URL temporal para descargar un archivo del bucket privado.

    Devuelve None si falla: que un comprobante no se pueda mostrar no debe
    tumbar el listado completo de adjuntos de una transacción.
    """
    if not is_configured():
        return None
    try:
        response = httpx.post(
            f"{SUPABASE_URL}/storage/v1/object/sign/{SUPABASE_STORAGE_BUCKET}/{path}",
            headers={**_headers(), "Content-Type": "application/json"},
            json={"expiresIn": SIGNED_URL_EXPIRES_IN},
            timeout=15,
        )
        response.raise_for_status()
        signed = response.json().get("signedURL") or response.json().get("signedUrl")
        if not signed:
            return None
        return f"{SUPABASE_URL}/storage/v1{signed}"
    except Exception:
        logger.exception("Fallo firmando URL para %s", path)
        return None


def delete_file(path: str) -> None:
    """Borra un archivo. No lanza: si el archivo ya no existe en el bucket,
    igual queremos poder eliminar la fila que lo referencia -- si no, una
    inconsistencia dejaría adjuntos imposibles de quitar."""
    if not is_configured():
        return
    try:
        httpx.request(
            "DELETE",
            f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_STORAGE_BUCKET}/{path}",
            headers=_headers(),
            timeout=15,
        )
    except Exception:
        logger.exception("Fallo borrando archivo %s", path)
