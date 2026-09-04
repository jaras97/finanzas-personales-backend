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
| POST | `/auth/logout` | Pública | Limpia ambas cookies (`access_token` y `refresh_token`) y **revoca** los refresh tokens del usuario — sin eso, cerrar sesión dejaría la sesión aún renovable con la cookie que quedó en el navegador. Sin body. |
| POST | `/auth/forgot-password` | Pública | `{email}` → envía por correo (Resend) un enlace a `FRONTEND_URL/auth/reset-password?token=...`, válido 60 min (`PASSWORD_RESET_EXPIRE_MINUTES`) y de un solo uso. Pedir uno nuevo **invalida el anterior**. La respuesta es idéntica exista o no la cuenta, y un fallo de envío tampoco la cambia — si variara, el endpoint sería un detector de correos registrados. |
| POST | `/auth/reset-password` | Pública (token) | `{token, new_password}` → 400 si el token no existe, ya se usó o venció. Revoca todas las sesiones renovables del usuario: quien recupera su contraseña suele hacerlo porque perdió el control de la cuenta. |
| POST | `/auth/refresh` | Cookie `refresh_token` | Renueva el access token sin pedir credenciales. **Rota** el refresh token en cada uso (el anterior queda revocado, así un token robado y usado delata el robo al expulsar al legítimo). 401 si falta, no existe, ya se usó o expiró — y en ese caso limpia ambas cookies. El refresh token **nunca** viaja en el body, solo como cookie httpOnly. |
| GET | `/auth/me` | Auth | → `{user_id, email, role, report_currency}`. `role` (`user`\|`admin`) lo usa el frontend para decidir si muestra la sección de administración. `report_currency` (desde 2026-08-30, default `COP`) es la moneda del patrimonio neto consolidado, ver `/summary-extra/net-worth-consolidated`. |
| POST | `/auth/change-password` | Auth | `{current_password, new_password}` → verifica password actual antes de cambiar. Revoca las sesiones renovables: si alguien más tenía acceso, este es el momento en que lo pierde. |
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
| POST | `/saving-accounts/{id}/withdraw` | `{amount>0}` → 400 si fondos insuficientes. Registra `expense` con `source_type="account_withdraw"` (era `account_deposit`, copiado del endpoint de depósito; corregido el 2026-09-02 — no hubo que arreglar datos históricos porque ningún retiro llegó a archivarse). |
| POST | `/saving-accounts/{id}/deposit` | `{amount>0, description}` → `{"message", "nuevo_balance"}` (forma de respuesta distinta a withdraw). Registra `income` con `source_type="account_deposit"`. |
| POST | `/saving-accounts/{id}/close` | Requiere `balance == 0` (400 si no). |
| POST | `/saving-accounts/{id}/reopen` | Requiere estado `closed`. |
| GET | `/saving-accounts/{id}/transactions` | Movimientos donde `saving_account_id == id` — para una transferencia, cada cuenta ve únicamente su propia pata (egreso en origen, ingreso en destino), no ambas; `from_account`/`to_account` vienen resueltos en cada fila para mostrar la contraparte. |
| GET | `/saving-accounts/{id}/has-transactions` | → `{"hasTransactions": bool}` |

## Comprobantes — `app/api/attachments.py` (Auth+Sub)

