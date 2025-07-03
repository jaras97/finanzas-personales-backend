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

    model_config = ConfigDict(from_attributes=True)