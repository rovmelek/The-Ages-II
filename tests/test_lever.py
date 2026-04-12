"""Tests for lever interactive objects (Story 3.3)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.net.handlers.interact import handle_interact
from server.player.entity import PlayerEntity
from server.room.objects.lever import LeverObject
from server.room.objects.registry import OBJECT_HANDLERS
from server.room.room import RoomInstance
from server.room.tile import TileType


from server.player.session import PlayerSession


def _ps(d: dict) -> PlayerSession:
    """Build a PlayerSession from a dict (test helper)."""
    entity = d["entity"]
    return PlayerSession(
        entity=entity,
        room_key=d["room_key"],
        db_id=d.get("db_id") or getattr(entity, "player_db_id", 0),
        inventory=d.get("inventory"),
        visited_rooms=set(d.get("visited_rooms", [])),
        pending_level_ups=d.get("pending_level_ups", 0),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_transaction():
    mock_session = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=mock_ctx)


def _make_game():
    from server.app import Game
    game = Game()
    game.transaction = _mock_transaction()
    return game


def _make_room_with_lever(room_key="test", target_x=3, target_y=2, initial_tile=TileType.WALL):
    """5x5 room with a lever that targets tile (target_x, target_y)."""
    tile_data = [[0] * 5 for _ in range(5)]
    tile_data[target_y][target_x] = initial_tile
    objects = [{
        "id": "lever_01", "type": "lever", "category": "interactive",
        "x": 1, "y": 0, "state_scope": "room",
        "config": {"target_x": target_x, "target_y": target_y, "action": "toggle"},
    }]
    return RoomInstance(room_key, "Test Room", 5, 5, tile_data, objects=objects)


def _setup_player(game, room, entity_id="player_1", db_id=1):
    entity = PlayerEntity(id=entity_id, name="hero", x=0, y=0, player_db_id=db_id)
    room.add_entity(entity)
    game.room_manager._rooms[room.room_key] = room
    ws = AsyncMock()
    game.connection_manager.connect(entity_id, ws, room.room_key)
    game.player_manager.set_session(entity_id, _ps({
        "entity": entity, "room_key": room.room_key, "db_id": db_id,
    }))
    return ws, entity


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def test_lever_registered():
    assert "lever" in OBJECT_HANDLERS
    assert OBJECT_HANDLERS["lever"] is LeverObject


# ---------------------------------------------------------------------------
# Lever interaction
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_lever_toggles_wall_to_floor():
    """First toggle: wall → floor."""
    game = _make_game()
    room = _make_room_with_lever(target_x=3, target_y=2, initial_tile=TileType.WALL)
    ws, _ = _setup_player(game, room)

    with patch("server.room.objects.lever.get_room_object_state", return_value={}), \
         patch("server.room.objects.lever.set_room_object_state") as mock_set, \
         patch("server.net.handlers.interact.get_player_object_state", return_value={}), \
         patch("server.net.handlers.interact.set_player_object_state"):

        await handle_interact(ws, {"action": "interact", "target_id": "lever_01"}, game=game)

    # Tile should now be floor
    assert room._grid[2][3] == TileType.FLOOR

    # interact_result should confirm toggle
    msg = ws.send_json.call_args_list[0].args[0]
    # First call is broadcast (tile_changed), find interact_result
    calls = [c.args[0] for c in ws.send_json.call_args_list]
    result_msgs = [c for c in calls if c.get("type") == "interact_result"]
    assert len(result_msgs) == 1
    assert result_msgs[0]["result"]["status"] == "toggled"
    assert result_msgs[0]["result"]["active"] is True

    # State should be saved
    mock_set.assert_called_once()
    # set_room_object_state(session, room_key, object_id, state_data)
    assert mock_set.call_args.args[2] == "lever_01"
    assert mock_set.call_args.args[3] == {"active": True}


@pytest.mark.asyncio
async def test_lever_toggles_back_to_wall():
    """Second toggle: floor → wall (already active)."""
    game = _make_game()
    room = _make_room_with_lever(target_x=3, target_y=2, initial_tile=TileType.FLOOR)
    ws, _ = _setup_player(game, room)

    with patch("server.room.objects.lever.get_room_object_state", return_value={"active": True}), \
         patch("server.room.objects.lever.set_room_object_state") as mock_set, \
         patch("server.net.handlers.interact.get_player_object_state", return_value={}), \
         patch("server.net.handlers.interact.set_player_object_state"):

        await handle_interact(ws, {"action": "interact", "target_id": "lever_01"}, game=game)

    # Tile should now be wall
    assert room._grid[2][3] == TileType.WALL

    calls = [c.args[0] for c in ws.send_json.call_args_list]
    result_msgs = [c for c in calls if c.get("type") == "interact_result"]
    assert result_msgs[0]["result"]["active"] is False

    mock_set.assert_called_once()
    assert mock_set.call_args.args[3] == {"active": False}


@pytest.mark.asyncio
async def test_lever_broadcasts_tile_changed():
    """All players in room receive tile_changed broadcast."""
    game = _make_game()
    room = _make_room_with_lever(target_x=3, target_y=2, initial_tile=TileType.WALL)
    ws1, _ = _setup_player(game, room, "player_1")

    # Add second player
    e2 = PlayerEntity(id="player_2", name="bob", x=0, y=0, player_db_id=2)
    room.add_entity(e2)
    ws2 = AsyncMock()
    game.connection_manager.connect("player_2", ws2, "test")
    game.player_manager.set_session("player_2", _ps({"entity": e2, "room_key": "test", "db_id": 2}))

    with patch("server.room.objects.lever.get_room_object_state", return_value={}), \
         patch("server.room.objects.lever.set_room_object_state"), \
         patch("server.net.handlers.interact.get_player_object_state", return_value={}), \
         patch("server.net.handlers.interact.set_player_object_state"):

        await handle_interact(ws1, {"action": "interact", "target_id": "lever_01"}, game=game)

    # Both players should receive tile_changed
    calls2 = [c.args[0] for c in ws2.send_json.call_args_list]
    tile_msgs = [c for c in calls2 if c.get("type") == "tile_changed"]
    assert len(tile_msgs) == 1
    assert tile_msgs[0]["x"] == 3
    assert tile_msgs[0]["y"] == 2
    assert tile_msgs[0]["tile_type"] == int(TileType.FLOOR)


@pytest.mark.asyncio
async def test_lever_interact_result_format():
    """interact_result contains status, active, target coordinates."""
    game = _make_game()
    room = _make_room_with_lever()
    ws, _ = _setup_player(game, room)

    with patch("server.room.objects.lever.get_room_object_state", return_value={}), \
         patch("server.room.objects.lever.set_room_object_state"), \
         patch("server.net.handlers.interact.get_player_object_state", return_value={}), \
         patch("server.net.handlers.interact.set_player_object_state"):

        await handle_interact(ws, {"action": "interact", "target_id": "lever_01"}, game=game)

    calls = [c.args[0] for c in ws.send_json.call_args_list]
    result_msgs = [c for c in calls if c.get("type") == "interact_result"]
    result = result_msgs[0]["result"]
    assert result["status"] == "toggled"
    assert "active" in result
    assert "target_x" in result
    assert "target_y" in result
