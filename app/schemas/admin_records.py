"""Schemas del historial de suscripciones y las paramétricas de administración."""

from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# --- Planes (paramétrica) --------------------------------------------------
class PlanCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    duration_months: int = Field(ge=1, le=60)
    price: float = Field(default=0, ge=0)
    currency: str = Field(default="COP", min_length=3, max_length=3)
    is_active: bool = True


class PlanUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    duration_months: Optional[int] = Field(default=None, ge=1, le=60)
    price: Optional[float] = Field(default=None, ge=0)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    is_active: Optional[bool] = None


class PlanRead(BaseModel):
    id: int
    name: str
    duration_months: int
    price: float
    currency: str
    is_active: bool

    class Config:
        from_attributes = True


# --- Etiquetas (paramétrica) -----------------------------------------------
class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    color: str = Field(default="slate", max_length=20)


class TagRead(BaseModel):
    id: int
    name: str
    color: str

    class Config:
        from_attributes = True


class TagAssign(BaseModel):
    tag_ids: List[int]


# --- Historial -------------------------------------------------------------
class PeriodRead(BaseModel):
    id: int
    start_date: datetime
    end_date: datetime
    price: float
    currency: str
    origin: str
    note: Optional[str] = None
    plan_name: Optional[str] = None
    created_at: datetime
    created_by_email: Optional[str] = None


class EventRead(BaseModel):
    id: int
    action: str
    end_date_before: Optional[datetime] = None
    end_date_after: Optional[datetime] = None
    months: Optional[int] = None
    detail: Optional[str] = None
    created_at: datetime
    performed_by_email: Optional[str] = None


# --- Pagos -----------------------------------------------------------------
class PaymentCreate(BaseModel):
    amount: float = Field(gt=0)
    currency: str = Field(default="COP", min_length=3, max_length=3)
    method: Literal["cash", "transfer", "card", "other"] = "transfer"
    reference: Optional[str] = None
    note: Optional[str] = None
    paid_at: Optional[datetime] = None
    period_id: Optional[int] = None


class PaymentRead(BaseModel):
    id: int
    amount: float
    currency: str
    method: str
    reference: Optional[str] = None
    note: Optional[str] = None
    paid_at: datetime
    created_at: datetime
    created_by_email: Optional[str] = None

    class Config:
        from_attributes = True


# --- Ficha del usuario -----------------------------------------------------
class ProfileUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=120)
    phone: Optional[str] = Field(default=None, max_length=40)
    notes: Optional[str] = None


class UserMetrics(BaseModel):
    """Métricas de uso real. Distinguen a quien usa la app de quien se
    registró y nunca volvió, que es lo que no se podía saber antes."""

    last_login_at: Optional[datetime] = None
    transactions: int = 0
    accounts: int = 0
    debts: int = 0
    days_since_last_login: Optional[int] = None
    has_ever_logged_in: bool = False


class AdminUserDetail(BaseModel):
    id: UUID
    email: str
    role: str
    created_at: datetime
    subscription_status: str
    subscription_start: Optional[datetime] = None
    subscription_end: Optional[datetime] = None

    full_name: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    tags: List[TagRead] = []

    metrics: UserMetrics
    periods: List[PeriodRead] = []
    events: List[EventRead] = []
    payments: List[PaymentRead] = []
    total_paid: float = 0
    first_subscribed_at: Optional[datetime] = None
