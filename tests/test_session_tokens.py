"""Tests for session token generation, validation, and reconnect handler."""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.player.tokens import TokenStore, generate_session_token


# =========================================================================
# TokenStore unit tests
# =========================================================================


class TestGenerateSessionToken:
    def test_generates_string(self):
        token = generate_session_token()
        assert isinstance(token, str)
        assert len(token) > 0

    def test_unique_tokens(self):
        tokens = {generate_session_token() for _ in range(100)}
        assert len(tokens) == 100


class TestTokenStoreIssue:
    def test_issue_returns_token(self):
        store = TokenStore()
        token = store.issue(1)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_issue_revokes_previous_for_same_player(self):
        store = TokenStore()
        token1 = store.issue(1)
        token2 = store.issue(1)
        assert token1 != token2
        assert store.validate(token1) is None  # old revoked
        assert store.validate(token2) == 1  # new valid

    def test_issue_does_not_revoke_other_players(self):
        store = TokenStore()
        token1 = store.issue(1)
        token2 = store.issue(2)
        assert store.validate(token1) == 1
        assert store.validate(token2) == 2

    def test_issue_purges_expired(self):
        store = TokenStore()
        # Manually insert expired token
        store._tokens["expired_token"] = (99, time.time() - 10)
        assert "expired_token" in store._tokens
        store.issue(1)
        assert "expired_token" not in store._tokens


class TestTokenStoreValidate:
    def test_validate_valid_token(self):
        store = TokenStore()
        token = store.issue(42)
        assert store.validate(token) == 42

    def test_validate_invalid_token(self):
        store = TokenStore()
        assert store.validate("nonexistent") is None

    def test_validate_expired_token(self):
        store = TokenStore()
        token = store.issue(1)
        # Force expiry
        db_id, _ = store._tokens[token]
        store._tokens[token] = (db_id, time.time() - 1)
        assert store.validate(token) is None
        # Token removed from store
        assert token not in store._tokens


class TestTokenStoreRevoke:
    def test_revoke_specific_token(self):
        store = TokenStore()
        token = store.issue(1)
        store.revoke(token)
        assert store.validate(token) is None

    def test_revoke_nonexistent_is_noop(self):
        store = TokenStore()
        store.revoke("nonexistent")  # no error

    def test_revoke_for_player(self):
        store = TokenStore()
        token = store.issue(1)
        store.revoke_for_player(1)
        assert store.validate(token) is None

    def test_revoke_for_player_preserves_others(self):
        store = TokenStore()
        token1 = store.issue(1)
        token2 = store.issue(2)
        store.revoke_for_player(1)
        assert store.validate(token1) is None
        assert store.validate(token2) == 2


class TestTokenStorePurge:
    def test_purge_removes_expired(self):
        store = TokenStore()
        store._tokens["a"] = (1, time.time() - 100)
        store._tokens["b"] = (2, time.time() + 100)
        store._purge_expired()
        assert "a" not in store._tokens
        assert "b" in store._tokens

    def test_purge_empty_store(self):
        store = TokenStore()
        store._purge_expired()  # no error
        assert len(store._tokens) == 0


# =========================================================================
# handle_login includes session_token
# =========================================================================


def _make_mock_game():
    """Create a mock Game with async-safe mocks for all managers."""
    game = MagicMock()
    game.token_store = TokenStore()
    game.connection_manager = MagicMock()
    game.connection_manager.get_websocket.return_value = None
    game.connection_manager.get_entity_id.return_value = None
    game.connection_manager.broadcast_to_room = AsyncMock()
    game.connection_manager.send_to_player = AsyncMock()
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


class TestLoginIncludesToken:
    @pytest.fixture
    def mock_game(self):
        return _make_mock_game()

    @pytest.mark.asyncio
    async def test_login_success_includes_session_token(self, mock_game):
        game, mock_session = mock_game

        mock_player = MagicMock()
        mock_player.id = 1
        mock_player.username = "testuser"
        mock_player.password_hash = "$2b$04$fakehash"
        mock_player.stats = {"hp": 100, "max_hp": 100, "attack": 10, "xp": 0, "level": 1}
        mock_player.current_room_id = "town_square"
        mock_player.position_x = 5
        mock_player.position_y = 5
        mock_player.inventory = {}
        mock_player.visited_rooms = ["town_square"]

        mock_room = MagicMock()
        mock_room.is_walkable.return_value = True
        mock_room.get_state.return_value = {"room_key": "town_square", "name": "Town Square", "width": 5, "height": 5, "tiles": [], "entities": [], "npcs": [], "exits": [], "objects": []}

        game.room_manager.get_room.return_value = mock_room

        ws = AsyncMock()
        sent_messages = []
        ws.send_json = AsyncMock(side_effect=lambda msg: sent_messages.append(msg))

        with patch("server.net.handlers.auth.player_repo") as mock_repo, \
             patch("server.net.handlers.auth.verify_password", return_value=True), \
             patch("server.net.handlers.auth.item_repo"):
            mock_repo.get_by_username = AsyncMock(return_value=mock_player)
            mock_repo.update_stats = AsyncMock()
            mock_repo.update_position = AsyncMock()

            from server.net.handlers.auth import handle_login
            await handle_login(ws, {"action": "login", "username": "testuser", "password": "pass123"}, game=game)

        # Find login_success message
        login_msg = next((m for m in sent_messages if m.get("type") == "login_success"), None)
        assert login_msg is not None
        assert "session_token" in login_msg
        assert isinstance(login_msg["session_token"], str)
        assert len(login_msg["session_token"]) > 0


