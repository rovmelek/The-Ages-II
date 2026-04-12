"""Tests for room transitions via exit tiles (Story 2.3)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.net.handlers.movement import handle_move
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
# Helpers
# ---------------------------------------------------------------------------

def _mock_transaction():
    """Create a mock async context manager for game.transaction."""
    mock_session = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_factory = MagicMock(return_value=mock_ctx)
    return mock_factory, mock_session


def _make_game():
    from server.app import Game
    game = Game()
    factory, _ = _mock_transaction()
    game.transaction = factory
    return game


def _make_exit_room(room_key="room_a"):
    """5x5 room with exit tile at (4, 2) leading to room_b."""
    tile_data = [[0] * 5 for _ in range(5)]
    tile_data[2][4] = TileType.EXIT
    exits = [{"target_room": "room_b", "x": 4, "y": 2, "entry_x": 1, "entry_y": 1}]
    return RoomInstance(
        room_key, "Room A", 5, 5, tile_data,
        exits=exits,
        spawn_points=[{"type": "player", "x": 0, "y": 0}],
    )


def _make_target_room(room_key="room_b"):
    """5x5 target room with spawn at (1, 1)."""
    return RoomInstance(
        room_key, "Room B", 5, 5, [[0] * 5 for _ in range(5)],
        spawn_points=[{"type": "player", "x": 1, "y": 1}],
    )


def _setup_player_in_room(game, room, entity_id="player_1", x=3, y=2):
    """Place a player in a room and register with game."""
    entity = PlayerEntity(id=entity_id, name="hero", x=x, y=y, player_db_id=1)
    room.add_entity(entity)
    game.room_manager._rooms[room.room_key] = room

    ws = AsyncMock()
    game.connection_manager.connect(entity_id, ws, room.room_key)
    game.player_manager.set_session(entity_id, _ps({
        "entity": entity, "room_key": room.room_key, "db_id": 1,
    }))
    return ws, entity


# ---------------------------------------------------------------------------
# Successful room transition
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_exit_removes_from_old_room():
    game = _make_game()
    room_a = _make_exit_room()
    room_b = _make_target_room()
    game.room_manager._rooms["room_b"] = room_b

    ws, entity = _setup_player_in_room(game, room_a, x=3, y=2)

    await handle_move(ws, {"action": "move", "direction": "right"}, game=game)

    # Entity removed from old room
    assert "player_1" not in room_a.get_player_ids()
    # Entity added to new room
    assert "player_1" in room_b.get_player_ids()


@pytest.mark.asyncio
async def test_exit_entity_at_entry_coordinates():
    game = _make_game()
    room_a = _make_exit_room()
    room_b = _make_target_room()
    game.room_manager._rooms["room_b"] = room_b

    ws, entity = _setup_player_in_room(game, room_a, x=3, y=2)

    await handle_move(ws, {"action": "move", "direction": "right"}, game=game)

    # Entity should be at entry coordinates from exit info
    assert entity.x == 1
    assert entity.y == 1


@pytest.mark.asyncio
async def test_exit_uses_spawn_when_no_entry_coords():
    """If exit has no entry_x/entry_y, use target room's player spawn."""
    game = _make_game()
    tile_data = [[0] * 5 for _ in range(5)]
    tile_data[2][4] = TileType.EXIT
    # Exit without entry_x/entry_y
    exits = [{"target_room": "room_b", "x": 4, "y": 2}]
    room_a = RoomInstance("room_a", "Room A", 5, 5, tile_data, exits=exits)

    room_b = RoomInstance("room_b", "Room B", 5, 5, [[0] * 5 for _ in range(5)],
                          spawn_points=[{"type": "player", "x": 3, "y": 3}])
    game.room_manager._rooms["room_b"] = room_b

    ws, entity = _setup_player_in_room(game, room_a, x=3, y=2)

    await handle_move(ws, {"action": "move", "direction": "right"}, game=game)

    assert entity.x == 3
    assert entity.y == 3


@pytest.mark.asyncio
async def test_exit_sends_room_state():
    game = _make_game()
    room_a = _make_exit_room()
    room_b = _make_target_room()
    game.room_manager._rooms["room_b"] = room_b

    ws, entity = _setup_player_in_room(game, room_a, x=3, y=2)

    await handle_move(ws, {"action": "move", "direction": "right"}, game=game)

    # Player should receive room_state for new room
    calls = [c.args[0] for c in ws.send_json.call_args_list]
    room_state_msgs = [c for c in calls if c.get("type") == "room_state"]
    assert len(room_state_msgs) == 1
    assert room_state_msgs[0]["room_key"] == "room_b"


@pytest.mark.asyncio
async def test_exit_updates_tracking():
    game = _make_game()
    room_a = _make_exit_room()
    room_b = _make_target_room()
    game.room_manager._rooms["room_b"] = room_b

    ws, entity = _setup_player_in_room(game, room_a, x=3, y=2)

    await handle_move(ws, {"action": "move", "direction": "right"}, game=game)

    # player_manager should reflect new room
    assert game.player_manager.get_session("player_1").room_key == "room_b"
    # connection_manager should reflect new room
    assert game.connection_manager.get_room("player_1") == "room_b"


@pytest.mark.asyncio
async def test_exit_saves_position_to_db():
    game = _make_game()
    room_a = _make_exit_room()
    room_b = _make_target_room()
    game.room_manager._rooms["room_b"] = room_b

    ws, entity = _setup_player_in_room(game, room_a, x=3, y=2)

    factory, mock_sess = _mock_transaction()
    game.transaction = factory

    with patch("server.net.handlers.movement.player_repo") as mock_repo, \
         patch("server.net.handlers.movement.grant_xp", new_callable=AsyncMock):
        mock_repo.update_position = AsyncMock()
        mock_repo.update_visited_rooms = AsyncMock()

        await handle_move(ws, {"action": "move", "direction": "right"}, game=game)

        mock_repo.update_position.assert_called_once_with(
            mock_sess, 1, "room_b", 1, 1
        )


