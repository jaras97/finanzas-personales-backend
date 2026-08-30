from dotenv import load_dotenv
import os

load_dotenv()  # Carga automáticamente desde .env

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))
# Ventana de renovación: mientras el usuario vuelva dentro de este plazo, su
# sesión se renueva sola y no lo expulsa a media tarea.
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 30))

# Cookie de sesión (auth httpOnly). En producción, COOKIE_DOMAIN debe ser el
# dominio raíz compartido entre frontend y backend (p. ej. ".balancedcent.com")
# para que la cookie viaje tanto al middleware del frontend como a la API.
# Sin configurar, la cookie queda acotada al host exacto que la emite (correcto
# para desarrollo local, donde frontend y backend comparten "localhost").
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
COOKIE_DOMAIN = os.getenv("COOKIE_DOMAIN") or None
COOKIE_SECURE = ENVIRONMENT == "production"

# --- Correo transaccional (Resend) ------------------------------------------
# Sin RESEND_API_KEY el envío queda deshabilitado: los endpoints siguen
# funcionando y el enlace se registra en el log, para poder desarrollar sin
# llaves. En producción, si falta, se registra un error visible.
RESEND_API_KEY = os.getenv("RESEND_API_KEY") or None
EMAIL_FROM = os.getenv("EMAIL_FROM", "Balanced Cent <no-reply@balancedcent.com>")
# Base para armar el enlace de restablecimiento que se envía por correo.
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")
PASSWORD_RESET_EXPIRE_MINUTES = int(os.getenv("PASSWORD_RESET_EXPIRE_MINUTES", 60))