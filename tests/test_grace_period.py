"""Tests for disconnected player grace period (Story 16.10)."""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.core.config import settings
from server.player.entity import PlayerEntity
from server.player.session import PlayerSession
from tests.conftest import make_bare_game


def _make_game():
    """Create a Game for grace period testing with async-safe mocks."""
    game = make_bare_game()
    game.connection_manager.get_entity_id.return_value = "player_1"
    game.connection_manager.get_websocket.return_value = None
    game.connection_manager.broadcast_to_room = AsyncMock()
    game.connection_manager.send_to_player = AsyncMock()
    game.player_manager.cancel_trade = AsyncMock()
    game.player_manager.cleanup_session = AsyncMock()
    game.player_manager.deferred_cleanup = AsyncMock()
    game.combat_manager.get_player_instance.return_value = None
    return game


def _make_session(entity_id="player_1", room_key="town_square", db_id=1):
    """Create a PlayerSession with entity."""
    entity = PlayerEntity(
        id=entity_id, name="testuser", x=5, y=5,
        player_db_id=db_id, stats={"hp": 100, "max_hp": 100, "level": 1},
    )
    return PlayerSession(entity=entity, room_key=room_key, db_id=db_id)


class TestHandleDisconnectGracePeriod:
    """Test handle_disconnect with grace period > 0."""

    async def test_disconnect_schedules_deferred_cleanup(self, monkeypatch):
        """With DISCONNECT_GRACE_SECONDS > 0, session stays alive."""
        monkeypatch.setattr(settings, "DISCONNECT_GRACE_SECONDS", 120)
        game = _make_game()
        session = _make_session()
        game.player_manager.get_session.return_value = session

        ws = MagicMock()
        await game.handle_disconnect(ws)

        # Session kept alive
        game.player_manager.deferred_cleanup.assert_not_called()
        game.player_manager.cleanup_session.assert_not_called()

        # WebSocket mapping removed
        game.connection_manager.disconnect.assert_called_once_with("player_1")

        # Trades cancelled immediately
        game.player_manager.cancel_trade.assert_called_once_with("player_1", game)

        # Entity marked disconnected
        assert session.disconnected_at is not None
        assert session.entity.connected is False

        # Timer handle stored
        assert "player_1" in game._cleanup_handles

        # Cleanup the timer to prevent warnings
        game._cleanup_handles["player_1"].cancel()

    async def test_disconnect_immediate_when_grace_zero(self):
        """With DISCONNECT_GRACE_SECONDS=0, cleanup runs immediately."""
        # Default is 0 via autouse fixture
        assert settings.DISCONNECT_GRACE_SECONDS == 0
        game = _make_game()
        session = _make_session()
        game.player_manager.get_session.return_value = session

        ws = MagicMock()
        await game.handle_disconnect(ws)

        # Deferred cleanup called immediately (not via timer)
        game.player_manager.deferred_cleanup.assert_called_once_with("player_1", game)
        assert "player_1" not in game._cleanup_handles

    async def test_disconnect_during_shutdown_returns_early(self):
        """When _shutting_down is True, handle_disconnect returns without action."""
        game = _make_game()
        game._shutting_down = True
        session = _make_session()
        game.player_manager.get_session.return_value = session

        ws = MagicMock()
        await game.handle_disconnect(ws)

        # No cleanup happened
        game.player_manager.deferred_cleanup.assert_not_called()
        game.player_manager.cleanup_session.assert_not_called()
        game.connection_manager.disconnect.assert_not_called()

    async def test_disconnect_no_session_disconnects_ws(self):
        """If no session exists, just disconnect the WebSocket mapping."""
        game = _make_game()
        game.player_manager.get_session.return_value = None

        ws = MagicMock()
        await game.handle_disconnect(ws)

        game.connection_manager.disconnect.assert_called_once_with("player_1")
        game.player_manager.deferred_cleanup.assert_not_called()

    async def test_disconnect_cancels_existing_timer(self, monkeypatch):
        """Idempotent: existing timer cancelled before new one stored."""
        monkeypatch.setattr(settings, "DISCONNECT_GRACE_SECONDS", 120)
        game = _make_game()
        session = _make_session()
        game.player_manager.get_session.return_value = session

        # Pre-existing timer
        old_handle = MagicMock()
        game._cleanup_handles["player_1"] = old_handle

        ws = MagicMock()
        await game.handle_disconnect(ws)

        # Old timer cancelled
        old_handle.cancel.assert_called_once()
        # New timer stored
        assert "player_1" in game._cleanup_handles
        assert game._cleanup_handles["player_1"] is not old_handle

        # Cleanup new timer
        game._cleanup_handles["player_1"].cancel()


