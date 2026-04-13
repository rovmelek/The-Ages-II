"""Restore energy effect handler."""
from __future__ import annotations

from server.core.constants import EffectType


async def handle_restore_energy(
    effect: dict, source: dict, target: dict, context: dict
) -> dict:
    """Restore energy to target, capped at max_energy.

    Flat restore — no stat scaling (ADR-18-12).
    """
    value = effect.get("value", 0)
    old_energy = target.get("energy", 0)
    max_energy = target.get("max_energy", 0)
    target["energy"] = min(old_energy + value, max_energy)
    actual = target["energy"] - old_energy
    return {
        "type": EffectType.RESTORE_ENERGY,
        "value": actual,
        "target_energy": target["energy"],
    }
