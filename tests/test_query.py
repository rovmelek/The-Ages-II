"""Tests for query handlers: look, who, stats, help_actions (Story 10.4)."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from server.net.handlers.query import (
    handle_help_actions,
    handle_look,
    handle_stats,
    handle_who,
)
from server.player.entity import PlayerEntity
from server.room.objects.npc import NpcEntity
from server.room.room import RoomInstance


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_game():
    from server.app import Game
    return Game()


def _make_room(width=10, height=10, objects=None):
    return RoomInstance(
        "test", "Test Room", width, height,
        [[0] * width for _ in range(height)],
        objects=objects,
    )


_DEFAULT_STATS = {"hp": 85, "max_hp": 100, "attack": 12, "xp": 150}


def _setup_player(game, room, entity_id="player_1", name="alice", x=5, y=5, db_id=1, stats=None):
    entity = PlayerEntity(id=entity_id, name=name, x=x, y=y, player_db_id=db_id, stats=stats if stats is not None else dict(_DEFAULT_STATS))
    room.add_entity(entity)
    ws = AsyncMock()
    game.connection_manager.connect(entity_id, ws, "test")
    game.player_entities[entity_id] = {"entity": entity, "room_key": "test", "db_id": db_id}
    game.room_manager._rooms["test"] = room
    return ws, entity


# ---------------------------------------------------------------------------
# handle_look tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_look_returns_nearby_entities():
    game = _make_game()
    room = _make_room(objects=[
        {"id": "chest_01", "type": "chest", "x": 6, "y": 5, "category": "interactive", "blocking": False},
    ])
    ws, entity = _setup_player(game, room)

    # Add NPC adjacent (up)
    npc = NpcEntity(id="npc_1", npc_key="goblin", name="Goblin", x=5, y=4, behavior_type="hostile")
    room.add_npc(npc)

    # Add another player adjacent (down)
    bob = PlayerEntity(id="player_2", name="bob", x=5, y=6, player_db_id=2)
    room.add_entity(bob)

    await handle_look(ws, {"action": "look"}, game=game)

    response = ws.send_json.call_args[0][0]
    assert response["type"] == "look_result"
    assert {"id": "chest_01", "type": "chest", "direction": "right"} in response["objects"]
    assert {"name": "Goblin", "alive": True, "direction": "up"} in response["npcs"]
    assert {"name": "bob", "direction": "down"} in response["players"]


@pytest.mark.asyncio
async def test_look_excludes_self():
    game = _make_game()
    room = _make_room()
    ws, entity = _setup_player(game, room)

    await handle_look(ws, {"action": "look"}, game=game)

    response = ws.send_json.call_args[0][0]
    assert response["type"] == "look_result"
    player_names = [p["name"] for p in response["players"]]
    assert "alice" not in player_names


@pytest.mark.asyncio
async def test_look_empty_area():
    game = _make_game()
    room = _make_room()
    ws, _ = _setup_player(game, room)

    await handle_look(ws, {"action": "look"}, game=game)

    response = ws.send_json.call_args[0][0]
    assert response["type"] == "look_result"
    assert response["objects"] == []
    assert response["npcs"] == []
    assert response["players"] == []


@pytest.mark.asyncio
async def test_look_dead_npc():
    game = _make_game()
    room = _make_room()
    ws, _ = _setup_player(game, room)

    dead_npc = NpcEntity(id="npc_dead", npc_key="slime", name="Slime", x=6, y=5, behavior_type="hostile", is_alive=False)
    room.add_npc(dead_npc)

    await handle_look(ws, {"action": "look"}, game=game)

    response = ws.send_json.call_args[0][0]
    assert {"name": "Slime", "alive": False, "direction": "right"} in response["npcs"]


@pytest.mark.asyncio
async def test_look_object_on_player_tile():
    game = _make_game()
    room = _make_room(objects=[
        {"id": "lever_01", "type": "lever", "x": 5, "y": 5, "category": "interactive", "blocking": False},
    ])
    ws, _ = _setup_player(game, room)

    await handle_look(ws, {"action": "look"}, game=game)

    response = ws.send_json.call_args[0][0]
    assert {"id": "lever_01", "type": "lever", "direction": "here"} in response["objects"]


# ---------------------------------------------------------------------------
# handle_who tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_who_returns_room_players():
    game = _make_game()
    room = _make_room()
    ws, _ = _setup_player(game, room, entity_id="player_1", name="alice", x=5, y=5, db_id=1)

    bob = PlayerEntity(id="player_2", name="bob", x=3, y=7, player_db_id=2)
    room.add_entity(bob)
    game.player_entities["player_2"] = {"entity": bob, "room_key": "test", "db_id": 2}

    await handle_who(ws, {"action": "who"}, game=game)

    response = ws.send_json.call_args[0][0]
    assert response["type"] == "who_result"
    assert response["room"] == "test"
    names = {p["name"] for p in response["players"]}
    assert names == {"alice", "bob"}
    for p in response["players"]:
        assert "x" in p and "y" in p


@pytest.mark.asyncio
async def test_who_solo_player():
    game = _make_game()
    room = _make_room()
    ws, _ = _setup_player(game, room)

    await handle_who(ws, {"action": "who"}, game=game)

    response = ws.send_json.call_args[0][0]
    assert response["type"] == "who_result"
    assert len(response["players"]) == 1
    assert response["players"][0]["name"] == "alice"


# ---------------------------------------------------------------------------
# handle_stats tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stats_returns_player_stats():
    game = _make_game()
    room = _make_room()
    ws, _ = _setup_player(game, room, stats={"hp": 85, "max_hp": 100, "attack": 12, "xp": 150})

    await handle_stats(ws, {"action": "stats"}, game=game)

    response = ws.send_json.call_args[0][0]
    assert response == {
        "type": "stats_result",
        "stats": {"hp": 85, "max_hp": 100, "attack": 12, "xp": 150},
    }


@pytest.mark.asyncio
async def test_stats_excludes_transient():
    game = _make_game()
    room = _make_room()
    ws, _ = _setup_player(game, room, stats={"hp": 50, "max_hp": 100, "attack": 10, "xp": 0, "shield": 25})

    await handle_stats(ws, {"action": "stats"}, game=game)

    response = ws.send_json.call_args[0][0]
    assert "shield" not in response["stats"]
    assert set(response["stats"].keys()) == {"hp", "max_hp", "attack", "xp"}


@pytest.mark.asyncio
async def test_stats_defaults_for_missing_keys():
    game = _make_game()
    room = _make_room()
    ws, _ = _setup_player(game, room, stats={})

    await handle_stats(ws, {"action": "stats"}, game=game)

    response = ws.send_json.call_args[0][0]
    assert response == {
        "type": "stats_result",
        "stats": {"hp": 100, "max_hp": 100, "attack": 10, "xp": 0},
    }


# ---------------------------------------------------------------------------
# handle_help_actions tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_help_actions_returns_registered():
    game = _make_game()
    game._register_handlers()  # handlers registered during startup(), not __init__
    room = _make_room()
    ws, _ = _setup_player(game, room)

    await handle_help_actions(ws, {"action": "help_actions"}, game=game)

    response = ws.send_json.call_args[0][0]
    assert response["type"] == "help_result"
    actions = response["actions"]
    assert isinstance(actions, list)
    assert actions == sorted(actions)  # deterministic sorted order
    for expected in ["move", "chat", "look", "who", "stats", "help_actions", "logout", "interact", "inventory"]:
        assert expected in actions


# ---------------------------------------------------------------------------
# Not-logged-in tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_query_not_logged_in():
    game = _make_game()
    ws = AsyncMock()
    # WebSocket not registered — get_entity_id returns None

    for handler in [handle_look, handle_who, handle_stats, handle_help_actions]:
        ws.reset_mock()
        await handler(ws, {"action": "test"}, game=game)
        ws.send_json.assert_called_once_with({"type": "error", "detail": "Not logged in"})
