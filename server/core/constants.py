"""Shared type constants for cross-cutting concerns."""
from __future__ import annotations

from enum import StrEnum

# D&D-style ability stat names used across player, NPC, and combat systems
STAT_NAMES: tuple[str, ...] = (
    "strength",
    "dexterity",
    "constitution",
    "intelligence",
    "wisdom",
    "charisma",
)


class EffectType(StrEnum):
    """Card and item effect types used in the shared effect registry."""

    DAMAGE = "damage"
    HEAL = "heal"
    SHIELD = "shield"
    DOT = "dot"
    DRAW = "draw"


# NPC spawn type identifiers (from NPC template JSON)
SPAWN_PERSISTENT = "persistent"
SPAWN_RARE = "rare"

# Protocol version included in login_success responses
PROTOCOL_VERSION = "1.0"
