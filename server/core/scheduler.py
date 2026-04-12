"""Scheduler — periodic task runner for NPC respawns and rare spawn checks."""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from server.room.npc import create_npc_from_template
from server.room.spawn_models import SpawnCheckpoint

if TYPE_CHECKING:
    from server.app import Game

logger = logging.getLogger(__name__)


def _ensure_aware(dt: datetime | None) -> datetime | None:
    """Ensure a datetime is timezone-aware (SQLite returns naive datetimes)."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt

# How often the rare-spawn loop checks for due spawn rolls (seconds)
_RARE_CHECK_INTERVAL = 60


class Scheduler:
    """Manages NPC respawn timers and periodic rare spawn checks."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._respawn_tasks: dict[str, asyncio.Task] = {}
        self._game: Game | None = None
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self, game: Game) -> None:
        """Start the scheduler: recover checkpoints, launch background loop."""
        self._game = game
        self._running = True
        await self._recover_checkpoints()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Cancel all scheduled tasks and wait for cleanup."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        for t in list(self._respawn_tasks.values()):
            t.cancel()
        for t in list(self._respawn_tasks.values()):
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        self._respawn_tasks.clear()

    # ------------------------------------------------------------------
    # Persistent NPC respawn
    # ------------------------------------------------------------------

    def schedule_respawn(self, room_key: str, npc_id: str, delay_seconds: float) -> None:
        """Schedule a persistent NPC to respawn after *delay_seconds*."""
        key = f"{room_key}:{npc_id}"
        # Cancel any existing task for this NPC
        old = self._respawn_tasks.pop(key, None)
        if old:
            old.cancel()
        task = asyncio.create_task(self._do_respawn(room_key, npc_id, delay_seconds))
        self._respawn_tasks[key] = task

    async def _do_respawn(self, room_key: str, npc_id: str, delay: float) -> None:
        """Wait, then respawn the NPC."""
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        await self.respawn_npc(room_key, npc_id)
        self._respawn_tasks.pop(f"{room_key}:{npc_id}", None)

    async def respawn_npc(self, room_key: str, npc_id: str) -> None:
        """Reset an NPC to alive with full HP and notify the room."""
        if not self._game:
            return
        room = self._game.room_manager.get_room(room_key)
        if room is None:
            return
        npc = room.get_npc(npc_id)
        if npc is None:
            return

        # Restore from template
        tmpl = self._game.npc_templates.get(npc.npc_key) if self._game else None
        if tmpl:
            npc.stats = dict(tmpl.get("stats", {}))
        npc.is_alive = True

        await self._game.connection_manager.broadcast_to_room(
            room_key,
            {"type": "entity_entered", "entity": npc.to_dict()},
        )

    # ------------------------------------------------------------------
    # Rare NPC spawn checks
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        """Background loop that periodically runs rare spawn checks."""
        try:
            while self._running:
                await self._run_rare_spawn_checks()
                await asyncio.sleep(_RARE_CHECK_INTERVAL)
        except asyncio.CancelledError:
            return

    async def _run_rare_spawn_checks(self) -> None:
        """Roll for each rare NPC template that is due for a check."""
        now = datetime.now(UTC)

        rare_templates = [
            t for t in self._game.npc_templates.values()
            if t.get("spawn_type") == "rare"
        ]
        if not rare_templates:
            return

        async with self._game.transaction() as session:
            for tmpl in rare_templates:
                npc_key = tmpl["npc_key"]
                cfg = tmpl.get("spawn_config", {})
                room_key = cfg.get("room_key", "")
                if not room_key:
                    continue

                # Load or create checkpoint
                result = await session.execute(
                    select(SpawnCheckpoint).where(
                        SpawnCheckpoint.npc_key == npc_key,
                        SpawnCheckpoint.room_key == room_key,
                    )
                )
                cp = result.scalar_one_or_none()
                if cp is None:
                    cp = SpawnCheckpoint(
                        npc_key=npc_key,
                        room_key=room_key,
                        next_check_at=now,
                        currently_spawned=False,
                    )
                    session.add(cp)
                    await session.flush()

                # Not yet due
                if cp.next_check_at and _ensure_aware(cp.next_check_at) > now:
                    continue

                # Already at max active
                max_active = cfg.get("max_active", 1)
                if cp.currently_spawned and max_active <= 1:
                    # Update next check time even if skipped
                    interval_hours = cfg.get("check_interval_hours", 12)
                    cp.last_check_at = now
                    cp.next_check_at = now + timedelta(hours=interval_hours)
                    continue

                # Roll
                chance = cfg.get("spawn_chance", 0.1)
                roll = random.random()
                interval_hours = cfg.get("check_interval_hours", 12)
                cp.last_check_at = now
                cp.next_check_at = now + timedelta(hours=interval_hours)

                if roll < chance:
                    # Spawn the NPC
                    x = cfg.get("x", 0)
                    y = cfg.get("y", 0)
                    npc_id = f"{room_key}_{npc_key}_{x}_{y}"
                    npc = create_npc_from_template(npc_key, npc_id, x, y, templates=self._game.npc_templates)
                    if npc and self._game:
                        room = self._game.room_manager.get_room(room_key)
                        if room:
                            room.add_npc(npc)
                            cp.currently_spawned = True
                            await self._game.connection_manager.broadcast_to_room(
                                room_key,
                                {"type": "entity_entered", "entity": npc.to_dict()},
                            )
                            # Emit global rare spawn announcement
                            await self._game.event_bus.emit(
                                "rare_spawn",
                                npc_name=npc.name,
                                room_name=room.name,
                            )


    # ------------------------------------------------------------------
    # Checkpoint recovery on startup
    # ------------------------------------------------------------------

    async def _recover_checkpoints(self) -> None:
        """Load SpawnCheckpoints from DB and run any overdue checks."""
        now = datetime.now(UTC)
        async with self._game.transaction() as session:
            result = await session.execute(select(SpawnCheckpoint))
            checkpoints = result.scalars().all()

        for cp in checkpoints:
            if cp.next_check_at and _ensure_aware(cp.next_check_at) <= now:
                # Overdue — will be picked up on next loop iteration immediately
                logger.info(
                    "Overdue spawn check for %s in %s, will run immediately",
                    cp.npc_key,
                    cp.room_key,
                )
