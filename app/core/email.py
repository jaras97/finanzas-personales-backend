"""Envío de correo transaccional vía Resend.

Se llama a la API REST directamente con `httpx` (ya es dependencia del
proyecto por `/fx/rate`) en vez de sumar el SDK de Resend: es un solo POST
y evita una dependencia más.

Sin `RESEND_API_KEY` configurada el envío queda deshabilitado y el enlace se
escribe en el log. Eso permite desarrollar y correr los tests sin llaves, y
sin que un fallo de correo tumbe el endpoint que lo invoca.
"""
import logging

import httpx

from app.core.config import EMAIL_FROM, ENVIRONMENT, RESEND_API_KEY

logger = logging.getLogger(__name__)

RESEND_ENDPOINT = "https://api.resend.com/emails"


def send_email(to: str, subject: str, html: str) -> bool:
    """Devuelve True si el correo se entregó a Resend.

    Nunca lanza: el llamador (p. ej. "olvidé mi contraseña") no debe fallar
    ni cambiar su respuesta porque el proveedor de correo esté caído -- eso
    filtraría qué direcciones existen.
    """
    if not RESEND_API_KEY:
        message = "RESEND_API_KEY no configurada: correo no enviado a %s (asunto: %s)"
        if ENVIRONMENT == "production":
            logger.error(message, to, subject)
        else:
            logger.warning(message, to, subject)
        return False

    try:
        response = httpx.post(
            RESEND_ENDPOINT,
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"from": EMAIL_FROM, "to": [to], "subject": subject, "html": html},
            timeout=10,
        )
        response.raise_for_status()
        return True
    except Exception:
        # Se registra con traza para poder diagnosticar, pero el flujo sigue.
        logger.exception("Fallo enviando correo a %s (asunto: %s)", to, subject)
        return False


def send_password_reset_email(to: str, reset_url: str, expire_minutes: int) -> bool:
    # Fuera de producción y sin llave configurada, el enlace va al log para
    # poder probar el flujo completo sin proveedor de correo. Nunca en
    # producción: un token de restablecimiento en los logs es una credencial
    # a la vista de cualquiera con acceso a ellos.
    if not RESEND_API_KEY and ENVIRONMENT != "production":
        logger.warning("Enlace de restablecimiento para %s: %s", to, reset_url)

    subject = "Restablece tu contraseña de Balanced Cent"
    html = f"""\
<div style="font-family:system-ui,-apple-system,sans-serif;max-width:480px;margin:0 auto;color:#1e293b">
  <h2 style="color:#0f172a">Restablece tu contraseña</h2>
  <p>Recibimos una solicitud para restablecer la contraseña de tu cuenta en Balanced Cent.</p>
  <p style="margin:28px 0">
    <a href="{reset_url}"
       style="background:#059669;color:#fff;padding:12px 22px;border-radius:8px;
              text-decoration:none;display:inline-block;font-weight:600">
      Crear una contraseña nueva
    </a>
  </p>
  <p style="color:#64748b;font-size:14px">
    El enlace vence en {expire_minutes} minutos y solo se puede usar una vez.
  </p>
  <p style="color:#64748b;font-size:14px">
    Si no fuiste tú, puedes ignorar este correo: tu contraseña actual sigue funcionando.
  </p>
  <hr style="border:none;border-top:1px solid #e2e8f0;margin:28px 0">
  <p style="color:#94a3b8;font-size:12px">
    Si el botón no funciona, copia este enlace en tu navegador:<br>{reset_url}
  </p>
</div>"""
    return send_email(to, subject, html)
