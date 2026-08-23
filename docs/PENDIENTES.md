# Pendientes — Balanced Cent

Lista viva de lo que queda por hacer, para que nada quede en el olvido. Actualizada 2026-08-22.

> Cubre **ambos** repos (backend y [frontend](https://github.com/jaras97/finanzas-personal-frontend)); vive aquí porque la carpeta que los agrupa en local no está versionada.

Contexto completo en [PLAN_DE_MEJORA.md](PLAN_DE_MEJORA.md) · [roadmap visual](https://claude.ai/code/artifact/a0b5d000-7576-497e-b1b7-2bc971266cc7).

## 🔴 Acción manual del usuario (no resoluble por código)

- [ ] **Rotar la contraseña de Supabase.** El código ya no la hardcodea (corregido en `alembic/env.py`), pero la contraseña filtrada **sigue siendo válida** y está en el historial de git. Pasos: dashboard de Supabase → Project Settings → Database → Reset database password → luego `flyctl secrets set DATABASE_URL='<nueva cadena>' -a personal-finances-backend`.

## Fase 0 — Seguridad y estabilidad (resto)


- [x] ~~**Suite de tests + gate en CI**~~ ✅ 2026-08-23 — 67 tests contra Postgres real; el job de deploy ahora depende de que pasen. Verificado introduciendo un bug de comisiones a propósito (lo detectó) y confirmando que el deploy queda en `skipped` cuando fallan.
- [ ] **Refresh token.** El access token expira (8h en prod) sin renovación → el usuario es expulsado a media sesión sin aviso. Esfuerzo: M.

## Fase 1 — Multi-moneda (resto)

- [ ] **Moneda de reporte + patrimonio neto consolidado.** Hoy todo se reporta en silos por moneda; falta una "moneda de referencia" por usuario y un total consolidado convertido con FX. El endpoint `/fx/rate` ya soporta cualquier par de monedas — falta el endpoint de agregación y la UI. Esfuerzo: M.

## ~~Fase 2 — Panel de usuarios y suscripciones~~ ✅ COMPLETA (2026-08-22)

- [x] `role` expuesto en `GET /auth/me`.
- [x] `GET /admin/users` — paginado, buscador por correo, con estado de suscripción resuelto por fila.
- [x] `PATCH /admin/users/{id}/role` — con protección contra quitar el último admin.
- [x] Ruta `/admin` en el frontend con tabla de usuarios, buscador y gestión de suscripciones.
- [x] Bug encontrado y corregido en el camino: los admins quedaban bloqueados por el gate de suscripción del layout `(app)` — ahora lo omiten (son personal, no clientes).

Pendiente menor derivado: `/subscriptions/admin/me` es código muerto inalcanzable (la ruta `/{user_id}` lo captura primero). Ver sección de bugs abajo.

## Fase 3 — Reducir fricción de captura

Esto es lo que hace que "ingresar información sea tedioso", en orden de impacto real:

- [ ] **Importación de extractos bancarios (CSV).** Hoy cada movimiento se teclea uno por uno. Esfuerzo: L.
- [x] ~~**Transacciones recurrentes** (nómina, arriendo, suscripciones)~~ ✅ 2026-08-22 — sección `/recurring`, generación idempotente, sin sobregiro, materialización automática una vez por sesión.
- [x] ~~Recordar última cuenta/categoría usada~~ ✅ 2026-08-22 — tipo/cuenta/categoría se recuerdan por tipo de movimiento y se precargan.
- [ ] Botón explícito "repetir última transacción" (complemento al anterior). Esfuerzo: XS.
- [ ] Registro rápido flotante (quick add) accesible desde cualquier pantalla. Esfuerzo: M.

## Fase 4 — Profundidad financiera

- [ ] Presupuesto por categoría + alerta real de sobregasto (hoy la única alerta es global: "gasté más de lo que ingresó"). Esfuerzo: M.
- [ ] Ciclo de facturación de tarjeta de crédito (fecha de corte, fecha límite, pago mínimo, cupo/límite). Esfuerzo: M.
- [ ] Tabla de amortización real para préstamos — **o** aclarar en la UI que `interest_rate` es solo informativo (hoy se guarda pero no genera acumulación). Esfuerzo: M.
- [ ] Subcategorías. Esfuerzo: M.
- [ ] Exportar reportes a PDF/Excel. Esfuerzo: M.
- [ ] Tendencia histórica multi-mes / interanual en el dashboard. Esfuerzo: M.
- [ ] Adjuntar comprobante/foto de recibo a una transacción. Esfuerzo: M.
- [ ] Transacciones divididas (un recibo, varias categorías). Esfuerzo: M.
- [ ] Conciliación bancaria (comparar saldo de la app contra el extracto real). Esfuerzo: M.

## Seguridad de cuentas (agregado 2026-08-22)

- [x] ~~Validación de longitud mínima de contraseña en el backend~~ ✅ — antes la API aceptaba contraseñas de 1 carácter aunque el frontend pidiera 8.
- [x] ~~Pantalla para cambiar la propia contraseña~~ ✅ — `/account`, el endpoint existía sin UI.
- [ ] **Rotar la contraseña temporal de `mateojaras97@gmail.com`** — se fijó en una sesión de trabajo y quedó escrita en el historial de esa conversación. Cambiarla desde `/account`.

## Fase 5 — Pulido técnico y UI/UX

- [ ] Adoptar `react-hook-form` + `zod` en los formularios (ya están instalados y sin usar; hoy todo es `useState` manual por campo). Esfuerzo: L.
- [ ] Separar visualmente "compra con tarjeta" de "gasto desde cuenta" en el flujo de nueva transacción (hoy la tarjeta aparece como si fuera una cuenta más, con prefijo `debt-` interno). Esfuerzo: S.
- [ ] Enlazar o eliminar `WithdrawFromAccountModal` — existe en el código pero ningún botón lo abre (el botón "Depositar" también está comentado en `AccountsSection.tsx`). Esfuerzo: S.
- [ ] Eliminar componentes huérfanos (`Header.tsx`, `MobileSidebarTrigger.tsx`, `SummaryLineChart.tsx`, `SummaryPieChart.tsx`). Esfuerzo: XS.
- [ ] Quitar los `console.log` de debug con emojis del middleware de Next.js (están activos en producción). Esfuerzo: XS.
- [ ] Centralizar el patrón "fecha a mediodía local" — está copiado en al menos 4 archivos. Esfuerzo: S.
- [ ] Unificar el manejo de errores de API: varios modales reimplementan su propio `extractApiError` en vez de usar `src/lib/extractErrorMessage.ts`. Esfuerzo: S.

## Cobertura de tests (ampliable)

La suite cubre hoy la lógica de plata y control de acceso. Lo que **no** está cubierto y valdría la pena agregar cuando se toque:

- [ ] Endpoints de depósito/retiro de cuentas (`/saving-accounts/{id}/deposit|withdraw`).
- [ ] Reversión de compras con tarjeta de crédito (el camino que decrementa la deuda).
- [ ] Reversión de transferencias (revierte ambas patas).
- [ ] `/cash-flow` y el desglose por categoría de `/summary`.
- [ ] Reset de contraseña por token (`/auth/reset-password`).
- [ ] Tests de frontend: hoy no hay ninguno (solo `tsc --noEmit` como red).

## Bugs conocidos del backend (no urgentes, documentados)

- [ ] `summary_extra.py`: el cálculo de pasivos filtra `Transaction.type == "payment"`, valor que nunca se asigna. Bug enmascarado (el resultado actual es casualmente correcto porque `debt.total_amount` ya se decrementa en vivo), pero frágil ante cualquier refactor.
- [ ] `DebtTransactionType.charge_reversal` no existe en el enum; las reversiones de compras con tarjeta se registran como `extra_charge`.
- [ ] `POST /saving-accounts/{id}/withdraw` etiqueta la transacción como `source_type="account_deposit"` (debería ser `account_withdraw`).
- [ ] Inconsistencia de respuesta: `deposit` devuelve `{message, nuevo_balance}` y `withdraw` devuelve el objeto completo.
- [ ] `DELETE /transactions/{id}` en una transferencia revierte solo la pata borrada — la otra queda huérfana con su efecto de balance sin revertir.
- [ ] Reset de contraseña: `RESET_TOKENS` es un dict en memoria (se pierde en cada deploy, no escala a 2 instancias) y el envío de correo está comentado → el flujo "olvidé mi contraseña" no envía correos reales hoy.
- [ ] `/fx/rate` no tiene auth (endpoint público) y su cache de 12h es en memoria de proceso.
- [ ] Crear una cuenta con saldo inicial ≠ 0 no genera transacción de apertura → el saldo inicial no queda trazado como movimiento.
- [ ] Modelos `Account` e `Investment` sin uso por ningún endpoint — candidatos a eliminar.
- [ ] `/subscriptions/admin/me` es inalcanzable: la ruta `/{user_id}` se declara antes y la captura, exigiendo admin y fallando al parsear `"me"` como UUID. Eliminar la ruta muerta (el equivalente vivo es `/subscriptions/me`). Esfuerzo: XS.
- [ ] Drift de esquema entre local y producción: ya se corrigió el caso de `saving_account.currency`, pero conviene auditar si hay otras columnas divergentes (comparar `\d <tabla>` en ambos entornos).
