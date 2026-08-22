from dotenv import load_dotenv
import os

load_dotenv()  # Carga automáticamente desde .env

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))

# Cookie de sesión (auth httpOnly). En producción, COOKIE_DOMAIN debe ser el
# dominio raíz compartido entre frontend y backend (p. ej. ".balancedcent.com")
# para que la cookie viaje tanto al middleware del frontend como a la API.
# Sin configurar, la cookie queda acotada al host exacto que la emite (correcto
# para desarrollo local, donde frontend y backend comparten "localhost").
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
COOKIE_DOMAIN = os.getenv("COOKIE_DOMAIN") or None
COOKIE_SECURE = ENVIRONMENT == "production"