# Categorías v2 — grupos, hojas y todo lo que cuelga de eso

> Cubre **ambos** repos. Escrito el 2026-09-08, antes de empezar a implementar.
>
> Documento de contexto: explica **qué** vamos a hacer, **por qué** esa decisión y no otra, y **en qué orden**. Si retomas esto en tres meses, empieza por «La decisión» y «Invariantes» — el resto es ejecución.

---

## La decisión

**Un solo cambio estructural sostiene todo lo demás:**

> Las categorías tienen exactamente dos niveles. El primer nivel es un **grupo** y **nunca recibe dinero**. Las transacciones y los presupuestos van **siempre** a una hoja del segundo nivel.

Es el modelo de YNAB, Monarch y Actual Budget. Lo descartamos el 2026-09-03 y lo adoptamos el 2026-09-08 cuando aparecieron dos datos nuevos: **hay importación bancaria en el roadmap** y **hay un módulo de presupuestos robusto en el roadmap**. Esas dos cosas invierten el cálculo, y conviene dejar constancia del porqué para no re-litigarlo.

### Por qué antes dijimos que no

Con entrada 100% manual y sin presupuesto de sobre, el modelo de Mint (padre e hija reciben dinero) era mejor: la jerarquía queda opcional, nadie se ve obligado a inventar una subcategoría para anotar un gasto, y el coste de bajar un nivel lo paga el usuario en **cada** registro. El modo de fallo medido de este producto es la fricción de entrada — 11 de 17 usuarios nunca registraron una transacción — así que todo lo que añade un toque es peligroso.

### Por qué ahora decimos que sí

**1. El presupuesto robusto lo exige.** Si un grupo puede tener presupuesto propio *y* sus hijas también, no existe respuesta correcta a «¿los 500k del padre incluyen a las hijas o se suman?». YNAB no resuelve esa pregunta: la elimina, haciendo que el grupo muestre la suma de sus hijas sin ser editable.

Esto **ya está roto en nuestro código**. `api/budgets.py::_calc_spent` incluye las transacciones de las hijas al calcular el gasto del padre, y no hay ninguna validación que impida presupuestar el padre y la hija a la vez. Los mismos pesos cuentan dos veces. Es un bug introducido el 2026-09-04 junto con las subcategorías, y el modelo nuevo lo mata por construcción en vez de por parche.

**2. La importación bancaria lo agradece.** Una regla que puede apuntar al padre *o* a la hija produce archivado inconsistente, y con importación el volumen se multiplica por diez. Con hojas estrictas la regla no tiene ambigüedad. Además desaparece el argumento principal en contra —el toque extra en cada registro— porque con importación ese coste ya no lo paga el usuario.

**3. El coste de migrar es hoy prácticamente cero** (una sola cuenta con datos) y en seis meses es un proyecto.

### Por qué NO una entidad `CategoryGroup` aparte

YNAB y Monarch tienen una tabla distinta para grupos. Nosotros **no la necesitamos**: la misma tabla `category` con `parent_id` lo expresa igual.

- `parent_id IS NULL` → **grupo**
- `parent_id IS NOT NULL` → **hoja**

Una tabla, una regla, cero migraciones de esquema para las relaciones existentes. Todo lo ya construido (validación de dos niveles, herencia de tipo, rollup del resumen, selector de taxonomía) sigue sirviendo; lo único que cambia es que el grupo deja de ser elegible.

---

## Invariantes

Estas siete reglas son el contrato. Todo lo demás se deriva. **Si una se rompe, el resto del sistema empieza a dar números que no cuadran.**

| # | Invariante | Dónde se hace cumplir |
|---|---|---|
| **I1** | Toda transacción apunta a una hoja (`category.parent_id IS NOT NULL`) | `api/transactions.py`, `api/debts.py`, `api/csv_import.py` |
| **I2** | Todo presupuesto apunta a una hoja. El presupuesto de un grupo es **derivado** (suma de sus hojas), nunca almacenado | `api/budgets.py` |
| **I3** | Un grupo activo siempre tiene **≥1 hoja activa** | `api/categories.py` (crear/desactivar/mover) |
| **I4** | Máximo dos niveles | `_validar_padre` (ya implementado) |
| **I5** | El tipo lo define el grupo; las hojas lo heredan. Un grupo de tipo `both` admite hojas de cualquier tipo | `_validar_padre` (ya implementado) |
| **I6** | Nombre único por grupo, no global | `api/categories.py` (ya implementado) |
| **I7** | Las categorías del sistema son hojas de un grupo oculto | Migración + `category_helpers.py` |

