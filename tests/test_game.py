"""Tests for Game orchestrator and server lifecycle (Story 1.8)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from server.core.database import Base
from server.net.connection_manager import ConnectionManager
from server.player.entity import PlayerEntity
from server.player.models import Player
from server.room.manager import RoomManager
from server.room.room import RoomInstance


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def async_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def test_session_factory(async_engine):
    return async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

def test_health_endpoint():
    from server.app import app
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Game startup
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_game_startup_initializes_db(test_session_factory):
    """Game.startup() calls init_db and loads rooms."""
    from server.app import Game

    game = Game()
    game.session_factory = test_session_factory
    with patch("server.app.init_db") as mock_init, \
         patch("server.app.settings") as mock_settings:
        mock_init.return_value = None
        # Point DATA_DIR to a temp path so card/item loading is skipped
        mock_settings.DATA_DIR = Path("/tmp/nonexistent_data_dir")
        with patch("server.app.JsonRoomProvider") as MockProvider:
            instance = MockProvider.return_value
            instance.load_rooms = AsyncMock(return_value=[])
            await game.startup()
            try:
                mock_init.assert_called_once()
                instance.load_rooms.assert_called_once()
            finally:
                await game.shutdown()


@pytest.mark.asyncio
async def test_game_startup_registers_handlers(test_session_factory):
    """Game.startup() registers login and register handlers."""
    from server.app import Game

    game = Game()
    game.session_factory = test_session_factory
    with patch("server.app.init_db", return_value=None), \
         patch("server.app.settings") as mock_settings, \
         patch("server.app.JsonRoomProvider") as MockProvider:
        mock_settings.DATA_DIR = Path("/tmp/nonexistent_data_dir")
        instance = MockProvider.return_value
        instance.load_rooms = AsyncMock(return_value=[])
        await game.startup()
        try:
            assert "login" in game.router._handlers
            assert "register" in game.router._handlers
        finally:
            await game.shutdown()


@pytest.mark.asyncio
async def test_game_startup_loads_rooms_into_manager(test_session_factory):
    """Game.startup() loads rooms from provider into room_manager."""
    from server.app import Game
    from server.room.models import Room

    # Create a mock room DB object
    mock_room = MagicMock(spec=Room)
    mock_room.room_key = "test_room"
    mock_room.name = "Test Room"
    mock_room.width = 5
    mock_room.height = 5
    mock_room.tile_data = [[0] * 5 for _ in range(5)]
    mock_room.exits = []
    mock_room.objects = []
    mock_room.spawn_points = []

    game = Game()
    game.session_factory = test_session_factory
    with patch("server.app.init_db", return_value=None), \
         patch("server.app.settings") as mock_settings, \
         patch("server.app.JsonRoomProvider") as MockProvider:
        mock_settings.DATA_DIR = Path("/tmp/nonexistent_data_dir")
        instance = MockProvider.return_value
        instance.load_rooms = AsyncMock(return_value=[mock_room])
        await game.startup()
        try:
            assert game.room_manager.get_room("test_room") is not None
        finally:
            await game.shutdown()


# ---------------------------------------------------------------------------
# Game shutdown
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_game_shutdown_empty():
    """Game.shutdown() completes without error on empty state."""
    from server.app import Game
    game = Game()
    await game.shutdown()


@pytest.mark.asyncio
async def test_game_shutdown_saves_player_state():
    """Game.shutdown() saves all player states, notifies, and disconnects."""
    from server.app import Game

    game = Game()
    room = RoomInstance("test_room", "Test", 5, 5, [[0] * 5 for _ in range(5)])
    game.room_manager._rooms["test_room"] = room

    entity = PlayerEntity(id="player_1", name="hero", x=2, y=3, player_db_id=10)
    room.add_entity(entity)

    mock_ws = AsyncMock()
    game.connection_manager.connect("player_1", mock_ws, "test_room")
    game.player_entities["player_1"] = {
        "entity": entity,
        "room_key": "test_room",
        "db_id": 10,
    }

    mock_session = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    game.transaction = MagicMock(return_value=mock_ctx)

    with patch("server.net.handlers.auth.player_repo", new_callable=AsyncMock) as mock_repo:
        await game.shutdown()

        # Position saved
        mock_repo.update_position.assert_called_once_with(
            mock_session, 10, "test_room", 2, 3
        )
        # Stats saved
        mock_repo.update_stats.assert_called_once()

    # Server shutdown notification sent before cleanup
    shutdown_calls = [
        call for call in mock_ws.send_json.call_args_list
        if isinstance(call[0][0], dict) and call[0][0].get("type") == "server_shutdown"
    ]
    assert len(shutdown_calls) == 1
    # WebSocket closed with 1001 (Going Away)
    mock_ws.close.assert_called_with(code=1001)
    # Player tracking cleared
    assert len(game.player_entities) == 0
    assert game.connection_manager.get_entity_id(mock_ws) is None


# ---------------------------------------------------------------------------
# Disconnect handling (unit tests)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_disconnect_removes_entity_from_room():
    """handle_disconnect removes entity from room and player_entities."""
    from server.app import Game

    game = Game()
    room = RoomInstance("test_room", "Test", 5, 5, [[0] * 5 for _ in range(5)])
    game.room_manager._rooms["test_room"] = room

    entity = PlayerEntity(id="player_1", name="hero", x=2, y=2, player_db_id=1)
    room.add_entity(entity)

    mock_ws = AsyncMock()
    game.connection_manager.connect("player_1", mock_ws, "test_room")
    game.player_entities["player_1"] = {
        "entity": entity,
        "room_key": "test_room",
        "db_id": 1,
    }

    mock_session = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    game.transaction = MagicMock(return_value=mock_ctx)

    await game.handle_disconnect(mock_ws)

    # Entity removed from room
    assert len(room._entities) == 0
    # Player removed from tracking
    assert "player_1" not in game.player_entities
    # Connection cleaned up
    assert game.connection_manager.get_entity_id(mock_ws) is None


@pytest.mark.asyncio
async def test_handle_disconnect_saves_position():
    """handle_disconnect saves player position to DB."""
    from server.app import Game

    game = Game()
    room = RoomInstance("test_room", "Test", 5, 5, [[0] * 5 for _ in range(5)])
    game.room_manager._rooms["test_room"] = room

    entity = PlayerEntity(id="player_1", name="hero", x=3, y=4, player_db_id=42)
    room.add_entity(entity)

    mock_ws = AsyncMock()
    game.connection_manager.connect("player_1", mock_ws, "test_room")
    game.player_entities["player_1"] = {
        "entity": entity,
        "room_key": "test_room",
        "db_id": 42,
    }

    mock_session = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    game.transaction = MagicMock(return_value=mock_ctx)

    with patch("server.net.handlers.auth.player_repo", new_callable=AsyncMock) as mock_repo:
        await game.handle_disconnect(mock_ws)

        mock_repo.update_position.assert_called_once_with(
            mock_session, 42, "test_room", 3, 4
        )


@pytest.mark.asyncio
async def test_handle_disconnect_broadcasts_entity_left():
    """handle_disconnect broadcasts entity_left to other players."""
    from server.app import Game

    game = Game()
    room = RoomInstance("test_room", "Test", 5, 5, [[0] * 5 for _ in range(5)])
    game.room_manager._rooms["test_room"] = room

    # Two players in room
    entity1 = PlayerEntity(id="player_1", name="alice", x=0, y=0, player_db_id=1)
    entity2 = PlayerEntity(id="player_2", name="bob", x=1, y=1, player_db_id=2)
    room.add_entity(entity1)
    room.add_entity(entity2)

    ws1 = AsyncMock()
    ws2 = AsyncMock()
    game.connection_manager.connect("player_1", ws1, "test_room")
    game.connection_manager.connect("player_2", ws2, "test_room")
    game.player_entities["player_1"] = {"entity": entity1, "room_key": "test_room", "db_id": 1}
    game.player_entities["player_2"] = {"entity": entity2, "room_key": "test_room", "db_id": 2}

    mock_session = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    game.transaction = MagicMock(return_value=mock_ctx)

    # Player 2 disconnects
    await game.handle_disconnect(ws2)

    # Player 1 should receive entity_left
    entity_left_calls = [
        call for call in ws1.send_json.call_args_list
        if call[0][0].get("type") == "entity_left"
    ]
    assert len(entity_left_calls) == 1
    assert entity_left_calls[0][0][0]["entity_id"] == "player_2"
    # Player 2's send_json should NOT be called for the broadcast
    # (exclude=entity_id prevents self-notification)


@pytest.mark.asyncio
async def test_handle_disconnect_unauthenticated_is_noop():
    """Disconnecting without logging in should not crash."""
    from server.app import Game

    game = Game()
    mock_ws = AsyncMock()
    # No connection registered — should return silently
    await game.handle_disconnect(mock_ws)


