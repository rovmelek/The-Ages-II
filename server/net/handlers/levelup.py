"""Level-up handler for WebSocket clients."""
from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import WebSocket

from server.core.config import settings
from server.core.xp import get_pending_level_ups, send_level_up_available
from server.net.auth_middleware import requires_auth
from server.player import repo as player_repo
from server.player.session import PlayerSession

if TYPE_CHECKING:
    from server.app import Game

_VALID_LEVEL_UP_STATS = {
    "strength", "dexterity", "constitution",
    "intelligence", "wisdom", "charisma",
}


@requires_auth
async def handle_level_up(
    websocket: WebSocket, data: dict, *, game: Game,
    entity_id: str, player_info: PlayerSession,
) -> None:
    """Handle the 'level_up' action: apply stat choices for a pending level-up."""
    entity = player_info.entity
    if entity.in_combat:
        await websocket.send_json(
            {"type": "error", "detail": "Cannot level up during combat"}
        )
        return

    pending = player_info.pending_level_ups
    if pending <= 0:
        await websocket.send_json(
            {"type": "error", "detail": "No level-up available"}
        )
        return

    chosen_stats = data.get("stats", [])

    # Validate and deduplicate (max 3 unique)
    unique_stats = list(dict.fromkeys(chosen_stats))[:settings.LEVEL_UP_STAT_CHOICES]
    if not unique_stats:
        await websocket.send_json(
            {"type": "error", "detail": "Must choose at least 1 stat"}
        )
        return
    for s in unique_stats:
        if s not in _VALID_LEVEL_UP_STATS:
            await websocket.send_json(
                {"type": "error", "detail": f"Invalid stat: {s}"}
            )
            return

    stats = entity.stats

    # Apply stat boosts
    stat_changes = {}
    skipped = []
    for s in unique_stats:
        if stats.get(s, settings.DEFAULT_STAT_VALUE) >= settings.STAT_CAP:
            skipped.append(s)
        else:
            stats[s] = stats.get(s, settings.DEFAULT_STAT_VALUE) + 1
            stat_changes[s] = stats[s]

    # Increment level
    stats["level"] = stats.get("level", 1) + 1

    # Recalculate max_hp from CON and full heal
    stats["max_hp"] = settings.DEFAULT_BASE_HP + stats.get("constitution", settings.DEFAULT_STAT_VALUE) * settings.CON_HP_PER_POINT
    stats["hp"] = stats["max_hp"]

    # Persist to DB
    async with game.transaction() as session:
        await player_repo.update_stats(session, entity.player_db_id, stats)

    # Build response
    response: dict = {
        "type": "level_up_complete",
        "level": stats["level"],
        "stat_changes": stat_changes,
        "new_max_hp": stats["max_hp"],
        "new_hp": stats["hp"],
    }
    if skipped:
        response["skipped_at_cap"] = skipped
    await websocket.send_json(response)

    # Check for queued level-ups
    remaining = get_pending_level_ups(stats)
    player_info.pending_level_ups = remaining
    if remaining > 0:
        await send_level_up_available(entity_id, entity, game)
