# Modelo de datos

Todos los modelos están en `app/models/` (SQLModel). Los PKs de entidades orientadas al usuario final usan UUID (`user`, `account`, `investment`); el resto usa entero autoincremental.

> **Aviso sobre las columnas `datetime`.** En **producción** las 21 columnas de fecha son `timestamp WITHOUT time zone`; en local y en la suite, `create_all` las produce *con* zona. Por eso toda comparación contra un `datetime` aware debe pasar por `app/utils/datetime_helpers.as_utc()`: sin eso funciona en local y lanza `TypeError` → **500 solo en producción** (ya ocurrió dos veces). La suite replica el esquema de producción vía `conftest._igualar_fechas_a_produccion`. Detalle en [PENDIENTES.md](PENDIENTES.md).

## `User` (`app/models/user.py`)

| Campo | Tipo | Notas |
|---|---|---|
| `id` | UUID (PK) | `default_factory=uuid4` |
| `email` | str | único, indexado |
| `hashed_password` | str | bcrypt |
| `created_at` | datetime | default `utcnow` |
| `role` | str | default `"user"`; `"admin"` habilita endpoints de `subscriptions_admin.py` |
| `report_currency` | str (FK → `currency.code`) | default `"COP"` (desde 2026-08-30); moneda del patrimonio neto consolidado, ver `GET /summary-extra/net-worth-consolidated` en [API.md](API.md) |
| `last_login_at` | datetime \| None | desde 2026-09-01; se refresca en cada login. **`None` significa "nunca ha entrado"**, que es información útil y no un dato faltante: alimenta las métricas de la ficha de admin |

## `Currency` (`app/models/currency.py`, tabla `currency`)

Catálogo de monedas soportadas (desde 2026-08-22, migración `c4a2f9e6d1b3`). Reemplazó el enum fijo COP/USD/EUR — `saving_account.currency` y `debt.currency` son FKs a esta tabla, no un tipo cerrado.

| Campo | Tipo | Notas |
|---|---|---|
| `code` | str (PK) | ISO-4217, ej. `COP`, `USD`, `MXN` — máx. 3 caracteres |
| `name` | str | ej. "Peso colombiano" |
| `symbol` | str | ej. `$`, `€`, `¥` |
| `decimal_digits` | int | default `2`; `0` para monedas sin centavos (COP, JPY, CLP, KRW, VND, PYG en el seed) |

42 monedas sembradas en la migración. `GET /currencies` las expone; `app/utils/currency_helpers.py` tiene los helpers de validación (`validate_currency_code`) y de consulta (`get_user_currencies`).

## `SavingAccount` (`app/models/saving_account.py`, tabla `saving_account`)

La abstracción real de "cuenta" usada en toda la app.

| Campo | Tipo | Notas |
|---|---|---|
| `id` | int (PK) | |
| `user_id` | UUID (FK → `user.id`) | |
| `name` | str | único por usuario (validado en el endpoint, no en DB) |
| `type` | `SavingAccountType` enum | `cash` \| `bank` \| `investment` |
| `balance` | float | default `0.0` |
| `currency` | str (FK → `currency.code`) | default `"COP"` — cualquier código del catálogo (ver `Currency` abajo), no un enum fijo |
| `status` | `SavingAccountStatus` enum | `active` \| `closed`, default `active` |
| `closed_at` | datetime? | seteado al cerrar |

## `Category` (`app/models/category.py`)

| Campo | Tipo | Notas |
|---|---|---|
| `id` | int (PK) | |
| `name` | str | |
| `type` | `CategoryType` enum | `income` \| `expense` \| `both`, default `expense` |
| `user_id` | UUID (FK) | |
| `is_active` | bool | default `True` — soft-delete |
| `is_system` | bool | default `False`, indexado |
| `system_key` | str? | indexado, uno de `SystemCategoryKey` |

`UniqueConstraint(user_id, system_key)`. Relación `transactions: List[Transaction]`.

