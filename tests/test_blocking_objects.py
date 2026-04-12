"""Tests for non-walkable interactive objects (Story 10.2)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.player.entity import PlayerEntity
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
# Blocking behavior
# ---------------------------------------------------------------------------

def test_blocking_interactive_object_makes_tile_unwalkable():
    """Interactive object with blocking=true stamps WALL on the grid."""
    tile_data = [[0] * 5 for _ in range(5)]
    objects = [
        {"id": "chest_01", "type": "chest", "x": 2, "y": 2,
         "category": "interactive", "blocking": True,
         "state_scope": "player", "config": {}},
    ]
    room = RoomInstance("test", "Test", 5, 5, tile_data, objects=objects)

    assert room._grid[2][2] == TileType.WALL
    assert not room.is_walkable(2, 2)


def test_non_blocking_interactive_object_remains_walkable():
    """Interactive object with blocking=false does NOT affect the grid."""
    tile_data = [[0] * 5 for _ in range(5)]
    objects = [
        {"id": "fountain_01", "type": "fountain", "x": 2, "y": 2,
         "category": "static", "blocking": False},
    ]
    room = RoomInstance("test", "Test", 5, 5, tile_data, objects=objects)

    assert room._grid[2][2] == TileType.FLOOR
    assert room.is_walkable(2, 2)


def test_movement_blocked_by_interactive_object():
    """Player cannot walk onto a tile with a blocking interactive object."""
    tile_data = [[0] * 5 for _ in range(5)]
    objects = [
        {"id": "chest_01", "type": "chest", "x": 1, "y": 0,
         "category": "interactive", "blocking": True,
         "state_scope": "player", "config": {}},
    ]
    room = RoomInstance("test", "Test", 5, 5, tile_data, objects=objects)

    entity = PlayerEntity(id="player_1", name="hero", x=0, y=0, player_db_id=1)
    room.add_entity(entity)

    result = room.move_entity("player_1", "right")
    assert result["success"] is False
    assert entity.x == 0  # Position unchanged


# ---------------------------------------------------------------------------
# Adjacency check
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_interact_adjacent_succeeds():
    """Interact succeeds when player is adjacent (Manhattan distance = 1)."""
    from server.net.handlers.interact import handle_interact

    game = _make_game()
    objects = [
        {"id": "chest_01", "type": "chest", "x": 1, "y": 0,
         "category": "interactive", "blocking": True,
         "state_scope": "player", "config": {"loot_table": "common_chest", "locked": False}},
    ]
    room = RoomInstance("test", "Test", 5, 5, [[0] * 5 for _ in range(5)], objects=objects)
    ws, entity = _setup_player(game, room)
    # Player at (0,0), chest at (1,0) — distance 1

    with _chest_patches():
        await handle_interact(ws, {"action": "interact", "target_id": "chest_01"}, game=game)

    # Should succeed (get interact_result, not error)
    last_msg = ws.send_json.call_args[0][0]
    assert last_msg["type"] == "interact_result"


@pytest.mark.asyncio
async def test_interact_too_far_rejected():
    """Interact fails with 'Too far to interact' when player is distant."""
    from server.net.handlers.interact import handle_interact

    game = _make_game()
    objects = [
        {"id": "chest_01", "type": "chest", "x": 3, "y": 3,
         "category": "interactive", "blocking": True,
         "state_scope": "player", "config": {"loot_table": "common_chest", "locked": False}},
    ]
    room = RoomInstance("test", "Test", 5, 5, [[0] * 5 for _ in range(5)], objects=objects)
    ws, entity = _setup_player(game, room)
    # Player at (0,0), chest at (3,3) — distance 6

    await handle_interact(ws, {"action": "interact", "target_id": "chest_01"}, game=game)

    ws.send_json.assert_called_with({"type": "error", "detail": "Too far to interact"})


@pytest.mark.asyncio
async def test_interact_distance_zero_allowed():
    """Interact succeeds when player is on the same tile (distance 0)."""
    from server.net.handlers.interact import handle_interact

    game = _make_game()
    objects = [
        {"id": "chest_01", "type": "chest", "x": 0, "y": 0,
         "category": "interactive",
         "state_scope": "player", "config": {"loot_table": "common_chest", "locked": False}},
    ]
    # No blocking — so player can be placed at (0,0)
    room = RoomInstance("test", "Test", 5, 5, [[0] * 5 for _ in range(5)], objects=objects)
    ws, entity = _setup_player(game, room)
    # Player at (0,0), chest at (0,0) — distance 0

    with _chest_patches():
        await handle_interact(ws, {"action": "interact", "target_id": "chest_01"}, game=game)

    last_msg = ws.send_json.call_args[0][0]
    assert last_msg["type"] == "interact_result"


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


def _setup_player(game, room, entity_id="player_1"):
    entity = PlayerEntity(
        id=entity_id, name="hero", x=0, y=0, player_db_id=1,
        stats={"hp": 100, "max_hp": 100, "attack": 10},
    )
    room.add_entity(entity)
    game.room_manager._rooms[room.room_key] = room
    ws = AsyncMock()
    game.connection_manager.connect(entity_id, ws, room.room_key)
    game.player_manager.set_session(entity_id, _ps({
        "entity": entity, "room_key": room.room_key, "db_id": 1,
    }))
    return ws, entity


def _chest_patches():
    """Context manager that patches chest DB calls for interact tests."""
    from contextlib import contextmanager
    from unittest.mock import patch

    @contextmanager
    def _patch():
        mock_player = AsyncMock()
        mock_player.inventory = {}
        with patch("server.room.objects.chest.player_repo") as mock_repo, \
             patch("server.room.objects.chest.get_player_object_state", return_value={}), \
             patch("server.room.objects.chest.set_player_object_state"), \
             patch("server.net.handlers.interact.get_player_object_state", return_value={}), \
             patch("server.net.handlers.interact.set_player_object_state"):
            mock_repo.get_by_id = AsyncMock(return_value=mock_player)
            mock_repo.update_inventory = AsyncMock()
            yield
    return _patch()