### I7 merece explicación

Hoy `Transferencia`, `Sin categorizar`, `Comisiones`, `Pago de Deuda` y `Rendimientos` son categorías de primer nivel con `is_system=True`, y **sí reciben transacciones** (una transferencia se archiva en `Transferencia`). Bajo I1 eso sería ilegal.

La solución es meterlas como hojas de un grupo `Sistema` de tipo `both`, oculto de los selectores. Por I5, un grupo `both` admite hojas de cualquier tipo, así que `Rendimientos` (ingreso) y `Comisiones` (egreso) conviven ahí sin excepciones.

**Elegimos esto en vez de «las de sistema están exentas de I1»** a propósito: una arquitectura sin excepciones es la que permite que la siguiente funcionalidad se integre sin condicionales. Cada exención que aceptas hoy es un `if` que alguien tiene que recordar dentro de seis meses.

### La hoja «General»

Cuando el usuario quiere una categoría sin desglosar (`Mascotas`, sin más), por debajo se crea el grupo **y una hoja llamada `General`**. Eso satisface I3 sin obligar a nadie a inventarse nada.

**Y la interfaz colapsa los grupos de una sola hoja en una única línea.** El usuario ve «Mascotas» y registra ahí, sin enterarse de que hay dos niveles. La redundancia vive en la base de datos, que es donde no molesta.

`General` se crea **solo si el grupo no tiene otras hojas**, y se elimina automáticamente cuando el usuario agrega hojas de verdad — I3 se mantiene sola sin intervención.

---

## Por qué esta arquitectura sostiene lo que viene

Cada funcionalidad del roadmap y qué le da este modelo:

| Lo que viene | Qué necesita | Cómo encaja |
|---|---|---|
| **Importación bancaria** | Mapear comercio → categoría, sin ambigüedad | Las reglas apuntan solo a hojas. Lo no reconocido cae en `Sistema › Sin categorizar`, que ya existe como hoja |
| **Presupuesto de sobre** | Asignar dinero a un bucket definido; cabeceras de grupo con total | I2 exactamente. El grupo muestra la suma, no se edita |
| **Comparación entre períodos** | Agregar por un nivel estable | El rollup a grupo es un solo `JOIN`. Ya implementado |
| **Reportes / export** | Que los totales cuadren | Total del grupo **es** la suma de sus hojas, siempre. Sin línea «sin desglosar» |
| **Reglas de categorización** | Un destino inequívoco | Solo hojas |
| **Multi-moneda** | Nada nuevo | El nivel de categoría es ortogonal a la moneda |
| **Metas de ahorro / deudas** | Nada nuevo | No dependen de la jerarquía |

**El criterio de diseño que conviene conservar:** cuando dudes entre dos opciones, elige la que deja **menos excepciones**. La ambigüedad del presupuesto padre/hija costó un bug silencioso; las excepciones se pagan siempre, solo que tarde.

---

# Fases

Cada fase deja el sistema **coherente y desplegable**. No hay estados intermedios rotos.

---

## Fase 0 — Fundación del modelo ✅ (2026-09-09)

*Backend + el mínimo de frontend para que fuera desplegable sola.*

**Qué se hace**

1. **Migración de datos** (detalle en la sección «Migración» más abajo). Va primero: las validaciones de I1/I2 rechazarían los datos actuales.
2. **Grupo `Sistema`** y las 5 categorías operativas movidas dentro como hojas (I7).
3. **I1**: rechazar transacciones cuya categoría sea un grupo. Toca `transactions.py`, `debts.py` (compras con tarjeta), `csv_import.py`, `recurring_transactions.py`.
4. **I2**: rechazar presupuestos sobre un grupo. `_calc_spent` deja de sumar hijas — cada hoja cuenta lo suyo — y el total del grupo se expone como campo derivado.
5. **I3**: al crear la primera hoja de verdad, borrar `General` si estaba vacía; al desactivar la última hoja, desactivar el grupo o recrear `General`.
6. `GET /categories` marca cada fila con `is_group` para que el frontend no tenga que deducirlo.

**Por qué en este orden:** la migración antes que las validaciones, o el propio deploy quedaría rechazando datos que él mismo creó.

**Riesgo:** es la fase que toca más superficie del backend. Mitigación: los ~211 tests actuales son la red, y hay que añadir los de las invariantes **antes** de escribir el código que las hace cumplir.

**Verificación:** hecha. 224 tests backend (15 nuevos de invariantes) y 112 de frontend, más una comprobación en navegador de punta a punta.