# =========================================================================
# handle_reconnect tests
# =========================================================================


class TestHandleReconnect:
    @pytest.fixture
    def mock_game(self):
        return _make_mock_game()

    @pytest.mark.asyncio
    async def test_missing_token_returns_error(self, mock_game):
        game, _ = mock_game
        ws = AsyncMock()
        from server.net.handlers.auth import handle_reconnect
        await handle_reconnect(ws, {"action": "reconnect"}, game=game)
        ws.send_json.assert_called_once()
        msg = ws.send_json.call_args[0][0]
        assert msg["type"] == "error"
        assert "Missing session_token" in msg["detail"]

    @pytest.mark.asyncio
    async def test_invalid_token_returns_error(self, mock_game):
        game, _ = mock_game
        ws = AsyncMock()
        from server.net.handlers.auth import handle_reconnect
        await handle_reconnect(ws, {"action": "reconnect", "session_token": "bad_token"}, game=game)
        ws.send_json.assert_called_once()
        msg = ws.send_json.call_args[0][0]
        assert msg["type"] == "error"
        assert "Invalid or expired token" in msg["detail"]

    @pytest.mark.asyncio
    async def test_expired_token_returns_error(self, mock_game):
        game, _ = mock_game
        token = game.token_store.issue(1)
        # Force expiry
        db_id, _ = game.token_store._tokens[token]
        game.token_store._tokens[token] = (db_id, time.time() - 1)

        ws = AsyncMock()
        from server.net.handlers.auth import handle_reconnect
        await handle_reconnect(ws, {"action": "reconnect", "session_token": token}, game=game)
        ws.send_json.assert_called_once()
        msg = ws.send_json.call_args[0][0]
        assert msg["type"] == "error"
        assert "Invalid or expired token" in msg["detail"]

    @pytest.mark.asyncio
    async def test_token_single_use(self, mock_game):
        """Token is consumed on reconnect — can't be used twice."""
        game, mock_session = mock_game
        token = game.token_store.issue(1)

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
        mock_room.get_state.return_value = {"room_key": "town_square", "name": "Town Square", "width": 5, "height": 5, "tiles": [], "entities": [], "npcs": [], "exits": [], "objects": []}
        game.room_manager.get_room.return_value = mock_room

        ws = AsyncMock()
        with patch("server.net.handlers.auth.player_repo") as mock_repo, \
             patch("server.net.handlers.auth.item_repo"):
            mock_repo.get_by_id = AsyncMock(return_value=mock_player)
            mock_repo.update_stats = AsyncMock()
            mock_repo.update_position = AsyncMock()

            from server.net.handlers.auth import handle_reconnect

            # First use — succeeds
            await handle_reconnect(ws, {"action": "reconnect", "session_token": token}, game=game)
            login_msg = next((c[0][0] for c in ws.send_json.call_args_list if c[0][0].get("type") == "login_success"), None)
            assert login_msg is not None

            # Second use — fails (token consumed)
            ws.reset_mock()
            await handle_reconnect(ws, {"action": "reconnect", "session_token": token}, game=game)
            msg = ws.send_json.call_args[0][0]
            assert msg["type"] == "error"
            assert "Invalid or expired token" in msg["detail"]

    @pytest.mark.asyncio
    async def test_reconnect_case2_full_db_restore(self, mock_game):
        """Case 2: No session exists, restore from DB."""
        game, mock_session = mock_game
        token = game.token_store.issue(1)

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
        mock_room.get_state.return_value = {"room_key": "town_square", "name": "Town Square", "width": 5, "height": 5, "tiles": [], "entities": [], "npcs": [], "exits": [], "objects": []}
        game.room_manager.get_room.return_value = mock_room

        ws = AsyncMock()
        sent = []
        ws.send_json = AsyncMock(side_effect=lambda msg: sent.append(msg))

        with patch("server.net.handlers.auth.player_repo") as mock_repo, \
             patch("server.net.handlers.auth.item_repo"):
            mock_repo.get_by_id = AsyncMock(return_value=mock_player)
            mock_repo.update_stats = AsyncMock()
            mock_repo.update_position = AsyncMock()

            from server.net.handlers.auth import handle_reconnect
            await handle_reconnect(ws, {"action": "reconnect", "session_token": token}, game=game)

        # Should receive login_success with new token
        login_msg = next((m for m in sent if m.get("type") == "login_success"), None)
        assert login_msg is not None
        assert "session_token" in login_msg
        assert login_msg["session_token"] != token  # new token issued

        # Should receive room_state
        room_msg = next((m for m in sent if m.get("type") == "room_state"), None)
        assert room_msg is not None

        # Session should be set
        game.player_manager.set_session.assert_called_once()
        game._start_heartbeat.assert_called_once_with("player_1")

    @pytest.mark.asyncio
    async def test_reconnect_player_not_found(self, mock_game):
        """Case 2: Token valid but player deleted from DB."""
        game, mock_session = mock_game
        token = game.token_store.issue(999)

        ws = AsyncMock()
        with patch("server.net.handlers.auth.player_repo") as mock_repo:
            mock_repo.get_by_id = AsyncMock(return_value=None)

            from server.net.handlers.auth import handle_reconnect
            await handle_reconnect(ws, {"action": "reconnect", "session_token": token}, game=game)

        msg = ws.send_json.call_args[0][0]
        assert msg["type"] == "error"
        assert "Player not found" in msg["detail"]

    @pytest.mark.asyncio
    async def test_reconnect_cleans_up_existing_session_on_ws(self, mock_game):
        """If WS already has a different player session, clean up first."""
        game, mock_session = mock_game
        token = game.token_store.issue(1)

        # WebSocket already has player_2 logged in
        game.connection_manager.get_entity_id.return_value = "player_2"

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
        mock_room.get_state.return_value = {"room_key": "town_square", "name": "Town Square", "width": 5, "height": 5, "tiles": [], "entities": [], "npcs": [], "exits": [], "objects": []}
        game.room_manager.get_room.return_value = mock_room

        ws = AsyncMock()
        with patch("server.net.handlers.auth.player_repo") as mock_repo, \
             patch("server.net.handlers.auth.item_repo"):
            mock_repo.get_by_id = AsyncMock(return_value=mock_player)
            mock_repo.update_stats = AsyncMock()
            mock_repo.update_position = AsyncMock()

            from server.net.handlers.auth import handle_reconnect
            await handle_reconnect(ws, {"action": "reconnect", "session_token": token}, game=game)

        # Should have cleaned up player_2's session
        game._cancel_heartbeat.assert_called_with("player_2")
        game.player_manager.cleanup_session.assert_called_with("player_2", game)


