"""Tests for chest interactive objects (Story 3.2)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from server.net.handlers.interact import handle_interact
from server.player.entity import PlayerEntity
from server.room.objects.chest import ChestObject, generate_loot
from server.room.objects.registry import OBJECT_HANDLERS
from server.room.room import RoomInstance


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_game():
    from server.app import Game
    return Game()


def _chest_object_dict(obj_id="chest_01", loot_table="common_chest"):
    return {
        "id": obj_id,
        "type": "chest",
        "category": "interactive",
        "x": 1, "y": 0,
        "state_scope": "player",
        "config": {"loot_table": loot_table, "locked": False},
    }


def _make_room_with_chest(room_key="test", obj_id="chest_01", loot_table="common_chest"):
    objects = [_chest_object_dict(obj_id, loot_table)]
    return RoomInstance(
        room_key, "Test Room", 5, 5, [[0] * 5 for _ in range(5)],
        objects=objects,
    )


def _setup_player(game, room, entity_id="player_1", db_id=1):
    entity = PlayerEntity(id=entity_id, name="hero", x=0, y=0, player_db_id=db_id)
    room.add_entity(entity)
    game.room_manager._rooms[room.room_key] = room

    ws = AsyncMock()
    game.connection_manager.connect(entity_id, ws, room.room_key)
    game.player_entities[entity_id] = {
        "entity": entity, "room_key": room.room_key, "db_id": db_id,
    }
    return ws, entity


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def test_chest_registered_in_object_handlers():
    assert "chest" in OBJECT_HANDLERS
    assert OBJECT_HANDLERS["chest"] is ChestObject


# ---------------------------------------------------------------------------
# Loot generation
# ---------------------------------------------------------------------------

def test_generate_loot_common():
    items = generate_loot("common_chest")
    assert len(items) == 2
    keys = {i["item_key"] for i in items}
    assert "healing_potion" in keys
    assert "iron_shard" in keys


def test_generate_loot_unknown_table():
    items = generate_loot("nonexistent")
    assert items == []


# ---------------------------------------------------------------------------
# Chest interaction via handler
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_open_chest_first_time():
    """Opening a chest for the first time returns loot."""
    game = _make_game()
    room = _make_room_with_chest()
    ws, _ = _setup_player(game, room)

    # Mock DB calls inside ChestObject.interact
    mock_player = AsyncMock()
    mock_player.inventory = {}

    with patch("server.room.objects.chest.async_session") as mock_session, \
         patch("server.room.objects.chest.player_repo") as mock_repo, \
         patch("server.room.objects.chest.get_player_object_state", return_value={}), \
         patch("server.room.objects.chest.set_player_object_state") as mock_set_state:
        mock_sess = AsyncMock()
        mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_sess)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_repo.get_by_id = AsyncMock(return_value=mock_player)

        await handle_interact(
            ws, {"action": "interact", "target_id": "chest_01"}, game=game
        )

    msg = ws.send_json.call_args.args[0]
    assert msg["type"] == "interact_result"
    assert msg["result"]["status"] == "looted"
    assert len(msg["result"]["items"]) == 2

    # State should be marked opened
    mock_set_state.assert_called_once()
    call_args = mock_set_state.call_args
    assert call_args.args[3] == "chest_01"  # object_id
    assert call_args.args[4] == {"opened": True}  # state_data


@pytest.mark.asyncio
async def test_open_chest_already_looted():
    """Opening an already-opened chest returns 'Already looted'."""
    game = _make_game()
    room = _make_room_with_chest()
    ws, _ = _setup_player(game, room)

    with patch("server.room.objects.chest.async_session") as mock_session, \
         patch("server.room.objects.chest.get_player_object_state", return_value={"opened": True}):
        mock_sess = AsyncMock()
        mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_sess)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

        await handle_interact(
            ws, {"action": "interact", "target_id": "chest_01"}, game=game
        )

    msg = ws.send_json.call_args.args[0]
    assert msg["type"] == "interact_result"
    assert msg["result"]["status"] == "already_looted"
    assert msg["result"]["message"] == "Already looted"


@pytest.mark.asyncio
async def test_two_players_open_chest_independently():
    """Two players can open the same chest independently."""
    game = _make_game()
    room = _make_room_with_chest()
    ws1, _ = _setup_player(game, room, "player_1", db_id=1)
    ws2, _ = _setup_player(game, room, "player_2", db_id=2)

    mock_player = AsyncMock()
    mock_player.inventory = {}

    # Track per-player state
    player_states = {}

    async def mock_get_state(session, pid, rk, oid):
        return player_states.get((pid, oid), {})

    async def mock_set_state(session, pid, rk, oid, data):
        player_states[(pid, oid)] = data

    with patch("server.room.objects.chest.async_session") as mock_session, \
         patch("server.room.objects.chest.player_repo") as mock_repo, \
         patch("server.room.objects.chest.get_player_object_state", side_effect=mock_get_state), \
         patch("server.room.objects.chest.set_player_object_state", side_effect=mock_set_state):
        mock_sess = AsyncMock()
        mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_sess)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_repo.get_by_id = AsyncMock(return_value=mock_player)

        # Player 1 opens
        await handle_interact(
            ws1, {"action": "interact", "target_id": "chest_01"}, game=game
        )
        msg1 = ws1.send_json.call_args.args[0]
        assert msg1["result"]["status"] == "looted"

        # Player 2 opens independently
        await handle_interact(
            ws2, {"action": "interact", "target_id": "chest_01"}, game=game
        )
        msg2 = ws2.send_json.call_args.args[0]
        assert msg2["result"]["status"] == "looted"


@pytest.mark.asyncio
async def test_chest_loot_added_to_inventory():
    """Opening a chest adds items to the player's inventory."""
    game = _make_game()
    room = _make_room_with_chest()
    ws, _ = _setup_player(game, room)

    mock_player = AsyncMock()
    mock_player.inventory = {"healing_potion": 1}  # Already has 1

    with patch("server.room.objects.chest.async_session") as mock_session, \
         patch("server.room.objects.chest.player_repo") as mock_repo, \
         patch("server.room.objects.chest.get_player_object_state", return_value={}), \
         patch("server.room.objects.chest.set_player_object_state"):
        mock_sess = AsyncMock()
        mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_sess)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_repo.get_by_id = AsyncMock(return_value=mock_player)

        await handle_interact(
            ws, {"action": "interact", "target_id": "chest_01"}, game=game
        )

    # Inventory should have been updated: existing 1 + 1 from loot = 2
    assert mock_player.inventory["healing_potion"] == 2
    assert mock_player.inventory["iron_shard"] == 2
