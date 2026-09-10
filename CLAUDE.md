# Contexto para trabajar en este repo

API de **Balanced Cent**, app de finanzas personales en español. FastAPI + SQLModel + PostgreSQL, desplegada en Fly.io (`api.balancedcent.com`). El frontend es un repo hermano (`../frontend`, Next.js en Vercel).

**La documentación de referencia está en [`docs/`](docs) y se mantiene al día — leerla antes de asumir cómo funciona algo:**

| | |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Wiring, auth, deploy, tests, deuda técnica |
| [docs/DATA_MODEL.md](docs/DATA_MODEL.md) | Todas las tablas, sus relaciones y las invariantes que las sostienen |
| [docs/API.md](docs/API.md) | Referencia de endpoints |
| [docs/PLAN_CATEGORIAS_V2.md](docs/PLAN_CATEGORIAS_V2.md) | El modelo grupo/hoja: invariantes, migración y lo aprendido en cada fase |
| [docs/PENDIENTES.md](docs/PENDIENTES.md) | Lista viva de tareas — cubre **ambos** repos |

## Reglas duras

**Nunca borrar ni resetear datos de producción.** Siempre migrar en sitio. `reset_db.py` existe y es destructivo: no correrlo jamás contra producción.

**Las credenciales de producción viven en `.env`** (gitignoreado). No imprimir sus valores, no mandarlas a servicios ajenos, no commitearlas. `SECRET_KEY` firma los JWT y **debe** coincidir con `JWT_SECRET` del frontend — sobrescribirla con otra clave rompe el login entero.

**Las escrituras directas contra la base de producción requieren autorización explícita del usuario** en esa conversación.

**Cualquier respaldo de datos de otro usuario excluye** `hashed_password`, `refresh_token` y `password_reset_token`.

## Lo que hay que saber antes de tocar código

**Categorías: modelo grupo / hoja.** `parent_id IS NULL` es un **grupo** y **nunca recibe dinero**; `parent_id NOT NULL` es una **hoja** y es la única que lo recibe. Toda transacción, presupuesto, regla y recurrente apunta a una hoja. La regla vive en **un solo sitio**, `app/utils/category_rules.py::exigir_hoja`, y la llaman los cinco endpoints que asignan categoría — basta con que uno se olvide para que la invariante deje de valerse (ya pasó: `PATCH /transactions/{id}` se la saltó hasta la Fase 4). Para mostrar el nombre de una categoría usar `nombre_visible()`, nunca `category.name`: la hoja que crea el sistema se llama «General» y el usuario **nunca** debe verla.

**Drift de esquema entre local y producción.** Las 21 columnas de fecha de producción son `timestamp WITHOUT time zone`; `create_all` (local y tests) las produce *con* zona. Toda comparación contra un `datetime` aware tiene que pasar por `app/utils/datetime_helpers.as_utc()`: sin eso funciona en local y lanza **500 solo en producción**. Ya ocurrió dos veces. `conftest._igualar_fechas_a_produccion` hace que la suite vea esta clase de bug.

**Alembic para todo cambio de esquema.** `main.py` llama `create_all` al arrancar como red de seguridad, pero eso **solo crea tablas nuevas** — nunca aplica cambios de columnas o constraints. Las migraciones se escriben a mano, con un docstring que explica el porqué y no solo el qué, y llevan sus propias comprobaciones cuando mueven datos: en la Fase 0, un `assert` dentro de la migración atrapó que se estaban creando grupos vacíos, antes de escribir nada.

**«Sin clasificar» son dos estados**, no uno: `category_id IS NULL` (movimientos manuales viejos) y la hoja de sistema `uncategorized` (donde la importación de CSV deja lo que ninguna regla resuelve). Usar `es_sin_clasificar()` / `condicion_sin_clasificar()`, nunca comparar contra `None` a mano.

## Cómo se trabaja acá

- **Comentarios y mensajes de commit en español**, explicando el **porqué** y no el qué. Los mensajes de error de cara al usuario también, y deben decir qué hacer al respecto.
- **Tests contra Postgres real**, no SQLite (el proyecto usa tipos específicos de PG y ya hubo incidentes por diferencias entre entornos). `pytest`, 249 casos.
- **Cada defecto corregido se verifica por mutación**: revertir el arreglo a mano y confirmar que al menos un test falla. No es ceremonia — en la Fase 4 una mutación sobrevivió y reveló un test que probaba un caso que ya quedaba fuera por otro motivo.
- ⚠️ **No correr `pytest` con el servidor de desarrollo activo**: el mismo contenedor de Postgres (puerto 5433) sirve `finances_db` y `finances_test`, y produce errores intermitentes en archivos sin relación con lo que se está tocando.
- **Verificar en un navegador real, no solo con tests.** Varios de los bugs más visibles de este proyecto (una subcategoría que desaparecía al crearla, trece opciones llamadas «General» en una cuenta nueva, el footer a media página) son estructuralmente invisibles para jsdom.
- **CI bloquea el deploy**: push a `main` → job `test` → `flyctl deploy` → `alembic upgrade head` como `release_command`.
- `gh` **no está instalado**. La app de Fly se auto-detiene (`min_machines_running = 0`), así que `fly ssh` necesita un `curl` de despertador antes.
