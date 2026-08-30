import csv
import datetime as dt
import io
import json
import re
from difflib import SequenceMatcher
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlmodel import Session, select

from app.core.security import get_current_user_with_subscription_check
from app.database import engine
from app.models.category import Category
from app.models.category_rule import CategoryRule
from app.models.enums import TransactionType
from app.models.import_profile import ImportProfile
from app.models.saving_account import SavingAccount, SavingAccountStatus
from app.models.transaction import Transaction
from app.schemas.csv_import import (
    ColumnMapping,
    ImportConfirmRequest,
    ImportConfirmResult,
    ImportInspectResult,
    ImportProfileCreate,
    ImportProfileRead,
    ImportReviewResult,
    ImportRowPreview,
)
from app.utils.category_helpers import get_or_create_uncategorized_category
from app.utils.category_rule_helpers import suggest_category

transactions_import_router = APIRouter(prefix="/transactions/import", tags=["csv-import"])
import_profiles_router = APIRouter(prefix="/import-profiles", tags=["csv-import"])

MAX_ROWS = 1000
DUPLICATE_WINDOW_DAYS = 3
DUPLICATE_DESCRIPTION_RATIO = 0.6
SAMPLE_ROW_COUNT = 6


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            return raw.decode("latin-1")
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=400,
                detail="No se pudo leer el archivo: codificación no reconocida.",
            )


def _parse_csv(text: str) -> List[List[str]]:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    return [row for row in reader if any(cell.strip() for cell in row)]


def _parse_amount(raw: str) -> float:
    s = raw.strip()
    if not s:
        raise ValueError("Monto vacío")
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    if s.startswith("-"):
        neg = True
        s = s[1:]
    elif s.startswith("+"):
        s = s[1:]
    s = re.sub(r"[^\d.,]", "", s)
    if not s:
        raise ValueError("Monto sin dígitos")

    last_dot = s.rfind(".")
    last_comma = s.rfind(",")
    if last_dot != -1 and last_comma != -1:
        # El separador que aparece de último es el decimal (150.000,50 vs 1,234.56)
        if last_comma > last_dot:
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif last_comma != -1:
        # Solo comas: decimal si hay una sola coma con <=2 dígitos después, si no son miles.
        if s.count(",") == 1 and len(s) - last_comma - 1 <= 2:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")

    val = float(s)
    return -val if neg else val


def _is_duplicate(
    existing: List[Transaction], parsed_date: dt.date, amount: float, description: str
) -> bool:
    desc_b = description.lower()
    for tx in existing:
        if abs((tx.date.date() - parsed_date).days) > DUPLICATE_WINDOW_DAYS:
            continue
        if abs(tx.amount - amount) > 0.01:
            continue
        desc_a = (tx.description or "").lower()
        if SequenceMatcher(None, desc_a, desc_b).ratio() >= DUPLICATE_DESCRIPTION_RATIO:
            return True
    return False


