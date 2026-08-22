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

Relación `transactions: List[Transaction]` (vía `Transaction.debt_id`).

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