### Lo que se aprendió al implementarla

- **El frontend NO podía quedarse fuera.** Los selectores ofrecían grupos, y elegir uno daría 400 al guardar. La fase incluyó `postableCategories` (solo hojas) y `categoryDisplayName` (colapso del grupo de una hoja) en los seis formularios. Sin eso, la Fase 0 no era desplegable sola.
- **El colapso también hace falta del lado del servidor.** `nombre_visible()` en `utils/category_rules.py`: la vista previa del CSV, las reglas y los presupuestos devuelven un nombre ya renderizado, y sin él mostraban «General» en vez de «Streaming». El grupo `Sistema` se excluye del prefijo, o daría «Sistema › Sin categorizar».
- **`GET /budgets` cambió de forma** a `{groups, items}` — `groups` son los totales derivados. Es un cambio incompatible, por eso el hook del frontend fue en el mismo despliegue.
- **El selector de taxonomía bloqueaba mal.** Un grupo no tiene movimientos propios, así que aparecía como desmarcable aunque sus hojas tuvieran; ahora suma los de sus hojas.
- **Tres tests del modelo anterior quedaron obsoletos** y se eliminaron dejando anotado qué los reemplaza. No se «arreglaron»: probaban un comportamiento que ya no queremos.
- **Un grupo `Sistema` vacío viola I3.** La primera versión de la migración lo creaba para todos los usuarios, incluidos los 10 que no tenían ninguna categoría de sistema. La aserción de la propia migración lo detuvo antes de escribir nada.

---

## Fase 1 — Taxonomía y selector reestructurados

*Backend + frontend. El usuario empieza a ver el modelo nuevo.*

**Qué se hace**

1. **La taxonomía se reescribe como grupos + hojas.** Afortunadamente el PDF ya estaba escrito así: su estructura es *Bloque > Subcategoría > Ejemplos*, y esos «Ejemplos» son exactamente lo que uno gasta.

   - Grupo `Transporte` → hojas: Gasolina, Transporte público, Peajes, Mantenimiento
   - Grupo `Vivienda` → hojas: Arriendo, Hipoteca, Administración
   - Grupo `Mascotas` → hoja única `General` *(se ve como una línea)*

   Los 25 siguen siendo el nivel de reporte; las 69 pasan a ser donde se registra.

2. **El selector de taxonomía se adapta.** Marcar un grupo sin marcar hojas → crea el grupo + `General`. Marcar hojas concretas → esas, sin `General`. El diff del pie ya existe y sigue funcionando igual.

3. **Colapso visual de grupos con una sola hoja**, en la lista de categorías y en todos los selectores.

4. **Siembra al registrarse:** los 13 del núcleo como grupos, cada uno con su `General`.

**Riesgo:** que el colapso visual se implemente en un sitio y se olvide en otro, y el usuario vea «Mascotas › General» en unas pantallas y «Mascotas» en otras. Mitigación: una sola función compartida (`categoryDisplayName`), y un test que recorra los seis formularios.

---

## Fase 2 — El selector de categoría en transacciones

*Frontend. Es donde más se nota la mejora de experiencia.*

**El problema:** un `Select` plano con hasta 94 entradas se recorre con scroll. Es el control equivocado para esa cardinalidad.

**Qué se construye: un combobox con búsqueda.** No hace falta añadir librerías — `@radix-ui/react-popover` ya es dependencia.

```
┌─────────────────────────────────────┐
│ 🔍 gas|                             │
├─────────────────────────────────────┤
│ FRECUENTES                          │
│  🍽  Comida fuera › Restaurantes    │
│  🎟  Ocio › Salidas                 │
├─────────────────────────────────────┤
│ 🚗 TRANSPORTE                       │
│     Gasolina                        │
│     Peajes                          │
│ 🏠 VIVIENDA                         │
│     Arriendo                        │
├─────────────────────────────────────┤
│  + Crear «gas» en…                  │
└─────────────────────────────────────┘
```

**Decisiones y su porqué:**

- **«Frecuentes» arriba** (top 5 por uso en 90 días). En la cuenta con datos reales, las 3 categorías más usadas concentran el **58%** de los movimientos y las 5 primeras el **74%**. Eso resuelve tres de cada cuatro registros sin buscar ni desplegar nada.
- **Búsqueda por texto** que también acierta sobre el nombre del grupo: escribir «transporte» muestra sus hojas.
- **Cabecera de grupo no seleccionable**, con su icono y color. Sirve de contexto, no de opción — I1 hecha visible.
- **Se descarta el desplegable en dos pasos** (grupo → hoja): duplica los toques del caso común.
- **Crear al vuelo**: si no hay coincidencia, ofrecer crear esa hoja dentro de un grupo, sin salir del formulario. Es el momento exacto en que el usuario sabe qué necesita.
- **En móvil, hoja inferior a pantalla completa** con el buscador enfocado y objetivos de 44px. El `Select` actual obliga a un scroll incómodo dentro de un modal.

