# Referencia de la API

Base URL local: `http://localhost:8000`. Docs interactivas auto-generadas: `GET /docs`.

Niveles de auth usados en las tablas:
- **Pública** — sin token.
- **Auth** — requiere token válido (`get_current_user`), enviado como `Authorization: Bearer <token>` **o** como cookie httpOnly `access_token` (la que fija `/auth/login`) — lo que llegue primero.
- **Auth+Sub** — requiere token válido **y** suscripción activa y no vencida (`get_current_user_with_subscription_check`). Es el nivel usado por casi todos los endpoints de negocio.
- **Admin** — requiere token válido de un usuario con `role="admin"` (`get_current_admin_user`).

`GET /` — Pública. Health check, retorna `{"message": "Servidor de gastos personales"}`.

## Monedas — `app/api/currencies.py` (prefijo `/currencies`, Auth)

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/currencies` (`/`) | → `List[Currency]` (`code, name, symbol, decimal_digits`), las 42 monedas del catálogo, ordenadas por código. |

## Auth — `app/api/auth.py`, `app/api/auth_extra.py` (prefijo `/auth`)

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| POST | `/auth/register` | Pública | `{email, password}` → crea usuario, hashea password, siembra las 4 categorías del sistema. 400 si el email ya existe. |
| POST | `/auth/login` | Pública, con rate limit | `OAuth2PasswordRequestForm` (form-urlencoded `username`=email, `password`) → `{access_token, token_type}` **y** fija la cookie httpOnly `access_token` (`Set-Cookie`, `Secure`+`Domain` según `ENVIRONMENT`/`COOKIE_DOMAIN`). 401 si credenciales inválidas. 429 tras 5 intentos fallidos por correo o 20 por IP en 15 min. |
| POST | `/auth/logout` | Pública | Limpia la cookie `access_token` (`delete_cookie`). Sin body. |
| GET | `/auth/me` | Auth | → `{user_id, email, role}`. `role` (`user`\|`admin`) lo usa el frontend para decidir si muestra la sección de administración. |
| POST | `/auth/forgot-password` | Pública | `{email}` → genera token en memoria (dict `RESET_TOKENS`, **se pierde al reiniciar el proceso, no envía email real** — el `send_email` está comentado). Respuesta genérica para no filtrar existencia del email. |
| POST | `/auth/reset-password` | Pública | `{token, new_password}` → 400 si el token no existe/ya se usó. |
| POST | `/auth/change-password` | Auth | `{current_password, new_password}` → verifica password actual antes de cambiar. |
| GET | `/auth/subscription-status` | Auth | → `{state: "none"|"active"|"inactive"|"expired", end_date}` |

## Categorías — `app/api/categories.py` (prefijo `/categories`, todas Auth+Sub)

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/categories` (`/`) | `{name, type}` → crea categoría de usuario (`is_system=False`). 400 si ya existe una activa con ese nombre. |
| GET | `/categories` | Query `type` (`income`\|`expense`\|`both`), `status` (`active`\|`inactive`\|`all`, default `active`). |
| PUT | `/categories/{id}` | `{name, type}`. Sistema: solo renombrar (400 si cambia `type`). Usuario: bloquea cambio de `type` si ya tiene transacciones. |
| DELETE | `/categories/{id}` | Soft-delete (`is_active=False`). 400 si es de sistema o tiene transacciones asociadas. |
| PUT | `/categories/{id}/reactivate` | Reactiva (`is_active=True`). |