Categorías del sistema (creadas automáticamente al registrar un usuario, ver `app/utils/category_helpers.py::create_base_categories`):

| `system_key` | Nombre por defecto | Tipo |
|---|---|---|
| `interest_income` | Rendimientos | income |
| `fees` | Comisiones | expense |
| `transfer` | Transferencia | both |
| `debt_payment` | Pago de Deuda | expense |
| `uncategorized` | Sin categorizar | both |

(`opening_balance` y `adjustment` existen como valores del enum `SystemCategoryKey` pero no se usan actualmente.)

Desde 2026-09-04, dos columnas de presentación:

| Campo | Tipo | Notas |
|---|---|---|
| `color` | str? | **Clave de paleta** (`sky`, `emerald`…), nunca un hex: un hex fijo no puede verse bien en tema claro y oscuro a la vez. Validada contra `PALETTE` en `app/utils/default_categories.py`. Nula en todo lo anterior a esa fecha |
| `icon` | str? | Nombre de un icono de lucide (`Home`, `Car`…). El frontend lo resuelve en `lib/categoryIcon.tsx`, con `Tag` de reserva |
| `parent_id` | int? (FK → `category.id`) | Desde 2026-09-04. Nulo = **grupo** (primer nivel); no nulo = **hoja**. Exactamente dos niveles, validado en `api/categories.py` (no con una constraint: requeriría un trigger). Una hoja hereda el tipo de su grupo, y su nombre es único **por grupo**, no global |

### El modelo grupo / hoja (desde 2026-09-09)

**`parent_id IS NULL` es un grupo y NUNCA recibe dinero. `parent_id NOT NULL` es una hoja y es la única que lo recibe.** Toda `transaction`, `budget`, `category_rule` y `recurring_transaction` apunta siempre a una hoja.

El porqué, las alternativas descartadas y la migración están en **[PLAN_CATEGORIAS_V2.md](PLAN_CATEGORIAS_V2.md)**. En corto: el modelo anterior dejaba que un grupo recibiera movimientos *además* de sus hijas, y eso hacía que el total de un grupo no fuera la suma de sus hojas. Con importación bancaria y presupuestos robustos en el roadmap, esa ambigüedad se paga en cada reporte.

Las siete invariantes que sostienen el modelo (I1–I7) están enumeradas en el plan. Las tres que se validan en cada escritura:

| | Invariante | Dónde se hace cumplir |
|---|---|---|
| **I1** | Ninguna transacción apunta a un grupo | `app/utils/category_rules.py::exigir_hoja`, llamado desde `transactions.py` (crear **y** editar), `budgets.py`, `category_rules.py`, `recurring_transactions.py` |
| **I2** | Ningún presupuesto apunta a un grupo | misma función. Cierra por construcción el doble conteo que existía al presupuestar padre e hija a la vez |
| **I3** | Ningún grupo se queda sin hojas | `crear_hoja_por_defecto` al nacer un grupo; la migración `e4f5a6b7c8d9` lo comprueba con un `assert` que aborta |

**La hoja «General».** Un grupo recién creado nace con una hoja llamada `General` (`crear_hoja_por_defecto`), porque sin ella el grupo no podría recibir nada (I3). El usuario **nunca ve ese nombre**: `nombre_visible()` en el backend y `categoryDisplayName()` en el frontend colapsan un grupo de una sola hoja sintética en una única línea con el nombre del grupo. Quien creó «Mascotas» y nunca la desglosó ve «Mascotas», no «Mascotas › General».

> Solo se colapsa la hoja **sintética**. Si alguien crea «Transporte › Gasolina» y esa queda como única hoja, se muestra: colapsarla haría desaparecer lo que el usuario acaba de crear.