# ---------------------------------------------------------------------------
# Broadcasts
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_exit_broadcasts_entity_left_to_old_room():
    game = _make_game()
    room_a = _make_exit_room()
    room_b = _make_target_room()
    game.room_manager._rooms["room_b"] = room_b

    ws1, _ = _setup_player_in_room(game, room_a, "player_1", x=3, y=2)

    # Second player in room_a
    other = PlayerEntity(id="player_2", name="bob", x=0, y=0, player_db_id=2)
    room_a.add_entity(other)
    ws2 = AsyncMock()
    game.connection_manager.connect("player_2", ws2, "room_a")
    game.player_manager.set_session("player_2", _ps({"entity": other, "room_key": "room_a", "db_id": 2}))

    await handle_move(ws1, {"action": "move", "direction": "right"}, game=game)

    # Player 2 should receive entity_left
    calls = [c.args[0] for c in ws2.send_json.call_args_list]
    left_msgs = [c for c in calls if c.get("type") == "entity_left"]
    assert len(left_msgs) == 1
    assert left_msgs[0]["entity_id"] == "player_1"


@pytest.mark.asyncio
async def test_exit_broadcasts_entity_entered_to_new_room():
    game = _make_game()
    room_a = _make_exit_room()
    room_b = _make_target_room()
    game.room_manager._rooms["room_b"] = room_b

    # Player already in room_b
    other = PlayerEntity(id="player_2", name="bob", x=0, y=0, player_db_id=2)
    room_b.add_entity(other)
    ws2 = AsyncMock()
    game.connection_manager.connect("player_2", ws2, "room_b")
    game.player_manager.set_session("player_2", _ps({"entity": other, "room_key": "room_b", "db_id": 2}))

    ws1, _ = _setup_player_in_room(game, room_a, "player_1", x=3, y=2)

    await handle_move(ws1, {"action": "move", "direction": "right"}, game=game)

    # Player 2 (in room_b) should receive entity_entered
    calls = [c.args[0] for c in ws2.send_json.call_args_list]
    entered_msgs = [c for c in calls if c.get("type") == "entity_entered"]
    assert len(entered_msgs) == 1
    assert entered_msgs[0]["entity"]["name"] == "hero"


# ---------------------------------------------------------------------------
# Error: exit leads nowhere
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_exit_loads_target_room_from_db():
    """If target room is not in memory but exists in DB, load it and transition."""
    game = _make_game()
    room_a = _make_exit_room()
    # Do NOT add room_b to room_manager — it must be loaded from DB

    ws, entity = _setup_player_in_room(game, room_a, x=3, y=2)

    # Create a fake DB room model with the attributes load_room expects
    class FakeRoomDB:
        room_key = "room_b"
        name = "Room B"
        width = 5
        height = 5
        tile_data = [[0] * 5 for _ in range(5)]
        exits = []
        objects = []
        spawn_points = [{"type": "player", "x": 2, "y": 2}]

    factory, _ = _mock_transaction()
    game.transaction = factory

    with patch("server.net.handlers.movement.room_repo") as mock_room_repo, \
         patch("server.net.handlers.movement.player_repo") as mock_player_repo, \
         patch("server.net.handlers.movement.grant_xp", new_callable=AsyncMock):
        mock_room_repo.get_by_key = AsyncMock(return_value=FakeRoomDB())
        mock_player_repo.update_position = AsyncMock()
        mock_player_repo.update_visited_rooms = AsyncMock()

        await handle_move(ws, {"action": "move", "direction": "right"}, game=game)

    # Room should now be loaded in room_manager
    assert game.room_manager.get_room("room_b") is not None
    # Entity should be in room_b at entry coords from exit info
    assert entity.x == 1
    assert entity.y == 1
    assert "player_1" in game.room_manager.get_room("room_b").get_player_ids()
    assert "player_1" not in room_a.get_player_ids()
    # Player should receive room_state
    calls = [c.args[0] for c in ws.send_json.call_args_list]
    room_state_msgs = [c for c in calls if c.get("type") == "room_state"]
    assert len(room_state_msgs) == 1
    assert room_state_msgs[0]["room_key"] == "room_b"


@pytest.mark.asyncio
async def test_exit_leads_nowhere():
    """If target room doesn't exist in memory or DB, error and revert position."""
    game = _make_game()
    tile_data = [[0] * 5 for _ in range(5)]
    tile_data[2][4] = TileType.EXIT
    exits = [{"target_room": "nonexistent_room", "x": 4, "y": 2}]
    room_a = RoomInstance("room_a", "Room A", 5, 5, tile_data, exits=exits)

    ws, entity = _setup_player_in_room(game, room_a, x=3, y=2)

    factory, _ = _mock_transaction()
    game.transaction = factory

    with patch("server.net.handlers.movement.room_repo") as mock_room_repo:
        mock_room_repo.get_by_key = AsyncMock(return_value=None)

        await handle_move(ws, {"action": "move", "direction": "right"}, game=game)

    ws.send_json.assert_called_with(
        {"type": "error", "detail": "Exit leads nowhere"}
    )
    # Position should be reverted
    assert entity.x == 3
    assert entity.y == 2
    # Entity should still be in old room
    assert "player_1" in room_a.get_player_ids()
