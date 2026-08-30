from typing import Optional

from pydantic import BaseModel


class CategoryRuleCreate(BaseModel):
    category_id: int
    match_text: str


class CategoryRuleUpdate(BaseModel):
    category_id: Optional[int] = None
    match_text: Optional[str] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None


class CategoryRuleRead(BaseModel):
    id: int
    category_id: int
    category_name: str
    match_text: str
    priority: int
    is_active: bool

    class Config:
        from_attributes = True


class ApplyRulesResult(BaseModel):
    updated: int
