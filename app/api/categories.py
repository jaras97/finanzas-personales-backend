# app/api/categories.py

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select, func

from app.database import engine
from app.models.category import Category, CategoryType
from app.models.transaction import Transaction
from app.schemas.category import (
    CategoryCreate, CategoryRead,
    TaxonomyRead, TaxonomyBlock, TaxonomyItem, TaxonomyApply, TaxonomyApplyResult,
)
from app.utils.default_categories import (
    DEFAULT_CATEGORIES, DEFAULT_SUBCATEGORIES, BLOCK_LABELS, _slug,
)
from app.core.security import get_current_user_with_subscription_check
from app.utils.category_rules import (
    crear_hoja_por_defecto, hojas_de, tiene_referencias, NOMBRE_HOJA_POR_DEFECTO,
)

def _validar_padre(
    session: Session,
    user_id: UUID,
    parent_id: Optional[int],
    tipo: CategoryType,
    *,
    hija_id: Optional[int] = None,
) -> Optional[Category]:
    """Comprueba que `parent_id` sea un padre válido y lo devuelve.

    Las cuatro reglas, y por qué cada una:

    - **Existe y es del usuario.** Sin esto, un id ajeno colgaría una categoría
      del árbol de otra persona.
    - **El padre no puede ser ya una subcategoría.** La jerarquía es de dos
      niveles a propósito (recomendación del PDF); permitir tres convertiría
      cada reporte en un recorrido de árbol.
    - **Mismo tipo.** Una subcategoría de egreso dentro de un padre de ingreso
      haría que los totales del padre mezclaran signos.
    - **No puede ser ella misma, ni una de sus propias hijas.** Es lo que
      evita un ciclo, que colgaría cualquier consulta recursiva.
    """
    if parent_id is None:
        return None

    padre = session.exec(
        select(Category).where(Category.id == parent_id, Category.user_id == user_id)
    ).first()
    if not padre:
        raise HTTPException(status_code=404, detail="La categoría padre no existe.")

    if hija_id is not None and padre.id == hija_id:
        raise HTTPException(
            status_code=400, detail="Una categoría no puede ser su propia subcategoría."
        )

    if padre.parent_id is not None:
        raise HTTPException(
            status_code=400,
            detail=f"«{padre.name}» ya es una subcategoría. Solo se admiten dos niveles.",
        )

    if hija_id is not None:
        tiene_hijas = session.exec(
            select(Category).where(Category.parent_id == hija_id)
        ).first()
        if tiene_hijas:
            raise HTTPException(
                status_code=400,
                detail="Esta categoría tiene subcategorías: no puede convertirse en una.",
            )

    # `both` (Transferencia y similares) convive con cualquiera; el resto debe
    # coincidir para que los totales del padre no mezclen ingresos con egresos.
    if CategoryType.both not in (padre.type, tipo) and padre.type != tipo:
        raise HTTPException(
            status_code=400,
            detail=f"«{padre.name}» es de tipo {padre.type.value} y esta categoría es de tipo {tipo.value}.",
        )

    return padre


def _con_padre(session: Session, categoria: Category) -> dict:
    """Serializa una categoría con el nombre del padre y su naturaleza.

    `is_group` y `default_leaf_id` viajan también acá (no solo en el listado)
    para que quien acaba de crear una categoría sepa de inmediato dónde puede
    registrar movimientos, sin tener que volver a pedir la lista.
    """
    datos = CategoryRead.model_validate(categoria).model_dump()
    datos["is_group"] = categoria.parent_id is None
    if categoria.parent_id:
        padre = session.get(Category, categoria.parent_id)
        datos["parent_name"] = padre.name if padre else None
    else:
        hijas = hojas_de(session, categoria.id)
        datos["default_leaf_id"] = hijas[0].id if len(hijas) == 1 else None
    return datos



router = APIRouter(prefix="/categories", tags=["categories"])

