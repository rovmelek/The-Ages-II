"""Tests for heartbeat / connection health (Story 16.8)."""
from __future__ import annotations

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from server.core.config import settings
from tests.conftest import make_bare_game


class TestHeartbeatConfig:
    """Verify heartbeat settings exist and are configurable."""

    def test_heartbeat_interval_exists(self):
        assert hasattr(settings, "HEARTBEAT_INTERVAL_SECONDS")
        assert settings.HEARTBEAT_INTERVAL_SECONDS == 30

    def test_heartbeat_timeout_exists(self):
        assert hasattr(settings, "HEARTBEAT_TIMEOUT_SECONDS")
        assert settings.HEARTBEAT_TIMEOUT_SECONDS == 10


class TestPongSchema:
    """Verify PongMessage schema."""

    def test_pong_schema_exists(self):
        from server.net.schemas import PongMessage, ACTION_SCHEMAS
        assert "pong" in ACTION_SCHEMAS
        assert ACTION_SCHEMAS["pong"] is PongMessage

    def test_pong_schema_valid(self):
        from server.net.schemas import PongMessage
        m = PongMessage(action="pong")
        assert m.action == "pong"


class TestPingOutboundSchema:
    """Verify PingMessage outbound schema."""

    def test_ping_schema_exists(self):
        from server.net.outbound_schemas import PingMessage
        m = PingMessage()
        assert m.type == "ping"
        assert m.model_dump() == {"type": "ping"}


class TestHeartbeatLifecycle:
    """Test heartbeat task lifecycle on Game."""

    def _make_game(self):
        """Create a minimal Game-like object with heartbeat support."""
        return make_bare_game()

    def test_start_heartbeat_creates_task_and_event(self):
        game = self._make_game()
        ws = AsyncMock()
        game.connection_manager.get_websocket.return_value = ws

        with patch("asyncio.create_task") as mock_create:
            mock_task = MagicMock()
            def _consume_coro(coro):
                coro.close()
                return mock_task
            mock_create.side_effect = _consume_coro
            game._start_heartbeat("player_1")

        assert "player_1" in game._heartbeat_tasks
        assert "player_1" in game._pong_events
        assert isinstance(game._pong_events["player_1"], asyncio.Event)

    def test_cancel_heartbeat_removes_task_and_event(self):
        game = self._make_game()
        mock_task = MagicMock()
        mock_task.done.return_value = False
        game._heartbeat_tasks["player_1"] = mock_task
        game._pong_events["player_1"] = asyncio.Event()

        game._cancel_heartbeat("player_1")

        assert "player_1" not in game._heartbeat_tasks
        assert "player_1" not in game._pong_events
        mock_task.cancel.assert_called_once()

    def test_cancel_heartbeat_noop_for_unknown(self):
        game = self._make_game()
        # Should not raise
        game._cancel_heartbeat("nonexistent")

    def test_start_heartbeat_cancels_existing_first(self):
        game = self._make_game()
        old_task = MagicMock()
        old_task.done.return_value = False
        game._heartbeat_tasks["player_1"] = old_task
        game._pong_events["player_1"] = asyncio.Event()

        with patch("asyncio.create_task") as mock_create:
            def _consume_coro(coro):
                coro.close()
                return MagicMock()
            mock_create.side_effect = _consume_coro
            game._start_heartbeat("player_1")

        old_task.cancel.assert_called_once()
        assert "player_1" in game._heartbeat_tasks