**El grupo `Sistema`.** Las categorías operativas (Transferencia, Sin categorizar, Comisiones, Pago de Deuda, Rendimientos) son hojas de un grupo oculto con `system_key='system_group'`. Existe para que la regla «solo las hojas reciben dinero» no necesite ninguna excepción: sin él, Transferencia sería un grupo de primer nivel y no podría recibir los movimientos que sí recibe. La interfaz nunca lo muestra, y `nombre_visible` no lo usa como prefijo («Sistema › Sin categorizar» no le dice nada a nadie).

> **Qué implica para los reportes.** `/summary` devuelve cada grupo con sus hojas anidadas, y **el total del grupo es exactamente la suma de sus hojas** — ya no hace falta una línea «sin desglosar». Un presupuesto solo puede ir sobre una hoja, así que tampoco puede contar los mismos pesos dos veces.

**«Sin clasificar» son DOS estados en la base y uno solo para el usuario** (detectado en la Fase 4):

- `transaction.category_id IS NULL` — movimientos manuales anteriores a que la categoría fuera obligatoria.
- `category_id` → la hoja de sistema `uncategorized` — donde la importación de CSV deja lo que ninguna regla resuelve.

La regla que los une vive en un solo sitio: `es_sin_clasificar()` / `condicion_sin_clasificar()` en `app/utils/category_rules.py`. Tratarlos por separado hacía que el desglose del Resumen pintara **dos filas llamadas «Sin categorizar»**, indistinguibles entre sí.

> Cuando `color` es nulo, el frontend **deriva el color de un hash estable del nombre** (`lib/categoryStyle.ts`). Eso corrige un defecto anterior: los gráficos asignaban color por POSICIÓN, así que una categoría cambiaba de color entre un mes y otro según su ranking de gasto. La solución por hash arregla también las categorías que ya existían, sin tocar una sola fila.

**Categorías sembradas.** Al registrarse se crean 13 categorías de la taxonomía sugerida (`app/utils/default_categories.py`, derivada de `docs/Categorias_Finanzas_Egresos_e_Ingresos.pdf`), cada una como un **grupo con su hoja `General`** dentro. **No son `is_system`**: el usuario puede renombrarlas, recolorearlas y desactivarlas. Las de sistema (Transferencia, Sin categorizar…) son operativas, viven en `category_helpers.py` y cuelgan del grupo `Sistema`. El catálogo completo son 25 grupos y 69 hojas, que se ofrecen bajo demanda en el selector de taxonomía — ninguna hoja se siembra: 94 casillas premarcadas serían el mismo muro que la jerarquía venía a evitar.


## `Debt` (`app/models/debt.py`)

| Campo | Tipo | Notas |
|---|---|---|
| `id` | int (PK) | |
| `user_id` | UUID (FK) | |
| `name` | str | |
| `total_amount` | float | **saldo pendiente actual**, se muta en el tiempo (no es el monto original inmutable) |
| `interest_rate` | float | solo informativo, no genera acumulación automática |
| `due_date` | date? | |
| `status` | `DebtStatus` enum | `active` \| `closed` |
| `currency` | str (FK → `currency.code`) | default `"COP"` |
| `kind` | `DebtKind` enum | `loan` \| `credit_card`, default `loan` |
| `credit_limit` | float? | desde 2026-08-30; solo con sentido en `kind=credit_card` |
| `statement_day` | int? | día del mes de corte, 1-28 (se evitan 29-31 por meses cortos) |
| `payment_due_days` | int? | días desde el corte hasta la fecha límite de pago |
| `minimum_payment_percent` | float? | % del saldo que el usuario indica que exige su banco; el cálculo resultante siempre se muestra como estimado, no hay fórmula universal por banco |

Relación `transactions: List[Transaction]` (vía `Transaction.debt_id`). El ciclo de facturación (`GET /debts/{id}/statement`, ver [API.md](API.md)) se calcula en vivo a partir de `DebtTransaction`, no hay tabla de estados de cuenta históricos.

## `DebtTransaction` (`app/models/debt_transaction.py`, tabla `debt_transaction`)

