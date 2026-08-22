from typing import List

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.core.security import get_current_user
from app.database import engine
from app.models.currency import Currency

router = APIRouter(prefix="/currencies", tags=["currencies"])


@router.get("", response_model=List[Currency])
@router.get("/", response_model=List[Currency])
def list_currencies(user_id=Depends(get_current_user)):
    with Session(engine) as session:
        return session.exec(select(Currency).order_by(Currency.code)).all()
