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
- Sin middleware propio aparte de CORS: no hay logging middleware. `/auth/login` sí tiene rate limiting propio (no vía middleware) — ver sección de Auth.
- CORS incluye `https://www.balancedcent.com` (dominio de producción del frontend) y `https://api.balancedcent.com` no necesita estar en esta lista (es el propio backend, no un origen que llame al backend).

## Configuración (`app/core/config.py`, `app/database.py`)

- `config.py` **no** usa Pydantic `BaseSettings` — son variables de módulo planas cargadas con `python-dotenv` + `os.getenv`. `SECRET_KEY` no tiene default (rompe JWT silenciosamente si falta).
- `database.py` también hace su propio `load_dotenv()` (duplicado). Engine síncrono vía `sqlmodel.create_engine(DATABASE_URL, echo=False)`.
- `get_session()` es una dependencia FastAPI, pero **la mayoría de las rutas no la usan** — abren su propia sesión con `with Session(engine) as session:` directamente en el body del endpoint, en vez de usar DI. Solo `auth_extra.py`, `subscriptions.py` y `subscriptions_admin.py` usan `Depends(get_session)`. Inconsistente pero funcional; tenerlo presente al tocar código de sesión/transacciones.

## Auth y seguridad (`app/core/security.py`, `app/api/auth.py`, `app/core/rate_limit.py`)

- Password hashing: bcrypt (passlib `CryptContext`).
- JWT: `jose.jwt`, algoritmo de `ALGORITHM` (default `HS256`), firmado con `SECRET_KEY`. Payload solo lleva `sub` (UUID del usuario) y `exp`.
- **Doble mecanismo de transporte del token** (desde 2026-08-22): `POST /auth/login` fija una cookie httpOnly (`access_token`) además de devolver `{access_token, token_type}` en el body. `get_token()` (dependencia base de la que salen las tres de abajo) acepta el token desde el header `Authorization: Bearer` **o** desde la cookie, en ese orden — el header sigue existiendo por compatibilidad con Postman/Swagger/scripts, pero el frontend web ya solo usa la cookie (ver `frontend/docs/ARCHITECTURE.md`). `oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)` (no rechaza solo por faltar el header, deja que `get_token` intente la cookie antes de devolver 401).
- `POST /auth/logout` limpia la cookie (`response.delete_cookie`) — necesario porque JS no puede borrar una cookie httpOnly por sí solo.
- Config de la cookie (`app/core/config.py`): `ENVIRONMENT` (`development` default, `production` en Fly) controla `COOKIE_SECURE`; `COOKIE_DOMAIN` (vacío en local, `.balancedcent.com` en producción) es lo que permite que la misma cookie llegue tanto al middleware del frontend (dominio `balancedcent.com`) como a la API (`api.balancedcent.com`) — **debe ser el dominio padre compartido, no funciona si backend y frontend están en dominios distintos** (ver incidente de dominio en el README raíz del monorepo / memoria de proyecto).
- **Rate limiting en `/auth/login`** (`app/core/rate_limit.py`): limitador in-memory de ventana deslizante, 5 intentos fallidos por correo / 15 min y 20 por IP / 15 min (lo que se agote primero), se resetea en un login exitoso. Mismo patrón que `RESET_TOKENS` (dict en memoria de proceso) — no persiste entre deploys ni se comparte entre las 2 máquinas de Fly; suficiente para desincentivar fuerza bruta en una app de este tamaño, no una garantía dura.
- Tres dependencias de "usuario actual", cada una para un nivel de acceso distinto:
  - `get_current_user` — decodifica el JWT, retorna `user_id`. 401 si el token es inválido/falta `sub`.
  - `get_current_user_with_subscription_check` — además valida que exista una suscripción, esté `is_active` y no haya vencido (`end_date`). **Usada por casi todos los endpoints de negocio** (transacciones, cuentas, deudas, categorías, resúmenes, cash-flow) — la app entera está gateada por suscripción activa.
  - `get_current_admin_user` — además requiere `user.role == "admin"`. Solo usada por `subscriptions_admin.py`.
- **Row-Level Security**: activado (2026-08-22) en las 11 tablas del schema `public`, sin políticas. El backend se conecta como dueño de las tablas (vía `DATABASE_URL`), así que RLS no le afecta; lo que cierra es el acceso público que Supabase expone en paralelo vía su API PostgREST (alcanzable con la anon/service key aunque la app nunca use el SDK de Supabase).

## Modelo de dominio

Ver [DATA_MODEL.md](DATA_MODEL.md) para el detalle de tablas. Puntos clave de diseño:

- **`SavingAccount`** es la cuenta real usada en la app (no `Account`, que es un modelo legacy sin uso).
- **`Transaction`** es el ledger central; las transferencias se modelan como un par expense+income unidos por `transfer_group_id`, no con `type="transfer"`.
- **`DebtTransaction`** es un subledger separado, solo para el historial de una deuda puntual (pagos/cargos), distinto de las filas que también se crean en `Transaction` para que esos movimientos aparezcan en los reportes generales.
- **Categorías de sistema** (`is_system=True`, `system_key`) se crean automáticamente al registrar un usuario (`create_base_categories`) y no pueden eliminarse ni cambiar de tipo desde la API.

## Deploy

