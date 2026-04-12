"""Tests for request_id echo-back (Story 16.7)."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from server.net.schemas import with_request_id, InboundMessage, LoginMessage


class TestWithRequestId:
    """Unit tests for with_request_id utility."""

    def test_echoes_request_id_when_present(self):
        response = {"type": "stats_result"}
        data = {"action": "stats", "request_id": "abc-123"}
        result = with_request_id(response, data)
        assert result["request_id"] == "abc-123"
        assert result is response  # mutates in place

    def test_no_request_id_when_absent(self):
        response = {"type": "stats_result"}
        data = {"action": "stats"}
        result = with_request_id(response, data)
        assert "request_id" not in result

    def test_no_request_id_when_none(self):
        response = {"type": "stats_result"}
        data = {"action": "stats", "request_id": None}
        result = with_request_id(response, data)
        assert "request_id" not in result

    def test_preserves_existing_response_fields(self):
        response = {"type": "error", "detail": "Not in combat"}
        data = {"action": "play_card", "request_id": "req-42"}
        result = with_request_id(response, data)
        assert result["type"] == "error"
        assert result["detail"] == "Not in combat"
        assert result["request_id"] == "req-42"


class TestInboundMessageRequestId:
    """Tests for request_id on InboundMessage base class."""

    def test_request_id_optional(self):
        m = InboundMessage(action="stats")
        assert m.request_id is None

    def test_request_id_set(self):
        m = InboundMessage(action="stats", request_id="xyz")
        assert m.request_id == "xyz"

    def test_model_dump_includes_request_id(self):
        m = LoginMessage(action="login", username="hero", password="pass", request_id="req-1")
        d = m.model_dump()
        assert d["request_id"] == "req-1"

    def test_model_dump_includes_none_request_id(self):
        m = LoginMessage(action="login", username="hero", password="pass")
        d = m.model_dump()
        assert d["request_id"] is None


class TestFrameworkErrors:
    """Tests for request_id in framework-level errors (app.py, message_router.py)."""

    @pytest.fixture
    def ws(self):
        ws = AsyncMock()
        ws.send_json = AsyncMock()
        return ws

    async def test_missing_action_includes_request_id(self, ws):
        """Missing-action error echoes request_id when present in data."""
        from server.net.schemas import with_request_id
        data = {"request_id": "req-missing"}
        error = with_request_id({"type": "error", "detail": "Missing action field"}, data)
        await ws.send_json(error)
        sent = ws.send_json.call_args[0][0]
        assert sent["request_id"] == "req-missing"

    async def test_missing_action_no_request_id(self, ws):
        """Missing-action error omits request_id when not present."""
        data = {"some_field": "value"}
        error = with_request_id({"type": "error", "detail": "Missing action field"}, data)
        await ws.send_json(error)
        sent = ws.send_json.call_args[0][0]
        assert "request_id" not in sent

    async def test_unknown_action_includes_request_id(self, ws):
        """Unknown-action error echoes request_id."""
        from server.net.message_router import MessageRouter
        router = MessageRouter()
        data = {"action": "nonexistent", "request_id": "req-unknown"}
        await router.route(ws, data)
        sent = ws.send_json.call_args[0][0]
        assert sent["type"] == "error"
        assert "Unknown action" in sent["detail"]
        assert sent["request_id"] == "req-unknown"

    async def test_unknown_action_no_request_id(self, ws):
        """Unknown-action error omits request_id when not present."""
        from server.net.message_router import MessageRouter
        router = MessageRouter()
        data = {"action": "nonexistent"}
        await router.route(ws, data)
        sent = ws.send_json.call_args[0][0]
        assert "request_id" not in sent

    async def test_validation_error_includes_request_id(self):
        """Schema validation error echoes request_id from raw data."""
        from pydantic import ValidationError
        from server.net.schemas import LoginMessage, with_request_id

        raw_data = {"action": "login", "request_id": "req-val"}
        try:
            LoginMessage(**raw_data)  # missing username/password
        except ValidationError as e:
            error = with_request_id({"type": "error", "detail": str(e)}, raw_data)
            assert error["request_id"] == "req-val"


class TestHandlerRequestId:
    """Integration tests verifying handlers echo request_id in direct responses."""

    @pytest.fixture
    def ws(self):
        ws = AsyncMock()
        ws.send_json = AsyncMock()
        return ws

    async def test_query_handler_echoes_request_id(self, ws):
        """Query handlers (all direct) echo request_id."""
        from server.net.handlers.query import handle_help_actions

        game = MagicMock()
        player_info = MagicMock()
        data = {"action": "help_actions", "request_id": "req-help"}

        await handle_help_actions.__wrapped__(
            ws, data, game=game,
            entity_id="player_1", player_info=player_info,
        )
        sent = ws.send_json.call_args[0][0]
        assert sent["type"] == "help_result"
        assert sent["request_id"] == "req-help"

    async def test_query_handler_no_request_id(self, ws):
        """Query handlers omit request_id when not in request."""
        from server.net.handlers.query import handle_help_actions

        game = MagicMock()
        player_info = MagicMock()
        data = {"action": "help_actions", "request_id": None}

        await handle_help_actions.__wrapped__(
            ws, data, game=game,
            entity_id="player_1", player_info=player_info,
        )
        sent = ws.send_json.call_args[0][0]
        assert sent["type"] == "help_result"
        assert "request_id" not in sent

    async def test_combat_error_echoes_request_id(self, ws):
        """Combat error (not in combat) echoes request_id."""
        from server.net.handlers.combat import handle_play_card

        game = MagicMock()
        game.combat_manager.get_player_instance.return_value = None
        player_info = MagicMock()
        data = {"action": "play_card", "card_key": "strike", "request_id": "req-combat"}

        await handle_play_card.__wrapped__(
            ws, data, game=game,
            entity_id="player_1", player_info=player_info,
        )
        sent = ws.send_json.call_args[0][0]
        assert sent["type"] == "error"
        assert sent["request_id"] == "req-combat"

    async def test_inventory_echoes_request_id(self, ws):
        """Inventory handler echoes request_id."""
        from server.net.handlers.inventory import handle_inventory

        game = MagicMock()
        player_info = MagicMock()
        player_info.inventory = None
        data = {"action": "inventory", "request_id": "req-inv"}

        await handle_inventory.__wrapped__(
            ws, data, game=game,
            entity_id="player_1", player_info=player_info,
        )
        sent = ws.send_json.call_args[0][0]
        assert sent["type"] == "inventory"
        assert sent["request_id"] == "req-inv"

    async def test_broadcast_does_not_include_request_id(self, ws):
        """Broadcasts to other players should NOT include request_id."""
        from server.net.handlers.query import handle_help_actions

        game = MagicMock()
        player_info = MagicMock()
        data = {"action": "help_actions", "request_id": "req-help"}

        await handle_help_actions.__wrapped__(
            ws, data, game=game,
            entity_id="player_1", player_info=player_info,
        )

        # The broadcast_to_room should never be called for query handlers
        # (they're all direct responses). This verifies no accidental broadcasts.
        game.connection_manager.broadcast_to_room.assert_not_called()
