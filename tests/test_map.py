"""Tests for handle_map (Story 12.8: World Map)."""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest

from server.net.handlers.query import handle_map
from server.player.entity import PlayerEntity
from server.room.room import RoomInstance


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_game():
    from server.app import Game
    return Game()


def _make_room(room_key, name, width=5, height=5, exits=None):
    return RoomInstance(
        room_key=room_key,
        name=name,
        width=width,
        height=height,
        tile_data=[[0] * width for _ in range(height)],
        exits=exits or [],
    )


def _setup_player(game, room_key, entity_id="player_1", name="alice",
                   x=1, y=1, db_id=1, visited_rooms=None):
    entity = PlayerEntity(
        id=entity_id, name=name, x=x, y=y, player_db_id=db_id,
        stats={"hp": 100, "max_hp": 100},
    )
    ws = AsyncMock()
    game.connection_manager.connect(entity_id, ws, room_key)
    game.player_entities[entity_id] = {
        "entity": entity,
        "room_key": room_key,
        "db_id": db_id,
        "visited_rooms": visited_rooms if visited_rooms is not None else [],
    }
    return ws, entity


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_map_not_logged_in():
    """Unauthenticated player gets error."""
    game = _make_game()
    ws = AsyncMock()

    await handle_map(ws, {"action": "map"}, game=game)

    ws.send_json.assert_called_once_with({"type": "error", "detail": "Not logged in"})


@pytest.mark.asyncio
async def test_map_no_visited_rooms():
    """Empty visited_rooms returns empty map."""
    game = _make_game()
    room = _make_room("town_square", "Town Square")
    game.room_manager._rooms["town_square"] = room
    ws, _ = _setup_player(game, "town_square", visited_rooms=[])

    await handle_map(ws, {"action": "map"}, game=game)

    response = ws.send_json.call_args[0][0]
    assert response["type"] == "map_data"
    assert response["rooms"] == []
    assert response["connections"] == []


@pytest.mark.asyncio
async def test_map_single_room():
    """One visited room shows room + connections with ??? destinations."""
    game = _make_game()
    room = _make_room("town_square", "Town Square", exits=[
        {"target_room": "dark_cave", "x": 50, "y": 99, "direction": "south", "entry_x": 50, "entry_y": 1},
        {"target_room": "test_room", "x": 99, "y": 50, "direction": "east", "entry_x": 1, "entry_y": 2},
    ])
    game.room_manager._rooms["town_square"] = room
    ws, _ = _setup_player(game, "town_square", visited_rooms=["town_square"])

    await handle_map(ws, {"action": "map"}, game=game)

    response = ws.send_json.call_args[0][0]
    assert response["type"] == "map_data"
    assert len(response["rooms"]) == 1
    assert response["rooms"][0] == {"room_key": "town_square", "name": "Town Square"}
    assert len(response["connections"]) == 2
    for conn in response["connections"]:
        assert conn["from_room"] == "town_square"
        assert conn["to_room"] == "???"


@pytest.mark.asyncio
async def test_map_multiple_rooms():
    """Two visited rooms show both rooms and resolved connections."""
    game = _make_game()
    ts = _make_room("town_square", "Town Square", exits=[
        {"target_room": "dark_cave", "x": 50, "y": 99, "direction": "south", "entry_x": 50, "entry_y": 1},
        {"target_room": "test_room", "x": 99, "y": 50, "direction": "east", "entry_x": 1, "entry_y": 2},
    ])
    dc = _make_room("dark_cave", "Dark Cave", exits=[
        {"target_room": "town_square", "x": 50, "y": 1, "direction": "north", "entry_x": 50, "entry_y": 98},
    ])
    game.room_manager._rooms["town_square"] = ts
    game.room_manager._rooms["dark_cave"] = dc
    ws, _ = _setup_player(game, "town_square", visited_rooms=["town_square", "dark_cave"])

    await handle_map(ws, {"action": "map"}, game=game)

    response = ws.send_json.call_args[0][0]
    assert len(response["rooms"]) == 2
    room_keys = {r["room_key"] for r in response["rooms"]}
    assert room_keys == {"town_square", "dark_cave"}

    # town_square -> dark_cave should be resolved (name)
    ts_to_dc = [c for c in response["connections"]
                if c["from_room"] == "town_square" and c["direction"] == "south"]
    assert len(ts_to_dc) == 1
    assert ts_to_dc[0]["to_room"] == "Dark Cave"

    # town_square -> test_room should be ???
    ts_to_tr = [c for c in response["connections"]
                if c["from_room"] == "town_square" and c["direction"] == "east"]
    assert len(ts_to_tr) == 1
    assert ts_to_tr[0]["to_room"] == "???"

    # dark_cave -> town_square should be resolved
    dc_to_ts = [c for c in response["connections"]
                if c["from_room"] == "dark_cave" and c["direction"] == "north"]
    assert len(dc_to_ts) == 1
    assert dc_to_ts[0]["to_room"] == "Town Square"