Subledger **separado** de `Transaction`, específico de deudas.

| Campo | Tipo | Notas |
|---|---|---|
| `id` | int (PK) | |
| `user_id` | UUID (FK) | |
| `debt_id` | int (FK → `debt.id`) | |
| `amount` | float | |
| `type` | `DebtTransactionType` enum | `payment` \| `interest_charge` \| `extra_charge` |
| `description` | str? | |
| `date` | datetime | default `utcnow` |

⚠️ El código de `transactions.py::reverse_transaction` intenta usar `DebtTransactionType.charge_reversal`, que **no existe** en el enum; el `hasattr()` guard hace que caiga silenciosamente a `extra_charge`. Ver [ARCHITECTURE.md](ARCHITECTURE.md).

## `Transaction` (`app/models/transaction.py`)

Ledger central de todos los movimientos.

| Campo | Tipo | Notas |
|---|---|---|
| `id` | int (PK) | |
| `user_id` | UUID (FK) | |
| `amount` | float | |
| `type` | `TransactionType` enum | `income` \| `expense` \| `transfer` — **`transfer` nunca se asigna en la práctica**; las transferencias se registran como un par expense+income con `source_type="transfer"` |
| `transaction_fee` | float | default `0.0` |
| `date` | datetime | default `utcnow` |
| `description` | str? | |
| `is_cancelled` | bool | default `False` |
| `reversed_transaction_id` | int? (self-FK) | en la fila de **reversión**, apunta a la original |
| `debt_id` | int? (FK → `debt.id`) | |
| `source_type` | str? | `debt_payment`, `credit_card_purchase`, `credit_card_purchase_reversal`, `transfer`, `investment_yield`, `account_deposit`, `account_withdraw` (desde 2026-09-02; antes los retiros se archivaban como `account_deposit`), o `None` para movimientos manuales. El frontend solo ramifica por `credit_card_purchase` y `transfer`; el resto se muestra como un ingreso o egreso normal |
| `transfer_group_id` | UUID? | indexado, une las dos patas de una transferencia |
| `reversal_note` | str? | máx. 500 caracteres |
| `category_id` | int? (FK → `category.id`) | **Siempre una hoja** (invariante I1) — `exigir_hoja` rechaza un grupo con 400 al crear **y** al editar. Nulo solo en datos anteriores a que fuera obligatoria y en `investment_yield`; ese nulo es una de las dos formas de «sin clasificar» (ver `Category` arriba) |

Relaciones: `category`, `saving_account` (pata única de income/expense), `from_account`/`to_account` (patas de transferencia, cada una con `foreign_keys` explícito), `debt`.

## `Budget` (`app/models/budget.py`)

Meta de gasto mensual por categoría y moneda. Ver [API.md](API.md) para los endpoints (`app/api/budgets.py`).

| Campo | Tipo | Notas |
|---|---|---|
| `id` | int (PK) | |
| `user_id` | UUID (FK) | indexado |
| `category_id` | int (FK → `category.id`) | indexado. **Siempre una hoja** (invariante I2) — `exigir_hoja` rechaza un grupo con 400 |
| `currency` | str (FK → `currency.code`) | máx. 3 caracteres |
| `amount` | float | `0` significa "pausado desde este mes" |
| `effective_from` | date | indexado; siempre el día 1 de un mes |
| `created_at` | datetime | default `utcnow` |

`UniqueConstraint(user_id, category_id, currency, effective_from)`.

Diseño: cada fila es una **versión** del presupuesto vigente a partir de `effective_from`, no un valor mutable único — editar el mes en curso actualiza esa misma fila (mismo `effective_from`), pero no se puede reescribir un mes que ya pasó (`POST /budgets` rechaza `effective_from` anterior al mes actual). Pausar inserta/actualiza una fila con `amount=0` en el mes en curso en vez de borrar histórico. La misma categoría se trackea por separado en cada moneda (no se fusionan montos entre monedas). El gasto real (`GET /budgets`) reutiliza el mismo criterio de exclusión que `GET /summary`: no cuentan transferencias, rendimientos de inversión ni pagos de deuda, y se excluyen transacciones canceladas o reversadas.