class TestHeartbeatLoop:
    """Test the heartbeat loop behavior."""

    async def test_heartbeat_sends_ping(self):
        """Heartbeat loop sends ping after interval."""
        game = make_bare_game()

        ws = AsyncMock()
        game.connection_manager.get_websocket.return_value = ws

        event = asyncio.Event()
        game._pong_events["player_1"] = event

        # Run heartbeat with short interval, simulate pong then stop
        with patch.object(settings, "HEARTBEAT_INTERVAL_SECONDS", 0.01), \
             patch.object(settings, "HEARTBEAT_TIMEOUT_SECONDS", 0.01):

            async def _set_and_clear():
                await asyncio.sleep(0.02)
                event.set()
                await asyncio.sleep(0.02)
                # Remove event to break loop
                game._pong_events.pop("player_1", None)

            task = asyncio.create_task(game._heartbeat_loop("player_1"))
            helper = asyncio.create_task(_set_and_clear())

            await asyncio.wait_for(task, timeout=1.0)
            helper.cancel()

        # Should have sent at least one ping
        assert ws.send_json.call_count >= 1
        sent = ws.send_json.call_args_list[0][0][0]
        assert sent == {"type": "ping"}

    async def test_heartbeat_timeout_closes_ws(self):
        """Heartbeat closes WebSocket when pong not received within timeout."""
        game = make_bare_game()

        ws = AsyncMock()
        game.connection_manager.get_websocket.return_value = ws

        event = asyncio.Event()
        game._pong_events["player_1"] = event

        with patch.object(settings, "HEARTBEAT_INTERVAL_SECONDS", 0.01), \
             patch.object(settings, "HEARTBEAT_TIMEOUT_SECONDS", 0.01):
            task = asyncio.create_task(game._heartbeat_loop("player_1"))
            await asyncio.wait_for(task, timeout=1.0)

        # Should have closed the WebSocket
        ws.close.assert_called_once_with(code=1001)


class TestHandleDisconnectCancelsHeartbeat:
    """Verify handle_disconnect cancels heartbeat before cleanup."""

    async def test_disconnect_cancels_heartbeat(self):
        game = make_bare_game()
        game.player_manager.get_session.return_value = MagicMock(disconnected_at=None)
        game.player_manager.cancel_trade = AsyncMock()
        game.player_manager.deferred_cleanup = AsyncMock()

        ws = MagicMock()
        game.connection_manager.get_entity_id.return_value = "player_1"

        mock_task = MagicMock()
        mock_task.done.return_value = False
        game._heartbeat_tasks["player_1"] = mock_task
        game._pong_events["player_1"] = asyncio.Event()

        await game.handle_disconnect(ws)

        # Heartbeat cancelled
        mock_task.cancel.assert_called_once()
        assert "player_1" not in game._heartbeat_tasks
        # Cleanup still happened (deferred_cleanup since DISCONNECT_GRACE_SECONDS=0)
        game.player_manager.deferred_cleanup.assert_called_once_with("player_1", game)


class TestShutdownCancelsHeartbeats:
    """Verify shutdown cancels all heartbeat tasks."""

    async def test_shutdown_cancels_all(self):
        game = make_bare_game()
        game.player_manager.all_entity_ids.return_value = []
        game.player_manager.clear = MagicMock()
        game.scheduler.stop = AsyncMock()

        task1 = MagicMock()
        task1.done.return_value = False
        task2 = MagicMock()
        task2.done.return_value = False
        game._heartbeat_tasks["p1"] = task1
        game._heartbeat_tasks["p2"] = task2
        game._pong_events["p1"] = asyncio.Event()
        game._pong_events["p2"] = asyncio.Event()

        await game.shutdown()

        task1.cancel.assert_called_once()
        task2.cancel.assert_called_once()
        assert len(game._heartbeat_tasks) == 0
        assert len(game._pong_events) == 0


class TestPongHandler:
    """Test the pong handler."""

    async def test_pong_sets_event(self):
        from server.net.handlers.auth import handle_pong

        game = MagicMock()
        event = asyncio.Event()
        game._pong_events = {"player_1": event}

        ws = AsyncMock()
        player_info = MagicMock()

        await handle_pong.__wrapped__(
            ws, {"action": "pong"}, game=game,
            entity_id="player_1", player_info=player_info,
        )

        assert event.is_set()

    async def test_pong_noop_without_event(self):
        from server.net.handlers.auth import handle_pong

        game = MagicMock()
        game._pong_events = {}

        ws = AsyncMock()
        player_info = MagicMock()

        # Should not raise
        await handle_pong.__wrapped__(
            ws, {"action": "pong"}, game=game,
            entity_id="player_1", player_info=player_info,
        )


class TestDuplicateLoginHeartbeat:
    """Test that duplicate login cancels old heartbeat and starts new."""

    async def test_kick_cancels_heartbeat(self):
        from server.net.handlers.auth import _kick_old_session

        game = MagicMock()
        game._cancel_heartbeat = MagicMock()
        game.player_manager = MagicMock()
        game.player_manager.cleanup_session = AsyncMock()

        old_ws = AsyncMock()

        await _kick_old_session("player_1", old_ws, game)

        game._cancel_heartbeat.assert_called_once_with("player_1")
        game.player_manager.cleanup_session.assert_called_once()