Adjuntos de una transacción (foto de recibo, PDF del banco). El binario vive en **Supabase Storage** (bucket privado); en Postgres solo queda la ruta y los metadatos. En una transferencia se adjunta a la **pata de salida**, que es la fila que el usuario ve tras la fusión de pares.

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/transactions/{id}/attachments` | Multipart `file`. Solo JPG/PNG/WEBP/HEIC/PDF (400 en otro caso), máx. 5 MB (`MAX_ATTACHMENT_BYTES`) y 5 comprobantes por movimiento. 404 si la transacción no es del usuario. La ruta en el bucket se construye **en el servidor** (`{user_id}/{transaction_id}/{uuid}.{ext}`), nunca con el `filename` del cliente — un nombre como `../../otro-usuario/x.jpg` no puede escapar de su carpeta; el nombre original solo se guarda para mostrarlo. |
| GET | `/transactions/{id}/attachments` | Lista los comprobantes con una **URL firmada de 1 hora** cada uno. Si el almacenamiento no responde, `url` viene en `null` y el resto del listado igual se devuelve. |
| DELETE | `/attachments/{id}` | Borra el binario del bucket y la fila. Si el archivo ya no estaba en el bucket, igual borra la fila — si no, una inconsistencia dejaría adjuntos imposibles de quitar. |

`GET /transactions/with-category` incluye `attachments_count` por fila (una sola consulta agrupada por página, no N+1) para que la lista marque qué movimientos tienen comprobante sin pedirlos uno por uno.

## Metas de ahorro — `app/api/saving_goals.py` (prefijo `/saving-goals`, todas Auth+Sub)

Atada 1:1 a una `SavingAccount` completa — "esta cuenta ES mi fondo para el viaje", nada de varias metas compartiendo el saldo de una sola cuenta. El progreso es simplemente `saldo_actual / target_amount` en el momento de consultar, sin trackear aportes/retiros por separado. La moneda de la meta es la de la cuenta, siempre.

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/saving-goals` (`/`) | `{saving_account_id, name, target_amount>0, target_date?}` → 400 si la cuenta no es del usuario o no está activa, 400 si **ya existe una meta activa** para esa cuenta (índice único parcial en DB, `WHERE is_active=true`, más el chequeo aplicación). |
| GET | `/saving-goals` (`/`) | Lista solo las metas **activas** del usuario, cada una con `current_balance`, `progress_percent` y, si tiene `target_date`, `monthly_savings_needed` ya calculados. |
| PUT | `/saving-goals/{id}` | Actualiza cualquier subconjunto de `{name, target_amount, target_date, is_active}`. Poner `is_active=false` "libera" la cuenta para una meta nueva sin borrar el histórico. |
| DELETE | `/saving-goals/{id}` | Borrado real (a diferencia de pausar con `is_active=false`). |

**`monthly_savings_needed`**: `(target_amount − saldo_actual) / meses_restantes` hasta `target_date`. Si el saldo ya alcanzó o superó la meta, es `0`. Si `target_date` cae en el mes en curso (o ya pasó), es todo lo que falta de una vez — ya no hay margen para repartirlo entre meses.

### Categorías sugeridas

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/categories/suggested` | Añade las categorías de la taxonomía que al usuario le **falten** → `{created: [...], skipped_existing: n}`. Solo aditivo: nunca renombra, fusiona ni desactiva nada. Compara ignorando tildes y mayúsculas (en producción conviven «Alimentacion» y «Alimentación»). Ofrece las 25 completas, no solo el núcleo: quien lo pulsa pide el catálogo. |

`POST`/`PUT /categories` aceptan además `color` (clave de paleta, 422 si no está en la lista) e `icon`. El color se puede cambiar incluso en categorías de sistema: es presentación, no comportamiento.

## Transacciones — `app/api/transactions.py` (prefijo `/transactions`, todas Auth+Sub)

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/transactions` (`/`) | `{amount, category_id, description, type, saving_account_id, transaction_fee, date}` → valida categoría/cuenta del usuario, cuenta activa. `income`: se acredita `amount - fee` (400 si negativo). `expense`: se debita `amount + fee` (400 si fondos insuficientes). Si `fee > 0`, crea una **segunda** fila de transacción solo para reflejar la comisión en reportes. |
| POST | `/transactions/transfer` | `{amount, description, from_account_id, to_account_id, transaction_fee, exchange_rate, date}` → cuentas distintas, ambas activas del usuario. Distinta moneda requiere `exchange_rate>0`; `converted_amount = amount * exchange_rate` (mismo si es misma moneda). Requiere `from.balance >= amount+fee`. Crea pata `expense` (from) + pata `income` (to), ambas con el mismo `transfer_group_id`, categoría de sistema "Transferencia". `date` es opcional (default `now`), igual que en `POST /transactions`. Si `fee>0`, crea una tercera fila de comisión. Retorna lista de las transacciones creadas. |
| POST | `/transactions/register-yield/{account_id}` | `{amount>0, description}` → solo cuentas `investment` activas. Acredita balance, `source_type="investment_yield"`, sin categoría. |
| GET | `/transactions/with-category` | Query `startDate`, `endDate`, `categoryId`, `type`, `source` (`account`→`debt_id IS NULL`, `credit_card`→`debt_id IS NOT NULL`), `page`, `page_size` (máx 100), `include_reversals` (default `False`). → `{items, total, page, page_size, totalPages}`. |
| PATCH | `/transactions/{id}` | `{description?, category_id?, date?}` (al menos uno). Solo permite editar transacciones manuales `income`/`expense`: bloqueado si está cancelada, si es ella misma una reversión, o si tiene `source_type` (cualquier transacción auto-generada es inmutable). |
| DELETE | `/transactions/{id}` | Hard delete. Revierte el efecto en balance antes de borrar. ⚠️ En transferencias opera por fila — borrar solo una pata deja la otra huérfana con su efecto de balance sin revertir. |
| POST | `/transactions/{id}/reverse` | `{note}` → no reversible si ya cancelada o si ya es una reversión; solo income/expense. Si pertenece a una transferencia (`transfer_group_id`), también revierte automáticamente la pata complementaria. Crea transacción inversa (`reversed_transaction_id` apuntando al original), ajusta balance (400 si dejaría la cuenta en negativo), marca original `is_cancelled=True` con `reversal_note`. Si la original era `credit_card_purchase`, también decrementa `debt.total_amount` y registra un `DebtTransaction`. |

