"""Level-up handler for WebSocket clients."""
from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import WebSocket

from server.core.config import settings
from server.core.constants import STAT_NAMES
from server.core.xp import get_pending_level_ups
from server.net.xp_notifications import send_level_up_available
from server.net.auth_middleware import requires_auth
from server.net.schemas import with_request_id
from server.player import repo as player_repo
from server.player.service import compute_max_energy
from server.player.session import PlayerSession

if TYPE_CHECKING:
    from server.app import Game

_VALID_LEVEL_UP_STATS = set(STAT_NAMES)


@requires_auth
async def handle_level_up(
    websocket: WebSocket, data: dict, *, game: Game,
    entity_id: str, player_info: PlayerSession,
) -> None:
    """Handle the 'level_up' action: apply stat choices for a pending level-up."""
    entity = player_info.entity
    if entity.in_combat:
        await websocket.send_json(
            with_request_id({"type": "error", "detail": "Cannot level up during combat"}, data)
        )
        return

    pending = player_info.pending_level_ups
    if pending <= 0:
        await websocket.send_json(
            with_request_id({"type": "error", "detail": "No level-up available"}, data)
        )
        return

    chosen_stats = data.get("stats", [])

    # Validate (allow stacking — no dedup)
    chosen = chosen_stats[:settings.LEVEL_UP_STAT_CHOICES]
    if not chosen:
        await websocket.send_json(
            with_request_id({"type": "error", "detail": "Must choose at least 1 stat"}, data)
        )
        return
    for s in chosen:
        if s not in _VALID_LEVEL_UP_STATS:
            await websocket.send_json(
                with_request_id({"type": "error", "detail": f"Invalid stat: {s}"}, data)
            )
            return

    stats = entity.stats

    # Apply stat boosts (stacking allowed)
    stat_changes = {}
    stat_increases: dict[str, int] = {}
    skipped = []
    for s in chosen:
        if stats.get(s, settings.DEFAULT_STAT_VALUE) >= settings.STAT_CAP:
            skipped.append(s)
        else:
            stats[s] = stats.get(s, settings.DEFAULT_STAT_VALUE) + 1
            stat_changes[s] = stats[s]
            stat_increases[s] = stat_increases.get(s, 0) + 1

    # Increment level
    stats["level"] = stats.get("level", 1) + 1

    # Recalculate max_hp from CON and full heal
    stats["max_hp"] = settings.DEFAULT_BASE_HP + stats.get("constitution", settings.DEFAULT_STAT_VALUE) * settings.CON_HP_PER_POINT
    stats["hp"] = stats["max_hp"]

    # Recalculate max_energy from INT+WIS and full restore (ADR-18-9)
    stats["max_energy"] = compute_max_energy(stats)
    stats["energy"] = stats["max_energy"]

    # Persist to DB
    async with game.transaction() as session:
        await player_repo.update_stats(session, entity.player_db_id, stats)

    # Build response
    new_level = stats["level"]
    response: dict = {
        "type": "level_up_complete",
        "level": new_level,
        "stat_changes": stat_changes,
        "stat_increases": stat_increases,
        "new_max_hp": stats["max_hp"],
        "new_hp": stats["hp"],
        "new_max_energy": stats["max_energy"],
        "new_energy": stats["energy"],
        "xp_for_next_level": new_level * settings.XP_LEVEL_THRESHOLD_MULTIPLIER,
        "xp_for_current_level": (new_level - 1) * settings.XP_LEVEL_THRESHOLD_MULTIPLIER,
    }
    if skipped:
        response["skipped_at_cap"] = skipped
    await websocket.send_json(with_request_id(response, data))

    # Check for queued level-ups
    remaining = get_pending_level_ups(stats)
    player_info.pending_level_ups = remaining
    if remaining > 0:
        await send_level_up_available(entity_id, entity, game)
