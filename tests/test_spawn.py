"""Tests for NPC spawn system: persistent respawn, rare spawns, scheduler lifecycle."""
from __future__ import annotations

import asyncio
import contextlib
import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import make_bare_game
from server.core.scheduler import Scheduler
from server.room.npc import (
    NpcEntity,
    create_npc_from_template,
    load_npc_templates,
)
from server.room.room import RoomInstance


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_room(room_key: str = "test", width: int = 5, height: int = 5) -> RoomInstance:
    tile_data = [[0] * width for _ in range(height)]
    return RoomInstance(
        room_key=room_key,
        name="Test",
        width=width,
        height=height,
        tile_data=tile_data,
        spawn_points=[{"type": "player", "x": 0, "y": 0}],
    )


def _make_game(room: RoomInstance | None = None, npc_templates: dict | None = None) -> MagicMock:
    """Create a mock Game object with room_manager, connection_manager, event_bus."""
    game = MagicMock()
    game.connection_manager = MagicMock()
    game.connection_manager.broadcast_to_room = AsyncMock()
    game.event_bus = MagicMock()
    game.event_bus.emit = AsyncMock()
    game.npc_templates = npc_templates if npc_templates is not None else {}

    rm = MagicMock()
    if room:
        rm.get_room.return_value = room
    else:
        rm.get_room.return_value = None
    game.room_manager = rm
    return game


def _load_test_templates() -> dict[str, dict]:
    """Load persistent + rare NPC templates and return them."""
    templates = [
        {
            "npc_key": "test_goblin",
            "name": "Test Goblin",
            "behavior_type": "hostile",
            "spawn_type": "persistent",
            "spawn_config": {"respawn_seconds": 0.1},
            "stats": {"hp": 50, "max_hp": 50, "attack": 10, "defense": 5},
            "loot_table": "goblin_loot",
        },
        {
            "npc_key": "test_dragon",
            "name": "Test Dragon",
            "behavior_type": "hostile",
            "spawn_type": "rare",
            "spawn_config": {
                "check_interval_hours": 12,
                "spawn_chance": 0.5,
                "despawn_after_hours": 6,
                "max_active": 1,
                "room_key": "test",
                "x": 2,
                "y": 3,
            },
            "stats": {"hp": 500, "max_hp": 500, "attack": 25, "defense": 15},
            "loot_table": "dragon_loot",
        },
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir) / "test.json"
        p.write_text(json.dumps(templates))
        return load_npc_templates(Path(tmpdir))


# ---------------------------------------------------------------------------
# Persistent NPC respawn
# ---------------------------------------------------------------------------

class TestPersistentRespawn:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.npc_templates = _load_test_templates()

    @pytest.mark.asyncio
    async def test_respawn_npc_restores_hp_and_alive(self):
        """AC #1: NPC respawns with full HP and is_alive = True."""
        room = _make_room()
        npc = create_npc_from_template("test_goblin", "npc_1", 3, 3, templates=self.npc_templates)
        assert npc is not None
        room.add_npc(npc)

        # Kill the NPC
        npc.is_alive = False
        npc.stats["hp"] = 0

        game = _make_game(room, npc_templates=self.npc_templates)
        scheduler = Scheduler()
        scheduler._game = game

        await scheduler.respawn_npc("test", "npc_1")

        assert npc.is_alive is True
        assert npc.stats["hp"] == 50
        game.connection_manager.broadcast_to_room.assert_called_once()
        call_args = game.connection_manager.broadcast_to_room.call_args
        assert call_args[0][0] == "test"
        msg = call_args[0][1]
        assert msg["type"] == "entity_entered"
        assert msg["entity"]["id"] == "npc_1"

    @pytest.mark.asyncio
    async def test_schedule_respawn_calls_after_delay(self):
        """AC #1: Respawn fires after configured delay."""
        room = _make_room()
        npc = create_npc_from_template("test_goblin", "npc_1", 3, 3, templates=self.npc_templates)
        assert npc is not None
        room.add_npc(npc)
        npc.is_alive = False
        npc.stats["hp"] = 0

        game = _make_game(room, npc_templates=self.npc_templates)
        scheduler = Scheduler()
        scheduler._game = game

        scheduler.schedule_respawn("test", "npc_1", 0.05)
        await asyncio.sleep(0.15)

        assert npc.is_alive is True
        assert npc.stats["hp"] == 50

    @pytest.mark.asyncio
    async def test_respawn_npc_no_room(self):
        """Respawn with missing room is a no-op."""
        game = _make_game()
        game.room_manager.get_room.return_value = None
        scheduler = Scheduler()
        scheduler._game = game
        # Should not raise
        await scheduler.respawn_npc("nonexistent", "npc_1")


