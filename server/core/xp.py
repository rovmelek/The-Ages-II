"""XP calculation utilities for combat and future XP sources."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from server.core.config import settings
from server.core.constants import STAT_NAMES
from server.player import repo as player_repo


@dataclass
class XpResult:
    """Result of XP application — used to decouple business logic from messaging."""

    final_xp: int
    source: str
    detail: str
    new_total_xp: int
    level_up_available: bool
    new_level: int | None = None


def calculate_combat_xp(hit_dice: int, charisma: int) -> int:
    """Calculate XP reward for defeating an NPC.

    Args:
        hit_dice: NPC hit dice value (difficulty).
        charisma: Player's charisma stat (affects XP bonus).

    Returns:
        Final XP amount after CHA bonus applied.
    """
    if settings.XP_CURVE_TYPE == "linear":
        base_xp = hit_dice * settings.XP_CURVE_MULTIPLIER
    else:  # quadratic (default)
        base_xp = (hit_dice ** 2) * settings.XP_CURVE_MULTIPLIER
    cha_multiplier = 1 + charisma * settings.XP_CHA_BONUS_PER_POINT
    return math.floor(base_xp * cha_multiplier)


async def apply_xp(
    entity_id: str,
    player_entity: Any,
    amount: int,
    source: str,
    detail: str,
    game: Any,
    apply_cha_bonus: bool = True,
    session: Any = None,
) -> XpResult:
    """Calculate XP, update entity stats, persist to DB. Returns result for caller to notify.

    Args:
        session: Optional DB session. When provided, uses it instead of
            opening a new transaction (for transaction consolidation).
    """
    if apply_cha_bonus:
        cha = player_entity.stats.get("charisma", 0)
        cha_multiplier = 1 + cha * settings.XP_CHA_BONUS_PER_POINT
        final_xp = math.floor(amount * cha_multiplier)
    else:
        final_xp = amount
    player_entity.stats["xp"] = player_entity.stats.get("xp", 0) + final_xp
    # Persist
    if session is not None:
        await player_repo.update_stats(session, player_entity.player_db_id, player_entity.stats)
    else:
        async with game.transaction() as s:
            await player_repo.update_stats(s, player_entity.player_db_id, player_entity.stats)
    # Level-up threshold detection (state mutation only — no messaging)
    level_up = False
    new_level = None
    player_info = game.player_manager.get_session(entity_id)
    if player_info is not None:
        new_pending = get_pending_level_ups(player_entity.stats)
        old_pending = player_info.pending_level_ups
        if new_pending > old_pending:
            player_info.pending_level_ups = new_pending
            level_up = old_pending == 0
            new_level = player_entity.stats.get("level", 1) + 1
    return XpResult(
        final_xp=final_xp,
        source=source,
        detail=detail,
        new_total_xp=player_entity.stats["xp"],
        level_up_available=level_up,
        new_level=new_level,
    )


def get_pending_level_ups(stats: dict) -> int:
    """Return how many level-ups are available based on current XP and level."""
    if settings.XP_LEVEL_THRESHOLD_MULTIPLIER <= 0:
        return 0
    level = stats.get("level", 1)
    xp = stats.get("xp", 0)
    pending = 0
    check_level = level
    while xp >= check_level * settings.XP_LEVEL_THRESHOLD_MULTIPLIER:
        pending += 1
        check_level += 1
    return pending
