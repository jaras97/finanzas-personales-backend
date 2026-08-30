from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlmodel import Session, select

from app.core.security import get_current_user_with_subscription_check
from app.database import engine
from app.models.category import Category
from app.models.category_rule import CategoryRule
from app.models.transaction import Transaction
from app.schemas.category_rule import (
    ApplyRulesResult,
    CategoryRuleCreate,
    CategoryRuleRead,
    CategoryRuleUpdate,
)
from app.utils.category_helpers import get_or_create_uncategorized_category
from app.utils.category_rule_helpers import suggest_category

router = APIRouter(prefix="/category-rules", tags=["category-rules"])


def _to_read(session: Session, rule: CategoryRule) -> CategoryRuleRead:
    category = session.get(Category, rule.category_id)
    return CategoryRuleRead(
        id=rule.id,
        category_id=rule.category_id,
        category_name=category.name if category else "(categoría eliminada)",
        match_text=rule.match_text,
        priority=rule.priority,
        is_active=rule.is_active,
    )


@router.post("", response_model=CategoryRuleRead)
@router.post("/", response_model=CategoryRuleRead)
def create_rule(
    data: CategoryRuleCreate,
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    if not data.match_text.strip():
        raise HTTPException(status_code=400, detail="El texto a buscar no puede estar vacío.")

    with Session(engine) as session:
        category = session.exec(
            select(Category).where(
                Category.id == data.category_id,
                Category.user_id == user_id,
                Category.is_active == True,  # noqa: E712
            )
        ).first()
        if not category:
            raise HTTPException(status_code=400, detail="Categoría inválida o inactiva.")

        max_priority = session.exec(
            select(func.max(CategoryRule.priority)).where(CategoryRule.user_id == user_id)
        ).first()
        next_priority = (max_priority or 0) + 1

        rule = CategoryRule(
            user_id=user_id,
            category_id=data.category_id,
            match_text=data.match_text.strip(),
            priority=next_priority,
        )
        session.add(rule)
        session.commit()
        session.refresh(rule)
        return _to_read(session, rule)


@router.get("", response_model=List[CategoryRuleRead])
@router.get("/", response_model=List[CategoryRuleRead])
def list_rules(user_id: UUID = Depends(get_current_user_with_subscription_check)):
    with Session(engine) as session:
        rules = session.exec(
            select(CategoryRule)
            .where(CategoryRule.user_id == user_id)
            .order_by(CategoryRule.priority)
        ).all()
        return [_to_read(session, r) for r in rules]


@router.put("/{rule_id}", response_model=CategoryRuleRead)
def update_rule(
    rule_id: int,
    data: CategoryRuleUpdate,
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    with Session(engine) as session:
        rule = session.get(CategoryRule, rule_id)
        if not rule or rule.user_id != user_id:
            raise HTTPException(status_code=404, detail="Regla no encontrada.")

        if data.category_id is not None:
            category = session.exec(
                select(Category).where(
                    Category.id == data.category_id,
                    Category.user_id == user_id,
                    Category.is_active == True,  # noqa: E712
                )
            ).first()
            if not category:
                raise HTTPException(status_code=400, detail="Categoría inválida o inactiva.")
            rule.category_id = data.category_id

        if data.match_text is not None:
            if not data.match_text.strip():
                raise HTTPException(status_code=400, detail="El texto a buscar no puede estar vacío.")
            rule.match_text = data.match_text.strip()

        if data.priority is not None:
            rule.priority = data.priority

        if data.is_active is not None:
            rule.is_active = data.is_active

        session.add(rule)
        session.commit()
        session.refresh(rule)
        return _to_read(session, rule)


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, user_id: UUID = Depends(get_current_user_with_subscription_check)):
    with Session(engine) as session:
        rule = session.get(CategoryRule, rule_id)
        if not rule or rule.user_id != user_id:
            raise HTTPException(status_code=404, detail="Regla no encontrada.")
        session.delete(rule)
        session.commit()
        return {"message": "Regla eliminada."}


@router.post("/apply", response_model=ApplyRulesResult)
def apply_rules(user_id: UUID = Depends(get_current_user_with_subscription_check)):
    """Aplica las reglas activas contra transacciones ya existentes que
    todavía están en "Sin categorizar" -- útil después de crear una regla
    nueva, o de una importación que dejó filas sin categorizar."""
    with Session(engine) as session:
        uncategorized = get_or_create_uncategorized_category(session, user_id)

        rules = session.exec(
            select(CategoryRule).where(
                CategoryRule.user_id == user_id, CategoryRule.is_active == True  # noqa: E712
            )
        ).all()
        if not rules:
            return ApplyRulesResult(updated=0)

        candidates = session.exec(
            select(Transaction).where(
                Transaction.user_id == user_id,
                Transaction.category_id == uncategorized.id,
                Transaction.is_cancelled == False,  # noqa: E712
            )
        ).all()

        updated = 0
        for tx in candidates:
            suggestion = suggest_category(tx.description, rules)
            if suggestion is not None:
                tx.category_id = suggestion
                session.add(tx)
                updated += 1

        session.commit()
        return ApplyRulesResult(updated=updated)
