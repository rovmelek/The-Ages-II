"""Tests for interactive object framework (Story 3.1)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from server.net.handlers.interact import handle_interact
from server.player.entity import PlayerEntity
from server.room.objects.base import InteractiveObject
from server.room.objects.registry import OBJECT_HANDLERS, register_object_type
from server.room.room import RoomInstance


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_game():
    from server.app import Game
    return Game()


def _make_room_with_objects(room_key="test", objects=None):
    """5x5 room with interactive objects."""
    return RoomInstance(
        room_key, "Test Room", 5, 5, [[0] * 5 for _ in range(5)],
        objects=objects or [],
    )


def _setup_player(game, room, entity_id="player_1"):
    """Place a player in a room and register with game."""
    entity = PlayerEntity(id=entity_id, name="hero", x=0, y=0, player_db_id=1)
    room.add_entity(entity)
    game.room_manager._rooms[room.room_key] = room

    ws = AsyncMock()
    game.connection_manager.connect(entity_id, ws, room.room_key)
    game.player_entities[entity_id] = {
        "entity": entity, "room_key": room.room_key, "db_id": 1,
    }
    return ws, entity


# A minimal test interactive object type
class EchoObject(InteractiveObject):
    async def interact(self, player_id, game):
        return {"echo": True, "player_id": player_id}


# ---------------------------------------------------------------------------
# Register/cleanup test object type
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _register_echo():
    register_object_type("echo", EchoObject)
    yield
    OBJECT_HANDLERS.pop("echo", None)


# ---------------------------------------------------------------------------
# Interact handler tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_interact_returns_result():
    game = _make_game()
    objects = [{"id": "obj_1", "type": "echo", "category": "interactive",
                "x": 1, "y": 1, "state_scope": "player", "config": {}}]
    room = _make_room_with_objects(objects=objects)
    ws, _ = _setup_player(game, room)

    await handle_interact(ws, {"action": "interact", "target_id": "obj_1"}, game=game)

    msg = ws.send_json.call_args.args[0]
    assert msg["type"] == "interact_result"
    assert msg["object_id"] == "obj_1"
    assert msg["result"]["echo"] is True
    assert msg["result"]["player_id"] == 1


@pytest.mark.asyncio
async def test_interact_object_not_found():
    game = _make_game()
    room = _make_room_with_objects()
    ws, _ = _setup_player(game, room)

    await handle_interact(ws, {"action": "interact", "target_id": "nonexistent"}, game=game)

    ws.send_json.assert_called_with({"type": "error", "detail": "Object not found"})


@pytest.mark.asyncio
async def test_interact_not_logged_in():
    game = _make_game()
    mock_ws = AsyncMock()

    await handle_interact(mock_ws, {"action": "interact", "target_id": "obj_1"}, game=game)

    mock_ws.send_json.assert_called_with({"type": "error", "detail": "Not logged in"})


@pytest.mark.asyncio
async def test_interact_static_object_not_interactable():
    """Static objects should not be interactable."""
    game = _make_game()
    # Static objects are NOT indexed as interactive
    objects = [{"id": "rock_1", "type": "rock", "category": "static",
                "x": 1, "y": 1, "blocking": True}]
    room = _make_room_with_objects(objects=objects)
    ws, _ = _setup_player(game, room)

    await handle_interact(ws, {"action": "interact", "target_id": "rock_1"}, game=game)

    ws.send_json.assert_called_with({"type": "error", "detail": "Object not found"})


@pytest.mark.asyncio
async def test_interact_missing_target_id():
    game = _make_game()
    room = _make_room_with_objects()
    ws, _ = _setup_player(game, room)

    await handle_interact(ws, {"action": "interact"}, game=game)

    ws.send_json.assert_called_with({"type": "error", "detail": "Missing target_id"})


# ---------------------------------------------------------------------------
# RoomInstance object lookup
# ---------------------------------------------------------------------------

def test_room_get_object_found():
    objects = [{"id": "chest_01", "type": "chest", "category": "interactive",
                "x": 2, "y": 3, "state_scope": "player", "config": {}}]
    room = _make_room_with_objects(objects=objects)
    assert room.get_object("chest_01") is not None
    assert room.get_object("chest_01")["type"] == "chest"


def test_room_get_object_not_found():
    room = _make_room_with_objects()
    assert room.get_object("nonexistent") is None


def test_room_ignores_static_objects_in_interactive_index():
    objects = [
        {"id": "rock_1", "type": "rock", "category": "static", "x": 1, "y": 1, "blocking": True},
        {"id": "chest_01", "type": "chest", "category": "interactive", "x": 2, "y": 2},
    ]
    room = _make_room_with_objects(objects=objects)
    assert room.get_object("rock_1") is None
    assert room.get_object("chest_01") is not None


# ---------------------------------------------------------------------------
# State helpers (player-scoped and room-scoped)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_player_object_state_round_trip():
    """Write and read back player-scoped state."""
    from sqlalchemy import delete

    from server.core.database import async_session, init_db
    from server.room.models import PlayerObjectState
    from server.room.objects.state import get_player_object_state, set_player_object_state

    await init_db()
    async with async_session() as session:
        room_key, obj_id, pid = "rt_room", "rt_chest", 99

        # Clean up any leftover data from prior runs
        await session.execute(
            delete(PlayerObjectState).where(
                PlayerObjectState.player_id == pid,
                PlayerObjectState.room_key == room_key,
                PlayerObjectState.object_id == obj_id,
            )
        )
        await session.commit()

        # Initially empty
        state = await get_player_object_state(session, pid, room_key, obj_id)
        assert state == {}

        # Set state
        await set_player_object_state(session, pid, room_key, obj_id, {"opened": True})

        # Read back
        state = await get_player_object_state(session, pid, room_key, obj_id)
        assert state == {"opened": True}

        # Update state
        await set_player_object_state(session, pid, room_key, obj_id, {"opened": True, "looted": True})
        state = await get_player_object_state(session, pid, room_key, obj_id)
        assert state == {"opened": True, "looted": True}


@pytest.mark.asyncio
async def test_player_object_state_per_player():
    """Different players have independent state for the same object."""
    from server.core.database import async_session, init_db
    from server.room.objects.state import get_player_object_state, set_player_object_state

    await init_db()
    async with async_session() as session:
        room_key, obj_id = "pp_room", "pp_chest"
        await set_player_object_state(session, 101, room_key, obj_id, {"opened": True})
        await set_player_object_state(session, 102, room_key, obj_id, {"opened": False})

        state1 = await get_player_object_state(session, 101, room_key, obj_id)
        state2 = await get_player_object_state(session, 102, room_key, obj_id)
        assert state1 == {"opened": True}
        assert state2 == {"opened": False}


@pytest.mark.asyncio
async def test_room_object_state_round_trip():
    """Write and read back room-scoped (shared) state."""
    from sqlalchemy import delete

    from server.core.database import async_session, init_db
    from server.room.models import RoomState
    from server.room.objects.state import get_room_object_state, set_room_object_state

    await init_db()
    async with async_session() as session:
        room_key, obj_id = "rrt_room", "rrt_lever"

        # Clean up any leftover data from prior runs
        await session.execute(
            delete(RoomState).where(RoomState.room_key == room_key)
        )
        await session.commit()

        # Initially empty
        state = await get_room_object_state(session, room_key, obj_id)
        assert state == {}

        # Set state
        await set_room_object_state(session, room_key, obj_id, {"active": True})

        # Read back
        state = await get_room_object_state(session, room_key, obj_id)
        assert state == {"active": True}


@pytest.mark.asyncio
async def test_room_object_state_shared_across_objects():
    """Multiple objects in the same room have independent shared state."""
    from server.core.database import async_session, init_db
    from server.room.objects.state import get_room_object_state, set_room_object_state

    await init_db()
    async with async_session() as session:
        room_key = "rso_room"
        await set_room_object_state(session, room_key, "lever_a", {"active": True})
        await set_room_object_state(session, room_key, "lever_b", {"active": False})

        state1 = await get_room_object_state(session, room_key, "lever_a")
        state2 = await get_room_object_state(session, room_key, "lever_b")
        assert state1 == {"active": True}
        assert state2 == {"active": False}
