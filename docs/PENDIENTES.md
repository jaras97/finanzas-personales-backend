# Pendientes — Balanced Cent

Lista viva de lo que queda por hacer, para que nada quede en el olvido. Actualizada 2026-08-28.

> Cubre **ambos** repos (backend y [frontend](https://github.com/jaras97/finanzas-personal-frontend)); vive aquí porque la carpeta que los agrupa en local no está versionada.

Contexto completo en [PLAN_DE_MEJORA.md](PLAN_DE_MEJORA.md) · [roadmap visual](https://claude.ai/code/artifact/a0b5d000-7576-497e-b1b7-2bc971266cc7).

## 🔴 Acción manual del usuario (no resoluble por código)

- [x] ~~**Rotar la contraseña de Supabase.**~~ ✅ 2026-08-28
- [x] ~~**Configurar variables de entorno en Fly.io**~~ ✅ 2026-08-31 — `RESEND_API_KEY`, `EMAIL_FROM`, `FRONTEND_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` cargadas con `fly secrets import`. Bucket privado `comprobantes` creado con tope de 5 MB y lista blanca de MIME (JPG/PNG/WEBP/HEIC/PDF), verificado que rechaza otros tipos y que el acceso público directo está bloqueado. Ojo al reconfigurar: la llave de Supabase es `SUPABASE_SERVICE_KEY`, **no** `SECRET_KEY` — esta última es la de firma de los JWT y pisarla invalida todas las sesiones.

## Fase 0 — Seguridad y estabilidad (resto)


- [x] ~~**Suite de tests + gate en CI**~~ ✅ 2026-08-23 — 67 tests contra Postgres real; el job de deploy ahora depende de que pasen. Verificado introduciendo un bug de comisiones a propósito (lo detectó) y confirmando que el deploy queda en `skipped` cuando fallan.
- [x] ~~**Refresh token.**~~ ✅ 2026-08-30 — tabla `refresh_token` (SHA-256 del token, nunca el crudo), rotación en cada uso, revocación en logout / cambio de contraseña / reset. Interceptor de axios renueva en el primer 401 y deduplica los concurrentes; el middleware deja pasar si el access venció pero hay refresh.

## Fase 1 — Multi-moneda (resto)

- [x] ~~**Moneda de reporte + patrimonio neto consolidado.**~~ ✅ 2026-08-30 — ver Fase 6 del roadmap abajo.

## ~~Fase 2 — Panel de usuarios y suscripciones~~ ✅ COMPLETA (2026-08-22)

- [x] `role` expuesto en `GET /auth/me`.
- [x] `GET /admin/users` — paginado, buscador por correo, con estado de suscripción resuelto por fila.
- [x] `PATCH /admin/users/{id}/role` — con protección contra quitar el último admin.
- [x] Ruta `/admin` en el frontend con tabla de usuarios, buscador y gestión de suscripciones.
- [x] Bug encontrado y corregido en el camino: los admins quedaban bloqueados por el gate de suscripción del layout `(app)` — ahora lo omiten (son personal, no clientes).

Pendiente menor derivado: `/subscriptions/admin/me` es código muerto inalcanzable (la ruta `/{user_id}` lo captura primero). Ver sección de bugs abajo.

## Fase 3 — Reducir fricción de captura

Esto es lo que hace que "ingresar información sea tedioso", en orden de impacto real:

- [x] ~~**Importación de extractos bancarios (CSV).**~~ ✅ 2026-08-30 — ver Fase 4 del roadmap abajo.
- [x] ~~**Transacciones recurrentes** (nómina, arriendo, suscripciones)~~ ✅ 2026-08-22 — sección `/recurring`, generación idempotente, sin sobregiro, materialización automática una vez por sesión.
- [x] ~~Recordar última cuenta/categoría usada~~ ✅ 2026-08-22 — tipo/cuenta/categoría se recuerdan por tipo de movimiento y se precargan.
- [x] ~~Botón explícito "repetir última transacción" (complemento al anterior)~~ ✅ 2026-08-28 — solo transacciones manuales (sin `source_type`); precarga el formulario con fecha de hoy, el usuario confirma antes de crear.
- [x] ~~Registro rápido flotante (quick add) accesible desde cualquier pantalla~~ ✅ 2026-08-28 — FAB en `(app)/layout.tsx`, reusa `NewTransactionModal`; recarga la página tras crear (no hay caché compartida entre features para invalidar selectivamente).

## Fase 4 — Profundidad financiera

- [x] ~~Presupuesto por categoría + alerta real de sobregasto~~ ✅ 2026-08-30 — ver Fases 2 y 3 del roadmap abajo.
- [x] ~~Ciclo de facturación de tarjeta de crédito~~ ✅ 2026-08-30 — ver Fase 7 del roadmap abajo.
- [x] ~~Patrimonio neto consolidado en una moneda de referencia~~ ✅ 2026-08-30 — ver Fase 6 del roadmap abajo.
- [x] ~~**Metas de ahorro**~~ ✅ 2026-08-30 — ver Fase 8 del roadmap abajo.
- [x] ~~**Reglas de categorización automática**~~ ✅ 2026-08-30 — ver Fase 5 del roadmap abajo. Nota de alcance: se conectó al import de CSV y a `apply` sobre lo existente, **no** a la autosugerencia mientras se escribe en el formulario manual (queda pendiente si se quiere).
- [ ] Tabla de amortización real para préstamos — **o** aclarar en la UI que `interest_rate` es solo informativo (hoy se guarda pero no genera acumulación). Esfuerzo: M.
- [ ] Subcategorías. Esfuerzo: M.
- [ ] Exportar reportes a PDF/Excel. Esfuerzo: M.
- [ ] Tendencia histórica multi-mes / interanual en el dashboard. Esfuerzo: M.
- [x] ~~Adjuntar comprobante/foto de recibo a una transacción~~ ✅ 2026-08-30 — Supabase Storage en bucket privado, URLs firmadas de 1h, ruta construida en el servidor (no con el `filename` del cliente). Ícono de clip con contador en Transacciones. **Requiere `SUPABASE_URL` y `SUPABASE_SERVICE_KEY` en producción.**
- [ ] Transacciones divididas (un recibo, varias categorías). Esfuerzo: M.
- [ ] Conciliación bancaria (comparar saldo de la app contra el extracto real). Esfuerzo: M.

### Hoja de ruta acordada para lo anterior (2026-08-30)

Orden completo con las 8 fases (transferencias, presupuestos ×2, CSV, reglas, consolidado, tarjeta, metas) en el [artifact de Presupuestos y funcionalidades](https://claude.ai/code/artifact/f7cb77b2-7572-449c-a612-afdb75657d23#roadmap).

- [x] ~~**Fase 1 del roadmap — Transferencias sin duplicar**~~ ✅ 2026-08-30 — una transferencia son 2 filas (`transfer_group_id` compartido) en los datos, pero se leían como dos movimientos independientes en Transacciones ("gasté Y también gané"). Ahora se fusionan client-side (`mergeTransferPairs` en `transactionDisplay.ts`) en una sola fila "Cuenta A → Cuenta B"; si cruza monedas se muestran ambos montos. De paso, se corrigió que `getStatusLabel` nunca devolvía "Transferencia" (el chequeo de `type==='income'/'expense'` iba antes que el de `source_type==='transfer'`, y `type` siempre es income/expense en la práctica) — afectaba también el historial por cuenta.
- [x] ~~**Fase 2 del roadmap — Presupuestos (backend + gestión)**~~ ✅ 2026-08-30 — tabla `budget` versionada por `effective_from` (editar el mes en curso actualiza esa fila, nunca reescribe meses pasados; `amount=0` = pausado) y 3 endpoints (`app/api/budgets.py`) que reutilizan el criterio de exclusión de `GET /summary` para el gasto real. Pestaña "Presupuestos" dentro de Categorías (`CategoriesTabs.tsx`): crear/editar (categoría y moneda quedan fijas al editar, es un upsert por mes)/pausar, con barra de progreso y aviso de presupuesto superado. De paso: se cerró un hueco de RLS en `currency` y `recurring_transaction` (creadas después de la única migración que activaba RLS, quedaron fuera desde entonces), y se agregó `/budgets` al middleware del frontend (faltaba en `privatePaths`/`matcher`).
- [x] ~~**Fase 3 del roadmap — Presupuestos, visibilidad en Resumen**~~ ✅ 2026-08-30 — sección "Presupuestos del mes" en `(app)/summary`, filtrada a la moneda seleccionada (nunca fusiona monedas), siempre del mes en curso (no respeta el rango de fechas del dashboard). Se oculta si no hay presupuestos en esa moneda. Banner rojo al cruzar 100%, mismo patrón visual que el banner de sobregasto que ya existía. `progressTone` (`lib/budgetDisplay.ts`) compartido con `/budgets` para que ambas vistas se vean iguales.
- [x] ~~**Fase 4 del roadmap — Importación de CSV**~~ ✅ 2026-08-30 — `POST /transactions/import/preview` en dos modos (sin mapeo: muestra cruda para elegir columnas; con mapeo: parsea todo, marca duplicados por monto+fecha±3d+descripción similar, sugiere "Sin categorizar"). `POST /transactions/import/confirm` crea solo lo aprobado, sin bloquear por fondos insuficientes (es historial, no una decisión de gasto nueva). `import_profile` recuerda el mapeo por cuenta. Wizard de 4 pasos en `(app)/import`, botón "Importar CSV" en Cuentas.
- [x] ~~**Fase 5 del roadmap — Reglas de categorización**~~ ✅ 2026-08-30 — `category_rule` (texto-contiene, sin regex, orden manual por `priority`) con CRUD + `POST /category-rules/apply` (recategoriza lo que sigue en "Sin categorizar"). Conectada al preview de CSV (Fase 4). Pestaña "Reglas" en Categorías + atajo "crear regla" desde una transacción en Transacciones (solo tabla de escritorio). Fuera de alcance a propósito: autosugerencia mientras se escribe en el formulario manual.
- [x] ~~**Fase 6 del roadmap — Patrimonio neto consolidado**~~ ✅ 2026-08-30 — `User.report_currency` (default COP) + `GET /summary-extra/net-worth-consolidated`, que convierte el resumen por moneda ya existente a una sola moneda con la tasa de **hoy** de `/fx/rate` (no es reconstrucción histórica). Degrada con gracia si una moneda no consigue tasa (`degraded=true`, esa fila sin convertir, no rompe el resto). Tercera tarjeta hero en Resumen + selector en Mi cuenta.
- [x] ~~**Fase 7 del roadmap — Ciclo de tarjeta de crédito**~~ ✅ 2026-08-30 — 4 campos nuevos en `Debt` (cupo, día de corte 1-28, días para pagar, % de pago mínimo), solo con efecto en `kind=credit_card`. `GET /debts/{id}/statement` calcula el ciclo en vivo desde `DebtTransaction` (sin tabla de estados de cuenta históricos). Barra de cupo disponible + cuenta regresiva a la fecha de pago en cada tarjeta de `(app)/debts`. Pago mínimo siempre etiquetado como estimado, nunca como el valor exacto del banco.
- [x] ~~**Fase 8 del roadmap — Metas de ahorro**~~ ✅ 2026-08-30 — meta atada 1:1 a una `SavingAccount` completa, no "sobres" compartiendo una cuenta. Progreso = `saldo_actual / target_amount` en vivo, sin trackear aportes/retiros. Índice único parcial: a lo sumo una meta activa por cuenta. `monthly_savings_needed` precalculado cuando hay `target_date`. Sección "Metas de ahorro" en Cuentas, con badge de celebración al llegar al 100%.

**Las 8 fases del roadmap quedaron completas y desplegadas a producción el mismo día.**

## Seguridad de cuentas (agregado 2026-08-22)

- [x] ~~Validación de longitud mínima de contraseña en el backend~~ ✅ — antes la API aceptaba contraseñas de 1 carácter aunque el frontend pidiera 8.
- [x] ~~Pantalla para cambiar la propia contraseña~~ ✅ — `/account`, el endpoint existía sin UI.
- [x] ~~**Rotar la contraseña temporal de `mateojaras97@gmail.com`**~~ ✅ 2026-08-28

## Fase 5 — Pulido técnico y UI/UX

- [ ] Adoptar `react-hook-form` + `zod` en los formularios (ya están instalados y sin usar; hoy todo es `useState` manual por campo). Esfuerzo: L.
- [ ] Separar visualmente "compra con tarjeta" de "gasto desde cuenta" en el flujo de nueva transacción (hoy la tarjeta aparece como si fuera una cuenta más, con prefijo `debt-` interno). Esfuerzo: S.
- [ ] Enlazar o eliminar `WithdrawFromAccountModal` — existe en el código pero ningún botón lo abre (el botón "Depositar" también está comentado en `AccountsSection.tsx`). Esfuerzo: S.
- [ ] Eliminar componentes huérfanos (`Header.tsx`, `MobileSidebarTrigger.tsx`, `SummaryLineChart.tsx`, `SummaryPieChart.tsx`). Esfuerzo: XS.
- [x] ~~Quitar los `console.log` de debug con emojis del middleware de Next.js~~ ✅ 2026-08-30
- [ ] Centralizar el patrón "fecha a mediodía local" — está copiado en al menos 4 archivos. Esfuerzo: S.
- [ ] Unificar el manejo de errores de API: varios modales reimplementan su propio `extractApiError` en vez de usar `src/lib/extractErrorMessage.ts`. Esfuerzo: S.

## Fase 6 — Diseño: navegación e identidad visual (agregado 2026-08-29)

Diagnóstico completo (evidencia visual + hallazgos + hoja de ruta) en el [artifact publicado](https://claude.ai/code/artifact/498e4c58-3959-48ee-8386-9e942ccd11ad). Resumen: el problema no era falta de sistema de diseño (`globals.css`, `Card`, `Button` ya tenían tokens/variantes) sino que casi nada lo adoptaba — el color comunicaba de qué *tipo* de cuenta/deuda se trataba en vez de si algo era bueno/malo/requería atención.

- [x] ~~**Fase A — fundación**~~ ✅ 2026-08-29 — mapa de color único (`frontend/src/lib/colorRoles.ts`); corregidos los 3 hallazgos de severidad alta ("Total deudas" verde en Resumen vs. rojo en Deudas, patrimonio neto negativo en tarjeta verde, botones "Ver movimientos"/"Pagar" con color por tipo de cuenta/deuda en vez de por acción); primitivos `FormModal`/`PageHeader` (`frontend/src/components/ui/`) con un modal y una página migrados como prueba (`NewTransactionModal`, `/transactions`).
- [x] ~~**Fase B — migración sistemática**~~ ✅ 2026-08-29 — los 20 modales que aún calculaban su propio `panelTint`/`headerFooterTint` a mano migrados a `FormModal`; `PageHeader` adoptado en las 6 páginas restantes (`summary`, `saving-accounts`, `debts`, `categories`, `recurring`, `admin`, `account`). Jerarquía de KPI en Resumen: 2 tarjetas "hero" grandes (Patrimonio neto, Balance del período) + 8 métricas secundarias en tarjetas pequeñas y silenciosas (color solo en el texto, no en el fondo). Espacio de seguridad (`pb-20`) en el shell móvil para que el FAB de registro rápido no tape el contenido justo antes del footer. `WithdrawFromAccountModal` quedó fuera a propósito (ver Fase 5: no está enlazado a ningún botón).
- [x] ~~**Fase C — navegación e identidad**~~ ✅ 2026-08-30 — sidebar agrupado (Resumen/Transacciones sueltos arriba, PATRIMONIO: Cuentas+Deudas, AJUSTES: Categorías+Mi cuenta+Usuarios); Recurrentes se movió a pestaña dentro de `/transactions` (`TransactionsTabs.tsx`, misma ruta `/recurring`, ya no tiene ítem propio en el sidebar); rebrand a "Balanced Cent" (logomark "B" en el color de acento en vez de ₿, sidebar/footer/`<title>`/pantalla de suscripción vencida); footer del shell recortado de 3 columnas + CTA "Conectar cuentas" (funcionalidad inexistente, era engañoso) a una sola línea (© + versión + disclaimer); KPI "Total en cuentas"/"Total deudas" del Resumen ahora enlazan a `/saving-accounts`/`/debts`.
  - `NEXT_PUBLIC_APP_NAME` **no está configurado** en Vercel producción (verificado con `vercel env ls production`) — usa el fallback del código, que ya es `Balanced Cent`. Nada que hacer ahí; `.env.local`/`.env.example` también actualizados para desarrollo/referencia.
  - Pendiente menor no crítico: `src/app/favicon.ico` sigue siendo el ícono genérico de Next.js, no una marca propia de Balanced Cent — requiere generar un asset de imagen, fuera del alcance de esta sesión.
- [x] ~~**Filtros de Transacciones — rediseño de UX**~~ ✅ 2026-08-30 — el bug real: la tabla no tenía ningún límite de fecha por defecto (mostraba todo el historial) mientras las tarjetas KPI de la misma pantalla ya mostraban "mes actual", contradicción visible desde el primer render. `TransactionFilters` ahora es un componente controlado (`value`/`onChange`, sin estado propio "en borrador") con el mismo default que las KPI; los selects de tipo/categoría/origen aplican solos, sin botón; los presets del calendario ("Este mes", "Este año"...) aplican con un clic y cierran el popover, en vez de requerir un "Aplicar" adicional; el popover del calendario tenía además un bug de layout serio -- en laptops de pantalla corta (1366×768 y similares) el botón "Aplicar" o los presets quedaban fuera de la pantalla sin scroll, dependiendo de hacia qué lado volteaba Radix el popover -- corregido con header/footer fijos y solo el calendario con scroll interno (`max-h-[var(--radix-popover-content-available-height)]`). Botón "Filtros" ahora muestra un punto cuando hay filtros activos.

## Cobertura de tests (ampliable)

La suite cubre hoy la lógica de plata y control de acceso. Lo que **no** está cubierto y valdría la pena agregar cuando se toque:

- [ ] Endpoints de depósito/retiro de cuentas (`/saving-accounts/{id}/deposit|withdraw`).
- [ ] Reversión de compras con tarjeta de crédito (el camino que decrementa la deuda).
- [ ] Reversión de transferencias (revierte ambas patas).
- [ ] `/cash-flow` y el desglose por categoría de `/summary`.
- [x] ~~Reset de contraseña por token (`/auth/reset-password`)~~ ✅ 2026-08-30 — 9 tests.
- [x] ~~Tests de frontend~~ ✅ 2026-08-31 — Vitest + Testing Library, 55 tests sobre la lógica pura de mayor riesgo (`transactionDisplay`, interceptor de refresh en `api.ts`, `middleware`, `budgetDisplay`, `format`), con CI propio (typecheck → tests → build) en push y PR. Cada test crítico se validó por mutación: se reintrodujo el bug y se confirmó que el suite lo atrapa.
- [x] ~~Ampliar cobertura de frontend a componentes~~ ✅ 2026-08-31 — wizard de import CSV (los 4 pasos) y modal de comprobantes; 76 tests en total. Destapó un bug real: "marcar todas" incluía las filas con error y el confirm entero fallaba con 422, así que una sola línea ilegible del extracto impedía importar todas las demás. Corregido y desplegado.
- [ ] Seguir ampliando cobertura de componentes: quedan sin tests los formularios de transacción/deuda/presupuesto y las páginas de Resumen y Transacciones. Esfuerzo: M.

## Bugs conocidos del backend (no urgentes, documentados)

- [ ] `summary_extra.py`: el cálculo de pasivos filtra `Transaction.type == "payment"`, valor que nunca se asigna. Bug enmascarado (el resultado actual es casualmente correcto porque `debt.total_amount` ya se decrementa en vivo), pero frágil ante cualquier refactor.
- [ ] `DebtTransactionType.charge_reversal` no existe en el enum; las reversiones de compras con tarjeta se registran como `extra_charge`.
- [ ] `POST /saving-accounts/{id}/withdraw` etiqueta la transacción como `source_type="account_deposit"` (debería ser `account_withdraw`).
- [ ] Inconsistencia de respuesta: `deposit` devuelve `{message, nuevo_balance}` y `withdraw` devuelve el objeto completo.
- [x] ~~`DELETE /transactions/{id}` en una transferencia~~ ✅ 2026-08-30 — era peor de lo documentado: revertía **dos veces** la cuenta de la pata borrada (ambos bloques del endpoint se disparaban) y dejaba la otra pata viva. Ahora borra el grupo completo revirtiendo cada cuenta una sola vez. La comisión se deja intacta a propósito (el banco sí la cobró).
- [x] ~~Reset de contraseña~~ ✅ 2026-08-30 — tokens en tabla `password_reset_token` (hasheados, un solo uso, 60 min, pedir uno nuevo invalida el anterior), envío por Resend, pantalla `/auth/reset-password` y pestaña de recuperación habilitada en el login. **Requiere `RESEND_API_KEY` en producción.**
- [ ] `/fx/rate` no tiene auth (endpoint público) y su cache de 12h es en memoria de proceso.
- [ ] Crear una cuenta con saldo inicial ≠ 0 no genera transacción de apertura → el saldo inicial no queda trazado como movimiento.
- [ ] Modelos `Account` e `Investment` sin uso por ningún endpoint — candidatos a eliminar.
- [ ] `/subscriptions/admin/me` es inalcanzable: la ruta `/{user_id}` se declara antes y la captura, exigiendo admin y fallando al parsear `"me"` como UUID. Eliminar la ruta muerta (el equivalente vivo es `/subscriptions/me`). Esfuerzo: XS.
- [ ] Drift de esquema entre local y producción: ya se corrigió el caso de `saving_account.currency`, pero conviene auditar si hay otras columnas divergentes (comparar `\d <tabla>` en ambos entornos).