class TestDeferredCleanup:
    """Test Game._deferred_cleanup method."""

    async def test_deferred_cleanup_runs_when_disconnected(self):
        """Grace period expired — full cleanup runs."""
        game = _make_game()
        session = _make_session()
        session.disconnected_at = time.time() - 200
        game.player_manager.get_session.return_value = session

        await game._deferred_cleanup("player_1")

        game.player_manager.deferred_cleanup.assert_called_once_with("player_1", game)

    async def test_deferred_cleanup_skips_if_reconnected(self):
        """Player reconnected — disconnected_at is None, skip cleanup."""
        game = _make_game()
        session = _make_session()
        session.disconnected_at = None  # Reconnected
        game.player_manager.get_session.return_value = session

        await game._deferred_cleanup("player_1")

        game.player_manager.deferred_cleanup.assert_not_called()

    async def test_deferred_cleanup_skips_if_no_session(self):
        """Session already cleaned up — no-op."""
        game = _make_game()
        game.player_manager.get_session.return_value = None

        await game._deferred_cleanup("player_1")

        game.player_manager.deferred_cleanup.assert_not_called()


class TestPlayerManagerDeferredCleanup:
    """Test PlayerManager.deferred_cleanup public method."""

    async def test_deferred_cleanup_cleans_combat_party_room(self):
        """Deferred cleanup handles combat, party, save, and room removal."""
        from server.player.manager import PlayerManager

        pm = PlayerManager()
        session = _make_session()
        pm.set_session("player_1", session)

        game = MagicMock()
        game.combat_manager = MagicMock()
        game.party_manager = MagicMock()
        game.party_manager.handle_disconnect.return_value = (None, None)
        game.party_manager.cleanup_invites = MagicMock()
        game.room_manager = MagicMock()
        game.connection_manager = MagicMock()
        game.connection_manager.broadcast_to_room = AsyncMock()

        mock_ctx = MagicMock()
        mock_session = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        game.transaction = MagicMock(return_value=mock_ctx)

        with patch("server.player.manager.player_repo") as mock_repo:
            mock_repo.update_position = AsyncMock()
            mock_repo.update_stats = AsyncMock()
            mock_repo.update_inventory = AsyncMock()
            mock_repo.update_visited_rooms = AsyncMock()

            await pm.deferred_cleanup("player_1", game)

        # Session removed
        assert pm.get_session("player_1") is None

    async def test_deferred_cleanup_no_session_is_noop(self):
        """No session — deferred_cleanup returns without error."""
        from server.player.manager import PlayerManager

        pm = PlayerManager()
        game = MagicMock()
        await pm.deferred_cleanup("player_99", game)
        # No error raised


