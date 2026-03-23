"""Heal effect handler."""
from __future__ import annotations


async def handle_heal(
    effect: dict, source: dict, target: dict, context: dict
) -> dict:
    """Restore HP to target, capped at max_hp."""
    value = effect.get("value", 0)
    old_hp = target["hp"]
    target["hp"] = min(target["hp"] + value, target["max_hp"])
    actual_heal = target["hp"] - old_hp
    return {
        "type": "heal",
        "value": actual_heal,
        "target_hp": target["hp"],
    }
