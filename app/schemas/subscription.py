from pydantic import BaseModel, field_validator
from datetime import date, datetime
from typing import Optional
from uuid import UUID

class SubscriptionCreate(BaseModel):
    user_id: UUID
    start_date: date
    end_date: date
    is_active: bool = True

    @field_validator("end_date")
    @classmethod
    def end_date_after_start(cls, v, values):
        if "start_date" in values and v <= values["start_date"]:
            raise ValueError("La fecha de finalización debe ser posterior a la fecha de inicio.")
        return v

class SubscriptionRead(BaseModel):
    id: int
    user_id: UUID
    start_date: datetime  # ✅ Ahora datetime
    end_date: datetime    # ✅ Ahora datetime
    is_active: bool

    class Config:
        from_attributes = True

class SubscriptionUpdate(BaseModel):
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_active: Optional[bool] = None

    @field_validator("end_date")
    @classmethod
    def end_date_after_start(cls, v, values):
        if "start_date" in values and v and values["start_date"] and v <= values["start_date"]:
            raise ValueError("La fecha de finalización debe ser posterior a la fecha de inicio.")
        return v
    
class SubscriptionStatusRead(BaseModel):
    id: int
    user_id: UUID
    start_date: datetime
    end_date: datetime
    is_active: bool
    status: str