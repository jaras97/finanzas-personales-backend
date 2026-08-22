# Arquitectura

## Stack

- **FastAPI** 0.115 / Starlette 0.46 / Uvicorn 0.34.
- **SQLModel** 0.0.24 (SQLAlchemy 2.0) — los modelos son a la vez schema Pydantic y tabla SQLAlchemy (`class X(SQLModel, table=True)`). Engine **síncrono**; casi todas las rutas son `def`, no `async def` (excepción: `app/routes/fx.py`).
- **Alembic** 1.16 para migraciones (`alembic/versions/`, 4 revisiones a la fecha).
- **psycopg2-binary** — driver Postgres síncrono.
- **python-jose** para JWT, **passlib[bcrypt]** para hashing de contraseñas.
- **httpx** para llamadas salientes (tasas de cambio).
- Sin librería de background jobs/queue, sin caché externo (Redis, etc.) — el único "cache" es un dict en memoria de proceso en `fx.py`.

## Entrypoint y wiring (`app/main.py`)

- `lifespan` ejecuta `create_db_and_tables()` al arrancar (`SQLModel.metadata.create_all`), como red de seguridad adicional a Alembic — pero **solo Alembic aplica cambios de columnas/constraints en tablas existentes**.
- CORS con allow-list hardcodeada: `https://finanzas-personal-frontend-1xt6.vercel.app`, `https://www.balancedcent.com`, `http://localhost:3000`, `http://localhost:3001`. `allow_credentials=True`.
- Routers (cada uno define su propio `prefix`):

  | Router | Prefijo |
  |---|---|
  | `auth.router` | `/auth` |
  | `auth_extra.router` | `/auth` (comparte prefijo con el anterior) |
  | `transactions.router` | `/transactions` |
  | `categories.router` | `/categories` |
  | `saving_accounts.router` | `/saving-accounts` |
  | `debts.router` | `/debts` |
  | `subscriptions.router` | `/subscriptions` |
  | `subscriptions_admin.router` | `/subscriptions/admin` |
  | `summary.router` | `/summary` |
  | `summary_extra.router` | `/summary-extra` |
  | `cash_flow.router` | `/cash-flow` |
  | `fx_router` | `/fx` |

- `GET /` — health check público.
- Sin middleware propio aparte de CORS: no hay rate limiting ni logging middleware.

## Configuración (`app/core/config.py`, `app/database.py`)

- `config.py` **no** usa Pydantic `BaseSettings` — son variables de módulo planas cargadas con `python-dotenv` + `os.getenv`. `SECRET_KEY` no tiene default (rompe JWT silenciosamente si falta).
- `database.py` también hace su propio `load_dotenv()` (duplicado). Engine síncrono vía `sqlmodel.create_engine(DATABASE_URL, echo=False)`.
- `get_session()` es una dependencia FastAPI, pero **la mayoría de las rutas no la usan** — abren su propia sesión con `with Session(engine) as session:` directamente en el body del endpoint, en vez de usar DI. Solo `auth_extra.py`, `subscriptions.py` y `subscriptions_admin.py` usan `Depends(get_session)`. Inconsistente pero funcional; tenerlo presente al tocar código de sesión/transacciones.

## Auth y seguridad (`app/core/security.py`)

- Password hashing: bcrypt (passlib `CryptContext`).
- JWT: `jose.jwt`, algoritmo de `ALGORITHM` (default `HS256`), firmado con `SECRET_KEY`. Payload solo lleva `sub` (UUID del usuario) y `exp`.
- `oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")`.
- Tres dependencias de "usuario actual", cada una para un nivel de acceso distinto:
  - `get_current_user` — decodifica el JWT, retorna `user_id`. 401 si el token es inválido/falta `sub`.
  - `get_current_user_with_subscription_check` — además valida que exista una suscripción, esté `is_active` y no haya vencido (`end_date`). **Usada por casi todos los endpoints de negocio** (transacciones, cuentas, deudas, categorías, resúmenes, cash-flow) — la app entera está gateada por suscripción activa.
  - `get_current_admin_user` — además requiere `user.role == "admin"`. Solo usada por `subscriptions_admin.py`.

## Modelo de dominio

Ver [DATA_MODEL.md](DATA_MODEL.md) para el detalle de tablas. Puntos clave de diseño:

