"""Tests for WebSocket connection, message routing, and ConnectionManager."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from server.app import app
from server.net.connection_manager import ConnectionManager
from server.net.message_router import MessageRouter
from server.net import websocket as ws_module


# --- WebSocket endpoint tests (using TestClient) ---


def test_websocket_connect():
    """Test that WebSocket connection is accepted at /ws/game."""
    client = TestClient(app)
    with client.websocket_connect("/ws/game") as ws:
        # Connection accepted — send a message to confirm it works
        ws.send_json({"action": "ping"})
        resp = ws.receive_json()
        # ping is not registered, so we get unknown action
        assert resp["type"] == "error"
        assert "Unknown action: ping" in resp["detail"]


def test_websocket_unknown_action():
    """Test unknown action returns error."""
    client = TestClient(app)
    with client.websocket_connect("/ws/game") as ws:
        ws.send_json({"action": "nonexistent"})
        resp = ws.receive_json()
        assert resp == {"type": "error", "detail": "Unknown action: nonexistent"}


def test_websocket_malformed_json():
    """Test malformed JSON returns error."""
    client = TestClient(app)
    with client.websocket_connect("/ws/game") as ws:
        ws.send_text("not valid json {{{")
        resp = ws.receive_json()
        assert resp == {"type": "error", "detail": "Invalid JSON"}


def test_websocket_missing_action():
    """Test missing action field returns error."""
    client = TestClient(app)
    with client.websocket_connect("/ws/game") as ws:
        ws.send_json({"username": "hero"})
        resp = ws.receive_json()
        assert resp == {"type": "error", "detail": "Missing action field"}


def test_websocket_routes_to_handler():
    """Test that a registered handler is called."""
    # Register a test handler
    async def handle_test(websocket, data):
        await websocket.send_json({"type": "test_response", "echo": data.get("msg")})

    ws_module.router.register("test_action", handle_test)
    try:
        client = TestClient(app)
        with client.websocket_connect("/ws/game") as ws:
            ws.send_json({"action": "test_action", "msg": "hello"})
            resp = ws.receive_json()
            assert resp == {"type": "test_response", "echo": "hello"}
    finally:
        # Clean up registered handler
        ws_module.router._handlers.pop("test_action", None)


# --- MessageRouter unit tests ---


@pytest.mark.asyncio
async def test_router_register_and_route():
    router = MessageRouter()
    called_with = {}

    async def handler(ws, data):
        called_with.update(data)

    router.register("greet", handler)
    mock_ws = AsyncMock()
    await router.route(mock_ws, {"action": "greet", "name": "hero"})
    assert called_with == {"action": "greet", "name": "hero"}


@pytest.mark.asyncio
async def test_router_unknown_action():
    router = MessageRouter()
    mock_ws = AsyncMock()
    await router.route(mock_ws, {"action": "unknown_thing"})
    mock_ws.send_json.assert_called_once_with(
        {"type": "error", "detail": "Unknown action: unknown_thing"}
    )


# --- ConnectionManager unit tests ---


def test_connection_manager_connect_disconnect():
    mgr = ConnectionManager()
    mock_ws = MagicMock()
    mgr.connect("player_1", mock_ws, "town")
    assert mgr.get_websocket("player_1") is mock_ws

    mgr.disconnect("player_1")
    assert mgr.get_websocket("player_1") is None


def test_connection_manager_get_websocket_missing():
    mgr = ConnectionManager()
    assert mgr.get_websocket("nonexistent") is None


@pytest.mark.asyncio
async def test_connection_manager_send_to_player():
    mgr = ConnectionManager()
    mock_ws = AsyncMock()
    mgr.connect("player_1", mock_ws, "town")

    await mgr.send_to_player("player_1", {"type": "hello"})
    mock_ws.send_json.assert_called_once_with({"type": "hello"})


@pytest.mark.asyncio
async def test_connection_manager_send_to_missing_player():
    mgr = ConnectionManager()
    # Should not raise
    await mgr.send_to_player("nonexistent", {"type": "hello"})


@pytest.mark.asyncio
async def test_connection_manager_broadcast_to_room():
    mgr = ConnectionManager()
    ws1 = AsyncMock()
    ws2 = AsyncMock()
    ws3 = AsyncMock()
    mgr.connect("p1", ws1, "town")
    mgr.connect("p2", ws2, "town")
    mgr.connect("p3", ws3, "forest")

    await mgr.broadcast_to_room("town", {"type": "chat", "msg": "hi"})
    ws1.send_json.assert_called_once_with({"type": "chat", "msg": "hi"})
    ws2.send_json.assert_called_once_with({"type": "chat", "msg": "hi"})
    ws3.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_connection_manager_broadcast_exclude():
    mgr = ConnectionManager()
    ws1 = AsyncMock()
    ws2 = AsyncMock()
    mgr.connect("p1", ws1, "town")
    mgr.connect("p2", ws2, "town")

    await mgr.broadcast_to_room("town", {"type": "moved"}, exclude="p1")
    ws1.send_json.assert_not_called()
    ws2.send_json.assert_called_once_with({"type": "moved"})