## Cuentas de ahorro — `app/api/saving_accounts.py` (prefijo `/saving-accounts`, todas Auth+Sub)

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/saving-accounts` (`/`) | `{name, type, balance, currency}` → 400 si nombre duplicado, 400 si `currency` no está en el catálogo (ver `/currencies`). El `balance` inicial **no genera transacción de apertura**. |
| GET | `/saving-accounts` (`/`) | Lista cuentas del usuario. |
| PUT | `/saving-accounts/{id}` | Renombrar libre; cambio de `type` bloqueado (400) si la cuenta ya tiene transacciones. |
| DELETE | `/saving-accounts/{id}` | Solo si tiene **cero** transacciones asociadas (independiente del balance). |
| POST | `/saving-accounts/{id}/withdraw` | `{amount>0}` → 400 si fondos insuficientes. Registra `expense` con `source_type="account_deposit"` (⚠️ nombre mal etiquetado, ver ARCHITECTURE.md). |
| POST | `/saving-accounts/{id}/deposit` | `{amount>0, description}` → `{"message", "nuevo_balance"}` (forma de respuesta distinta a withdraw). Registra `income` con `source_type="account_deposit"`. |
| POST | `/saving-accounts/{id}/close` | Requiere `balance == 0` (400 si no). |
| POST | `/saving-accounts/{id}/reopen` | Requiere estado `closed`. |
| GET | `/saving-accounts/{id}/transactions` | Movimientos donde la cuenta participa (directo, o como pata origen/destino de transferencia). |
| GET | `/saving-accounts/{id}/has-transactions` | → `{"hasTransactions": bool}` |

## Transacciones — `app/api/transactions.py` (prefijo `/transactions`, todas Auth+Sub)

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/transactions` (`/`) | `{amount, category_id, description, type, saving_account_id, transaction_fee, date}` → valida categoría/cuenta del usuario, cuenta activa. `income`: se acredita `amount - fee` (400 si negativo). `expense`: se debita `amount + fee` (400 si fondos insuficientes). Si `fee > 0`, crea una **segunda** fila de transacción solo para reflejar la comisión en reportes. |
| POST | `/transactions/transfer` | `{amount, description, from_account_id, to_account_id, transaction_fee, exchange_rate}` → cuentas distintas, ambas activas del usuario. Distinta moneda requiere `exchange_rate>0`; `converted_amount = amount * exchange_rate` (mismo si es misma moneda). Requiere `from.balance >= amount+fee`. Crea pata `expense` (from) + pata `income` (to), ambas con el mismo `transfer_group_id`, categoría de sistema "Transferencia". Si `fee>0`, crea una tercera fila de comisión. Retorna lista de las transacciones creadas. |
| POST | `/transactions/register-yield/{account_id}` | `{amount>0, description}` → solo cuentas `investment` activas. Acredita balance, `source_type="investment_yield"`, sin categoría. |
| GET | `/transactions/with-category` | Query `startDate`, `endDate`, `categoryId`, `type`, `source` (`account`→`debt_id IS NULL`, `credit_card`→`debt_id IS NOT NULL`), `page`, `page_size` (máx 100), `include_reversals` (default `False`). → `{items, total, page, page_size, totalPages}`. |
| PATCH | `/transactions/{id}` | `{description?, category_id?, date?}` (al menos uno). Solo permite editar transacciones manuales `income`/`expense`: bloqueado si está cancelada, si es ella misma una reversión, o si tiene `source_type` (cualquier transacción auto-generada es inmutable). |
| DELETE | `/transactions/{id}` | Hard delete. Revierte el efecto en balance antes de borrar. ⚠️ En transferencias opera por fila — borrar solo una pata deja la otra huérfana con su efecto de balance sin revertir. |
| POST | `/transactions/{id}/reverse` | `{note}` → no reversible si ya cancelada o si ya es una reversión; solo income/expense. Si pertenece a una transferencia (`transfer_group_id`), también revierte automáticamente la pata complementaria. Crea transacción inversa (`reversed_transaction_id` apuntando al original), ajusta balance (400 si dejaría la cuenta en negativo), marca original `is_cancelled=True` con `reversal_note`. Si la original era `credit_card_purchase`, también decrementa `debt.total_amount` y registra un `DebtTransaction`. |

## Deudas — `app/api/debts.py` (prefijo `/debts`, todas Auth+Sub)

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/debts` (`/`) | `{name, total_amount, interest_rate, due_date, currency, kind}` → 400 si `currency` no está en el catálogo. |
| GET | `/debts` (`/`) | Lista deudas del usuario, cada una con `transactions_count`. |
| PUT | `/debts/{id}` | Actualiza `name`/`interest_rate`/`due_date`/`currency`/`total_amount`. Cambiar `currency` o `total_amount` bloqueado (400) si ya tiene transacciones. |
| DELETE | `/debts/{id}` | Bloqueado (400) si tiene transacciones. |
| POST | `/debts/{id}/pay` | `{amount, saving_account_id, description, date}` → `TransactionRead`. Valida `amount>0`, no excede `total_amount` (tolerancia 0.01), cuenta del usuario, activa, **misma moneda que la deuda**, fondos suficientes. Crea `expense` (`source_type="debt_payment"`) + `DebtTransaction(type=payment)`, debita cuenta, decrementa `debt.total_amount`. Si el saldo resultante es ≤0.01: se pone en 0 y, **solo si `kind=loan`**, se autocierra la deuda (las tarjetas de crédito quedan activas en $0). |
| POST | `/debts/{id}/add-charge` | `{amount, description, date}` → `DebtRead`. Requiere deuda activa, `amount>0`. Incrementa `total_amount`, registra `DebtTransaction(type=interest_charge)`. |
| GET | `/debts/{id}/transactions` | → `List[DebtTransactionRead]` (subledger, no la tabla `transaction` principal), más reciente primero. |
| POST | `/debts/{id}/purchase` | `{amount, category_id, description, date, merchant, installments}` → `TransactionRead`. Requiere deuda activa y `kind=credit_card`. Categoría válida del usuario, activa, tipo `expense`/`both`. Incrementa `total_amount`, crea `expense` con `saving_account_id=None` (**no toca ninguna cuenta bancaria**), `source_type="credit_card_purchase"`, + `DebtTransaction(type=extra_charge)`. |
| POST | `/debts/{id}/close` | Requiere `total_amount == 0` y no cerrada. |
| POST | `/debts/{id}/reopen` | Requiere estado `closed`. |

## Resúmenes — `app/api/summary.py` (prefijo `/summary`, Auth+Sub)

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/summary` (`/`) | Query `start_date`, `end_date` (default mes-a-la-fecha local), `tz` (IANA, default UTC) → `Dict[str, SummaryResponse]`, una entrada por cada moneda que el usuario realmente tiene en cuentas/deudas (`get_user_currencies`), no una lista fija. Incluye transacciones de cuenta (excluyendo `transfer`/`investment_yield`/`debt_payment`) + compras de tarjeta de crédito (por moneda de la deuda). Retorna `total_income`, `total_expense`, `balance`, `expense_by_category`, `income_by_category` (con %), `daily_evolution`, `top_expense_category`, `top_income_category`, `top_expense_day`, `top_income_day`, `overspending_alert`. |