- **`SavingAccount`** es la cuenta real usada en la app (no `Account`, que es un modelo legacy sin uso).
- **`Transaction`** es el ledger central; las transferencias se modelan como un par expense+income unidos por `transfer_group_id`, no con `type="transfer"`.
- **`DebtTransaction`** es un subledger separado, solo para el historial de una deuda puntual (pagos/cargos), distinto de las filas que también se crean en `Transaction` para que esos movimientos aparezcan en los reportes generales.
- **Categorías de sistema** (`is_system=True`, `system_key`) se crean automáticamente al registrar un usuario (`create_base_categories`) y no pueden eliminarse ni cambiar de tipo desde la API.

## Deploy

- **Local**: `docker-compose.yml` levanta Postgres 15 en el puerto host `5433` (`finances_db` / `postgres`/`postgres`), solo para desarrollo.
- **Producción**: Fly.io (`fly.toml`, app `personal-finances-backend`, región `iad`, 1 VM compartida 1GB, auto-stop/auto-start). `release_command = "alembic upgrade head"` corre las migraciones automáticamente en cada deploy, antes de que la nueva versión reciba tráfico.
- **CI/CD**: `.github/workflows/fly-deploy.yml` — push a `main` dispara `flyctl deploy --remote-only` usando el secreto `FLY_API_TOKEN`. **No hay paso de tests ni lint** — el deploy es incondicional.
- **Base de datos de producción**: Postgres gestionado por Supabase, accedido vía `DATABASE_URL` normal con `psycopg2` (no se usa el SDK de Supabase, ni su Auth ni su Storage). La carpeta `supabase/` solo contiene metadata cacheada del CLI (`supabase link`/`status`), no hay `config.toml` ni migraciones de Supabase.

## Problemas conocidos / deuda técnica

Registrados aquí para no perder el contexto al retomar el proyecto.

- 🔴 **Credencial filtrada**: `alembic/env.py` (líneas ~18-19) tiene un connection string de Supabase **hardcodeado con password en texto plano**, que además sobreescribe el valor real de `DATABASE_URL` cuando este existe. Debe rotarse la contraseña en Supabase y eliminarse el hardcode del código lo antes posible.
- **`liabilities-summary` / `net-worth-summary`** (`summary_extra.py`): el cálculo de "pagos realizados" filtra `Transaction.type == "payment"`, valor que **nunca se asigna** (el enum real es `income`/`expense`/`transfer`). El bug está enmascarado porque `debt.total_amount` ya se decrementa en vivo en `/debts/{id}/pay`, así que el resultado final coincide con lo esperado — pero el código es frágil y engañoso si se refactoriza sin saber esto.
- **`DebtTransactionType.charge_reversal`** referenciado en `transactions.py::reverse_transaction` no existe en el enum (`payment`/`interest_charge`/`extra_charge`); el `hasattr()` guard hace que las reversiones de compras de tarjeta se registren como `extra_charge` en vez de un tipo dedicado de reversión.
- **`POST /saving-accounts/{id}/withdraw`** etiqueta la transacción resultante con `source_type="account_deposit"` (debería ser algo como `account_withdraw`) — copy-paste artifact.
- **Inconsistencia de respuesta**: `deposit` devuelve `{"message", "nuevo_balance"}` mientras que `withdraw` devuelve el `SavingAccountRead` completo.
- **Borrado de transferencias**: `DELETE /transactions/{id}` revierte el balance solo de la fila borrada; si se borra una sola pata de una transferencia (en vez de ambas), la otra pata queda huérfana con su efecto de balance sin revertir.
- **Modelos sin uso**: `Account` e `Investment` no los referencia ningún endpoint — candidatos a eliminar si se confirma que no hay planes de retomarlos.
- **Reset de contraseña en memoria**: `RESET_TOKENS` en `auth_extra.py` es un dict de proceso — se pierde en cada reinicio/deploy y no escala a más de una instancia. El envío de email está comentado (`send_email`), así que el flujo de "olvidé mi contraseña" no envía correos reales hoy.
- **`/fx/rate`** no tiene dependencia de auth — es un endpoint público, y su cache de 12h es en memoria de proceso (no compartido entre instancias, se pierde al reiniciar).
- **Balance inicial sin ledger**: crear una cuenta con `balance` distinto de cero no genera ninguna fila en `Transaction` — el balance inicial no queda trazado como movimiento.