@router.post("", response_model=CategoryRead)
@router.post("/", response_model=CategoryRead)
def create_category(
    category_data: CategoryCreate,
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    """
    Crea categorías del usuario. Las categorías creadas por el usuario
    nunca son de sistema (is_system=False, system_key=None).
    """
    with Session(engine) as session:
        _validar_padre(session, user_id, category_data.parent_id, category_data.type)

        # La unicidad es POR PADRE, no global: el sentido de la jerarquía es
        # que "Transporte › Gasolina" y "Viajes › Gasolina" puedan convivir.
        exists = session.exec(
            select(Category).where(
                Category.name == category_data.name,
                Category.user_id == user_id,
                Category.is_active == True,
                Category.parent_id.is_(None)
                if category_data.parent_id is None
                else Category.parent_id == category_data.parent_id,
            )
        ).first()
        if exists:
            raise HTTPException(
                status_code=400,
                detail="Ya existe una categoría con ese nombre en ese nivel.",
            )

        category = Category(
            **category_data.model_dump(),
            user_id=user_id,
            is_system=False,   # 👈 garantizamos que no sea de sistema
            system_key=None,   # 👈 sin clave de sistema
        )
        session.add(category)
        session.flush()

        if category.parent_id is None:
            # Nace como grupo, y un grupo sin hojas no sirve para nada (I3):
            # se le crea "General". La interfaz colapsa los grupos de una sola
            # hoja, así que quien solo quería "Mascotas" ve una línea.
            crear_hoja_por_defecto(session, category)
        else:
            # Al agregar una hoja de verdad, la "General" que nadie usó sobra:
            # dejarla convertiría cada grupo en "General + lo que importa".
            for hermana in hojas_de(session, category.parent_id):
                if (
                    hermana.id != category.id
                    and hermana.name == NOMBRE_HOJA_POR_DEFECTO
                    and not tiene_referencias(session, hermana.id)
                ):
                    session.delete(hermana)

        session.commit()
        session.refresh(category)
        return _con_padre(session, category)

@router.get("", response_model=list[CategoryRead])
@router.get("/", response_model=list[CategoryRead])
def list_categories(
    user_id: UUID = Depends(get_current_user_with_subscription_check),
    type: Optional[CategoryType] = Query(None),
    status: Optional[str] = Query("active"),  # "active", "inactive", "all"
):
    """
    Lista categorías del usuario, con filtros por tipo y estado.
    """
    with Session(engine) as session:
        query = select(Category).where(Category.user_id == user_id)

        if type:
            query = query.where((Category.type == type) | (Category.type == CategoryType.both))

        if status == "active":
            query = query.where(Category.is_active == True)
        elif status == "inactive":
            query = query.where(Category.is_active == False)
        # if "all": sin filtro extra

        categories = session.exec(query).all()

        # Nombre del padre resuelto en UNA consulta, no una por fila: la lista
        # se pide en cada formulario que tenga selector de categoría.
        nombres = {
            c.id: c.name
            for c in session.exec(
                select(Category).where(Category.user_id == user_id)
            ).all()
        }
        # Hojas por grupo, en una consulta, para poder resolver default_leaf_id
        # sin una query por fila.
        todas = session.exec(select(Category).where(Category.user_id == user_id)).all()
        hijas_por_grupo: dict[int, list[Category]] = {}
        for c in todas:
            if c.parent_id and c.is_active:
                hijas_por_grupo.setdefault(c.parent_id, []).append(c)

        salida = []
        for c in categories:
            datos = CategoryRead.model_validate(c).model_dump()
            datos["parent_name"] = nombres.get(c.parent_id) if c.parent_id else None
            datos["is_group"] = c.parent_id is None
            hijas = hijas_por_grupo.get(c.id, [])
            # Solo tiene sentido cuando hay UNA hoja: con varias, quién recibe
            # el movimiento es una decisión del usuario, no un valor por defecto.
            datos["default_leaf_id"] = hijas[0].id if len(hijas) == 1 else None
            salida.append(datos)

        # Padres antes que hijas, y cada hija junto a su padre: así cualquier
        # selector que solo itere la lista ya sale agrupado sin ordenar nada.
        salida.sort(key=lambda d: (d["parent_name"] or d["name"], d["parent_id"] is not None, d["name"]))
        return salida


# ===========================================================================
# Selector de taxonomía
# ===========================================================================
# Reemplaza al antiguo POST /categories/suggested, que creaba 12 categorías de
# un clic sin avisar ni mostrar qué iba a pasar. Acá el usuario ve el catálogo
# completo con lo que ya tiene marcado, ajusta a su gusto, y nada se escribe
# hasta que envía la selección.

def _indice_del_usuario(session: Session, user_id: UUID) -> dict:
    """Mapa {(slug_padre, slug_nombre): Category} de todo lo que tiene.

    La clave se normaliza (sin tildes ni mayúsculas) porque en producción ya
    conviven "Alimentacion" y "Alimentación": sin eso el selector le ofrecería
    a esa gente crear de nuevo lo que ya tiene.
    """
    categorias = session.exec(
        select(Category).where(Category.user_id == user_id)
    ).all()
    por_id = {c.id: c for c in categorias}

    indice = {}
    for c in categorias:
        padre = por_id.get(c.parent_id) if c.parent_id else None
        indice[(_slug(padre.name) if padre else None, _slug(c.name))] = c
    return indice


def _conteo_transacciones(session: Session, user_id: UUID) -> dict:
    """Transacciones por categoría, en UNA consulta."""
    filas = session.exec(
        select(Transaction.category_id, func.count(Transaction.id))
        .where(Transaction.user_id == user_id)
        .group_by(Transaction.category_id)
    ).all()
    return {cat_id: n for cat_id, n in filas if cat_id is not None}


def _construir_item(entrada, categoria, n_tx: int) -> TaxonomyItem:
    if categoria is None:
        estado = "absent"
    elif categoria.is_active:
        estado = "present"
    else:
        estado = "inactive"

    bloqueada = bool(categoria and categoria.is_active and n_tx > 0)
    return TaxonomyItem(
        key=entrada.key,
        name=entrada.name,
        type=entrada.type,
        color=entrada.color or None,
        icon=entrada.icon or None,
        core=entrada.core,
        state=estado,
        category_id=categoria.id if categoria else None,
        transactions=n_tx,
        locked=bloqueada,
        locked_reason=(
            f"Tiene {n_tx} {'movimiento' if n_tx == 1 else 'movimientos'}: quitarla dejaría huecos en tus reportes."
            if bloqueada else None
        ),
    )


@router.get("/taxonomy", response_model=TaxonomyRead)
def get_taxonomy(
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    """Catálogo completo con el estado de cada entrada en esta cuenta."""
    with Session(engine) as session:
        indice = _indice_del_usuario(session, user_id)
        conteos = _conteo_transacciones(session, user_id)

        hijas_por_padre = {}
        for e in DEFAULT_SUBCATEGORIES:
            hijas_por_padre.setdefault(e.parent, []).append(e)

        bloques = []
        for block_id, label in BLOCK_LABELS:
            items = []
            for padre in DEFAULT_CATEGORIES:
                if padre.block != block_id:
                    continue
                cat_padre = indice.get((None, _slug(padre.name)))
                # Un grupo no tiene movimientos propios (I1): los suyos son los
                # de sus hojas. Sin esto el selector dejaría desmarcar un grupo
                # que en realidad no se puede quitar, y el usuario solo se
                # enteraría al pulsar Aplicar.
                tx_padre = (
                    sum(conteos.get(h.id, 0) for h in hojas_de(session, cat_padre.id))
                    if cat_padre else 0
                )
                item = _construir_item(padre, cat_padre, tx_padre)
                for hija in hijas_por_padre.get(padre.name, []):
                    cat_hija = indice.get((_slug(padre.name), _slug(hija.name)))
                    item.children.append(
                        _construir_item(
                            hija, cat_hija, conteos.get(cat_hija.id, 0) if cat_hija else 0
                        )
                    )
                items.append(item)
            if items:
                bloques.append(TaxonomyBlock(id=block_id, label=label, items=items))

        return TaxonomyRead(blocks=bloques)


@router.put("/taxonomy", response_model=TaxonomyApplyResult)
def apply_taxonomy(
    payload: TaxonomyApply,
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    """Deja activas exactamente las entradas seleccionadas.

    Un solo commit: o se aplica el diff completo o no se aplica nada. Sin eso,
    un fallo a mitad dejaría al usuario con la mitad de sus categorías creadas
    y sin forma de saber cuáles.

    Solo toca entradas de la taxonomía. Las categorías propias del usuario
    ("Lotes mutata don Gildardo") y las de sistema no aparecen acá y no se
    ven afectadas por lo que se envíe.
    """
    seleccionadas = set(payload.selected)

    with Session(engine) as session:
        indice = _indice_del_usuario(session, user_id)
        conteos = _conteo_transacciones(session, user_id)

        creadas = reactivadas = desactivadas = 0
        omitidas: list[str] = []

        def _buscar(entrada):
            clave = (_slug(entrada.parent) if entrada.parent else None, _slug(entrada.name))
            return indice.get(clave)

        # 1) Altas y reactivaciones. Los padres primero: una hija necesita el
        #    id de su padre, que puede estar creándose en esta misma pasada.
        creados_ahora: dict[str, Category] = {}
        for entrada in DEFAULT_CATEGORIES + DEFAULT_SUBCATEGORIES:
            if entrada.key not in seleccionadas:
                continue
            existente = _buscar(entrada)
            if existente is None:
                parent_id = None
                if entrada.parent:
                    padre = creados_ahora.get(entrada.parent) or indice.get(
                        (None, _slug(entrada.parent))
                    )
                    if padre is None or not padre.is_active:
                        # Sin padre activo la hija no tiene dónde colgarse.
                        omitidas.append(
                            f"{entrada.name}: requiere que «{entrada.parent}» esté seleccionada."
                        )
                        continue
                    parent_id = padre.id
                nueva = Category(
                    name=entrada.name,
                    type=entrada.type,
                    user_id=user_id,
                    color=entrada.color or None,
                    icon=entrada.icon or None,
                    parent_id=parent_id,
                    is_system=False,
                )
                session.add(nueva)
                session.flush()  # necesitamos su id para las hijas de esta misma pasada
                if parent_id is None:
                    # Nace como grupo; sin una hoja no recibiría nada (I3).
                    crear_hoja_por_defecto(session, nueva)
                    session.flush()
                creados_ahora[entrada.name] = nueva
                creadas += 1
            elif not existente.is_active:
                existente.is_active = True
                session.add(existente)
                creados_ahora[entrada.name] = existente
                reactivadas += 1
            else:
                creados_ahora[entrada.name] = existente

        # 1b) Las hojas de verdad hacen sobrar la "General" que nadie tocó.
        for entrada in DEFAULT_CATEGORIES:
            if entrada.key not in seleccionadas:
                continue
            grupo = creados_ahora.get(entrada.name) or indice.get((None, _slug(entrada.name)))
            if not grupo:
                continue
            hojas = hojas_de(session, grupo.id)
            if len(hojas) > 1:
                for h in hojas:
                    if h.name == NOMBRE_HOJA_POR_DEFECTO and not tiene_referencias(session, h.id):
                        session.delete(h)
        session.flush()

        # 2) Bajas. Las hojas antes que los padres: al quitar un grupo se
        #    arrastran sus hojas, que es lo que el usuario quiere decir.
        for entrada in DEFAULT_SUBCATEGORIES + DEFAULT_CATEGORIES:
            if entrada.key in seleccionadas:
                continue
            existente = _buscar(entrada)
            if existente is None or not existente.is_active or existente.is_system:
                continue

            n_tx = conteos.get(existente.id, 0)
            if n_tx > 0:
                omitidas.append(
                    f"{entrada.name}: tiene {n_tx} {'movimiento' if n_tx == 1 else 'movimientos'}."
                )
                continue

            # Quitar un grupo arrastra a sus hojas: para el usuario es UNA
            # categoría, no un árbol que tenga que desmontar a mano.
            hijas_vivas = hojas_de(session, existente.id)
            con_movimientos = [h for h in hijas_vivas if conteos.get(h.id, 0) > 0]
            if con_movimientos:
                omitidas.append(
                    f"{entrada.name}: {con_movimientos[0].name} tiene movimientos."
                )
                continue
            for h in hijas_vivas:
                h.is_active = False
                session.add(h)

            existente.is_active = False
            session.add(existente)
            desactivadas += 1

        session.commit()

        return TaxonomyApplyResult(
            created=creadas,
            reactivated=reactivadas,
            deactivated=desactivadas,
            skipped=omitidas,
        )


# NOTA DE ORDEN: los endpoints de /taxonomy tienen que declararse ANTES que
# cualquier ruta `/{category_id}`. FastAPI resuelve por orden de declaración,
# así que con PUT /{category_id} arriba, un PUT a /categories/taxonomy se
# interpreta como "category_id = taxonomy" y muere en un 422. Es exactamente
# lo que dejó inalcanzable a /subscriptions/admin/me durante meses.
@router.put("/{category_id}", response_model=CategoryRead)
def update_category(
    category_id: int,
    category_data: CategoryCreate,
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    """
    Actualiza nombre/tipo de una categoría.
    - Si es de sistema: solo permite renombrar (bloquea cambio de tipo).
    - Si no es de sistema: permite cambiar nombre y tipo, pero no si ya tiene transacciones (para tipo).
    """
    with Session(engine) as session:
        category = session.exec(
            select(Category).where(Category.id == category_id, Category.user_id == user_id)
        ).first()

        if not category:
            raise HTTPException(status_code=404, detail="Categoría no encontrada")

        if category.is_system:
            # 🚫 No permitir cambiar el tipo de categorías del sistema
            if category_data.type != category.type:
                raise HTTPException(
                    status_code=400,
                    detail="No puedes cambiar el tipo de una categoría del sistema.",
                )
            # ✔️ Permitir renombrar
            category.name = category_data.name
        else:
            # Si quiere cambiar el tipo y ya tiene transacciones, bloquear
            if category.type != category_data.type:
                has_transactions = session.exec(
                    select(Transaction).where(
                        Transaction.category_id == category.id,
                        Transaction.user_id == user_id,
                    )
                ).first()
                if has_transactions:
                    raise HTTPException(
                        status_code=400,
                        detail="No puedes cambiar el tipo de esta categoría porque tiene transacciones asociadas.",
                    )
            category.name = category_data.name
            category.type = category_data.type

        # El color y el icono se pueden cambiar SIEMPRE, incluso en las de
        # sistema: son presentación, no comportamiento. Lo que se bloquea de
        # una categoría de sistema es su tipo, porque de él dependen las
        # transferencias y los pagos de deuda.
        category.color = category_data.color
        category.icon = category_data.icon

        # Mover de padre (o sacar al primer nivel). Las de sistema se quedan
        # siempre en el primer nivel: colgarlas de otra rompería los flujos que
        # las buscan por system_key.
        if not category.is_system:
            # Una hoja no puede subir a primer nivel: se convertiría en un grupo
            # sin hojas, que es exactamente lo que I3 prohíbe. Moverla a otro
            # grupo sí se permite.
            if category.parent_id is not None and category_data.parent_id is None:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"«{category.name}» es una subcategoría y necesita un grupo. "
                        "Muévela a otro grupo, o crea una categoría nueva."
                    ),
                )
            _validar_padre(
                session, user_id, category_data.parent_id, category.type,
                hija_id=category.id,
            )
            if category_data.parent_id is not None:
                category.parent_id = category_data.parent_id

        session.add(category)
        session.commit()
        session.refresh(category)
        return _con_padre(session, category)


@router.delete("/{category_id}")
def delete_category(
    category_id: int,
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    """
    Desactiva una categoría (soft delete).
    - 🚫 No permite desactivar categorías de sistema.
    - 🚫 No permite desactivar si tiene transacciones asociadas (para evitar agujeros en reportes).
    """
    with Session(engine) as session:
        category = session.exec(
            select(Category).where(
                Category.id == category_id,
                Category.user_id == user_id,
                Category.is_active == True,
            )
        ).first()

        if not category:
            raise HTTPException(status_code=404, detail="Categoría no encontrada")

        # 🚫 Bloquear desactivación de categorías de sistema
        if category.is_system:
            raise HTTPException(
                status_code=400,
                detail="No puedes desactivar una categoría del sistema.",
            )

        # 🚫 Bloquear si tiene transacciones asociadas
        tx_count = session.exec(
            select(func.count(Transaction.id)).where(Transaction.category_id == category_id)
        ).one()
        if tx_count and tx_count > 0:
            raise HTTPException(
                status_code=400,
                detail="No puedes desactivar una categoría con transacciones asociadas.",
            )

        # Soft delete
        if category.parent_id is None:
            # Retirar un GRUPO retira la categoría entera, así que arrastra a
            # sus hojas. Antes esto se bloqueaba, pero con el modelo grupo/hoja
            # obligaría al usuario a desactivar hoja por hoja algo que él
            # entiende como una sola categoría.
            hijas = hojas_de(session, category.id)
            con_movimientos = [h for h in hijas if tiene_referencias(session, h.id)]
            if con_movimientos:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"«{category.name}» no se puede quitar: "
                        f"{con_movimientos[0].name} tiene movimientos asociados."
                    ),
                )
            for h in hijas:
                h.is_active = False
                session.add(h)
        else:
            # Quitar la ÚLTIMA hoja dejaría un grupo inservible (I3). Se pide
            # retirar el grupo entero, que es lo que el usuario quiere decir.
            hermanas = [h for h in hojas_de(session, category.parent_id) if h.id != category.id]
            if not hermanas:
                grupo = session.get(Category, category.parent_id)
                if grupo and grupo.is_active:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"«{category.name}» es la única subcategoría de "
                            f"«{grupo.name}». Quita el grupo completo o crea otra antes."
                        ),
                    )

        category.is_active = False
        session.add(category)
        session.commit()
        return {"message": "Categoría desactivada correctamente"}


@router.put("/{category_id}/reactivate", response_model=CategoryRead)
def reactivate_category(
    category_id: int,
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    """
    Reactiva una categoría previamente desactivada.
    """
    with Session(engine) as session:
        category = session.exec(
            select(Category).where(
                Category.id == category_id,
                Category.user_id == user_id,
                Category.is_active == False,
            )
        ).first()

        if not category:
            raise HTTPException(status_code=404, detail="Categoría no encontrada o ya activa")

        category.is_active = True
        session.add(category)
        session.commit()
        session.refresh(category)
        return category

# El antiguo POST /categories/suggested se eliminó el 2026-09-08. Creaba doce
# categorías de un solo clic, sin avisar ni mostrar qué iba a pasar: reversible
# (baja lógica) pero a doce clics, y sobre todo decidía por el usuario. Lo
# reemplaza el selector de /categories/taxonomy, donde se ve el efecto exacto
# antes de escribir nada.
