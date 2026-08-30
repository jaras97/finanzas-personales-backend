import datetime as dt
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.security import get_current_user_with_subscription_check
from app.database import engine
from app.models.saving_account import SavingAccount, SavingAccountStatus
from app.models.saving_goal import SavingGoal
from app.schemas.saving_goal import SavingGoalCreate, SavingGoalRead, SavingGoalUpdate

router = APIRouter(prefix="/saving-goals", tags=["saving-goals"])


def _months_remaining(today: dt.date, target: dt.date) -> int:
    return max((target.year - today.year) * 12 + (target.month - today.month), 0)


def _to_read(session: Session, goal: SavingGoal) -> SavingGoalRead:
    account = session.get(SavingAccount, goal.saving_account_id)
    balance = account.balance if account else 0.0
    progress = (balance / goal.target_amount * 100) if goal.target_amount > 0 else 0.0

    monthly_needed = None
    if goal.target_date:
        remaining_amount = goal.target_amount - balance
        if remaining_amount <= 0:
            monthly_needed = 0.0
        else:
            months = _months_remaining(dt.date.today(), goal.target_date)
            # Meta vence este mes (o ya pasó, `months` clampeado a 0): hace
            # falta todo lo que falta, ya no hay margen para repartirlo.
            monthly_needed = remaining_amount if months == 0 else remaining_amount / months

    return SavingGoalRead(
        id=goal.id,
        saving_account_id=goal.saving_account_id,
        account_name=account.name if account else "(cuenta eliminada)",
        currency=account.currency if account else "COP",
        name=goal.name,
        target_amount=goal.target_amount,
        target_date=goal.target_date,
        is_active=goal.is_active,
        current_balance=balance,
        progress_percent=progress,
        monthly_savings_needed=monthly_needed,
    )


@router.post("", response_model=SavingGoalRead)
@router.post("/", response_model=SavingGoalRead)
def create_goal(
    data: SavingGoalCreate,
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    if data.target_amount <= 0:
        raise HTTPException(status_code=400, detail="La meta debe ser mayor a cero.")
    if not data.name.strip():
        raise HTTPException(status_code=400, detail="El nombre no puede estar vacío.")

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

        existing = session.exec(
            select(SavingGoal).where(
                SavingGoal.saving_account_id == data.saving_account_id,
                SavingGoal.is_active == True,  # noqa: E712
            )
        ).first()
        if existing:
            raise HTTPException(
                status_code=400, detail="Esta cuenta ya tiene una meta de ahorro activa."
            )

        goal = SavingGoal(
            user_id=user_id,
            saving_account_id=data.saving_account_id,
            name=data.name.strip(),
            target_amount=data.target_amount,
            target_date=data.target_date,
        )
        session.add(goal)
        session.commit()
        session.refresh(goal)
        return _to_read(session, goal)


@router.get("", response_model=List[SavingGoalRead])
@router.get("/", response_model=List[SavingGoalRead])
def list_goals(user_id: UUID = Depends(get_current_user_with_subscription_check)):
    with Session(engine) as session:
        goals = session.exec(
            select(SavingGoal).where(
                SavingGoal.user_id == user_id, SavingGoal.is_active == True  # noqa: E712
            )
        ).all()
        return [_to_read(session, g) for g in goals]


@router.put("/{goal_id}", response_model=SavingGoalRead)
def update_goal(
    goal_id: int,
    data: SavingGoalUpdate,
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    with Session(engine) as session:
        goal = session.get(SavingGoal, goal_id)
        if not goal or goal.user_id != user_id:
            raise HTTPException(status_code=404, detail="Meta no encontrada.")

        if data.name is not None:
            if not data.name.strip():
                raise HTTPException(status_code=400, detail="El nombre no puede estar vacío.")
            goal.name = data.name.strip()
        if data.target_amount is not None:
            if data.target_amount <= 0:
                raise HTTPException(status_code=400, detail="La meta debe ser mayor a cero.")
            goal.target_amount = data.target_amount
        if data.target_date is not None:
            goal.target_date = data.target_date
        if data.is_active is not None:
            goal.is_active = data.is_active

        session.add(goal)
        session.commit()
        session.refresh(goal)
        return _to_read(session, goal)


@router.delete("/{goal_id}")
def delete_goal(goal_id: int, user_id: UUID = Depends(get_current_user_with_subscription_check)):
    with Session(engine) as session:
        goal = session.get(SavingGoal, goal_id)
        if not goal or goal.user_id != user_id:
            raise HTTPException(status_code=404, detail="Meta no encontrada.")
        session.delete(goal)
        session.commit()
        return {"message": "Meta eliminada."}
