"""Tests for message acknowledgment IDs (Story 16.11)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.net.connection_manager import ConnectionManager


# =========================================================================
# ConnectionManager msg_seq unit tests
# =========================================================================


class TestMsgSeqInit:
    def test_connect_initializes_seq_to_zero(self):
        cm = ConnectionManager()
        ws = MagicMock()
        cm.connect("player_1", ws, "town_square", name="alice")
        assert cm.get_msg_seq("player_1") == 0

    def test_connect_preserves_existing_seq(self):
        """setdefault preserves value on reconnect."""
        cm = ConnectionManager()
        ws = MagicMock()
        cm.connect("player_1", ws, "town_square", name="alice")
        # Simulate some messages sent
        cm._msg_seq["player_1"] = 42
        # Reconnect
        ws2 = MagicMock()
        cm.connect("player_1", ws2, "town_square", name="alice")
        assert cm.get_msg_seq("player_1") == 42

    def test_get_msg_seq_unknown_player(self):
        cm = ConnectionManager()
        assert cm.get_msg_seq("player_99") == 0


class TestMsgSeqDisconnect:
    def test_disconnect_does_not_remove_seq(self):
        """Grace period needs seq to survive disconnect."""
        cm = ConnectionManager()
        ws = MagicMock()
        cm.connect("player_1", ws, "town_square", name="alice")
        cm._msg_seq["player_1"] = 5
        cm.disconnect("player_1")
        assert cm.get_msg_seq("player_1") == 5

    def test_clear_msg_seq_removes_counter(self):
        cm = ConnectionManager()
        cm._msg_seq["player_1"] = 10
        cm.clear_msg_seq("player_1")
        assert cm.get_msg_seq("player_1") == 0

    def test_clear_msg_seq_nonexistent_is_noop(self):
        cm = ConnectionManager()
        cm.clear_msg_seq("player_99")  # no error


class TestSendToPlayerSeq:
    async def test_increments_and_attaches_seq(self):
        cm = ConnectionManager()
        ws = AsyncMock()
        cm.connect("player_1", ws, "town_square", name="alice")

        msg = {"type": "combat_turn", "data": "test"}
        await cm.send_to_player_seq("player_1", msg)

        # Original message NOT mutated
        assert "seq" not in msg

        # WebSocket received message with seq
        ws.send_json.assert_called_once()
        sent = ws.send_json.call_args[0][0]
        assert sent["seq"] == 1
        assert sent["type"] == "combat_turn"

    async def test_seq_monotonically_increases(self):
        cm = ConnectionManager()
        ws = AsyncMock()
        cm.connect("player_1", ws, "town_square", name="alice")

        sent_seqs = []
        ws.send_json = AsyncMock(side_effect=lambda m: sent_seqs.append(m["seq"]))

        await cm.send_to_player_seq("player_1", {"type": "a"})
        await cm.send_to_player_seq("player_1", {"type": "b"})
        await cm.send_to_player_seq("player_1", {"type": "c"})

        assert sent_seqs == [1, 2, 3]
        assert cm.get_msg_seq("player_1") == 3

    async def test_seq_independent_per_player(self):
        cm = ConnectionManager()
        ws_a = AsyncMock()
        ws_b = AsyncMock()
        cm.connect("player_1", ws_a, "room", name="a")
        cm.connect("player_2", ws_b, "room", name="b")

        await cm.send_to_player_seq("player_1", {"type": "x"})
        await cm.send_to_player_seq("player_1", {"type": "y"})
        await cm.send_to_player_seq("player_2", {"type": "z"})

        assert cm.get_msg_seq("player_1") == 2
        assert cm.get_msg_seq("player_2") == 1

    async def test_increments_even_without_websocket(self):
        """Grace period: counter still increments for disconnected player."""
        cm = ConnectionManager()
        ws = AsyncMock()
        cm.connect("player_1", ws, "room", name="a")
        cm.disconnect("player_1")  # WS gone, seq stays

        await cm.send_to_player_seq("player_1", {"type": "combat_turn"})

        assert cm.get_msg_seq("player_1") == 1
        ws.send_json.assert_not_called()  # No WS, but counter incremented

    async def test_does_not_mutate_original_dict(self):
        """Aliasing safety: same dict sent to two players gets independent seq."""
        cm = ConnectionManager()
        ws_a = AsyncMock()
        ws_b = AsyncMock()
        cm.connect("player_1", ws_a, "room", name="a")
        cm.connect("player_2", ws_b, "room", name="b")

        msg = {"type": "trade_update", "state": "negotiating"}
        await cm.send_to_player_seq("player_1", msg)
        await cm.send_to_player_seq("player_2", msg)

        # Original dict unchanged
        assert "seq" not in msg

        # Each player got their own seq
        sent_a = ws_a.send_json.call_args[0][0]
        sent_b = ws_b.send_json.call_args[0][0]
        assert sent_a["seq"] == 1
        assert sent_b["seq"] == 1  # Independent counter

    async def test_handles_dead_connection(self):
        """Exception from ws.send_json is caught — seq still incremented."""
        cm = ConnectionManager()
        ws = AsyncMock()
        ws.send_json.side_effect = Exception("Connection lost")
        cm.connect("player_1", ws, "room", name="a")

        await cm.send_to_player_seq("player_1", {"type": "test"})

        assert cm.get_msg_seq("player_1") == 1  # Still incremented


# =========================================================================
# Reconnect last_seq check
# =========================================================================


class TestReconnectLastSeq:
    @pytest.fixture
    def mock_game(self):
        from server.player.tokens import TokenStore

        game = MagicMock()
        game.token_store = TokenStore()
        game.connection_manager = MagicMock()
        game.connection_manager.get_entity_id.return_value = None
        game.connection_manager.get_websocket.return_value = None
        game.connection_manager.broadcast_to_room = AsyncMock()
        game.connection_manager.send_to_player = AsyncMock()
        game.connection_manager.send_to_player_seq = AsyncMock()
        game.connection_manager.get_msg_seq.return_value = 5
        game.room_manager = MagicMock()
        game.player_manager = MagicMock()
        game.player_manager.get_session.return_value = None
        game.player_manager.cleanup_session = AsyncMock()
        game.combat_manager = MagicMock()
        game.combat_manager.get_player_instance.return_value = None
        game._start_heartbeat = MagicMock()
        game._cancel_heartbeat = MagicMock()
        game._cleanup_handles = {}

        mock_ctx = MagicMock()
        mock_session = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        game.transaction = MagicMock(return_value=mock_ctx)
        return game, mock_session

    async def test_reconnect_case1_with_matching_last_seq(self, mock_game):
        """Case 1 (grace period resume): last_seq matches → seq_status: up_to_date sent."""
        from server.player.entity import PlayerEntity
        from server.player.session import PlayerSession
        import time

        game, mock_session = mock_game
        token = game.token_store.issue(1)

        # Set up a grace-period session (disconnected_at set)
        entity = PlayerEntity(
            id="player_1", name="test", x=5, y=5,
            player_db_id=1, stats={"hp": 100, "max_hp": 100, "level": 1},
        )
        session = PlayerSession(entity=entity, room_key="town_square", db_id=1,
                                disconnected_at=time.time() - 10)
        game.player_manager.get_session.return_value = session
        game.connection_manager.get_msg_seq.return_value = 5

        mock_room = MagicMock()
        mock_room.get_state.return_value = {"room_key": "t", "name": "T", "width": 5, "height": 5, "tiles": [], "entities": [], "npcs": [], "exits": [], "objects": []}
        game.room_manager.get_room.return_value = mock_room

        ws = AsyncMock()
        sent = []
        ws.send_json = AsyncMock(side_effect=lambda m: sent.append(m))

        from server.net.handlers.auth import handle_reconnect
        await handle_reconnect(ws, {"action": "reconnect", "session_token": token, "last_seq": 5}, game=game)

        # Should have seq_status: up_to_date
        seq_msgs = [m for m in sent if m.get("type") == "seq_status"]
        assert len(seq_msgs) == 1
        assert seq_msgs[0]["status"] == "up_to_date"

    async def test_reconnect_without_last_seq(self, mock_game):
        """No last_seq → no seq_status sent (full resync only)."""
        game, mock_session = mock_game
        token = game.token_store.issue(1)

        mock_player = MagicMock()
        mock_player.id = 1
        mock_player.username = "test"
        mock_player.stats = {"hp": 100, "max_hp": 100, "attack": 10, "xp": 0, "level": 1}
        mock_player.current_room_id = "town_square"
        mock_player.position_x = 5
        mock_player.position_y = 5
        mock_player.inventory = {}
        mock_player.visited_rooms = ["town_square"]

        mock_room = MagicMock()
        mock_room.is_walkable.return_value = True
        mock_room.get_state.return_value = {"room_key": "t", "name": "T", "width": 5, "height": 5, "tiles": [], "entities": [], "npcs": [], "exits": [], "objects": []}
        game.room_manager.get_room.return_value = mock_room

        ws = AsyncMock()
        sent = []
        ws.send_json = AsyncMock(side_effect=lambda m: sent.append(m))

        with patch("server.net.handlers.auth.player_repo") as mock_repo, \
             patch("server.net.handlers.auth.item_repo"):
            mock_repo.get_by_id = AsyncMock(return_value=mock_player)
            mock_repo.update_stats = AsyncMock()
            mock_repo.update_position = AsyncMock()

            from server.net.handlers.auth import handle_reconnect
            await handle_reconnect(ws, {"action": "reconnect", "session_token": token}, game=game)

        # No seq_status message
        seq_msgs = [m for m in sent if m.get("type") == "seq_status"]
        assert len(seq_msgs) == 0


# =========================================================================
# Cleanup clears msg_seq
# =========================================================================


class TestCleanupClearsMsgSeq:
    async def test_cleanup_session_clears_seq(self):
        """cleanup_session calls clear_msg_seq."""
        from server.player.manager import PlayerManager
        from server.player.entity import PlayerEntity
        from server.player.session import PlayerSession

        pm = PlayerManager()
        entity = PlayerEntity(id="player_1", name="test", x=0, y=0, player_db_id=1)
        session = PlayerSession(entity=entity, room_key="town_square", db_id=1)
        pm.set_session("player_1", session)

        game = MagicMock()
        game.trade_manager = MagicMock()
        game.trade_manager.cancel_trades_for.return_value = None
        game.combat_manager = MagicMock()
        game.combat_manager.get_player_instance.return_value = None
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

            await pm.cleanup_session("player_1", game)

        game.connection_manager.clear_msg_seq.assert_called_once_with("player_1")


# =========================================================================
# Schema tests
# =========================================================================


class TestReconnectSchemaLastSeq:
    def test_reconnect_message_accepts_last_seq(self):
        from server.net.schemas import ReconnectMessage
        msg = ReconnectMessage(action="reconnect", session_token="abc", last_seq=42)
        assert msg.last_seq == 42

    def test_reconnect_message_last_seq_optional(self):
        from server.net.schemas import ReconnectMessage
        msg = ReconnectMessage(action="reconnect", session_token="abc")
        assert msg.last_seq is None
