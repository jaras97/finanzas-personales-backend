# Balanced Cent — Plan de mejora

> Cubre **ambos** repos (backend y [frontend](https://github.com/jaras97/finanzas-personal-frontend)).
>
> Versión navegable con tablas y prioridades visuales: [Balanced Cent Roadmap](https://claude.ai/code/artifact/a0b5d000-7576-497e-b1b7-2bc971266cc7)

## Estado de la Fase 0 (actualizado 2026-08-22)

✅ Completo: RLS activo en producción · cookie httpOnly reemplazando el token en `localStorage`/cookie no-httpOnly · rate limiting en `/auth/login` · pipeline de deploy reparado (estuvo roto ~1 año por dos causas independientes: `alembic_version` huérfano en prod + el secret `FLY_API_TOKEN` nunca creado en GitHub) · dominio propio `api.balancedcent.com` en producción, necesario para que la cookie de sesión cruce entre frontend y backend.

⏳ Pendiente de Fase 0: **rotar la contraseña real de Supabase** (el código ya no la hardcodea, pero la contraseña filtrada sigue siendo válida — acción manual en el dashboard de Supabase, no resoluble por código) · suite mínima de tests + gate en CI · refresh token.

Detalle técnico completo de lo resuelto en `docs/ARCHITECTURE.md` (sección "Problemas conocidos") y el `docs/ARCHITECTURE.md` del frontend (sección "Autenticación").

## Estado de la Fase 1 (completada 2026-08-22)

✅ Completo y desplegado en producción: catálogo real de monedas (tabla `currency`, 42 códigos ISO-4217, `GET /currencies`) reemplazando el enum fijo COP/USD/EUR · `saving_account.currency`/`debt.currency` ahora son texto validado contra el catálogo, no un tipo cerrado · `summary`/`summary-extra`/`cash-flow` iteran dinámicamente las monedas que cada usuario realmente tiene (arregla de raíz la inconsistencia de EUR entre `assets-summary` y `net-worth-summary`) · todos los selectores de moneda y heurísticas de decimales del frontend leen el catálogo real en vez de asumir solo COP/USD.

Un detalle de la migración vale la pena registrar: el primer intento de deploy a producción falló porque `saving_account.currency` resultó ser todavía el enum de Postgres ahí (a diferencia de local, donde ya era texto por un cambio ad-hoc anterior nunca migrado formalmente) — un *drift* de esquema entre entornos que no se había detectado hasta ahora. Se corrigió haciendo la migración robusta a ambos casos de partida, verificado explícitamente reproduciendo el estado exacto de producción en local antes de reintentar el deploy. Cero pérdida de datos en ambos intentos (Fly abortó limpio el primer deploy fallido).

Pendiente de Fase 1 (quedó fuera de este alcance, para una próxima sesión): moneda de reporte + patrimonio neto consolidado con conversión FX (el endpoint `/fx/rate` ya soporta cualquier par de monedas, falta la UI y el endpoint de agregación).

---

Auditoría funcional, técnica y financiera realizada el 2026-08-22 corriendo ambos proyectos en local (Postgres vía Docker, backend con `uvicorn --reload`, frontend con `pnpm dev`) y probando el flujo real vía API: registro, login, cuentas multi-moneda (COP/USD/EUR), tasa de cambio real (`GET /fx/rate`), transferencia entre monedas, compra con tarjeta de crédito y endpoints de resumen.

## Estado verificado en vivo

- El esquema de la base local ya estaba al día con los modelos actuales (`is_system`, `system_key`, `reversal_note`); solo el número de versión de Alembic estaba desincronizado por una reescritura de historial — se resolvió con `alembic stamp head --purge`, sin tocar datos.
- 🔴 **Se encontró y corrigió localmente** un problema serio: `backend/alembic/env.py` tenía hardcodeada la cadena de conexión de **producción** en Supabase con password en texto plano, sobreescribiendo cualquier `DATABASE_URL` real. Queda pendiente **rotar esa contraseña en Supabase** y confirmar el fix en el repositorio remoto.
- El backend **sí acepta EUR** como moneda (se creó una cuenta EUR exitosamente); `MXN` fue rechazado por el enum cerrado de Postgres.
- `GET /summary-extra/assets-summary` **omite EUR** en su respuesta mientras `GET /summary-extra/net-worth-summary` **sí lo incluye** — inconsistencia confirmada entre dos endpoints hermanos.
- La transferencia entre cuentas de distinta moneda funciona correctamente end-to-end: trae tasa real desde `open.er-api.com`, convierte el monto y genera las dos patas del movimiento con el mismo `transfer_group_id`.

## Análisis por módulo

### Cuentas
- **Bien resuelto**: tipos cash/banco/inversión; cierre solo permitido con saldo en cero; no se puede eliminar una cuenta con movimientos.
- **Brecha financiera**: el saldo inicial no genera transacción (rompe trazabilidad desde el día uno); no hay conciliación bancaria; moneda limitada a un enum fijo.
- **Fricción**: el modal "Retirar" existe en el código pero no está enlazado a ningún botón — funcionalidad a medio construir.

### Transacciones
- **Bien resuelto**: reversión con nota y trazabilidad; el monto es inmutable tras crear la transacción (buena práctica contable).
- **Brecha financiera**: sin transacciones recurrentes, sin importación de extractos, sin adjuntar comprobantes, sin transacciones divididas.
- **Fricción**: registrar un gasto requiere 7 interacciones y 2 esperas de red, sin plantillas ni "repetir último".

### Deudas
- **Bien resuelto**: separa préstamo vs. tarjeta de crédito con reglas propias; subledger propio de pagos/cargos.
- **Brecha financiera**: la tasa de interés es solo informativa (no hay acumulación real ni amortización); sin ciclo de facturación de tarjeta; el campo `installments` se recibe pero no se usa.
- **Fricción**: una compra con tarjeta se registra desde el mismo modal de "nueva transacción", mezclando dos metáforas distintas.

### Categorías
- **Bien resuelto**: categorías de sistema protegidas; desactivar es soft-delete.
- **Brecha financiera**: sin subcategorías; sin presupuesto por categoría (la única alerta es "gasté más de lo que ingresó" a nivel global).

### Resumen / Dashboard
- **Bien resuelto**: activos, pasivos, patrimonio neto y flujo de caja por moneda; evolución diaria y top categorías.
- **Brecha financiera**: todo se reporta en silos por moneda, sin un patrimonio neto consolidado en una moneda de referencia; sin comparación entre periodos; sin exportar a PDF/Excel.

## Multi-moneda: arquitectura propuesta

El backend limita la moneda a un `enum` de Postgres (`COP`/`USD`/`EUR`) y el frontend además solo expone COP/USD en su tipo TypeScript — dos capas de "moneda quemada".

1. Reemplazar el enum por una tabla de referencia `currencies` (ISO-4217) + `user_currencies` (las que cada usuario activa). Migración de Alembic para `saving_account.currency` y `debt.currency`.
2. Nuevos endpoints: `GET /currencies`, `GET/POST /users/me/currencies`.
3. Frontend: selector de moneda dinámico en cuentas, deudas, transferencias y filtros; el `CurrencyToggle` deja de estar hardcodeado.
4. Los endpoints de resumen deben iterar sobre las monedas que el usuario realmente usa, no sobre un diccionario fijo — resuelve de raíz la inconsistencia de EUR.
5. Agregar "moneda de reporte" por usuario + patrimonio neto consolidado usando `/fx/rate` (ya funcional).

## Panel de administración de usuarios/suscripciones — ✅ implementado (2026-08-22)

El backend ya tenía el CRUD de suscripciones bajo `/subscriptions/admin/*` pero no había forma de listar usuarios, por eso solo se operaba por Postman. Resuelto: `GET /admin/users` (paginado, buscador por correo, con el estado de suscripción resuelto por fila), `PATCH /admin/users/{id}/role`, `role` expuesto en `/auth/me`, y una ruta `/admin` en el frontend con tabla, buscador y modal de gestión de suscripción.

Dos decisiones de seguridad que vale la pena recordar: el backend **rechaza quitar el último administrador** (si no, nadie podría volver a entrar al panel), y los administradores **quedan exentos del gate de suscripción** del layout — son personal, no clientes, y antes un admin sin suscripción propia quedaba bloqueado fuera del panel que usa justamente para otorgarlas.

## Deuda técnica y seguridad (por severidad)

| Severidad | Hallazgo | Impacto | Estado |
|---|---|---|---|
| Crítico | Credencial de Supabase en texto plano en `alembic/env.py`, sobreescribiendo `DATABASE_URL` | Cualquiera con acceso al repo puede conectarse a producción. | Código corregido ✅ · contraseña real pendiente de rotar ⏳ |
| Crítico | RLS deshabilitado en las 11 tablas de Supabase | Cualquiera con la anon/service key lee/escribe todo vía la API REST de Supabase, sin pasar por el backend. | ✅ Resuelto — RLS activo en producción |
| Crítico | Pipeline de deploy roto ~1 año (alembic_version huérfano + `FLY_API_TOKEN` nunca creado) | Ningún fix llegaba a producción pese a estar en `main`; la app quedó "suspended" desde sep. 2025. | ✅ Resuelto — CI verde de punta a punta |
| Alto | Token duplicado en 3 lugares (cookie + 2 `localStorage`), sin `httpOnly` | Mayor superficie de robo de sesión ante XSS; logout no limpiaba las 3 copias. | ✅ Resuelto — cookie httpOnly, nada en el cliente |
| Alto | Sin rate limiting en `/auth/login` | Expuesto a fuerza bruta de contraseñas. | ✅ Resuelto — 5/correo, 20/IP cada 15 min |
| Alto | Sin tests ni gate en CI — deploy incondicional en cada push a `main` | Un bug de lógica financiera puede llegar directo a producción. | ⏳ Pendiente |
| Alto | Sin refresh token (expira en 30 min / 8h en prod) | Usuarios expulsados en medio de una sesión activa. | ⏳ Pendiente |
| Medio | `assets-summary` omite EUR vs. `net-worth-summary` que sí lo incluye | Cifras de patrimonio inconsistentes entre pantallas. | ✅ Resuelto (Fase 1) |
| Medio | Cálculo de pasivos filtra un valor de `Transaction.type` que nunca ocurre | Frágil ante refactors; resultado actual casualmente correcto. | ⏳ Pendiente |
| Medio | Reset de contraseña en memoria, envío de correo comentado | El flujo "olvidé mi contraseña" no envía correos reales hoy. | ⏳ Pendiente |
| Bajo | Componentes huérfanos y formularios sin adoptar `react-hook-form`/`zod` ya instalados | Mantenimiento más costoso, sin riesgo funcional inmediato. | ⏳ Pendiente |

## Hoja de ruta por fases

**Fase 0 — Seguridad y estabilidad**: ✅ RLS · ✅ cookie `httpOnly` sin duplicados · ✅ rate limiting en login · ✅ pipeline de deploy reparado · ⏳ rotar credencial filtrada (acción manual pendiente) · ⏳ suite mínima de tests + gate en CI · ⏳ refresh token.

**Fase 1 — Multi-moneda real**: ✅ catálogo `currency` · ✅ selector dinámico en toda la UI · ✅ resúmenes iterando monedas reales (arregla el bug de EUR) · ⏳ moneda de reporte + patrimonio consolidado con FX.

**Fase 2 — Panel de usuarios y suscripciones**: ✅ completa — `role` en `/auth/me` · `GET /admin/users` (paginado + buscador) · `PATCH /admin/users/{id}/role` con protección del último admin · sección `/admin` con tabla y gestión de suscripciones · admins exentos del gate de suscripción.

**Fase 3 — Reducir fricción de captura**: importación de extractos (CSV) · transacciones recurrentes · recordar última cuenta/categoría + "repetir última" · registro rápido flotante.

**Fase 4 — Profundidad financiera**: presupuesto por categoría con alerta real · ciclo de facturación de tarjeta · amortización real de préstamos (o aclarar que la tasa es informativa) · subcategorías · exportar a PDF/Excel · tendencia histórica multi-mes · adjuntar comprobantes.

**Fase 5 — Pulido técnico y UI/UX**: adoptar `react-hook-form`+`zod` en todos los formularios · separar visualmente "compra con tarjeta" de "gasto desde cuenta" · eliminar componentes huérfanos y unificar el logout.

Detalle completo con prioridad y esfuerzo estimado por iniciativa en la [versión artifact](https://claude.ai/code/artifact/a0b5d000-7576-497e-b1b7-2bc971266cc7).