@transactions_import_router.post("/preview", response_model=None)
async def preview_import(
    file: UploadFile = File(...),
    saving_account_id: int = Form(...),
    column_mapping: Optional[str] = Form(None),
    date_format: Optional[str] = Form(None),
    has_header: bool = Form(True),
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    with Session(engine) as session:
        account = session.exec(
            select(SavingAccount).where(
                SavingAccount.id == saving_account_id,
                SavingAccount.user_id == user_id,
            )
        ).first()
        if not account:
            raise HTTPException(status_code=400, detail="Cuenta de ahorro inválida.")
        if account.status != SavingAccountStatus.active:
            raise HTTPException(status_code=400, detail="La cuenta no está activa.")

        raw = await file.read()
        text = _decode(raw)
        try:
            all_rows = _parse_csv(text)
        except csv.Error:
            raise HTTPException(status_code=400, detail="No se pudo interpretar el archivo como CSV.")

        if not all_rows:
            raise HTTPException(status_code=400, detail="El archivo está vacío.")

        # Sin mapeo todavía: solo devolvemos una muestra para que el usuario
        # indique qué columna es cuál (paso 1 del flujo, en el frontend).
        if not column_mapping:
            saved = session.exec(
                select(ImportProfile).where(
                    ImportProfile.user_id == user_id,
                    ImportProfile.saving_account_id == saving_account_id,
                )
            ).first()
            return ImportInspectResult(
                sample_rows=all_rows[:SAMPLE_ROW_COUNT],
                column_count=max(len(r) for r in all_rows[:SAMPLE_ROW_COUNT]),
                saved_profile=saved,
            )

        if not date_format:
            raise HTTPException(status_code=400, detail="Falta el formato de fecha.")
        try:
            mapping = ColumnMapping(**json.loads(column_mapping))
        except (json.JSONDecodeError, ValueError):
            raise HTTPException(status_code=400, detail="Mapeo de columnas inválido.")

        data_rows = all_rows[1:] if has_header else all_rows
        if len(data_rows) > MAX_ROWS:
            raise HTTPException(
                status_code=400,
                detail=f"El archivo tiene {len(data_rows)} filas; el máximo por importación es {MAX_ROWS}.",
            )

        uncategorized = get_or_create_uncategorized_category(session, user_id)
        existing = session.exec(
            select(Transaction).where(
                Transaction.user_id == user_id,
                Transaction.saving_account_id == saving_account_id,
                Transaction.is_cancelled == False,  # noqa: E712
            )
        ).all()
        active_rules = session.exec(
            select(CategoryRule).where(
                CategoryRule.user_id == user_id, CategoryRule.is_active == True  # noqa: E712
            )
        ).all()
        categories_by_id = {
            c.id: c
            for c in session.exec(select(Category).where(Category.user_id == user_id)).all()
        }

        max_idx = max(mapping.date, mapping.description, mapping.amount)
        rows: List[ImportRowPreview] = []
        duplicate_count = 0
        error_count = 0

        for idx, row in enumerate(data_rows):
            if len(row) <= max_idx:
                rows.append(
                    ImportRowPreview(
                        row_index=idx,
                        description=" | ".join(row),
                        category_id=uncategorized.id,
                        category_name=uncategorized.name,
                        is_duplicate=False,
                        include=False,
                        error="Fila con menos columnas de las esperadas.",
                    )
                )
                error_count += 1
                continue

            raw_date = row[mapping.date].strip()
            raw_desc = row[mapping.description].strip()
            raw_amount = row[mapping.amount].strip()

            errors = []
            parsed_date: Optional[dt.date] = None
            try:
                parsed_date = dt.datetime.strptime(raw_date, date_format).date()
            except ValueError:
                errors.append("Fecha inválida")

            amount_val: Optional[float] = None
            tx_type: Optional[str] = None
            try:
                amount_val = _parse_amount(raw_amount)
                tx_type = "expense" if amount_val < 0 else "income"
                amount_val = abs(amount_val)
                if amount_val == 0:
                    errors.append("Monto en cero")
            except ValueError:
                errors.append("Monto inválido")

            is_dup = False
            if parsed_date is not None and amount_val is not None and not errors:
                is_dup = _is_duplicate(existing, parsed_date, amount_val, raw_desc)
                if is_dup:
                    duplicate_count += 1

            if errors:
                error_count += 1

            suggested_id = suggest_category(raw_desc, active_rules)
            suggested_category = categories_by_id.get(suggested_id) if suggested_id else None
            if suggested_category:
                category_id, category_name = suggested_category.id, suggested_category.name
            else:
                category_id, category_name = uncategorized.id, uncategorized.name

            rows.append(
                ImportRowPreview(
                    row_index=idx,
                    date=parsed_date.isoformat() if parsed_date else None,
                    description=raw_desc,
                    amount=amount_val,
                    type=tx_type,
                    category_id=category_id,
                    category_name=category_name,
                    is_duplicate=is_dup,
                    include=not errors and not is_dup,
                    error="; ".join(errors) if errors else None,
                )
            )

        return ImportReviewResult(
            rows=rows,
            total_rows=len(rows),
            duplicate_count=duplicate_count,
            error_count=error_count,
        )


@transactions_import_router.post("/confirm", response_model=ImportConfirmResult)
def confirm_import(
    data: ImportConfirmRequest,
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    if len(data.rows) > MAX_ROWS:
        raise HTTPException(
            status_code=400,
            detail=f"No se pueden importar más de {MAX_ROWS} movimientos a la vez.",
        )

    with Session(engine) as session:
        account = session.exec(
            select(SavingAccount).where(
                SavingAccount.id == data.saving_account_id,
                SavingAccount.user_id == user_id,
            )
        ).first()
        if not account:
            raise HTTPException(status_code=400, detail="Cuenta de ahorro inválida.")
        if account.status != SavingAccountStatus.active:
            raise HTTPException(status_code=400, detail="La cuenta no está activa.")

        created = 0
        skipped = 0
        net_delta = 0.0
        to_add: List[Transaction] = []

        for row in data.rows:
            if row.amount <= 0:
                skipped += 1
                continue
            category = session.exec(
                select(Category).where(
                    Category.id == row.category_id,
                    Category.user_id == user_id,
                    Category.is_active == True,  # noqa: E712
                )
            ).first()
            if not category:
                skipped += 1
                continue
            try:
                parsed_date = dt.datetime.fromisoformat(row.date)
            except ValueError:
                skipped += 1
                continue

            tx = Transaction(
                user_id=user_id,
                amount=row.amount,
                type=TransactionType(row.type),
                saving_account_id=data.saving_account_id,
                category_id=row.category_id,
                description=row.description or None,
                date=parsed_date,
            )
            to_add.append(tx)
            net_delta += row.amount if row.type == "income" else -row.amount
            created += 1

        # A diferencia de POST /transactions, una importación no bloquea por
        # fondos insuficientes: son movimientos históricos que ya ocurrieron
        # en el banco, el saldo actual de la cuenta simplemente se ajusta por
        # el neto -- no es una decisión de gasto nueva que pueda rechazarse.
        account.balance += net_delta
        session.add(account)
        for tx in to_add:
            session.add(tx)
        session.commit()

        return ImportConfirmResult(created=created, skipped=skipped)


@import_profiles_router.post("", response_model=ImportProfileRead)
@import_profiles_router.post("/", response_model=ImportProfileRead)
def upsert_import_profile(
    data: ImportProfileCreate,
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    with Session(engine) as session:
        account = session.exec(
            select(SavingAccount).where(
                SavingAccount.id == data.saving_account_id,
                SavingAccount.user_id == user_id,
            )
        ).first()
        if not account:
            raise HTTPException(status_code=400, detail="Cuenta de ahorro inválida.")

        existing = session.exec(
            select(ImportProfile).where(
                ImportProfile.user_id == user_id,
                ImportProfile.saving_account_id == data.saving_account_id,
            )
        ).first()
        if existing:
            existing.column_mapping = data.column_mapping.model_dump()
            existing.date_format = data.date_format
            existing.has_header = data.has_header
            existing.updated_at = dt.datetime.utcnow()
            profile = existing
        else:
            profile = ImportProfile(
                user_id=user_id,
                saving_account_id=data.saving_account_id,
                column_mapping=data.column_mapping.model_dump(),
                date_format=data.date_format,
                has_header=data.has_header,
            )
        session.add(profile)
        session.commit()
        session.refresh(profile)
        return profile


@import_profiles_router.get("", response_model=List[ImportProfileRead])
@import_profiles_router.get("/", response_model=List[ImportProfileRead])
def list_import_profiles(
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    with Session(engine) as session:
        return session.exec(
            select(ImportProfile).where(ImportProfile.user_id == user_id)
        ).all()
