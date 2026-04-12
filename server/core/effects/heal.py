"""Heal effect handler."""
from __future__ import annotations

import math

from server.core.config import settings


async def handle_heal(
    effect: dict, source: dict, target: dict, context: dict
) -> dict:
    """Restore HP to target, capped at max_hp.

    Stat bonus: +floor(source WIS × STAT_SCALING_FACTOR)
    """
    base_value = effect.get("value", 0)
    bonus = math.floor(source.get("wisdom", 0) * settings.STAT_SCALING_FACTOR)
    value = base_value + bonus
    old_hp = target["hp"]
    target["hp"] = min(target["hp"] + value, target["max_hp"])
    actual_heal = target["hp"] - old_hp
    return {
        "type": "heal",
        "value": actual_heal,
        "target_hp": target["hp"],
    }
