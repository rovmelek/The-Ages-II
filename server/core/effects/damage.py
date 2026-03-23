"""Damage effect handler."""
from __future__ import annotations


async def handle_damage(
    effect: dict, source: dict, target: dict, context: dict
) -> dict:
    """Apply direct damage to target, absorbing through shield first."""
    raw_damage = effect.get("value", 0)
    shield = target.get("shield", 0)
    absorbed = min(shield, raw_damage)
    target["shield"] = shield - absorbed
    actual_damage = raw_damage - absorbed
    target["hp"] = max(0, target["hp"] - actual_damage)
    return {
        "type": "damage",
        "value": actual_damage,
        "shield_absorbed": absorbed,
        "target_hp": target["hp"],
    }