> Desde el modelo grupo/hoja (2026-09-09) un presupuesto solo puede ir sobre una **hoja**. Eso cierra **por construcción** el doble conteo que existía antes: presupuestar un grupo y una de sus hijas contaba los mismos pesos dos veces, porque el gasto del grupo incluía a las hijas y nada impedía presupuestar ambos.

## `ImportProfile` (`app/models/import_profile.py`)

Mapeo de columnas de CSV recordado por cuenta. Ver [API.md](API.md) para los endpoints (`app/api/csv_import.py`).

| Campo | Tipo | Notas |
|---|---|---|
| `id` | int (PK) | |
| `user_id` | UUID (FK) | indexado |
| `saving_account_id` | int (FK → `saving_account.id`) | indexado |
| `column_mapping` | JSON | `{date, description, amount}`, índices de columna 0-based |
| `date_format` | str | ej. `%d/%m/%Y`, formato `strptime` |
| `has_header` | bool | default `True` |
| `created_at` / `updated_at` | datetime | default `utcnow` |

`UniqueConstraint(user_id, saving_account_id)` — un perfil por cuenta; volver a guardar actualiza en vez de duplicar.

## `CategoryRule` (`app/models/category_rule.py`)

Regla de categorización automática. Ver [API.md](API.md) para los endpoints (`app/api/category_rules.py`).

| Campo | Tipo | Notas |
|---|---|---|
| `id` | int (PK) | |
| `user_id` | UUID (FK) | indexado |
| `category_id` | int (FK → `category.id`) | **Siempre una hoja** — `exigir_hoja` rechaza un grupo con 400 |
| `match_text` | str | se compara en minúsculas, "contiene", sin regex |
| `priority` | int | indexado; menor va primero, gana la primera que matchea |
| `is_active` | bool | default `True` |

Sin índice único: nada impide dos reglas con el mismo `match_text` (la de menor `priority` simplemente gana siempre).

## `SavingGoal` (`app/models/saving_goal.py`)

Meta de ahorro atada 1:1 a una cuenta. Ver [API.md](API.md) para los endpoints (`app/api/saving_goals.py`).

| Campo | Tipo | Notas |
|---|---|---|
| `id` | int (PK) | |
| `user_id` | UUID (FK) | indexado |
| `saving_account_id` | int (FK → `saving_account.id`) | indexado |
| `name` | str | |
| `target_amount` | float | |
| `target_date` | date? | opcional — una meta sin fecha ("fondo de emergencia") es igual de válida |
| `is_active` | bool | default `True` |
| `created_at` | datetime | default `utcnow` |

Índice único parcial `uq_saving_goal_active_account` en `(saving_account_id) WHERE is_active = true` — a lo sumo una meta activa por cuenta; metas inactivas viejas no cuentan para ese límite.

## `RefreshToken` (`app/models/refresh_token.py`)

Renovación de sesión. Ver `POST /auth/refresh` en [API.md](API.md).

| Campo | Tipo | Notas |
|---|---|---|
| `id` | int (PK) | |
| `user_id` | UUID (FK) | indexado |
| `token_hash` | str | **SHA-256 del token**, único e indexado; el valor crudo nunca se guarda |
| `expires_at` | datetime | 30 días por defecto (`REFRESH_TOKEN_EXPIRE_DAYS`) |
| `revoked_at` | datetime? | se llena al rotar, al cerrar sesión o al cambiar contraseña |
| `created_at` | datetime | default `utcnow` |

Se hashea con SHA-256 y no con bcrypt a propósito: el token es un valor aleatorio de alta entropía (`secrets.token_urlsafe(48)`), no una contraseña elegida por una persona — bcrypt solo aportaría lentitud. Las filas revocadas se conservan (no se borran) para que un intento de reuso se distinga de un token inexistente.

