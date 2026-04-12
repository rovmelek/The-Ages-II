"""Tests for player login and room entry (Story 1.7)."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from server.core.database import Base
from server.player.models import Player
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


@pytest.fixture
def room_manager():
    """Fresh RoomManager with a pre-loaded test room."""
    from server.room.manager import RoomManager

    mgr = RoomManager()
    room = RoomInstance(
        room_key="town_square",
        name="Town Square",
        width=5,
        height=5,
        tile_data=[[0] * 5 for _ in range(5)],
        exits=[{"x": 4, "y": 4, "target_room": "cave_1", "entry_x": 0, "entry_y": 0}],
    )
    mgr._rooms["town_square"] = room
    return mgr


@pytest.fixture
def connection_manager():
    from server.net.connection_manager import ConnectionManager
    return ConnectionManager()


@pytest.fixture
def client(test_session_factory, room_manager, connection_manager):
    """TestClient with patched dependencies for login handler."""
    from server.app import app, game

    original_rm = game.room_manager
    original_cm = game.connection_manager
    original_sf = game.session_factory

    with TestClient(app) as c:
        # Swap managers and session factory AFTER startup
        game.room_manager = room_manager
        game.connection_manager = connection_manager
        game.session_factory = test_session_factory
        yield c

    game.room_manager = original_rm
    game.connection_manager = original_cm
    game.session_factory = original_sf
    game.player_manager.clear()


def _register_player(client, username="hero", password="secret123"):
    """Helper to register a player before testing login."""
    with client.websocket_connect("/ws/game") as ws:
        ws.send_json({"action": "register", "username": username, "password": password})
        return ws.receive_json()


# ---------------------------------------------------------------------------
# Login success tests
# ---------------------------------------------------------------------------

def test_login_success(client):
    _register_player(client)
    with client.websocket_connect("/ws/game") as ws:
        ws.send_json({"action": "login", "username": "hero", "password": "secret123"})
        resp = ws.receive_json()
        assert resp["type"] == "login_success"
        assert resp["username"] == "hero"
        assert "player_id" in resp


def test_login_returns_room_state(client):
    _register_player(client)
    with client.websocket_connect("/ws/game") as ws:
        ws.send_json({"action": "login", "username": "hero", "password": "secret123"})
        login_resp = ws.receive_json()
        assert login_resp["type"] == "login_success"

        room_resp = ws.receive_json()
        assert room_resp["type"] == "room_state"
        assert room_resp["room_key"] == "town_square"
        assert "tiles" in room_resp
        assert "entities" in room_resp
        assert "exits" in room_resp


def test_login_entity_at_saved_position(client, room_manager):
    _register_player(client)
    with client.websocket_connect("/ws/game") as ws:
        ws.send_json({"action": "login", "username": "hero", "password": "secret123"})
        ws.receive_json()  # login_success
        room_resp = ws.receive_json()

        # Entity should be in the entities list
        entities = room_resp["entities"]
        player_entities = [e for e in entities if e["name"] == "hero"]
        assert len(player_entities) == 1
        entity = player_entities[0]
        assert entity["id"].startswith("player_")
        # Spawn point fallback is (0, 0) when room has no explicit player spawn
        assert entity["x"] == 0
        assert entity["y"] == 0


def test_login_registers_connection(client, connection_manager):
    _register_player(client)
    with client.websocket_connect("/ws/game") as ws:
        ws.send_json({"action": "login", "username": "hero", "password": "secret123"})
        ws.receive_json()  # login_success
        ws.receive_json()  # room_state

        # Connection should be registered
        assert connection_manager.get_websocket("player_1") is not None


# ---------------------------------------------------------------------------
# Entity entered broadcast test
# ---------------------------------------------------------------------------

def test_login_broadcasts_entity_entered(client, connection_manager):
    _register_player(client, "alice", "password1")
    _register_player(client, "bob", "password2")

    with client.websocket_connect("/ws/game") as ws_alice:
        ws_alice.send_json({"action": "login", "username": "alice", "password": "password1"})
        ws_alice.receive_json()  # login_success
        ws_alice.receive_json()  # room_state

        with client.websocket_connect("/ws/game") as ws_bob:
            ws_bob.send_json({"action": "login", "username": "bob", "password": "password2"})
            ws_bob.receive_json()  # login_success
            ws_bob.receive_json()  # room_state

            # Alice should receive entity_entered for Bob
            entered = ws_alice.receive_json()
            assert entered["type"] == "entity_entered"
            assert entered["entity"]["name"] == "bob"


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_login_invalid_username(client):
    with client.websocket_connect("/ws/game") as ws:
        ws.send_json({"action": "login", "username": "nonexistent", "password": "secret123"})
        resp = ws.receive_json()
        assert resp["type"] == "error"
        assert resp["detail"] == "Invalid username or password"


def test_login_wrong_password(client):
    _register_player(client)
    with client.websocket_connect("/ws/game") as ws:
        ws.send_json({"action": "login", "username": "hero", "password": "wrongpass"})
        resp = ws.receive_json()
        assert resp["type"] == "error"
        assert resp["detail"] == "Invalid username or password"


def test_login_empty_username(client):
    with client.websocket_connect("/ws/game") as ws:
        ws.send_json({"action": "login", "username": "", "password": "secret123"})
        resp = ws.receive_json()
        assert resp["type"] == "error"
        assert resp["detail"] == "Username and password required"


def test_login_empty_password(client):
    with client.websocket_connect("/ws/game") as ws:
        ws.send_json({"action": "login", "username": "hero", "password": ""})
        resp = ws.receive_json()
        assert resp["type"] == "error"
        assert resp["detail"] == "Username and password required"


def test_login_no_current_room_uses_default(client, room_manager):
    """New player with no current_room_id should land in town_square."""
    _register_player(client)
    with client.websocket_connect("/ws/game") as ws:
        ws.send_json({"action": "login", "username": "hero", "password": "secret123"})
        ws.receive_json()  # login_success
        room_resp = ws.receive_json()
        assert room_resp["type"] == "room_state"
        assert room_resp["room_key"] == "town_square"


def test_login_room_not_found(client, room_manager, test_session_factory):
    """If player's room doesn't exist, return error."""
    import asyncio

    _register_player(client)

    # Set current_room_id to a room that doesn't exist
    async def set_room():
        async with test_session_factory() as session:
            from sqlalchemy import update
            await session.execute(
                update(Player).where(Player.username == "hero").values(current_room_id="nonexistent_room")
            )
            await session.commit()

    asyncio.run(set_room())

    with client.websocket_connect("/ws/game") as ws:
        ws.send_json({"action": "login", "username": "hero", "password": "secret123"})
        resp = ws.receive_json()
        assert resp["type"] == "error"
        assert resp["detail"] == "Room not found"


def test_returning_player_on_wall_relocated_to_spawn(client, room_manager, test_session_factory):
    """Returning player saved on a non-walkable tile should be relocated to spawn."""
    import asyncio

    _register_player(client)

    # Replace room with one that has walls at (0,0) and a player spawn at (2,2)
    wall_room = RoomInstance(
        room_key="town_square",
        name="Town Square",
        width=5,
        height=5,
        tile_data=[
            [1, 1, 0, 0, 0],  # row 0: walls at x=0,1
            [1, 0, 0, 0, 0],
            [0, 0, 0, 0, 0],  # row 2: spawn at (2,2)
            [0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0],
        ],
        exits=[],
        spawn_points=[{"type": "player", "x": 2, "y": 2}],
    )
    room_manager._rooms["town_square"] = wall_room

    # Pre-condition: verify (0,0) is actually non-walkable in this room
    assert not wall_room.is_walkable(0, 0)

    # Simulate a returning player: set current_room_id and position to wall (0,0)
    async def set_wall_position():
        async with test_session_factory() as session:
            from sqlalchemy import update
            await session.execute(
                update(Player)
                .where(Player.username == "hero")
                .values(current_room_id="town_square", position_x=0, position_y=0)
            )
            await session.commit()

    asyncio.run(set_wall_position())

    with client.websocket_connect("/ws/game") as ws:
        ws.send_json({"action": "login", "username": "hero", "password": "secret123"})
        ws.receive_json()  # login_success
        room_resp = ws.receive_json()

        entities = room_resp["entities"]
        player_entities = [e for e in entities if e["name"] == "hero"]
        assert len(player_entities) == 1
        entity = player_entities[0]
        # Should be relocated to spawn (2,2), NOT stuck at wall (0,0)
        assert entity["x"] == 2
        assert entity["y"] == 2


def test_returning_player_spawn_also_unwalkable_uses_first_walkable(
    client, room_manager, test_session_factory
):
    """When both saved position AND spawn point are unwalkable, use first walkable tile."""
    import asyncio

    _register_player(client)

    # Room where spawn point (1,1) is a wall; first walkable tile is (2,0) by row scan
    bad_spawn_room = RoomInstance(
        room_key="town_square",
        name="Town Square",
        width=5,
        height=5,
        tile_data=[
            [1, 1, 0, 0, 0],  # row 0: first walkable at col=2 → (2,0)
            [1, 1, 0, 0, 0],  # row 1: spawn at (1,1) is wall
            [0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0],
        ],
        exits=[],
        spawn_points=[{"type": "player", "x": 1, "y": 1}],
    )
    room_manager._rooms["town_square"] = bad_spawn_room

    # Pre-conditions
    assert not bad_spawn_room.is_walkable(0, 0)
    assert not bad_spawn_room.is_walkable(1, 1)
    assert bad_spawn_room.is_walkable(2, 0)

    async def set_wall_position():
        async with test_session_factory() as session:
            from sqlalchemy import update
            await session.execute(
                update(Player)
                .where(Player.username == "hero")
                .values(current_room_id="town_square", position_x=0, position_y=0)
            )
            await session.commit()

    asyncio.run(set_wall_position())

    with client.websocket_connect("/ws/game") as ws:
        ws.send_json({"action": "login", "username": "hero", "password": "secret123"})
        ws.receive_json()  # login_success
        room_resp = ws.receive_json()

        entities = room_resp["entities"]
        player_entities = [e for e in entities if e["name"] == "hero"]
        assert len(player_entities) == 1
        entity = player_entities[0]
        # Should fall back to first walkable tile (2,0)
        assert entity["x"] == 2
        assert entity["y"] == 0


def test_returning_player_on_walkable_tile_stays_put(client, room_manager, test_session_factory):
    """Returning player on a valid walkable tile should NOT be relocated."""
    import asyncio

    _register_player(client)

    # Set saved position to walkable tile (3,3) with current_room_id set
    async def set_walkable_position():
        async with test_session_factory() as session:
            from sqlalchemy import update
            await session.execute(
                update(Player)
                .where(Player.username == "hero")
                .values(current_room_id="town_square", position_x=3, position_y=3)
            )
            await session.commit()

    asyncio.run(set_walkable_position())

    # Default room fixture has all floor tiles — (3,3) is walkable
    with client.websocket_connect("/ws/game") as ws:
        ws.send_json({"action": "login", "username": "hero", "password": "secret123"})
        ws.receive_json()  # login_success
        room_resp = ws.receive_json()

        entities = room_resp["entities"]
        player_entities = [e for e in entities if e["name"] == "hero"]
        assert len(player_entities) == 1
        entity = player_entities[0]
        # Should stay at saved position, not relocated to spawn
        assert entity["x"] == 3
        assert entity["y"] == 3
