"""Damage effect handler."""
from __future__ import annotations

import math

from server.core.config import settings


async def handle_damage(
    effect: dict, source: dict, target: dict, context: dict
) -> dict:
    """Apply direct damage to target, absorbing through shield first.

    Stat bonuses:
    - physical subtype: +floor(source STR × STAT_SCALING_FACTOR)
    - fire/ice/arcane subtype: +floor(source INT × STAT_SCALING_FACTOR)
    - DEX reduction applied after shield absorption (min damage 1)
    """
    base_damage = effect.get("value", 0)

    # Add stat bonus based on damage subtype
    subtype = effect.get("subtype", "physical")
    if subtype == "physical":
        bonus = math.floor(source.get("strength", 0) * settings.STAT_SCALING_FACTOR)
    elif subtype in ("fire", "ice", "arcane"):
        bonus = math.floor(source.get("intelligence", 0) * settings.STAT_SCALING_FACTOR)
    else:
        bonus = 0
    raw_damage = base_damage + bonus

    # Shield absorption
    shield = target.get("shield", 0)
    absorbed = min(shield, raw_damage)
    target["shield"] = shield - absorbed
    post_shield = raw_damage - absorbed

    # DEX reduction (after shield, min 1 — but 0 if fully absorbed)
    dex_reduction = math.floor(target.get("dexterity", 0) * settings.STAT_SCALING_FACTOR)
    actual_damage = max(settings.COMBAT_MIN_DAMAGE, post_shield - dex_reduction) if post_shield > 0 else 0
    target["hp"] = max(0, target["hp"] - actual_damage)

    return {
        "type": "damage",
        "value": actual_damage,
        "shield_absorbed": absorbed,
        "target_hp": target["hp"],
    }
