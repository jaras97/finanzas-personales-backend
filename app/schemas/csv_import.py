from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel


class ColumnMapping(BaseModel):
    date: int
    description: int
    amount: int


class ImportProfileCreate(BaseModel):
    saving_account_id: int
    column_mapping: ColumnMapping
    date_format: str
    has_header: bool = True


class ImportProfileRead(BaseModel):
    id: int
    saving_account_id: int
    column_mapping: dict
    date_format: str
    has_header: bool

    class Config:
        from_attributes = True


class ImportInspectResult(BaseModel):
    mode: Literal["inspect"] = "inspect"
    sample_rows: List[List[str]]
    column_count: int
    saved_profile: Optional[ImportProfileRead] = None


class ImportRowPreview(BaseModel):
    row_index: int
    date: Optional[str] = None
    description: str
    amount: Optional[float] = None
    type: Optional[Literal["income", "expense"]] = None
    category_id: int
    category_name: str
    is_duplicate: bool
    include: bool
    error: Optional[str] = None


class ImportReviewResult(BaseModel):
    mode: Literal["review"] = "review"
    rows: List[ImportRowPreview]
    total_rows: int
    duplicate_count: int
    error_count: int


class ImportConfirmRow(BaseModel):
    date: str
    description: str
    amount: float
    type: Literal["income", "expense"]
    category_id: int


class ImportConfirmRequest(BaseModel):
    saving_account_id: int
    rows: List[ImportConfirmRow]


class ImportConfirmResult(BaseModel):
    created: int
    skipped: int