## Deudas — `app/api/debts.py` (prefijo `/debts`, todas Auth+Sub)

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/debts` (`/`) | `{name, total_amount, interest_rate, due_date, currency, kind, credit_limit?, statement_day?, payment_due_days?, minimum_payment_percent?}` → 400 si `currency` no está en el catálogo. Los 4 campos de ciclo (desde 2026-08-30) solo tienen efecto real si `kind=credit_card`; `statement_day` 1-28 (422 fuera de rango — se evita 29-31 a propósito, meses cortos). |
| GET | `/debts` (`/`) | Lista deudas del usuario, cada una con `transactions_count`. |
| PUT | `/debts/{id}` | Actualiza `name`/`interest_rate`/`due_date`/`currency`/`total_amount`, y los 4 campos de ciclo **solo si `debt.kind == credit_card`** (se ignoran en préstamos, incluso si vienen en el body). Cambiar `currency` o `total_amount` bloqueado (400) si ya tiene transacciones. |
| DELETE | `/debts/{id}` | Bloqueado (400) si tiene transacciones. |
| POST | `/debts/{id}/pay` | `{amount, saving_account_id, description, date}` → `TransactionRead`. Valida `amount>0`, no excede `total_amount` (tolerancia 0.01), cuenta del usuario, activa, **misma moneda que la deuda**, fondos suficientes. Crea `expense` (`source_type="debt_payment"`) + `DebtTransaction(type=payment)`, debita cuenta, decrementa `debt.total_amount`. Si el saldo resultante es ≤0.01: se pone en 0 y, **solo si `kind=loan`**, se autocierra la deuda (las tarjetas de crédito quedan activas en $0). |
| POST | `/debts/{id}/add-charge` | `{amount, description, date}` → `DebtRead`. Requiere deuda activa, `amount>0`. Incrementa `total_amount`, registra `DebtTransaction(type=interest_charge)`. |
| GET | `/debts/{id}/transactions` | → `List[DebtTransactionRead]` (subledger, no la tabla `transaction` principal), más reciente primero. |
| POST | `/debts/{id}/purchase` | `{amount, category_id, description, date, merchant, installments}` → `TransactionRead`. Requiere deuda activa y `kind=credit_card`. Categoría válida del usuario, activa, tipo `expense`/`both`. Incrementa `total_amount`, crea `expense` con `saving_account_id=None` (**no toca ninguna cuenta bancaria**), `source_type="credit_card_purchase"`, + `DebtTransaction(type=extra_charge)`. |
| POST | `/debts/{id}/close` | Requiere `total_amount == 0` y no cerrada. |
| POST | `/debts/{id}/reopen` | Requiere estado `closed`. |
| GET | `/debts/{id}/statement` | Ciclo de facturación (desde 2026-08-30), calculado **en vivo** a partir de `DebtTransaction` — no hay tabla de estados de cuenta históricos. 400 si `kind != credit_card` o si `statement_day`/`payment_due_days` no están configurados. → `{next_statement_date, payment_due_date, current_period_charges, minimum_payment_estimate, available_credit}`. `current_period_charges` suma `extra_charge`+`interest_charge` (no `payment`) entre el corte anterior y el próximo. `minimum_payment_estimate` y `available_credit` vienen `null` si esos campos no están configurados en la deuda. **El pago mínimo es siempre una estimación** (`total_amount × minimum_payment_percent`) — no hay fórmula universal de bancos, se muestra tal cual, nunca como el valor exacto que cobrará el banco. |

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
| GET | `/summary-extra/net-worth-consolidated` | Convierte el resultado de `net-worth-summary` a una sola moneda (`User.report_currency`, ver `PATCH /account/preferences` abajo) usando la tasa de **hoy** de `/fx/rate` — no es una reconstrucción histórica. `{report_currency, total_assets, total_liabilities, net_worth, degraded, breakdown: [{currency, original_assets, original_liabilities, converted_assets, converted_liabilities, rate_used}]}`. Si `/fx/rate` falla para alguna moneda (sus dos proveedores externos caídos), esa fila del `breakdown` queda con los `converted_*`/`rate_used` en `null` y **no** entra en la suma — `degraded=true` avisa que el total es parcial, en vez de que todo el endpoint falle con 502. |

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
| POST | `/subscriptions/admin/activate` | Admin | Query `user_id`, `months` (default 1), `plan_id` (opcional: si se envía, **su duración manda sobre `months`**), `note` (opcional, queda en el historial). Crea la suscripción, o reactiva una vencida **o marcada inactiva**. Pone `is_active=True`. 400 solo si ya está vigente **y** activa. Deja período + evento en el historial. |
| POST | `/subscriptions/admin/renew` | Admin | Query `user_id`, `months`, `plan_id`, `note` (igual que activate). Vigente → suma `30*months` días al vencimiento actual; vencida → reinicia desde ahora. Pone `is_active=True`. El período nuevo arranca donde terminaba el anterior, para que el historial no muestre tramos solapados. |
| GET | `/subscriptions/admin/{user_id}` | Admin | 404 si no existe. |
| DELETE | `/subscriptions/admin/{user_id}` | Admin | Elimina la fila de suscripción. **No borra períodos ni pagos** (la persona sí estuvo cubierta y sí pagó); deja un evento `delete` en la bitácora. |
| GET | `/subscriptions/admin` (`/`) | Admin | Lista todas las suscripciones. |

> **Nota sobre fechas (2026-09-01).** `activate` y `renew` comparaban `end_date` contra un `datetime` aware. En producción esas columnas son `timestamp WITHOUT time zone`, así que la comparación lanzaba `TypeError` → **500**, y renovar una suscripción vencida era imposible. Todas las comparaciones de fecha pasan ahora por `app/utils/datetime_helpers.as_utc()`. Ver `docs/PENDIENTES.md` para el drift de esquema completo.
>
> La ruta `GET /subscriptions/admin/me` fue **eliminada** (2026-09-02): era inalcanzable porque `/{user_id}` se declara antes y la captura. El equivalente vivo es `GET /subscriptions/me`.

## Movimientos recurrentes — `app/api/recurring_transactions.py` (prefijo `/recurring-transactions`, todas Auth+Sub)

Plantillas de movimientos que se repiten (nómina, arriendo, suscripciones). No son movimientos: al vencer generan filas reales en `transaction`.

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/recurring-transactions` (`/`) | `{description, amount>0, type (income\|expense), category_id, saving_account_id, frequency (weekly\|biweekly\|monthly\|yearly), next_run (YYYY-MM-DD), end_date?}`. Valida que categoría y cuenta sean del usuario, estén activas y que la categoría corresponda al tipo. `next_run` puede ser pasada: las ocurrencias vencidas se generan en la siguiente corrida. |
| GET | `/recurring-transactions` (`/`) | Lista las del usuario ordenadas por `next_run`, con `category_name`/`account_name`/`account_currency` resueltos. |
| PUT | `/recurring-transactions/{id}` | Actualización parcial (incluye `is_active` para pausar/reactivar). |
| DELETE | `/recurring-transactions/{id}` | Borra solo la plantilla; **los movimientos ya generados se conservan** (son hechos contables). |
| POST | `/recurring-transactions/run` | Materializa todas las ocurrencias vencidas hasta hoy → `{generated[], skipped[], total_created}`. **Idempotente**: `next_run` solo avanza cuando su movimiento ya se creó, ambos confirmados juntos. Un gasto sin saldo suficiente **no sobregira**: se omite con motivo explícito y su `next_run` queda intacto para reintentar. Tope de 60 ocurrencias por regla por corrida. Los meses se suman recortando al último día válido (una regla del 31 cae en el 28/29 de febrero, no se pasa a marzo). |