**Animación:** entrada del popover de 150ms, resaltado suave al filtrar. Nada más — el selector se usa muchas veces al día y cualquier animación larga se vuelve un estorbo.

---

## Fase 3 — El Resumen con desglose

*Backend + frontend. Se puede hacer en paralelo con la Fase 2.*

**Qué se hace**

1. **`/summary` devuelve la jerarquía anidada.** Hoy aplasta todo al padre y pierde el detalle. Debe devolver cada grupo con sus hojas dentro, en la misma respuesta: el volumen es mínimo y hace el drill-down instantáneo sin una petición por clic.

2. **Drill-down en el donut.** Por defecto, grupos (8-10 rebanadas legibles — eso ya funciona bien). Clic en una rebanada o en la leyenda → el donut se redibuja con las hojas de ese grupo, con migaja de pan para volver. Transición animada del propio donut, no un cambio brusco.

3. **Tabla con filas expandibles**, debajo del donut: grupo → hojas, con importe, % del total y **variación contra el período anterior**. El donut sirve para ver proporciones; para decidir hace falta comparar. Un contador mira la tabla, no el donut.

4. **«Sin categorizar» como fila visible**, no omitida. Hoy hay 51 movimientos así en la cuenta real: cualquier desglose que los esconda miente. La fila enlaza al flujo de la Fase 4.

**Lo que el modelo nuevo nos ahorra:** ya **no** hace falta una línea «Sin desglosar». El total del grupo es exactamente la suma de sus hojas. Ese era el precio del modelo Mint y con este desaparece.

---

## Fase 4 — Higiene: recategorizar

*Frontend, reutilizando el selector de la Fase 2.*

1. **Aviso de pendientes**: banner discreto cuando hay transacciones sin categorizar, con el número y un enlace directo.
2. **Flujo de clasificación rápida**: lista filtrada a «Sin categorizar», con el selector inline en cada fila. Sin abrir un modal por transacción.
3. **Recategorización masiva**: seleccionar varias y asignar de una vez. Imprescindible cuando entre la importación bancaria.
4. **Cambio inline desde la lista**: clic en el chip de categoría → selector. Hoy hay que abrir el modal de edición completo.

---

## Fase 5 — Primer arranque

*Frontend.*

1. **Primer ingreso a Categorías**: se mantiene la invitación descartable que abre el selector. **No se convierte en un paso obligatorio de onboarding** — la app tiene que funcionar desde el minuto cero y anteponer configuración al primer gasto añade fricción justo donde ya se cae la gente.
2. **Estados vacíos que enseñan**: en Transacciones, Resumen y Presupuestos, con una acción concreta en vez de un «no hay datos».
3. **Iconos y color en todas partes**: ya existe el mapa (`lib/categoryIcon.tsx`) y el color estable por nombre (`lib/categoryStyle.ts`). Falta usarlos en la lista de transacciones y en la tabla del resumen — hoy solo se ven en Categorías y en el donut.

---

# Migración de los datos actuales

Solo hay una cuenta con datos (`mateojaras@gmail.com`, 1.330 transacciones). **Se hace en la Fase 0, antes de activar las validaciones.**

### Regla general

Toda categoría de primer nivel que hoy reciba transacciones pasa a ser una hoja, con un grupo nuevo encima que hereda su nombre.

**El truco importante: no se toca ni una transacción.** En vez de mover movimientos, se crea el grupo y se recuelga la categoría existente debajo:

```
ANTES:  Transporte (id 22, 92 movimientos)

DESPUÉS: Transporte (grupo, id nuevo)
           └─ General (id 22, los mismos 92 movimientos)
```

La fila 22 conserva su id, así que los 92 `transaction.category_id` siguen siendo válidos. Se la renombra a `General` y el grupo nuevo se queda con el nombre, color e icono originales.

### Los dos casos

