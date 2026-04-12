"""Tests for EventBus, broadcast_to_all, and rare spawn announcements."""
from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.core.events import EventBus
from server.net.connection_manager import ConnectionManager


# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------

class TestEventBus:
    @pytest.mark.asyncio
    async def test_subscribe_and_emit(self):
        bus = EventBus()
        received = []

        async def handler(**data):
            received.append(data)

        bus.subscribe("test_event", handler)
        await bus.emit("test_event", foo="bar", num=42)

        assert len(received) == 1
        assert received[0] == {"foo": "bar", "num": 42}

    @pytest.mark.asyncio
    async def test_emit_no_subscribers(self):
        """Emit with no subscribers should not raise."""
        bus = EventBus()
        await bus.emit("nonexistent_event", data="test")

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self):
        bus = EventBus()
        calls = []

        async def handler_a(**data):
            calls.append("a")

        async def handler_b(**data):
            calls.append("b")

        bus.subscribe("evt", handler_a)
        bus.subscribe("evt", handler_b)
        await bus.emit("evt")

        assert calls == ["a", "b"]

    @pytest.mark.asyncio
    async def test_different_event_types(self):
        bus = EventBus()
        results = []

        async def handler_x(**data):
            results.append("x")

        async def handler_y(**data):
            results.append("y")

        bus.subscribe("event_x", handler_x)
        bus.subscribe("event_y", handler_y)

        await bus.emit("event_x")
        assert results == ["x"]

    @pytest.mark.asyncio
    async def test_emit_subscriber_error_isolation(self):
        """A failing subscriber must not prevent remaining subscribers from running."""
        bus = EventBus()
        calls = []

        async def bad_handler(**data):
            raise RuntimeError("boom")

        async def good_handler(**data):
            calls.append("ok")

        bus.subscribe("evt", bad_handler)
        bus.subscribe("evt", good_handler)
        await bus.emit("evt")

        assert calls == ["ok"]


# ---------------------------------------------------------------------------
# ConnectionManager.broadcast_to_all
# ---------------------------------------------------------------------------

class TestBroadcastToAll:
    @pytest.mark.asyncio
    async def test_broadcast_to_all_sends_to_all(self):
        """AC #1: broadcast_to_all sends to ALL connected players."""
        cm = ConnectionManager()
        ws1 = MagicMock()
        ws1.send_json = AsyncMock()
        ws2 = MagicMock()
        ws2.send_json = AsyncMock()

        cm.connect("p1", ws1, "room_a")
        cm.connect("p2", ws2, "room_b")

        msg = {"type": "announcement", "message": "Hello all!"}
        await cm.broadcast_to_all(msg)

        ws1.send_json.assert_called_once_with(msg)
        ws2.send_json.assert_called_once_with(msg)

    @pytest.mark.asyncio
    async def test_broadcast_to_all_no_connections(self):
        """AC #3: No connections → no error."""
        cm = ConnectionManager()
        await cm.broadcast_to_all({"type": "announcement", "message": "Nobody here"})
        # Should not raise


# ---------------------------------------------------------------------------
# Rare spawn announcement integration
# ---------------------------------------------------------------------------

class TestRareSpawnAnnouncement:
    @pytest.mark.asyncio
    async def test_rare_spawn_triggers_announcement(self):
        """AC #1, #2: Rare spawn emits event → broadcast_to_all with announcement."""
        from server.app import Game

        game = Game.__new__(Game)
        game.connection_manager = MagicMock()
        game.connection_manager.broadcast_to_all = AsyncMock()
        game.event_bus = EventBus()

        # Register events the same way Game does
        game._register_events()

        await game.event_bus.emit("rare_spawn", npc_name="Ancient Forest Dragon", room_name="Dark Cave")

        game.connection_manager.broadcast_to_all.assert_called_once()
        call_msg = game.connection_manager.broadcast_to_all.call_args[0][0]
        assert call_msg["type"] == "announcement"
        assert "Ancient Forest Dragon" in call_msg["message"]
        assert "Dark Cave" in call_msg["message"]

    @pytest.mark.asyncio
    async def test_announcement_message_format(self):
        """Announcement format: '<NPC name> has appeared in <room name>!'"""
        from server.app import Game

        game = Game.__new__(Game)
        game.connection_manager = MagicMock()
        game.connection_manager.broadcast_to_all = AsyncMock()
        game.event_bus = EventBus()
        game._register_events()

        await game.event_bus.emit("rare_spawn", npc_name="Test Dragon", room_name="Test Room")

        msg = game.connection_manager.broadcast_to_all.call_args[0][0]
        assert msg == {
            "type": "announcement",
            "message": "Test Dragon has appeared in Test Room!",
        }

    @pytest.mark.asyncio
    async def test_scheduler_emits_rare_spawn_event(self):
        """AC #1: Scheduler emits rare_spawn event after successful spawn."""
        from server.core.scheduler import Scheduler
        from server.room.npc import load_npc_templates
        from server.room.room import RoomInstance

        templates = [
            {
                "npc_key": "evt_dragon",
                "name": "Event Dragon",
                "behavior_type": "hostile",
                "spawn_type": "rare",
                "spawn_config": {
                    "check_interval_hours": 12,
                    "spawn_chance": 1.0,  # Always spawn
                    "max_active": 1,
                    "room_key": "evt_room",
                    "x": 1,
                    "y": 1,
                },
                "stats": {"hp": 100},
            },
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "test.json"
            p.write_text(json.dumps(templates))
            npc_templates = load_npc_templates(Path(tmpdir))

        tile_data = [[0] * 5 for _ in range(5)]
        room = RoomInstance(
            room_key="evt_room", name="Event Room", width=5, height=5,
            tile_data=tile_data, spawn_points=[{"type": "player", "x": 0, "y": 0}],
        )

        game = MagicMock()
        game.room_manager.get_room.return_value = room
        game.connection_manager.broadcast_to_room = AsyncMock()
        game.event_bus = MagicMock()
        game.event_bus.emit = AsyncMock()
        game.npc_templates = npc_templates

        scheduler = Scheduler()
        scheduler._game = game

        now = datetime.now(UTC)
        mock_cp = MagicMock()
        mock_cp.npc_key = "evt_dragon"
        mock_cp.room_key = "evt_room"
        mock_cp.next_check_at = now - timedelta(hours=1)
        mock_cp.currently_spawned = False

        session = AsyncMock()
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        game.transaction = MagicMock(return_value=mock_ctx)

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = mock_cp
        session.execute = AsyncMock(return_value=result_mock)
        session.commit = AsyncMock()

        await scheduler._run_rare_spawn_checks()

        # event_bus.emit should have been called with rare_spawn
        game.event_bus.emit.assert_called_once_with(
            "rare_spawn",
            npc_name="Event Dragon",
            room_name="Event Room",
        )