## Presupuestos — `app/api/budgets.py` (prefijo `/budgets`, todas Auth+Sub)

Meta de gasto mensual por categoría **y moneda** (una categoría con gastos en COP y USD tiene dos presupuestos independientes, nunca uno fusionado). El monto está versionado por `effective_from`: editar el presupuesto hoy no reescribe cómo le fue al usuario en un mes ya pasado — cada fila es la meta vigente desde ese mes en adelante, hasta que otra fila más reciente la reemplace. `amount=0` significa "pausado desde este mes", no una meta de cero.

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/budgets` (`/`) | `{category_id, currency, amount>=0, effective_from?}` → crea o **actualiza** (si ya existe una fila para esa categoría+moneda+mes, la sobreescribe en vez de duplicar). 400 si la categoría no es del usuario/está inactiva, es de sistema, o es de tipo `income`. `effective_from` por defecto es el mes en curso; 400 si se intenta fijar en un mes que ya pasó. Devuelve el progreso ya calculado (ver GET). |
| GET | `/budgets` (`/`) | Query `month` (`YYYY-MM`, default mes en curso) → lista de presupuestos vigentes ese mes, cada uno con `spent` (gasto real acumulado) y `percentage` ya calculados. Resuelve "vigente" como la fila con `effective_from` más reciente que sea `<= month` por cada par (categoría, moneda); las pausadas (`amount=0`) no aparecen. |
| POST | `/budgets/{id}/pause` | Inserta (o actualiza) una fila con `amount=0` para el mes en curso, usando la categoría/moneda del presupuesto `{id}` como referencia — no borra el histórico. |

**Cálculo de `spent`**: mismo criterio de exclusión que `GET /summary` (transferencias, rendimientos de inversión y pagos de deuda no cuentan como gasto real; tampoco transacciones canceladas/reversadas), sumando tanto gastos de cuenta como compras con tarjeta de crédito en esa categoría y moneda, dentro del mes correspondiente.

## Importación de CSV — `app/api/csv_import.py` (prefijos `/transactions/import` y `/import-profiles`, todas Auth+Sub)

Sube un extracto bancario en CSV y crea las transacciones tras revisión manual — nunca crea nada directo del archivo. El mapeo de columnas es por **índice** (0-based), no por nombre de encabezado (el CSV puede no tener encabezado). Cada fila se categoriza con la primera regla activa de `/category-rules` que matchee la descripción; si ninguna matchea, cae en "Sin categorizar" (categoría de sistema, se autocrea la primera vez que se usa) — el usuario reasigna categoría por fila en la revisión antes de confirmar.

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/transactions/import/preview` | Multipart: `file`, `saving_account_id`, `column_mapping?` (JSON string `{date,description,amount}` con índices de columna), `date_format?` (ej. `%d/%m/%Y`), `has_header` (default `true`). **Sin `column_mapping`**: modo `inspect` — devuelve `sample_rows` (primeras 6 filas crudas) + `column_count` + el `import_profile` guardado para esa cuenta si existe, para que el frontend arme el paso de mapeo. **Con `column_mapping`**: modo `review` — parsea todas las filas (máx. 1.000, 400 si se excede), devuelve cada una con fecha/monto parseados, `type` derivado del signo del monto (no hay columna de tipo separada), `is_duplicate` (mismo monto ±3 días y descripción similar — `difflib.SequenceMatcher` ≥ 0.6 — contra transacciones ya existentes de esa cuenta) y `error` si la fila no pudo parsearse. `include` sugerido es `false` para filas con error o duplicado, `true` en el resto — el usuario ajusta antes de confirmar. |
| POST | `/transactions/import/confirm` | `{saving_account_id, rows: [{date, description, amount, type, category_id}]}` (ya filtradas/editadas por el usuario) → crea las transacciones reales en lote. Filas con categoría inválida o fecha inválida se cuentan en `skipped`, no abortan el resto. **No bloquea por fondos insuficientes** (a diferencia de `POST /transactions`): son movimientos históricos que ya ocurrieron en el banco, no una decisión de gasto nueva — el saldo de la cuenta se ajusta por el neto sin más. Devuelve `{created, skipped}`. |
| POST | `/import-profiles` (`/`) | `{saving_account_id, column_mapping, date_format, has_header}` → crea o actualiza (upsert por `user_id`+`saving_account_id`, un perfil por cuenta) el mapeo recordado para no volver a pedirlo en la próxima importación de esa misma cuenta. |
| GET | `/import-profiles` (`/`) | Lista los perfiles guardados del usuario. |