@pytest.mark.asyncio
async def test_map_all_rooms_visited():
    """All 4 rooms visited — complete map with no ???."""
    game = _make_game()
    rooms_data = [
        ("town_square", "Town Square", [
            {"target_room": "dark_cave", "x": 50, "y": 99, "direction": "south", "entry_x": 50, "entry_y": 1},
            {"target_room": "test_room", "x": 99, "y": 50, "direction": "east", "entry_x": 1, "entry_y": 2},
        ]),
        ("dark_cave", "Dark Cave", [
            {"target_room": "town_square", "x": 50, "y": 1, "direction": "north", "entry_x": 50, "entry_y": 98},
            {"target_room": "other_room", "x": 99, "y": 50, "direction": "east", "entry_x": 1, "entry_y": 2},
        ]),
        ("test_room", "Test Room", [
            {"target_room": "other_room", "x": 4, "y": 2, "direction": "east", "entry_x": 0, "entry_y": 2},
            {"target_room": "town_square", "x": 0, "y": 2, "direction": "west", "entry_x": 98, "entry_y": 50},
        ]),
        ("other_room", "Other Room", [
            {"target_room": "test_room", "x": 0, "y": 4, "direction": "west", "entry_x": 2, "entry_y": 2},
            {"target_room": "dark_cave", "x": 4, "y": 0, "direction": "north", "entry_x": 98, "entry_y": 50},
        ]),
    ]
    all_keys = [r[0] for r in rooms_data]
    for rk, name, exits in rooms_data:
        game.room_manager._rooms[rk] = _make_room(rk, name, exits=exits)

    ws, _ = _setup_player(game, "town_square", visited_rooms=list(all_keys))

    await handle_map(ws, {"action": "map"}, game=game)

    response = ws.send_json.call_args[0][0]
    assert len(response["rooms"]) == 4
    for conn in response["connections"]:
        assert conn["to_room"] != "???", f"Unexpected ??? for {conn}"


@pytest.mark.asyncio
async def test_map_stale_room_skipped(caplog):
    """Room key in visited_rooms but not in RoomManager is skipped with warning."""
    game = _make_game()
    room = _make_room("town_square", "Town Square")
    game.room_manager._rooms["town_square"] = room
    ws, _ = _setup_player(game, "town_square",
                           visited_rooms=["town_square", "deleted_room"])

    with caplog.at_level(logging.WARNING):
        await handle_map(ws, {"action": "map"}, game=game)

    response = ws.send_json.call_args[0][0]
    assert len(response["rooms"]) == 1
    assert response["rooms"][0]["room_key"] == "town_square"
    assert any("deleted_room" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_map_connections_undiscovered_shown_as_question_marks():
    """Exits to unvisited rooms show ??? as to_room."""
    game = _make_game()
    room = _make_room("town_square", "Town Square", exits=[
        {"target_room": "dark_cave", "x": 50, "y": 99, "direction": "south", "entry_x": 50, "entry_y": 1},
    ])
    game.room_manager._rooms["town_square"] = room
    # dark_cave exists in RoomManager but NOT in visited_rooms
    dc = _make_room("dark_cave", "Dark Cave")
    game.room_manager._rooms["dark_cave"] = dc
    ws, _ = _setup_player(game, "town_square", visited_rooms=["town_square"])

    await handle_map(ws, {"action": "map"}, game=game)

    response = ws.send_json.call_args[0][0]
    assert len(response["connections"]) == 1
    assert response["connections"][0]["to_room"] == "???"