## Resúmenes extra — `app/api/summary_extra.py` (prefijo `/summary-extra`, Auth+Sub)

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/summary-extra/assets-summary` | Por cada moneda en uso del usuario (`get_user_currencies`, ya no una lista fija — ver nota de "resuelto" en ARCHITECTURE.md): `total_savings` (cash+bank activas), `total_investments`, `total_assets`. |
| GET | `/summary-extra/liabilities-summary` | Por cada moneda en uso: `pending = total_amount - pagos`. ⚠️ El filtro de "pagos" busca `Transaction.type == "payment"`, que nunca ocurre (bug enmascarado, ver ARCHITECTURE.md) — el resultado práctico coincide con `total_amount` porque este ya se decrementa en vivo en `/debts/{id}/pay`. |
| GET | `/summary-extra/net-worth-summary` | Por cada moneda en uso: `total_assets`, `total_liabilities`, `net_worth`, `debt_ratio`. |

## Flujo de caja — `app/api/cash_flow.py` (prefijo `/cash-flow`, Auth+Sub)

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/cash-flow` (`/`) | Query `start_date`/`end_date` (default mes-a-la-fecha). Por cada moneda en uso del usuario: `total_income`, `total_expense` (excluye pagos de deuda), `total_debt_payments` (separado), `net_cash_flow = income - expense - debt_payments`. |

## Suscripciones — `app/api/subscriptions.py` (prefijo `/subscriptions`)

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| GET | `/subscriptions/me` | Auth | → `SubscriptionStatusRead`. 404 si no tiene suscripción. `status` = `active`/`expired` según `end_date`. |

## Suscripciones — administración — `app/api/subscriptions_admin.py` (prefijo `/subscriptions/admin`, todas Admin salvo donde se indica)

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| POST | `/subscriptions/admin/activate` | Admin | Query `user_id`, `months` (default 1). Crea o resetea suscripción vencida. 400 si ya tiene una activa vigente. |
| POST | `/subscriptions/admin/renew` | Admin | Query `user_id`, `months`. Extiende `end_date` en `30*months` días, o reinicia desde ahora si ya venció. |
| GET | `/subscriptions/admin/{user_id}` | Admin | 404 si no existe. |
| DELETE | `/subscriptions/admin/{user_id}` | Admin | Elimina la fila de suscripción. |
| GET | `/subscriptions/admin` (`/`) | Admin | Lista todas las suscripciones. |
| ~~GET~~ | ~~`/subscriptions/admin/me`~~ | — | ⚠️ **Código muerto, inalcanzable**: la ruta `/{user_id}` de arriba se declara antes y captura `/me`, que además exige Admin y falla al parsear `"me"` como UUID. Usar `/subscriptions/me`. |

## Administración de usuarios — `app/api/admin_users.py` (prefijo `/admin/users`, todas Admin)

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/admin/users` (`/`) | Query `search` (coincidencia parcial de correo, case-insensitive), `page` (≥1), `page_size` (1-100, default 25) → `{items, total, page, page_size, total_pages}`. Cada item trae `id, email, role, created_at` + el estado de suscripción ya resuelto (`subscription_status`: `active`\|`expired`\|`inactive`\|`none`, más `subscription_start`/`subscription_end`), para no obligar al frontend a cruzar dos endpoints por fila. Ordenado por fecha de registro descendente. |
| PATCH | `/admin/users/{user_id}/role` | Body `{role: "user" \| "admin"}` → `AdminUserRead`. 404 si el usuario no existe; **400 si el cambio dejaría al sistema sin ningún administrador** (protección contra quedarse sin acceso al panel). Cambiar al mismo rol que ya tiene es un no-op idempotente. |

## Tipo de cambio — `app/routes/fx.py` (prefijo `/fx`)

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| GET | `/fx/rate?from=XXX&to=YYY` | **Pública** (sin dependencia de auth) | Async. Misma moneda → `rate=1.0`. Cache en memoria de 12h (se pierde al reiniciar). Intenta `exchangerate.host`, fallback a `open.er-api.com`. 502 si ambos fallan. → `{from, to, rate, source, as_of}`. |