# ---------------------------------------------------------------------------
# Rare NPC spawn checks
# ---------------------------------------------------------------------------

class TestRareSpawnChecks:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.npc_templates = _load_test_templates()

    @pytest.mark.asyncio
    async def test_rare_spawn_success(self):
        """AC #2: Rare NPC spawns when roll succeeds."""
        room = _make_room()
        game = _make_game(room, npc_templates=self.npc_templates)
        scheduler = Scheduler()
        scheduler._game = game

        now = datetime.now(UTC)
        mock_cp = MagicMock()
        mock_cp.npc_key = "test_dragon"
        mock_cp.room_key = "test"
        mock_cp.next_check_at = now - timedelta(hours=1)  # overdue
        mock_cp.currently_spawned = False

        session = AsyncMock()
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        game.transaction = MagicMock(return_value=mock_ctx)
        with contextlib.nullcontext():

            # Return the checkpoint from query
            result_mock = MagicMock()
            result_mock.scalar_one_or_none.return_value = mock_cp
            session.execute = AsyncMock(return_value=result_mock)
            session.commit = AsyncMock()
            session.flush = AsyncMock()

            # Force spawn roll to succeed
            with patch("server.core.scheduler.random.random", return_value=0.01):
                await scheduler._run_rare_spawn_checks()

        # NPC should be added to room
        npc = room.get_npc("test_test_dragon_2_3")
        assert npc is not None
        assert npc.name == "Test Dragon"
        assert mock_cp.currently_spawned is True

    @pytest.mark.asyncio
    async def test_rare_spawn_roll_fails(self):
        """AC #2: No spawn when roll fails."""
        room = _make_room()
        game = _make_game(room, npc_templates=self.npc_templates)
        scheduler = Scheduler()
        scheduler._game = game

        now = datetime.now(UTC)
        mock_cp = MagicMock()
        mock_cp.npc_key = "test_dragon"
        mock_cp.room_key = "test"
        mock_cp.next_check_at = now - timedelta(hours=1)
        mock_cp.currently_spawned = False

        session = AsyncMock()
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        game.transaction = MagicMock(return_value=mock_ctx)
        with contextlib.nullcontext():

            result_mock = MagicMock()
            result_mock.scalar_one_or_none.return_value = mock_cp
            session.execute = AsyncMock(return_value=result_mock)
            session.commit = AsyncMock()

            # Force spawn roll to fail (0.99 > 0.5 chance)
            with patch("server.core.scheduler.random.random", return_value=0.99):
                await scheduler._run_rare_spawn_checks()

        # NPC should NOT be added
        npc = room.get_npc("test_test_dragon_2_3")
        assert npc is None
        assert mock_cp.currently_spawned is False

    @pytest.mark.asyncio
    async def test_max_active_prevents_duplicate(self):
        """AC #4: max_active=1 prevents spawning when already spawned."""
        room = _make_room()
        game = _make_game(room, npc_templates=self.npc_templates)
        scheduler = Scheduler()
        scheduler._game = game

        now = datetime.now(UTC)
        mock_cp = MagicMock()
        mock_cp.npc_key = "test_dragon"
        mock_cp.room_key = "test"
        mock_cp.next_check_at = now - timedelta(hours=1)
        mock_cp.currently_spawned = True  # Already spawned

        session = AsyncMock()
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        game.transaction = MagicMock(return_value=mock_ctx)
        with contextlib.nullcontext():

            result_mock = MagicMock()
            result_mock.scalar_one_or_none.return_value = mock_cp
            session.execute = AsyncMock(return_value=result_mock)
            session.commit = AsyncMock()

            with patch("server.core.scheduler.random.random", return_value=0.01):
                await scheduler._run_rare_spawn_checks()

        # NPC should NOT be added despite successful roll
        npc = room.get_npc("test_test_dragon_2_3")
        assert npc is None

    @pytest.mark.asyncio
    async def test_not_due_yet_skipped(self):
        """Spawn check not run when next_check_at is in the future."""
        room = _make_room()
        game = _make_game(room, npc_templates=self.npc_templates)
        scheduler = Scheduler()
        scheduler._game = game

        mock_cp = MagicMock()
        mock_cp.npc_key = "test_dragon"
        mock_cp.room_key = "test"
        mock_cp.next_check_at = datetime.now(UTC) + timedelta(hours=6)
        mock_cp.currently_spawned = False

        session = AsyncMock()
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        game.transaction = MagicMock(return_value=mock_ctx)
        with contextlib.nullcontext():

            result_mock = MagicMock()
            result_mock.scalar_one_or_none.return_value = mock_cp
            session.execute = AsyncMock(return_value=result_mock)
            session.commit = AsyncMock()

            with patch("server.core.scheduler.random.random", return_value=0.01):
                await scheduler._run_rare_spawn_checks()

        # Should NOT have spawned — not due yet
        npc = room.get_npc("test_test_dragon_2_3")
        assert npc is None