**Parseo de montos**: soporta formato con miles+decimales en cualquier orden (`1.234,56` o `1,234.56`), signo negativo o entre paréntesis `(150.000)`. El separador que aparece de último en el string se asume decimal.

## Reglas de categorización — `app/api/category_rules.py` (prefijo `/category-rules`, todas Auth+Sub)

Si la descripción de una transacción **contiene** `match_text` (comparación en minúsculas, sin regex — v1 deliberadamente simple), se sugiere `category_id`. Se evalúan en orden de `priority` ascendente y gana la **primera** que matchea (orden manual explícito, no "la más específica gana"). `suggest_category()` (`app/utils/category_rule_helpers.py`) es la función pura reutilizada tanto acá como en el preview de `/transactions/import/preview`.

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/category-rules` (`/`) | `{category_id, match_text}` → crea con `priority` = la más alta existente del usuario + 1 (queda al final de la cola de evaluación). 400 si `match_text` está vacío o la categoría no es del usuario/está inactiva. |
| GET | `/category-rules` (`/`) | Lista ordenada por `priority` ascendente. |
| PUT | `/category-rules/{id}` | Actualiza cualquier subconjunto de `{category_id, match_text, priority, is_active}` — reordenar es simplemente mandar un `priority` nuevo. |
| DELETE | `/category-rules/{id}` | Elimina la regla. |
| POST | `/category-rules/apply` | Aplica las reglas activas del usuario contra sus transacciones que **todavía** están en "Sin categorizar" (no toca las que ya tienen otra categoría). Devuelve `{updated}`. Pensado para correr después de crear una regla nueva, o después de una importación que dejó filas sin categorizar. |

**Alcance de v1** (ver artifact de diseño): sin autosugerencia mientras se escribe la descripción en el formulario manual de transacción — eso quedó fuera de esta fase, solo se conectó a CSV y a `apply`.

## Administración de usuarios — `app/api/admin_users.py` (prefijo `/admin/users`, todas Admin)

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/admin/users` (`/`) | Query `search` (coincidencia parcial de correo, case-insensitive), `page` (≥1), `page_size` (1-100, default 25) → `{items, total, page, page_size, total_pages}`. Cada item trae `id, email, role, created_at` + el estado de suscripción ya resuelto (`subscription_status`: `active`\|`expired`\|`inactive`\|`none`, más `subscription_start`/`subscription_end`), para no obligar al frontend a cruzar dos endpoints por fila. Ordenado por fecha de registro descendente. |
| PATCH | `/admin/users/{user_id}/role` | Body `{role: "user" \| "admin"}` → `AdminUserRead`. 404 si el usuario no existe; **400 si el cambio dejaría al sistema sin ningún administrador** (protección contra quedarse sin acceso al panel). Cambiar al mismo rol que ya tiene es un no-op idempotente. |

