# Modelo de datos

Todos los modelos están en `app/models/` (SQLModel). Los PKs de entidades orientadas al usuario final usan UUID (`user`, `account`, `investment`); el resto usa entero autoincremental.

## `User` (`app/models/user.py`)

| Campo | Tipo | Notas |
|---|---|---|
| `id` | UUID (PK) | `default_factory=uuid4` |
| `email` | str | único, indexado |
| `hashed_password` | str | bcrypt |
| `created_at` | datetime | default `utcnow` |
| `role` | str | default `"user"`; `"admin"` habilita endpoints de `subscriptions_admin.py` |
| `report_currency` | str (FK → `currency.code`) | default `"COP"` (desde 2026-08-30); moneda del patrimonio neto consolidado, ver `GET /summary-extra/net-worth-consolidated` en [API.md](API.md) |

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
| `source_type` | str? | `debt_payment`, `credit_card_purchase`, `credit_card_purchase_reversal`, `transfer`, `investment_yield`, `account_deposit`, o `None` para movimientos manuales |
| `transfer_group_id` | UUID? | indexado, une las dos patas de una transferencia |
| `reversal_note` | str? | máx. 500 caracteres |

Relaciones: `category`, `saving_account` (pata única de income/expense), `from_account`/`to_account` (patas de transferencia, cada una con `foreign_keys` explícito), `debt`.

## `Budget` (`app/models/budget.py`)

Meta de gasto mensual por categoría y moneda. Ver [API.md](API.md) para los endpoints (`app/api/budgets.py`).

| Campo | Tipo | Notas |
|---|---|---|
| `id` | int (PK) | |
| `user_id` | UUID (FK) | indexado |
| `category_id` | int (FK → `category.id`) | indexado |
| `currency` | str (FK → `currency.code`) | máx. 3 caracteres |
| `amount` | float | `0` significa "pausado desde este mes" |
| `effective_from` | date | indexado; siempre el día 1 de un mes |
| `created_at` | datetime | default `utcnow` |

`UniqueConstraint(user_id, category_id, currency, effective_from)`.

Diseño: cada fila es una **versión** del presupuesto vigente a partir de `effective_from`, no un valor mutable único — editar el mes en curso actualiza esa misma fila (mismo `effective_from`), pero no se puede reescribir un mes que ya pasó (`POST /budgets` rechaza `effective_from` anterior al mes actual). Pausar inserta/actualiza una fila con `amount=0` en el mes en curso en vez de borrar histórico. La misma categoría se trackea por separado en cada moneda (no se fusionan montos entre monedas). El gasto real (`GET /budgets`) reutiliza el mismo criterio de exclusión que `GET /summary`: no cuentan transferencias, rendimientos de inversión ni pagos de deuda, y se excluyen transacciones canceladas o reversadas.

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
| `category_id` | int (FK → `category.id`) | |
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

## `Subscription` (`app/models/subscription.py`)

| Campo | Tipo | Notas |
|---|---|---|
| `id` | int (PK) | |
| `user_id` | UUID (FK) | |
| `start_date` | datetime | |
| `end_date` | datetime | |
| `is_active` | bool | default `True` |
| `created_at` / `updated_at` | datetime | default `utcnow`; `updated_at` nunca se refresca realmente en `subscriptions_admin.py` |

## Enums (`app/models/enums.py`)

- `TransactionType`: `income`, `expense`, `transfer`

## Modelos sin uso (legacy)

- **`Account`** (`app/models/account.py`) — ningún endpoint de `app/api/*` lo referencia. Superado por `SavingAccount`. La tabla legacy `savingaccount` se elimina explícitamente vía `drop_savingaccount.py`.
- **`Investment`** (`app/models/investment.py`) — tampoco referenciado por ningún endpoint. Superado por `SavingAccount(type=investment)` + flujo de registro de rendimientos (`POST /transactions/register-yield/{account_id}`).

Ambos modelos podrían eliminarse del código si se confirma que no se necesitan; se mantienen documentados aquí para no perder el contexto de por qué existen.