# ---------------------------------------------------------------------------
# Scheduler lifecycle
# ---------------------------------------------------------------------------

class TestSchedulerLifecycle:
    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        """Test scheduler can be started and stopped cleanly."""
        scheduler = Scheduler()
        game = _make_game()

        with patch.object(scheduler, "_recover_checkpoints", new_callable=AsyncMock):
            await scheduler.start(game)

        assert scheduler._running is True
        assert scheduler._task is not None
        assert not scheduler._task.done()

        await scheduler.stop()
        assert scheduler._running is False
        assert scheduler._task is None

    @pytest.mark.asyncio
    async def test_stop_cancels_respawn_tasks(self):
        """Stop cancels all pending respawn tasks."""
        scheduler = Scheduler()
        game = _make_game()

        with patch.object(scheduler, "_recover_checkpoints", new_callable=AsyncMock):
            await scheduler.start(game)

        # Add a respawn task
        scheduler.schedule_respawn("test", "npc_1", 100)
        assert len(scheduler._respawn_tasks) == 1

        await scheduler.stop()
        assert len(scheduler._respawn_tasks) == 0


# ---------------------------------------------------------------------------
# Checkpoint recovery
# ---------------------------------------------------------------------------

class TestCheckpointRecovery:
    @pytest.mark.asyncio
    async def test_recover_checkpoints_logs_overdue(self):
        """AC #3: Overdue checkpoints are detected on startup."""
        scheduler = Scheduler()
        game = _make_game()
        scheduler._game = game
        now = datetime.now(UTC)

        mock_cp = MagicMock()
        mock_cp.npc_key = "test_dragon"
        mock_cp.room_key = "test"
        mock_cp.next_check_at = now - timedelta(hours=2)  # overdue

        session = AsyncMock()
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        game.transaction = MagicMock(return_value=mock_ctx)
        with contextlib.nullcontext():

            result_mock = MagicMock()
            scalars_mock = MagicMock()
            scalars_mock.all.return_value = [mock_cp]
            result_mock.scalars.return_value = scalars_mock
            session.execute = AsyncMock(return_value=result_mock)

            # Should not raise
            await scheduler._recover_checkpoints()


# ---------------------------------------------------------------------------
# Kill NPC hook (Game.kill_npc)
# ---------------------------------------------------------------------------

class TestKillNpcHook:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.npc_templates = _load_test_templates()

    @pytest.mark.asyncio
    async def test_kill_npc_marks_dead_and_schedules_respawn(self):
        """AC #1: kill_npc sets is_alive=False and schedules respawn for persistent."""
        room = _make_room()
        npc = create_npc_from_template("test_goblin", "npc_1", 3, 3, templates=self.npc_templates)
        assert npc is not None
        room.add_npc(npc)

        game = make_bare_game(npc_templates=self.npc_templates)
        game.room_manager.get_room.return_value = room
        game.scheduler.schedule_respawn = MagicMock()

        await game.kill_npc("test", "npc_1")

        assert npc.is_alive is False
        game.scheduler.schedule_respawn.assert_called_once_with("test", "npc_1", 0.1)

    @pytest.mark.asyncio
    async def test_kill_npc_dead_npc_noop(self):
        """Killing an already-dead NPC is a no-op."""
        room = _make_room()
        npc = create_npc_from_template("test_goblin", "npc_1", 3, 3, templates=self.npc_templates)
        assert npc is not None
        npc.is_alive = False
        room.add_npc(npc)

        game = make_bare_game(npc_templates=self.npc_templates)
        game.room_manager.get_room.return_value = room

        await game.kill_npc("test", "npc_1")
        game.scheduler.schedule_respawn.assert_not_called()