# =========================================================================
# Logout revokes token
# =========================================================================


class TestLogoutRevokesToken:
    @pytest.mark.asyncio
    async def test_logout_revokes_token(self):
        from server.player.session import PlayerSession
        from server.player.entity import PlayerEntity

        game, _ = _make_mock_game()

        entity = PlayerEntity(id="player_1", name="test", x=0, y=0, player_db_id=1)
        session = PlayerSession(entity=entity, room_key="town_square", db_id=1)

        # Make @requires_auth pass — return session for entity_id
        game.connection_manager.get_entity_id.return_value = "player_1"
        game.player_manager.get_session.return_value = session

        # Issue a token
        token = game.token_store.issue(1)
        assert game.token_store.validate(token) == 1

        ws = AsyncMock()
        from server.net.handlers.auth import handle_logout
        await handle_logout(ws, {"action": "logout"}, game=game)

        # Token should be revoked
        assert game.token_store.validate(token) is None


# =========================================================================
# Inbound schema test
# =========================================================================


class TestReconnectSchema:
    def test_reconnect_in_action_schemas(self):
        from server.net.schemas import ACTION_SCHEMAS, ReconnectMessage
        assert "reconnect" in ACTION_SCHEMAS
        assert ACTION_SCHEMAS["reconnect"] is ReconnectMessage

    def test_reconnect_message_validates(self):
        from server.net.schemas import ReconnectMessage
        msg = ReconnectMessage(action="reconnect", session_token="abc123")
        assert msg.session_token == "abc123"

    def test_reconnect_message_rejects_empty_token(self):
        from pydantic import ValidationError
        from server.net.schemas import ReconnectMessage
        with pytest.raises(ValidationError):
            ReconnectMessage(action="reconnect", session_token="")


# =========================================================================
# Outbound schema test
# =========================================================================


class TestLoginSuccessSchema:
    def test_login_success_has_session_token_field(self):
        from server.net.outbound_schemas import LoginSuccessMessage
        msg = LoginSuccessMessage(
            player_id=1, entity_id="player_1", username="test",
            stats={"hp": 100, "max_hp": 100, "attack": 10, "xp": 0, "level": 1,
                   "xp_for_next_level": 1000, "xp_for_current_level": 0,
                   "strength": 1, "dexterity": 1, "constitution": 1,
                   "intelligence": 1, "wisdom": 1, "charisma": 1},
            session_token="test_token",
        )
        assert msg.session_token == "test_token"

    def test_login_success_session_token_optional(self):
        from server.net.outbound_schemas import LoginSuccessMessage
        msg = LoginSuccessMessage(
            player_id=1, entity_id="player_1", username="test",
            stats={"hp": 100, "max_hp": 100, "attack": 10, "xp": 0, "level": 1,
                   "xp_for_next_level": 1000, "xp_for_current_level": 0,
                   "strength": 1, "dexterity": 1, "constitution": 1,
                   "intelligence": 1, "wisdom": 1, "charisma": 1},
        )
        assert msg.session_token is None
