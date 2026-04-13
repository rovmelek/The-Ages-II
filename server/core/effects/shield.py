"""Shield effect handler."""
from __future__ import annotations

from server.core.constants import EffectType


async def handle_shield(
    effect: dict, source: dict, target: dict, context: dict
) -> dict:
    """Add shield points to target."""
    value = effect.get("value", 0)
    current = target.get("shield", 0)
    target["shield"] = current + value
    return {
        "type": EffectType.SHIELD,
        "value": value,
        "total_shield": target["shield"],
    }
