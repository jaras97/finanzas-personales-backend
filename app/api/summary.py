from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select
import calendar
from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo
from uuid import UUID
from typing import Dict, List, Optional
from sqlalchemy.orm import joinedload
from sqlalchemy import or_, not_
from collections import defaultdict

# Línea sintética para lo que no tiene categoría. Id 0 porque ninguna fila
# real lo usa, y el frontend necesita una clave estable para pintarla.
SIN_CATEGORIA_ID = 0

from app.database import engine
from app.models.transaction import Transaction
from app.models.category import Category
from app.models.enums import TransactionType
from app.schemas.summary import SummaryResponse, CategorySummary, DailySummary
from app.models.saving_account import SavingAccount
from app.models.debt import Debt
from app.core.security import get_current_user_with_subscription_check
from app.utils.currency_helpers import get_user_currencies

router = APIRouter(prefix="/summary", tags=["summary"])


def _utc_bounds_for_local_day(d: date, tz: str):
    """Devuelve (start_utc, end_utc) para el día local `d` en tz IANA."""
    z = ZoneInfo(tz)
    start_local = datetime.combine(d, time.min).replace(tzinfo=z)
    end_local = datetime.combine(d, time.max).replace(tzinfo=z)
    # guardamos como naive UTC para comparar con columnas UTC/naive
    start_utc = start_local.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = end_local.astimezone(timezone.utc).replace(tzinfo=None)
    return start_utc, end_utc


def _to_local_day(dt: datetime, tz: str) -> date:
    """Convierte un datetime UTC (naive o tz-aware) al día local en tz IANA."""
    z = ZoneInfo(tz)
    # trata dt como UTC si viene naive (común cuando se guarda con datetime.utcnow())
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(z).date()


def _cargar_transacciones(session, user_id, currency, start_utc, end_utc):
    """Movimientos de una moneda en un rango: cuentas + compras con tarjeta.

    Extraído para poder pedir también el período anterior sin duplicar los
    filtros — que son delicados: excluyen transferencias, rendimientos y pagos
    de deuda, y si las dos consultas divergieran la variación mentiría.
    """
    query_saving = (
        select(Transaction)
        .join(SavingAccount, Transaction.saving_account_id == SavingAccount.id)
        .where(Transaction.user_id == user_id)
        .where(Transaction.date >= start_utc)
        .where(Transaction.date <= end_utc)
        .where(Transaction.is_cancelled == False)  # noqa: E712
        .where(Transaction.reversed_transaction_id.is_(None))
        .where(SavingAccount.currency == currency)
        .where(
            or_(
                Transaction.source_type.is_(None),
                not_(Transaction.source_type.in_(
                    ["transfer", "investment_yield", "debt_payment"]
                )),
            )
        )
        .options(joinedload(Transaction.category).joinedload(Category.parent))
    )
    query_credit_card = (
        select(Transaction)
        .join(Debt, Transaction.debt_id == Debt.id)
        .where(Transaction.user_id == user_id)
        .where(Transaction.date >= start_utc)
        .where(Transaction.date <= end_utc)
        .where(Transaction.is_cancelled == False)  # noqa: E712
        .where(Debt.currency == currency)
        .where(Transaction.source_type == "credit_card_purchase")
        .options(joinedload(Transaction.category).joinedload(Category.parent))
    )
    return list(session.exec(query_saving).all()) + list(session.exec(query_credit_card).all())


def _totales_por_categoria(transacciones, tipo) -> dict:
    """Total por categoría de reporte, con la misma regla de agrupación que
    `_desglose`: la hoja suma a su grupo salvo bajo el grupo Sistema."""
    from app.constants.categories import SystemCategoryKey

    totales: dict = defaultdict(float)
    for tx in transacciones:
        if tx.type != tipo:
            continue
        cat = tx.category
        if cat is None:
            totales[SIN_CATEGORIA_ID] += tx.amount
            continue
        padre = cat.parent if cat.parent_id else None
        oculto = padre is not None and padre.system_key == SystemCategoryKey.SYSTEM_GROUP.value
        if padre is None or oculto:
            totales[cat.id] += tx.amount
        else:
            totales[padre.id] += tx.amount
            totales[cat.id] += tx.amount   # también por hoja, para su propia variación
    return totales



def _periodo_anterior(inicio: date, fin: date) -> tuple[date, date]:
    """Rango con el que comparar.

    Si el rango es exactamente un mes de calendario, se compara con el mes de
    calendario anterior — que es lo que la gente quiere decir con «vs. agosto».
    En cualquier otro caso, con el rango de la misma duración inmediatamente
    anterior; comparar 15 días contra un mes daría una variación falsa.
    """
    ultimo_dia = calendar.monthrange(inicio.year, inicio.month)[1]
    es_mes_completo = inicio.day == 1 and fin.day == ultimo_dia and inicio.month == fin.month

    if es_mes_completo:
        fin_anterior = inicio - timedelta(days=1)
        return fin_anterior.replace(day=1), fin_anterior

    dias = (fin - inicio).days + 1
    return inicio - timedelta(days=dias), inicio - timedelta(days=1)


