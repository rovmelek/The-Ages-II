"""Tests for player movement and collision (Story 2.1)."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from server.net.handlers.movement import handle_move
from server.player.entity import PlayerEntity
from server.room.room import RoomInstance
from server.room.tile import TileType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_game():
    """Create a minimal Game object for testing movement."""
    from server.app import Game
    game = Game()
    return game


def _setup_player(game, entity_id="player_1", x=2, y=2, room_key="test",
                   in_combat=False, tile_data=None):
    """Register a player entity in the game with a room."""
    if tile_data is None:
        tile_data = [[0] * 5 for _ in range(5)]
    room = RoomInstance(room_key, "Test Room", 5, 5, tile_data)
    entity = PlayerEntity(
        id=entity_id, name="hero", x=x, y=y, player_db_id=1,
        in_combat=in_combat,
    )
    room.add_entity(entity)
    game.room_manager._rooms[room_key] = room

    mock_ws = AsyncMock()
    game.connection_manager.connect(entity_id, mock_ws, room_key)
    game.player_entities[entity_id] = {
        "entity": entity, "room_key": room_key, "db_id": 1,
    }
    return mock_ws, entity, room


# ---------------------------------------------------------------------------
# Successful movement
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_move_right():
    game = _make_game()
    ws, entity, _ = _setup_player(game, x=2, y=2)

    await handle_move(ws, {"action": "move", "direction": "right"}, game=game)

    ws.send_json.assert_called_with(
        {"type": "entity_moved", "entity_id": "player_1", "x": 3, "y": 2}
    )
    assert entity.x == 3
    assert entity.y == 2


@pytest.mark.asyncio
async def test_move_left():
    game = _make_game()
    ws, entity, _ = _setup_player(game, x=2, y=2)

    await handle_move(ws, {"action": "move", "direction": "left"}, game=game)

    ws.send_json.assert_called_with(
        {"type": "entity_moved", "entity_id": "player_1", "x": 1, "y": 2}
    )


@pytest.mark.asyncio
async def test_move_up():
    game = _make_game()
    ws, entity, _ = _setup_player(game, x=2, y=2)

    await handle_move(ws, {"action": "move", "direction": "up"}, game=game)

    ws.send_json.assert_called_with(
        {"type": "entity_moved", "entity_id": "player_1", "x": 2, "y": 1}
    )


@pytest.mark.asyncio
async def test_move_down():
    game = _make_game()
    ws, entity, _ = _setup_player(game, x=2, y=2)

    await handle_move(ws, {"action": "move", "direction": "down"}, game=game)

    ws.send_json.assert_called_with(
        {"type": "entity_moved", "entity_id": "player_1", "x": 2, "y": 3}
    )


# ---------------------------------------------------------------------------
# Broadcast to other players
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_move_broadcasts_to_other_players():
    game = _make_game()
    tile_data = [[0] * 5 for _ in range(5)]
    room = RoomInstance("test", "Test Room", 5, 5, tile_data)
    game.room_manager._rooms["test"] = room

    e1 = PlayerEntity(id="player_1", name="alice", x=2, y=2, player_db_id=1)
    e2 = PlayerEntity(id="player_2", name="bob", x=1, y=1, player_db_id=2)
    room.add_entity(e1)
    room.add_entity(e2)

    ws1 = AsyncMock()
    ws2 = AsyncMock()
    game.connection_manager.connect("player_1", ws1, "test")
    game.connection_manager.connect("player_2", ws2, "test")
    game.player_entities["player_1"] = {"entity": e1, "room_key": "test", "db_id": 1}
    game.player_entities["player_2"] = {"entity": e2, "room_key": "test", "db_id": 2}

    await handle_move(ws1, {"action": "move", "direction": "right"}, game=game)

    # Both players should receive the broadcast
    expected = {"type": "entity_moved", "entity_id": "player_1", "x": 3, "y": 2}
    ws1.send_json.assert_called_with(expected)
    ws2.send_json.assert_called_with(expected)


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_move_wall_blocked():
    tile_data = [[0] * 5 for _ in range(5)]
    tile_data[2][3] = TileType.WALL  # Wall at (3, 2)
    game = _make_game()
    ws, entity, _ = _setup_player(game, x=2, y=2, tile_data=tile_data)

    await handle_move(ws, {"action": "move", "direction": "right"}, game=game)

    ws.send_json.assert_called_with(
        {"type": "error", "detail": "Tile not walkable"}
    )
    assert entity.x == 2  # Didn't move


@pytest.mark.asyncio
async def test_move_out_of_bounds():
    game = _make_game()
    ws, entity, _ = _setup_player(game, x=0, y=0)

    await handle_move(ws, {"action": "move", "direction": "left"}, game=game)

    ws.send_json.assert_called_with(
        {"type": "error", "detail": "Out of bounds"}
    )
    assert entity.x == 0


@pytest.mark.asyncio
async def test_move_invalid_direction():
    game = _make_game()
    ws, _, _ = _setup_player(game)

    await handle_move(ws, {"action": "move", "direction": "northwest"}, game=game)

    ws.send_json.assert_called_with(
        {"type": "error", "detail": "Invalid direction: northwest"}
    )


@pytest.mark.asyncio
async def test_move_in_combat():
    game = _make_game()
    ws, _, _ = _setup_player(game, in_combat=True)

    await handle_move(ws, {"action": "move", "direction": "right"}, game=game)

    ws.send_json.assert_called_with(
        {"type": "error", "detail": "Cannot move while in combat"}
    )


@pytest.mark.asyncio
async def test_move_not_logged_in():
    game = _make_game()
    mock_ws = AsyncMock()

    await handle_move(mock_ws, {"action": "move", "direction": "right"}, game=game)

    mock_ws.send_json.assert_called_with(
        {"type": "error", "detail": "Not logged in"}
    )


@pytest.mark.asyncio
async def test_move_missing_direction():
    game = _make_game()
    ws, _, _ = _setup_player(game)

    await handle_move(ws, {"action": "move"}, game=game)

    ws.send_json.assert_called_with(
        {"type": "error", "detail": "Invalid direction: "}
    )


# ---------------------------------------------------------------------------
# Proximity notification tests (Story 10.5)
# ---------------------------------------------------------------------------

def _setup_player_with_objects(game, objects, x=2, y=2, room_key="test"):
    """Register a player and room with interactive objects for proximity tests."""
    tile_data = [[0] * 10 for _ in range(10)]
    room = RoomInstance(room_key, "Test Room", 10, 10, tile_data, objects=objects)
    entity = PlayerEntity(
        id="player_1", name="hero", x=x, y=y, player_db_id=1,
    )
    room.add_entity(entity)
    game.room_manager._rooms[room_key] = room

    mock_ws = AsyncMock()
    game.connection_manager.connect("player_1", mock_ws, room_key)
    game.player_entities["player_1"] = {
        "entity": entity, "room_key": room_key, "db_id": 1,
    }
    return mock_ws, entity, room


@pytest.mark.asyncio
async def test_move_nearby_objects():
    """Moving near an interactive object sends a nearby_objects message."""
    game = _make_game()
    # Chest at (4, 2) — player will move from (2, 2) to (3, 2), making chest adjacent
    objects = [{"id": "chest_01", "type": "chest", "category": "interactive",
                "x": 4, "y": 2, "state_scope": "player", "config": {}}]
    ws, entity, _ = _setup_player_with_objects(game, objects, x=2, y=2)

    await handle_move(ws, {"action": "move", "direction": "right"}, game=game)

    # Check all send_json calls for the nearby_objects message
    calls = [call.args[0] for call in ws.send_json.call_args_list]
    nearby_msgs = [c for c in calls if c.get("type") == "nearby_objects"]
    assert len(nearby_msgs) == 1
    assert nearby_msgs[0]["objects"] == [
        {"id": "chest_01", "type": "chest", "direction": "right"}
    ]


@pytest.mark.asyncio
async def test_move_no_nearby_objects():
    """Moving away from all objects does not send nearby_objects."""
    game = _make_game()
    # Chest at (8, 8) — far from player at (2, 2) moving to (3, 2)
    objects = [{"id": "chest_01", "type": "chest", "category": "interactive",
                "x": 8, "y": 8, "state_scope": "player", "config": {}}]
    ws, entity, _ = _setup_player_with_objects(game, objects, x=2, y=2)

    await handle_move(ws, {"action": "move", "direction": "right"}, game=game)

    calls = [call.args[0] for call in ws.send_json.call_args_list]
    nearby_msgs = [c for c in calls if c.get("type") == "nearby_objects"]
    assert len(nearby_msgs) == 0