## Historial y paramétricas de administración — `app/api/admin_records.py` (prefijo `/admin`, todas Admin)

Registro de clientes: quién es cliente desde cuándo, qué se le cobró, quién le renovó y si de verdad usa la app. Añadido el 2026-09-01.

**Planes** (paramétrica). El precio se **copia** al período en el momento de otorgarlo, así que cambiar el precio de un plan no reescribe lo ya cobrado.

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/admin/subscription-plans` | Query `include_inactive` (default `false`) → `List[PlanRead]`, ordenados por duración. |
| POST | `/admin/subscription-plans` | Body `{name, duration_months (1-60), price, currency, is_active}` → 201. |
| PUT | `/admin/subscription-plans/{plan_id}` | Campos parciales. 404 si no existe. |
| DELETE | `/admin/subscription-plans/{plan_id}` | **Baja lógica** (`is_active=False`), nunca física: los períodos y pagos históricos lo referencian y borrarlo dejaría el historial sin poder explicar qué se cobró. |

**Etiquetas** (paramétrica) para clasificar personas: prueba, cortesía, moroso…

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/admin/tags` | → `List[TagRead]` ordenadas por nombre. |
| POST | `/admin/tags` | Body `{name, color}` → 201. 400 si el nombre ya existe (comparación case-insensitive). |
| DELETE | `/admin/tags/{tag_id}` | Quita primero las asignaciones y luego la etiqueta (si no, la FK lo impide). |

