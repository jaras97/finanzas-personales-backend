"""Infraestructura de pruebas.

Dos cosas importantes sobre cómo está montada la app condicionan este archivo:

1. `app/database.py` crea el engine **al importarse**, leyendo `DATABASE_URL`.
   Por eso aquí se fija esa variable antes de cualquier import de `app.*`.
   `load_dotenv()` no pisa variables ya presentes en el entorno, así que el
   `.env` de desarrollo no interfiere.

2. Casi todas las rutas abren su propia sesión con `Session(engine)` en vez de
   usar la dependencia `get_session`. Eso hace inviable inyectar una sesión de
   prueba por DI: la única forma limpia de aislar es apuntar el engine real a
   una base de datos separada, que es lo que se hace aquí.

Se prueba contra Postgres real (no SQLite) a propósito: el proyecto usa tipos
específicos de Postgres (enums, UUID) y ya tuvo incidentes por diferencias
entre entornos, así que un motor distinto en pruebas daría falsa confianza.
"""
import os
import uuid

# --- Debe ir antes de importar app.* ---------------------------------------
DEFAULT_TEST_DB = "postgresql://postgres:postgres@localhost:5433/finances_test"
os.environ.setdefault("DATABASE_URL", os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DB))
os.environ.setdefault("SECRET_KEY", "test-secret-not-used-outside-tests")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
# ---------------------------------------------------------------------------

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402
from sqlmodel import Session, SQLModel  # noqa: E402


def _ensure_database_exists(url: str) -> None:
    """Crea la base de pruebas si no existe, para que correr `pytest` en local
    no requiera pasos manuales previos."""
    try:
        create_engine(url).connect().close()
        return
    except OperationalError as exc:
        if "does not exist" not in str(exc):
            raise

    base, _, dbname = url.rpartition("/")
    admin = create_engine(f"{base}/postgres", isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{dbname}"'))
    admin.dispose()


_ensure_database_exists(os.environ["DATABASE_URL"])

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.currency import Currency  # noqa: E402


SEED_CURRENCIES = [
    ("COP", "Peso colombiano", "$", 0),
    ("USD", "Dólar estadounidense", "$", 2),
    ("EUR", "Euro", "€", 2),
]


@pytest.fixture(scope="session", autouse=True)
def _schema():
    """Esquema creado una vez para toda la sesión de pruebas.

    Se usa `create_all` en vez de correr Alembic porque lo que interesa validar
    aquí es la lógica de negocio, no el historial de migraciones. (Las
    migraciones se ejercitan en cada deploy vía `release_command`.)
    """
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    yield
    SQLModel.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def _clean_tables():
    """Cada test arranca con la base vacía salvo el catálogo de monedas.

    TRUNCATE ... CASCADE en vez de borrar por tabla: evita tener que ordenar
    las dependencias de claves foráneas a mano cada vez que se agrega un
    modelo nuevo.
    """
    tables = [t.name for t in SQLModel.metadata.sorted_tables if t.name != "currency"]
    quoted = ", ".join('"{}"'.format(t) for t in tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE"))
        for code, name, symbol, digits in SEED_CURRENCIES:
            conn.execute(
                text(
                    "INSERT INTO currency (code, name, symbol, decimal_digits) "
                    "VALUES (:c, :n, :s, :d) ON CONFLICT (code) DO NOTHING"
                ),
                {"c": code, "n": name, "s": symbol, "d": digits},
            )
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def session():
    with Session(engine) as s:
        yield s


# --- Helpers de alto nivel --------------------------------------------------


def _unique_email() -> str:
    return f"user-{uuid.uuid4().hex[:10]}@test.dev"


@pytest.fixture
def make_user(client):
    """Crea un usuario con suscripción activa y devuelve un cliente autenticado.

    La suscripción se inserta directo en la base: el endpoint que la otorga
    requiere un admin, y para la mayoría de tests ese rodeo no aporta nada.
    """

    def _make(email: str | None = None, password: str = "TestPass123!", role: str = "user",
              with_subscription: bool = True):
        email = email or _unique_email()
        res = client.post("/auth/register", json={"email": email, "password": password})
        assert res.status_code == 200, res.text
        user_id = res.json()["id"]

        with engine.begin() as conn:
            if role != "user":
                conn.execute(
                    text('UPDATE "user" SET role = :r WHERE id = :i'),
                    {"r": role, "i": user_id},
                )
            if with_subscription:
                conn.execute(
                    text(
                        "INSERT INTO subscription (user_id, start_date, end_date, is_active, "
                        "created_at, updated_at) VALUES (:u, now(), now() + interval '30 days', "
                        "true, now(), now())"
                    ),
                    {"u": user_id},
                )

        login = client.post(
            "/auth/login",
            data={"username": email, "password": password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]

        return {
            "id": user_id,
            "email": email,
            "password": password,
            "headers": {"Authorization": f"Bearer {token}"},
        }

    return _make


@pytest.fixture
def user(make_user):
    return make_user()


@pytest.fixture
def auth(user):
    return user["headers"]


@pytest.fixture
def make_account(client, auth):
    def _make(name="Cuenta", balance=1_000_000.0, currency="COP", type_="bank"):
        res = client.post(
            "/saving-accounts",
            json={"name": name, "balance": balance, "type": type_, "currency": currency},
            headers=auth,
        )
        assert res.status_code == 200, res.text
        return res.json()

    return _make


@pytest.fixture
def make_category(client, auth):
    def _make(name="Categoría", type_="expense"):
        res = client.post(
            "/categories", json={"name": name, "type": type_}, headers=auth
        )
        assert res.status_code == 200, res.text
        return res.json()

    return _make
