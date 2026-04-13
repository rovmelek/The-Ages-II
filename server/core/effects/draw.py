"""Draw-cards effect handler."""
from __future__ import annotations

from server.core.constants import EffectType


async def handle_draw(
    effect: dict, source: dict, target: dict, context: dict
) -> dict:
    """Return a draw instruction — actual card draw handled by combat system."""
    value = effect.get("value", 1)
    return {
        "type": EffectType.DRAW,
        "value": value,
    }