## `PasswordResetToken` (`app/models/password_reset_token.py`)

Restablecimiento de contraseña. Ver `POST /auth/forgot-password` en [API.md](API.md).

| Campo | Tipo | Notas |
|---|---|---|
| `id` | int (PK) | |
| `user_id` | UUID (FK) | indexado |
| `token_hash` | str | SHA-256 del token, único e indexado |
| `expires_at` | datetime | 60 min por defecto (`PASSWORD_RESET_EXPIRE_MINUTES`) |
| `used_at` | datetime? | se llena al usarlo, o al pedir un enlace nuevo (que invalida los anteriores) |
| `created_at` | datetime | default `utcnow` |

Reemplazó a `RESET_TOKENS`, un dict en memoria que se perdía en cada deploy y no habría funcionado con más de una instancia — el flujo "olvidé mi contraseña" estaba roto en la práctica.

## `Attachment` (`app/models/attachment.py`)

Comprobante adjunto a una transacción. Ver [API.md](API.md) (`app/api/attachments.py`).

| Campo | Tipo | Notas |
|---|---|---|
| `id` | int (PK) | |
| `user_id` | UUID (FK) | indexado |
| `transaction_id` | int (FK → `transaction.id`) | indexado |
| `storage_path` | str | ruta completa en el bucket, `{user_id}/{transaction_id}/{uuid}.{ext}` |
| `filename` | str | nombre original, solo para mostrar — **nunca** se usa para construir la ruta |
| `content_type` | str | JPG/PNG/WEBP/HEIC/PDF |
| `size_bytes` | int | máx. 5 MB |
| `created_at` | datetime | default `utcnow` |

El binario vive en Supabase Storage, en un bucket **privado**: los archivos se sirven con URL firmada de 1 hora, nunca por URL pública, porque un comprobante lleva montos y datos bancarios. Se adjunta a una `Transaction` y no a un grupo de transferencia: en una transferencia cuelga de la pata de salida, que es la fila que el usuario ve tras `mergeTransferPairs`.

## `Subscription` (`app/models/subscription.py`)

| Campo | Tipo | Notas |
|---|---|---|
| `id` | int (PK) | |
| `user_id` | UUID (FK) | |
| `start_date` | datetime | |
| `end_date` | datetime | |
| `is_active` | bool | default `True` |
| `created_at` / `updated_at` | datetime | default `utcnow`; desde 2026-09-01 `updated_at` **sí** se refresca en `activate`/`renew` |

> **Esta tabla guarda solo el estado ACTUAL y se sobrescribe.** `activate` reinicia `start_date` cada vez que reactiva una suscripción vencida, así que no sirve para responder "¿desde cuándo es cliente?". Para eso está `subscription_period`. Se mantiene deliberadamente como única fuente de verdad del **acceso** (`get_current_user_with_subscription_check` la lee): el historial vive aparte para que un fallo allí nunca pueda dejar a nadie sin entrar.

## Historial de suscripciones y paramétricas de administración (desde 2026-09-01)

Ninguna de estas tablas participa en la decisión de acceso. Migración `b1c2d3e4f5a6`.

### `SubscriptionPlan` (`app/models/subscription_plan.py`, tabla `subscription_plan`)

| Campo | Tipo | Notas |
|---|---|---|
| `id` | int (PK) | |
| `name` | str | indexado |
| `duration_months` | int | manda sobre el `months` de la URL cuando se envía `plan_id` |
| `price` / `currency` | float / str (FK → `currency.code`) | se **copian** al período al otorgarlo: cambiar el precio no reescribe lo ya cobrado |
| `is_active` | bool | baja lógica; nunca se borra físicamente porque períodos y pagos lo referencian |

### `SubscriptionPeriod` (`app/models/subscription_period.py`, tabla `subscription_period`)

