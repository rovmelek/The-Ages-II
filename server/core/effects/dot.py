"""Damage-over-time effect handler."""
from __future__ import annotations


async def handle_dot(
    effect: dict, source: dict, target: dict, context: dict
) -> dict:
    """Apply a damage-over-time effect to the target."""
    subtype = effect.get("subtype", "generic")
    value = effect.get("value", 0)
    duration = effect.get("duration", 1)

    if "active_effects" not in target:
        target["active_effects"] = []

    target["active_effects"].append({
        "type": "dot",
        "subtype": subtype,
        "value": value,
        "remaining": duration,
    })

    return {
        "type": "dot",
        "subtype": subtype,
        "value": value,
        "duration": duration,
    }
