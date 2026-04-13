"""Out-of-combat HP and energy regeneration loop (ADR-18-3)."""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from server.core.config import settings

if TYPE_CHECKING:
    from server.app import Game

logger = logging.getLogger(__name__)

_regen_task: asyncio.Task | None = None


async def start_regen_loop(game: Game) -> None:
    """Start the background regen loop."""
    global _regen_task
    if _regen_task is not None and not _regen_task.done():
        return  # Already running
    _regen_task = asyncio.create_task(_regen_loop(game))


async def stop_regen_loop() -> None:
    """Stop the background regen loop."""
    global _regen_task
    if _regen_task is not None:
        _regen_task.cancel()
        try:
            await _regen_task
        except asyncio.CancelledError:
            pass
        _regen_task = None


async def _regen_loop(game: Game) -> None:
    """Background loop: regen HP and energy for out-of-combat players."""
    tick_count = 0
    dirty_ids: set[str] = set()  # Cumulative across ticks until persist
    while True:
        try:
            await asyncio.sleep(settings.REGEN_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            return

        tick_count += 1

        for entity_id, player_info in list(game.player_manager.all_sessions()):
            try:
                entity = player_info.entity
                if entity.in_combat:
                    continue

                stats = entity.stats
                hp = stats.get("hp", 0)
                max_hp = stats.get("max_hp", 0)
                energy = stats.get("energy", 0)
                max_energy = stats.get("max_energy", 0)

                if hp >= max_hp and energy >= max_energy:
                    continue

                # Apply regen in-place
                stats["hp"] = min(hp + settings.REGEN_HP_PER_TICK, max_hp)
                stats["energy"] = min(energy + settings.REGEN_ENERGY_PER_TICK, max_energy)
                dirty_ids.add(entity_id)

                # Send stats_update to client (skip if no WebSocket)
                ws = game.connection_manager.get_websocket(entity_id)
                if ws:
                    await game.connection_manager.send_to_player_seq(entity_id, {
                        "type": "stats_update",
                        "hp": stats["hp"],
                        "max_hp": stats["max_hp"],
                        "energy": stats.get("energy", 0),
                        "max_energy": stats.get("max_energy", 0),
                    })
            except Exception:
                logger.exception("Regen tick failed for %s", entity_id)

        # Persist to DB periodically
        if tick_count % settings.REGEN_PERSIST_INTERVAL == 0 and dirty_ids:
            try:
                from server.player import repo as player_repo

                async with game.transaction() as session:
                    for eid in dirty_ids:
                        pi = game.player_manager.get_session(eid)
                        if pi:
                            await player_repo.update_stats(
                                session, pi.entity.player_db_id, pi.entity.stats
                            )
                dirty_ids.clear()
            except Exception:
                logger.exception("Regen persist failed")
