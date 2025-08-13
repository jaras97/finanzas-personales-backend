from typing import Optional
from pydantic import BaseModel, ConfigDict

from app.models.category import CategoryType

class CategoryCreate(BaseModel):
    name: str
    type: CategoryType

class CategoryRead(BaseModel):
    id: int
    name: str
    type: CategoryType
    is_active: bool
    is_system: bool     
    system_key: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)