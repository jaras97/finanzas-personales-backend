from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app.core.security import get_current_user
from app.database import engine
from app.models.user import User
from app.utils.currency_helpers import validate_currency_code

router = APIRouter(prefix="/account", tags=["account"])


class AccountPreferencesUpdate(BaseModel):
    report_currency: str


@router.patch("/preferences")
def update_preferences(data: AccountPreferencesUpdate, user_id=Depends(get_current_user)):
    with Session(engine) as session:
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado.")
        validate_currency_code(session, data.report_currency)
        user.report_currency = data.report_currency
        session.add(user)
        session.commit()
        return {"report_currency": user.report_currency}
