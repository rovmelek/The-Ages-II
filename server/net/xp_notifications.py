"""XP notification functions — WebSocket messaging for XP events."""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

from server.core.config import settings
from server.core.constants import STAT_NAMES
from server.core.xp import XpResult, apply_xp

if TYPE_CHECKING:
    from server.app import Game


async def send_level_up_available(entity_id: str, player_entity: Any, game: Game) -> None:
    """Send level_up_available message to the player."""
    stats = player_entity.stats
    current_level = stats.get("level", 1)
    new_level = current_level + 1
    ssf = settings.STAT_SCALING_FACTOR
    await game.connection_manager.send_to_player_seq(entity_id, {
        "type": "level_up_available",
        "new_level": new_level,
        "choose_stats": settings.LEVEL_UP_STAT_CHOICES,
        "current_stats": {
            s: stats.get(s, settings.DEFAULT_STAT_VALUE) for s in STAT_NAMES
        },
        "stat_cap": settings.STAT_CAP,
        "xp_for_next_level": current_level * settings.XP_LEVEL_THRESHOLD_MULTIPLIER,
        "xp_for_current_level": (current_level - 1) * settings.XP_LEVEL_THRESHOLD_MULTIPLIER,
        "stat_effects": {
            "strength": f"+{ssf:g} physical damage per point",
            "dexterity": f"-{ssf:g} incoming damage per point",
            "constitution": f"+{settings.CON_HP_PER_POINT} max HP per point",
            "intelligence": f"+{ssf:g} magic dmg, +{settings.INT_ENERGY_PER_POINT} max energy per point",
            "wisdom": f"+{ssf:g} healing, +{settings.WIS_ENERGY_PER_POINT} max energy per point",
            "charisma": f"+{round(settings.XP_CHA_BONUS_PER_POINT * 100)}% XP per point",
        },
    })


async def notify_xp(
    entity_id: str,
    result: XpResult,
    player_entity: Any,
    game: Game,
) -> None:
    """Send xp_gained and optional level_up_available messages."""
    current_level = player_entity.stats.get("level", 1)
    await game.connection_manager.send_to_player_seq(entity_id, {
        "type": "xp_gained",
        "amount": result.final_xp,
        "source": result.source,
        "detail": result.detail,
        "new_total_xp": result.new_total_xp,
        "xp_for_next_level": current_level * settings.XP_LEVEL_THRESHOLD_MULTIPLIER,
        "xp_for_current_level": (current_level - 1) * settings.XP_LEVEL_THRESHOLD_MULTIPLIER,
    })
    if result.level_up_available:
        await send_level_up_available(entity_id, player_entity, game)


async def grant_xp(
    entity_id: str,
    player_entity: Any,
    amount: int,
    source: str,
    detail: str,
    game: Game,
    apply_cha_bonus: bool = True,
    session: Any = None,
) -> int:
    """Apply XP and notify. Backward-compatible wrapper.

    Returns final XP amount.
    """
    result = await apply_xp(
        entity_id, player_entity, amount, source, detail, game,
        apply_cha_bonus, session,
    )
    await notify_xp(entity_id, result, player_entity, game)
    return result.final_xp
