from typing import Iterable, Optional

from app.models.category_rule import CategoryRule


def suggest_category(description: Optional[str], rules: Iterable[CategoryRule]) -> Optional[int]:
    """Primera regla activa (en orden de `priority` ascendente) cuyo
    `match_text` aparece dentro de `description`, sin distinguir mayúsculas.
    `None` si ninguna matchea -- el llamador cae a "Sin categorizar".
    """
    if not description:
        return None
    text = description.lower()
    active = sorted((r for r in rules if r.is_active), key=lambda r: r.priority)
    for rule in active:
        if rule.match_text.lower() in text:
            return rule.category_id
    return None