**Ficha de una persona.** Todos los endpoints que la modifican devuelven la ficha completa ya actualizada, para que el frontend no tenga que volver a pedirla.

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/admin/users/{user_id}/detail` | → `AdminUserDetail`: suscripción vigente, `periods`, `events`, `payments`, `total_paid`, `first_subscribed_at`, `metrics` (`last_login_at`, `has_ever_logged_in`, `days_since_last_login`, conteo de transacciones/cuentas/deudas), `tags` y los campos de ficha. Los correos de quien actuó se resuelven en **una** consulta, no por fila. |
| PUT | `/admin/users/{user_id}/profile` | Body `{full_name, phone, notes}` (parcial). Datos privados del admin: el usuario no los ve ni los edita. |
| PUT | `/admin/users/{user_id}/tags` | Body `{tag_ids: [...]}`. **Reemplaza el conjunto completo.** 404 si alguna etiqueta no existe. |
| POST | `/admin/users/{user_id}/payments` | Body `{amount (>0), currency, method (`cash`\|`transfer`\|`card`\|`other`), reference, note, paid_at, period_id}` → 201. 404 si `period_id` no es de ese usuario. Deja evento en la bitácora. |
| DELETE | `/admin/users/{user_id}/payments/{payment_id}` | 404 si el pago no es de ese usuario. Deja constancia de la eliminación en la bitácora. |

**Advertencias:**
- `total_paid` **suma importes sin convertir monedas**. Hoy es correcto porque todo se cobra en COP; con varias monedas hay que pasarlo a un desglose por moneda.
- Los períodos con `origin="backfill"` fueron **reconstruidos** por la migración a partir de la suscripción vigente: no son historia registrada. Todo lo anterior al 2026-09-01 se perdió y no es recuperable.

## Tipo de cambio — `app/routes/fx.py` (prefijo `/fx`)

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| GET | `/fx/rate?from=XXX&to=YYY` | **Pública** (sin dependencia de auth) | Async. Misma moneda → `rate=1.0`. Cache en memoria de 12h (se pierde al reiniciar). Intenta `exchangerate.host`, fallback a `open.er-api.com`. 502 si ambos fallan. → `{from, to, rate, source, as_of}`. La lógica vive en `resolve_rate()` (desde 2026-08-30), reutilizada directamente (sin HTTP) por `/summary-extra/net-worth-consolidated`. |

## Cuenta — `app/api/account.py` (prefijo `/account`)

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| PATCH | `/account/preferences` | Auth (sin chequeo de suscripción, igual que cambiar contraseña) | `{report_currency}` → 400 si el código no existe en el catálogo de `currency`. No exige que el usuario tenga cuentas en esa moneda. |