- **Local**: `docker-compose.yml` levanta Postgres 15 en el puerto host `5433` (`finances_db` / `postgres`/`postgres`), solo para desarrollo.
- **Producción**: Fly.io (`fly.toml`, app `personal-finances-backend`, región `iad`, 1 VM compartida 1GB, auto-stop/auto-start). Servido en `https://api.balancedcent.com` (dominio propio, cert Let's Encrypt vía `flyctl certs create`, DNS: A `66.241.125.141` + AAAA `2a09:8280:1::83:41e:0`) — necesario para que la cookie de sesión sea compartida con el frontend (mismo dominio padre `balancedcent.com`); el host `personal-finances-backend.fly.dev` original sigue funcionando también. `release_command = "alembic upgrade head"` corre las migraciones automáticamente en cada deploy, antes de que la nueva versión reciba tráfico.
- **CI/CD**: `.github/workflows/fly-deploy.yml` — push a `main` dispara `flyctl deploy --remote-only` usando el secreto `FLY_API_TOKEN`. **No hay paso de tests ni lint** — el deploy es incondicional. Confirmado funcionando de nuevo desde 2026-08-22 (ver "Problemas conocidos" — estuvo roto casi un año).
- **Base de datos de producción**: Postgres gestionado por Supabase, accedido vía `DATABASE_URL` normal con `psycopg2` (no se usa el SDK de Supabase, ni su Auth ni su Storage). La carpeta `supabase/` solo contiene metadata cacheada del CLI (`supabase link`/`status`), no hay `config.toml` ni migraciones de Supabase.

## Problemas conocidos / deuda técnica

Registrados aquí para no perder el contexto al retomar el proyecto.

### Resueltos (2026-08-22)

- ~~Credencial de Supabase hardcodeada en `alembic/env.py`~~ — corregido, ahora usa `DATABASE_URL` del entorno. **La contraseña real sigue expuesta en el historial de git hasta que se rote manualmente en el dashboard de Supabase** (acción pendiente del lado del usuario, no resoluble por código).
- ~~RLS deshabilitado en todas las tablas~~ — activado en las 11 tablas de `public`, sin políticas (ver sección de Auth arriba).
- ~~Token JWT persistido en `localStorage`/cookie no-httpOnly~~ — reemplazado por cookie httpOnly (ver Auth arriba); el frontend ya no toca el token.
- ~~Sin rate limiting en login~~ — agregado (`app/core/rate_limit.py`).
- **Pipeline de deploy roto ~1 año**: dos causas independientes, ambas confirmadas y corregidas el 2026-08-22 — (1) `alembic_version` en producción apuntaba a una revisión huérfana (`80ae2ec8da91`, de una reescritura de historial pasada) que no existe en `alembic/versions/`, haciendo fallar `alembic upgrade head` en cada `release_command`; se resolvió con `alembic stamp head --purge` (no toca datos) tras verificar que el esquema real ya coincidía con los modelos. (2) El secret `FLY_API_TOKEN` **nunca se había creado** en GitHub (repo sin secrets configurados). Con ambas corregidas, un push a `main` despliega solo — confirmado con una corrida verde de punta a punta.

### Pendientes

- **`liabilities-summary` / `net-worth-summary`** (`summary_extra.py`): el cálculo de "pagos realizados" filtra `Transaction.type == "payment"`, valor que **nunca se asigna** (el enum real es `income`/`expense`/`transfer`). El bug está enmascarado porque `debt.total_amount` ya se decrementa en vivo en `/debts/{id}/pay`, así que el resultado final coincide con lo esperado — pero el código es frágil y engañoso si se refactoriza sin saber esto.
- **`DebtTransactionType.charge_reversal`** referenciado en `transactions.py::reverse_transaction` no existe en el enum (`payment`/`interest_charge`/`extra_charge`); el `hasattr()` guard hace que las reversiones de compras de tarjeta se registren como `extra_charge` en vez de un tipo dedicado de reversión.
- **`POST /saving-accounts/{id}/withdraw`** etiqueta la transacción resultante con `source_type="account_deposit"` (debería ser algo como `account_withdraw`) — copy-paste artifact.
- **Inconsistencia de respuesta**: `deposit` devuelve `{"message", "nuevo_balance"}` mientras que `withdraw` devuelve el `SavingAccountRead` completo.
- **Borrado de transferencias**: `DELETE /transactions/{id}` revierte el balance solo de la fila borrada; si se borra una sola pata de una transferencia (en vez de ambas), la otra pata queda huérfana con su efecto de balance sin revertir.
- **Modelos sin uso**: `Account` e `Investment` no los referencia ningún endpoint — candidatos a eliminar si se confirma que no hay planes de retomarlos.
- **Reset de contraseña en memoria**: `RESET_TOKENS` en `auth_extra.py` es un dict de proceso — se pierde en cada reinicio/deploy y no escala a más de una instancia. El envío de email está comentado (`send_email`), así que el flujo de "olvidé mi contraseña" no envía correos reales hoy.
- **`/fx/rate`** no tiene dependencia de auth — es un endpoint público, y su cache de 12h es en memoria de proceso (no compartido entre instancias, se pierde al reiniciar).
- **Balance inicial sin ledger**: crear una cuenta con `balance` distinto de cero no genera ninguna fila en `Transaction` — el balance inicial no queda trazado como movimiento.