def _desglose(
    session: Session,
    transacciones,
    tipo: TransactionType,
    total: float,
    previos: dict,
) -> List[CategorySummary]:
    """Agrupa por GRUPO, con las hojas dentro.

    Una hoja suma a su grupo, salvo las del grupo Sistema: ese está oculto,
    así que «Sin categorizar» se muestra por sí misma en vez de bajo un
    «Sistema» que el usuario nunca ha visto.

    Las transacciones sin categoría se agrupan en una línea sintética con
    id 0. Esconderlas convertiría el desglose en una media verdad.
    """
    from app.constants.categories import SystemCategoryKey

    grupos: dict = {}

    def _bucket(gid, nombre, color, icon):
        return grupos.setdefault(
            gid,
            {"id": gid, "nombre": nombre, "color": color, "icon": icon,
             "total": 0.0, "hojas": {}},
        )

    for tx in transacciones:
        if tx.type != tipo:
            continue
        cat = tx.category
        if cat is None:
            _bucket(SIN_CATEGORIA_ID, "Sin categorizar", "slate", None)["total"] += tx.amount
            continue

        padre = cat.parent if cat.parent_id else None
        oculto = padre is not None and padre.system_key == SystemCategoryKey.SYSTEM_GROUP.value

        if padre is None or oculto:
            # Se reporta como si fuera de primer nivel.
            g = _bucket(cat.id, cat.name, cat.color, cat.icon)
            g["total"] += tx.amount
        else:
            g = _bucket(padre.id, padre.name, padre.color, padre.icon)
            g["total"] += tx.amount
            hoja = g["hojas"].setdefault(
                cat.id, {"id": cat.id, "nombre": cat.name, "color": cat.color, "total": 0.0}
            )
            hoja["total"] += tx.amount

    def _delta(actual: float, previo: float):
        if previo <= 0:
            return None
        return round((actual - previo) / previo * 100, 1)

    salida = []
    for g in grupos.values():
        previo = previos.get(g["id"], 0.0)
        hijas = [
            CategorySummary(
                category_id=h["id"], category_name=h["nombre"], total=h["total"],
                percentage=(h["total"] / g["total"] * 100) if g["total"] > 0 else 0,
                color=h["color"], previous_total=previos.get(h["id"], 0.0),
                delta_percentage=_delta(h["total"], previos.get(h["id"], 0.0)),
            )
            for h in sorted(g["hojas"].values(), key=lambda x: -x["total"])
        ]
        salida.append(
            CategorySummary(
                category_id=g["id"], category_name=g["nombre"], total=g["total"],
                percentage=(g["total"] / total * 100) if total > 0 else 0,
                color=g["color"], icon=g["icon"],
                previous_total=previo, delta_percentage=_delta(g["total"], previo),
                children=hijas,
            )
        )
    salida.sort(key=lambda c: c.total, reverse=True)
    return salida


@router.get("", response_model=Dict[str, SummaryResponse])
@router.get("/", response_model=Dict[str, SummaryResponse])
def get_summary(
    user_id: UUID = Depends(get_current_user_with_subscription_check),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    tz: Optional[str] = Query(None, description="Zona horaria IANA del navegador, ej. America/Bogota"),
):
    tz = tz or "UTC"

    with Session(engine) as session:
        today_local = _to_local_day(datetime.utcnow(), tz)
        if not start_date:
            start_date = today_local.replace(day=1)
        if not end_date:
            end_date = today_local

        start_utc, _ = _utc_bounds_for_local_day(start_date, tz)
        _, end_utc = _utc_bounds_for_local_day(end_date, tz)

        result: Dict[str, SummaryResponse] = {}

        for currency in get_user_currencies(session, user_id):
            transactions = _cargar_transacciones(
                session, user_id, currency, start_utc, end_utc
            )

            total_income = 0.0
            total_expense = 0.0
            daily_summary = defaultdict(lambda: {"income": 0.0, "expense": 0.0})

            for tx in transactions:
                # Día local según tz del navegador
                tx_local_day = _to_local_day(tx.date, tz)
                if tx.type == TransactionType.income:
                    total_income += tx.amount
                    daily_summary[tx_local_day]["income"] += tx.amount
                elif tx.type == TransactionType.expense:
                    total_expense += tx.amount
                    daily_summary[tx_local_day]["expense"] += tx.amount

            balance = total_income - total_expense

            # Totales del período anterior, para la variación. Se cargan aparte
            # y solo se usan sus sumas: no hace falta recorrer nada más.
            prev_ini, prev_fin = _periodo_anterior(start_date, end_date)
            prev_start_utc, _ = _utc_bounds_for_local_day(prev_ini, tz)
            _, prev_end_utc = _utc_bounds_for_local_day(prev_fin, tz)
            transacciones_previas = _cargar_transacciones(
                session, user_id, currency, prev_start_utc, prev_end_utc
            )
            previos_gasto = _totales_por_categoria(transacciones_previas, TransactionType.expense)
            previos_ingreso = _totales_por_categoria(transacciones_previas, TransactionType.income)

            expense_summary = _desglose(
                session, transactions, TransactionType.expense, total_expense, previos_gasto
            )
            income_summary = _desglose(
                session, transactions, TransactionType.income, total_income, previos_ingreso
            )

            daily_summaries = [
                DailySummary(
                    date=d,
                    total_income=v["income"],
                    total_expense=v["expense"]
                )
                for d, v in sorted(daily_summary.items())
            ]

            top_expense_category = expense_summary[0] if expense_summary else None
            top_income_category = income_summary[0] if income_summary else None

            top_expense_day = max(daily_summaries, key=lambda x: x.total_expense, default=None)
            top_income_day = max(daily_summaries, key=lambda x: x.total_income, default=None)

            overspending_alert = total_expense > total_income

            result[currency] = SummaryResponse(
                total_income=total_income,
                total_expense=total_expense,
                balance=balance,
                expense_by_category=expense_summary,
                income_by_category=income_summary,
                daily_evolution=daily_summaries,
                top_expense_category=top_expense_category,
                top_income_category=top_income_category,
                top_expense_day=top_expense_day,
                top_income_day=top_income_day,
                overspending_alert=overspending_alert
            )

        return result
