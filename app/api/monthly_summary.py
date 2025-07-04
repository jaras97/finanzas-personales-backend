from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List
from uuid import UUID

from app.database import engine
from app.models.monthly_summary import MonthlySummary
from app.schemas.monthly_summary import MonthlySummaryCreate, MonthlySummaryRead
from app.core.security import get_current_user, get_current_user_with_subscription_check

router = APIRouter(prefix="/monthly-summaries", tags=["monthly_summaries"])


@router.post("/", response_model=MonthlySummaryRead)
def create_monthly_summary(
    summary_data: MonthlySummaryCreate,
    user_id: UUID = Depends(get_current_user_with_subscription_check)
):
    with Session(engine) as session:
        existing = session.exec(
            select(MonthlySummary).where(
                MonthlySummary.user_id == user_id,
                MonthlySummary.year == summary_data.year,
                MonthlySummary.month == summary_data.month,
            )
        ).first()

        if existing:
            raise HTTPException(
                status_code=400, detail="Resumen mensual ya existe para ese mes y año."
            )

        summary = MonthlySummary(**summary_data.dict(), user_id=user_id)
        session.add(summary)
        session.commit()
        session.refresh(summary)
        return summary


@router.get("/", response_model=List[MonthlySummaryRead])
def list_monthly_summaries(user_id: UUID = Depends(get_current_user_with_subscription_check)):
    with Session(engine) as session:
        summaries = session.exec(
            select(MonthlySummary).where(MonthlySummary.user_id == user_id).order_by(
                MonthlySummary.year.desc(), MonthlySummary.month.desc()
            )
        ).all()
        return summaries