| Caso | Cómo se resuelve |
|---|---|
| **Categoría sin hijas, con movimientos** (Transporte, Vivienda, Alimentación…) | Crear grupo con su nombre/color/icono → recolgar la fila existente → renombrarla `General`. **Cero escrituras en `transaction`** |
| **Categoría con hijas Y movimientos propios** (`Salario`: 10 propios + Cesantías + Liquidación) | La fila pasa a ser el grupo. Se crea una hoja `General` y **sí** se mueven esos 10 movimientos. Es la única que requiere tocar transacciones |

En la cuenta real esto son **10 transacciones movidas en total**. Las otras cuatro categorías con hijas (Compras personales, Negocios y ventas, Regalos, Ropa y cuidado personal) tienen cero movimientos propios: se convierten en grupos sin mover nada.

### Comprobaciones antes de confirmar

La migración va en una transacción y aborta si algo falla:

- Ninguna transacción apunta a un grupo (I1)
- Ningún presupuesto apunta a un grupo (I2)
- Ningún grupo se queda sin hojas (I3)
- No hay tercer nivel (I4)
- El total de transacciones por usuario es idéntico antes y después
- La suma de gasto por grupo es idéntica a la suma por categoría de antes

**La última es la que de verdad importa:** si los totales del Resumen cambian, la migración está mal aunque todo lo demás cuadre.

---

# Decisiones de experiencia

Resumen de lo que aporta valor, con el porqué. La regla de fondo: **lo simple tiene que ser rápido, y el detalle tiene que estar disponible sin estorbar.**

| Decisión | Por qué |
|---|---|
| Grupos de una sola hoja se ven como una línea | El 80% de los usuarios nunca va a desglosar nada, y no tienen por qué enterarse de que existe un segundo nivel |
| «Frecuentes» arriba en el selector | Resuelve 3 de cada 4 registros sin interacción |
| Buscar en vez de desplegar | 94 entradas no se recorren con scroll |
| Crear categoría desde el propio formulario | El momento en que el usuario sabe qué le falta es justo ese |
| Icono + color en todas partes | Reconocimiento visual: se lee más rápido que el texto |
| Drill-down en vez de mostrar todo | 8 rebanadas se entienden; 94 no |
| Variación contra el período anterior | Un número solo no dice nada; comparado, sí |
| «Sin categorizar» siempre visible | Esconder el hueco convierte el reporte en mentira |
| Animaciones cortas (150-200ms) y solo en transiciones de estado | El selector se usa decenas de veces al día; una animación larga se vuelve un estorbo a la tercera vez |
| Respetar `prefers-reduced-motion` | Accesibilidad, y ya es la convención del proyecto |

---

# Lo que NO vamos a hacer

Anotado para no re-abrir la discusión:

- **Tres niveles de categoría.** Dos cubren el caso real y cada nivel extra multiplica la complejidad de cada reporte.
- **Una tabla `category_group` aparte.** `parent_id IS NULL` lo expresa igual y sin migración de esquema.
- **Onboarding obligatorio.** Configurar antes de poder registrar el primer gasto es exactamente la fricción que ya está matando la activación.
- **Exención de las invariantes para las categorías de sistema.** Van en un grupo oculto. Cero excepciones.
- **Mantener el modelo Mint «por si acaso».** Soportar los dos es peor que cualquiera de los dos.

---

# Deudas conocidas que esto cierra

| Deuda | Cómo se cierra |
|---|---|
| **Doble conteo en presupuestos** (introducido 2026-09-04): presupuestar padre e hija cuenta los mismos pesos dos veces | I2. El presupuesto del grupo pasa a ser derivado |
| **El cubo mezclado**: un padre con movimientos propios más hijas obliga a una línea «Sin desglosar» | Desaparece: el total del grupo **es** la suma de sus hojas |
| **`/summary` pierde el detalle**: aplasta todo al padre y no hay forma de ver el desglose | Fase 3, jerarquía anidada en la respuesta |
| **51 transacciones sin categorizar invisibles** en el Resumen | Fase 3 (fila visible) + Fase 4 (flujo para resolverlas) |
| **El selector de categoría no escala** a 94 entradas | Fase 2 |

---

# Orden de ejecución

```
Fase 0  Fundación          ← bloquea todo lo demás
   │
Fase 1  Taxonomía + selector
   │
   ├── Fase 2  Selector en transacciones ──┐
   │                                        ├── Fase 4  Higiene
   └── Fase 3  Resumen con desglose ───────┘
                                            │
                                       Fase 5  Primer arranque
```

Las fases 2 y 3 son independientes entre sí y pueden ir en paralelo. La 4 reutiliza el selector de la 2. La 5 puede adelantarse si hace falta enseñar el producto.
