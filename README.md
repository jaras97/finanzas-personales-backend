# finanzas-personales-backend

API REST para la app de finanzas personales **Balanced Cent**. Gestiona usuarios, cuentas de ahorro/inversión, deudas (préstamos y tarjetas de crédito), transacciones, categorías y suscripciones. Consumida por [finanzas-personal-frontend](../frontend).

> Documentación detallada en [`docs/`](docs): [arquitectura](docs/ARCHITECTURE.md), [modelo de datos](docs/DATA_MODEL.md), [referencia de la API](docs/API.md).
>
> Transversales a ambos repos: **[pendientes](docs/PENDIENTES.md)** (incluye una acción manual crítica) y [plan de mejora](docs/PLAN_DE_MEJORA.md).

## Stack

- **FastAPI** 0.115 (Uvicorn) — framework web, todas las rutas son síncronas (`def`, no `async def`), excepto `app/routes/fx.py`.
- **SQLModel** (SQLAlchemy 2.0) — ORM síncrono, un engine (`app/database.py`).
- **Alembic** — migraciones (`alembic/versions/`).
- **PostgreSQL** — Postgres 15 en local (docker-compose), Supabase Postgres en producción.
- **python-jose** + **passlib[bcrypt]** — JWT y hashing de contraseñas.
- **Fly.io** — hosting, deploy automático vía GitHub Actions al hacer push a `main`.

## Requisitos

- Python 3.11
- Docker (para la base de datos local) o un Postgres accesible

## Puesta en marcha local

```bash
# 1. Levantar Postgres local (puerto 5433)
docker-compose up -d

# 2. Crear entorno virtual e instalar dependencias
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Configurar variables de entorno
cp .env.example .env
# editar .env si es necesario (DATABASE_URL ya apunta al docker-compose por defecto)

# 4. Aplicar migraciones
alembic upgrade head

# 5. Levantar el servidor
uvicorn app.main:app --reload --port 8000
```

La API queda disponible en `http://localhost:8000` (docs interactivas en `/docs`, generadas automáticamente por FastAPI).

> Nota: `app/main.py` también llama `SQLModel.metadata.create_all(engine)` al arrancar, además de Alembic — cualquier tabla nueva en los modelos se crea automáticamente aunque falte migración, pero **los cambios de columnas/constraints solo se aplican vía Alembic**. Siempre generar/correr migraciones para cambios de esquema reales.

## Variables de entorno

Ver [`.env.example`](.env.example). Resumen:

| Variable | Requerida | Descripción |
|---|---|---|
| `DATABASE_URL` | sí | Cadena de conexión Postgres |
| `SECRET_KEY` | sí | Secreto de firma JWT — debe coincidir con `JWT_SECRET` del frontend |
| `ALGORITHM` | no (default `HS256`) | Algoritmo de firma JWT |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | no (default `30`) | Expiración del access token (y de la cookie de sesión) |
| `ENVIRONMENT` | no (default `development`) | `production` marca la cookie de sesión como `Secure` |
| `COOKIE_DOMAIN` | no (vacío en local) | Dominio de la cookie de sesión. En producción debe ser el dominio padre compartido con el frontend (`.balancedcent.com`) — si no coincide, el login no funciona entre el frontend y la API |

## Estructura del proyecto

```
app/
  main.py              # entrypoint FastAPI, wiring de routers, CORS
  database.py          # engine, sesión, create_db_and_tables()
  core/
    config.py           # carga de env vars (SECRET_KEY, ALGORITHM, ...)
    security.py          # hashing, JWT, dependencias get_current_user*
  models/               # tablas SQLModel (ver docs/DATA_MODEL.md)
  schemas/              # schemas Pydantic de request/response
  api/                  # routers de negocio (ver docs/API.md)
  routes/fx.py          # endpoint público de tasas de cambio
  utils/                # helpers compartidos (balances, categorías sistema)
  constants/categories.py
  scripts/backfill_categories.py
alembic/                # migraciones
drop_savingaccount.py   # script de mantenimiento puntual (no forma parte de la app)
reset_db.py             # script destructivo de reseteo de esquema (¡solo dev!)
```

## Scripts sueltos (no forman parte de la app en runtime)

- `reset_db.py` — **destructivo**: borra y recrea el schema `public` completo. Nunca correr contra producción.
- `drop_savingaccount.py` — elimina la tabla legacy `savingaccount` (reemplazada por `saving_account`).
- `app/scripts/backfill_categories.py` — backfill antiguo de categorías base, superado por `app/utils/category_helpers.py::create_base_categories`.

## Deploy

Push a `main` dispara `.github/workflows/fly-deploy.yml`, que ejecuta `flyctl deploy --remote-only` (sin tests ni lint previos) usando el secret de GitHub `FLY_API_TOKEN`. `fly.toml` define `release_command = "alembic upgrade head"`, así que las migraciones corren automáticamente en cada deploy antes de que la nueva versión reciba tráfico. Servido en `https://api.balancedcent.com` (dominio propio) además de `https://personal-finances-backend.fly.dev`. Más detalle en [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#deploy).

⚠️ Pendiente: la contraseña de Supabase que estuvo hardcodeada en `alembic/env.py` (ya corregido en código) sigue siendo válida hasta que se rote manualmente en el dashboard de Supabase — ver [docs/ARCHITECTURE.md — Problemas conocidos](docs/ARCHITECTURE.md#problemas-conocidos--deuda-técnica).