Tramo de servicio efectivamente otorgado. El más antiguo responde "¿desde cuándo es cliente?".

| Campo | Tipo | Notas |
|---|---|---|
| `id` | int (PK) | |
| `user_id` | UUID (FK) | indexado |
| `plan_id` | int (FK) \| None | |
| `start_date` / `end_date` | datetime | al renovar una vigente, arranca donde terminaba la anterior (sin tramos solapados) |
| `price` / `currency` | float / str (FK) | copiados del plan |
| `origin` | str | `activate` \| `renew` \| **`backfill`** |
| `note` | str \| None | |
| `created_by` | UUID (FK) \| None | el admin que lo otorgó |

> `origin="backfill"` marca los períodos **reconstruidos** por la migración a partir de la suscripción vigente: son una deducción del estado actual, no historia registrada. La UI los rotula «reconstruido». Lo anterior al 2026-09-01 no existe en ninguna parte.

### `SubscriptionEvent` (`app/models/subscription_event.py`, tabla `subscription_event`)

Bitácora **inmutable**: nada la actualiza ni la borra, solo se inserta. Registra también acciones que no crean período (eliminar una suscripción, registrar o borrar un pago).

| Campo | Tipo | Notas |
|---|---|---|
| `id` | int (PK) | |
| `user_id` | UUID (FK) | indexado |
| `action` | str | `activate` \| `renew` \| `delete` \| `payment`; indexado |
| `end_date_before` / `end_date_after` | datetime \| None | permite reconstruir la línea de tiempo aunque no haya período |
| `months`, `plan_id`, `detail` | | |
| `performed_by` | UUID (FK) \| None | quién ejecutó la acción |
| `created_at` | datetime | indexado |

### `Payment` (`app/models/payment.py`, tabla `payment`)

Contabilidad **del negocio**, no de las finanzas del usuario: no aparece en Resumen ni toca ninguna cuenta ni saldo. Va en tabla propia para que nunca se mezcle con `Transaction`.

| Campo | Tipo | Notas |
|---|---|---|
| `id` | int (PK) | |
| `user_id` | UUID (FK) | indexado |
| `period_id` | int (FK) \| None | período que cubrió |
| `amount` / `currency` | float / str (FK) | ⚠️ `total_paid` en la ficha **suma sin convertir monedas** |
| `method` | str | `cash` \| `transfer` \| `card` \| `other`; texto libre a propósito |
| `reference`, `note` | str \| None | |
| `paid_at`, `created_by`, `created_at` | | |

### `UserAdminProfile`, `UserTag`, `UserTagLink` (`app/models/user_admin_profile.py`)

Datos que el **admin** lleva sobre una persona; el usuario no los ve ni los edita. En tabla aparte para no engordar `user`, que se lee en cada request autenticado.

| Tabla | Campos | Notas |
|---|---|---|
| `user_admin_profile` | `user_id` (PK/FK), `full_name`, `phone`, `notes`, `updated_by`, `updated_at` | notas privadas |
| `user_tag` | `id`, `name` (único), `color`, `created_at` | catálogo de etiquetas |
| `user_tag_link` | `user_id` + `tag_id` (PK compuesta) | N a N |

## Enums (`app/models/enums.py`)

- `TransactionType`: `income`, `expense`, `transfer`

## Modelos sin uso (legacy)

- **`Account`** (`app/models/account.py`) — ningún endpoint de `app/api/*` lo referencia. Superado por `SavingAccount`. La tabla legacy `savingaccount` se elimina explícitamente vía `drop_savingaccount.py`.
- **`Investment`** (`app/models/investment.py`) — tampoco referenciado por ningún endpoint. Superado por `SavingAccount(type=investment)` + flujo de registro de rendimientos (`POST /transactions/register-yield/{account_id}`).

Ambos modelos podrían eliminarse del código si se confirma que no se necesitan; se mantienen documentados aquí para no perder el contexto de por qué existen.