class TestHandleLoginGracePeriod:
    """Test handle_login detecting grace-period sessions."""

    async def test_login_during_grace_period_cleans_up_old(self):
        """Login from another device cancels timer and cleans up old session."""
        game = MagicMock()
        game.token_store = MagicMock()
        game.token_store.issue.return_value = "new_token"
        game.connection_manager = MagicMock()
        game.connection_manager.get_websocket.return_value = None
        game.connection_manager.broadcast_to_room = AsyncMock()
        game.room_manager = MagicMock()
        game.player_manager = MagicMock()
        game.player_manager.cleanup_session = AsyncMock()
        game.player_manager.get_session.return_value = _make_session()  # Grace period session
        game.combat_manager = MagicMock()
        game._start_heartbeat = MagicMock()
        game._cancel_heartbeat = MagicMock()
        game._cleanup_handles = {}

        # Set up a pending cleanup timer
        mock_handle = MagicMock()
        game._cleanup_handles["player_1"] = mock_handle

        mock_ctx = MagicMock()
        mock_session = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        game.transaction = MagicMock(return_value=mock_ctx)

        mock_player = MagicMock()
        mock_player.id = 1
        mock_player.username = "testuser"
        mock_player.stats = {"hp": 100, "max_hp": 100, "attack": 10, "xp": 0, "level": 1}
        mock_player.current_room_id = "town_square"
        mock_player.position_x = 5
        mock_player.position_y = 5
        mock_player.inventory = {}
        mock_player.visited_rooms = ["town_square"]

        mock_room = MagicMock()
        mock_room.is_walkable.return_value = True
        mock_room.get_state.return_value = {"room_key": "town_square", "name": "TS", "width": 5, "height": 5, "tiles": [], "entities": [], "npcs": [], "exits": [], "objects": []}
        game.room_manager.get_room.return_value = mock_room

        ws = AsyncMock()

        with patch("server.net.handlers.auth.player_repo") as mock_repo, \
             patch("server.net.handlers.auth.verify_password", return_value=True), \
             patch("server.net.handlers.auth.item_repo"):
            mock_repo.get_by_username = AsyncMock(return_value=mock_player)
            mock_repo.update_stats = AsyncMock()
            mock_repo.update_position = AsyncMock()

            from server.net.handlers.auth import handle_login
            await handle_login(ws, {"action": "login", "username": "testuser", "password": "pass"}, game=game)

        # Timer was cancelled
        mock_handle.cancel.assert_called_once()
        # Old session cleaned up
        game.player_manager.cleanup_session.assert_called()


class TestGetStateConnectedField:
    """Test that get_state() includes connected field."""

    def test_entity_connected_true(self):
        """Connected entity has connected: true in get_state."""
        from server.room.room import RoomInstance

        room = RoomInstance.__new__(RoomInstance)
        room.room_key = "test"
        room.name = "Test Room"
        room.width = 5
        room.height = 5
        room._grid = [[0] * 5 for _ in range(5)]
        room.exits = []
        room.objects = []
        room._npcs = {}
        room._entities = {}

        entity = PlayerEntity(
            id="player_1", name="test", x=1, y=1,
            player_db_id=1, stats={"level": 3},
        )
        room._entities["player_1"] = entity

        state = room.get_state()
        assert len(state["entities"]) == 1
        assert state["entities"][0]["connected"] is True

    def test_entity_connected_false(self):
        """Disconnected entity has connected: false in get_state."""
        from server.room.room import RoomInstance

        room = RoomInstance.__new__(RoomInstance)
        room.room_key = "test"
        room.name = "Test Room"
        room.width = 5
        room.height = 5
        room._grid = [[0] * 5 for _ in range(5)]
        room.exits = []
        room.objects = []
        room._npcs = {}
        room._entities = {}

        entity = PlayerEntity(
            id="player_1", name="test", x=1, y=1,
            player_db_id=1, stats={"level": 3},
            connected=False,
        )
        room._entities["player_1"] = entity

        state = room.get_state()
        assert state["entities"][0]["connected"] is False


class TestShutdownCancelsCleanupHandles:
    """Test that shutdown cancels all pending deferred cleanup timers."""

    async def test_shutdown_cancels_cleanup_handles(self):
        game = make_bare_game()
        game.player_manager.all_entity_ids.return_value = []
        game.player_manager.clear = MagicMock()
        game.scheduler.stop = AsyncMock()

        handle1 = MagicMock()
        handle2 = MagicMock()
        game._cleanup_handles["player_1"] = handle1
        game._cleanup_handles["player_2"] = handle2

        await game.shutdown()

        handle1.cancel.assert_called_once()
        handle2.cancel.assert_called_once()
        assert len(game._cleanup_handles) == 0
