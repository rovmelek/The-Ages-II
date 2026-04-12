"""Tests for interaction XP — first-time object interaction rewards."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.net.handlers.interact import handle_interact
from server.player.manager import PlayerManager
from server.player.session import PlayerSession
from server.room.objects.chest import ChestObject
from server.room.objects.lever import LeverObject


def _make_entity(entity_id="player_1", name="TestPlayer", x=2, y=2, db_id=1):
    entity = MagicMock()
    entity.id = entity_id
    entity.name = name
    entity.x = x
    entity.y = y
    entity.player_db_id = db_id
    entity.stats = {
        "hp": 100, "max_hp": 100, "xp": 0, "level": 1,
        "strength": 1, "dexterity": 1, "constitution": 1,
        "intelligence": 1, "wisdom": 1, "charisma": 1,
    }
    entity.in_combat = False
    return entity


def _mock_transaction():
    """Create a mock async context manager for game.transaction."""
    mock_session = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_factory = MagicMock(return_value=mock_ctx)
    return mock_factory, mock_session


def _make_game(entity, room_key="town_square"):
    game = MagicMock()
    factory, _ = _mock_transaction()
    game.transaction = factory
    player_info = PlayerSession(
        entity=entity,
        room_key=room_key,
        db_id=entity.player_db_id,
        inventory=MagicMock(),
        visited_rooms=set(),
    )
    game.player_manager = PlayerManager()
    game.player_manager.set_session(entity.id, player_info)
    game.connection_manager.get_entity_id.return_value = entity.id

    room = MagicMock()
    room.width = 5
    room.height = 5
    game.room_manager.get_room.return_value = room
    return game, room


class TestInteractionXP:
    """Tests for interaction XP on first object interaction."""

    async def test_first_chest_interact_grants_xp(self):
        """First chest interaction grants interaction XP."""
        entity = _make_entity(x=2, y=2)
        game, room = _make_game(entity)

        chest = ChestObject(
            id="chest_1", type="chest", x=3, y=2, category="interactive",
            state_scope="player", config={"loot_table": "common_chest"}, room_key="town_square",
        )
        chest.interact = AsyncMock(return_value={"status": "looted", "items": []})
        room.get_object.return_value = chest

        ws = AsyncMock()

        with patch("server.net.handlers.interact.get_player_object_state", new_callable=AsyncMock, return_value={}), \
             patch("server.net.handlers.interact.grant_xp", new_callable=AsyncMock) as mock_grant_xp:

            await handle_interact(ws, {"target_id": "chest_1"}, game=game)

            mock_grant_xp.assert_called_once()
            call_args = mock_grant_xp.call_args
            assert call_args[0][2] == 25  # XP_INTERACTION_REWARD default
            assert call_args[0][3] == "interaction"

    async def test_repeat_chest_interact_no_xp(self):
        """Already-looted chest grants no interaction XP."""
        entity = _make_entity(x=2, y=2)
        game, room = _make_game(entity)

        chest = ChestObject(
            id="chest_1", type="chest", x=3, y=2, category="interactive",
            state_scope="player", config={"loot_table": "common_chest"}, room_key="town_square",
        )
        chest.interact = AsyncMock(return_value={"status": "already_looted", "message": "Already looted"})
        room.get_object.return_value = chest

        ws = AsyncMock()

        with patch("server.net.handlers.interact.get_player_object_state", new_callable=AsyncMock, return_value={"opened": True}), \
             patch("server.net.handlers.interact.grant_xp", new_callable=AsyncMock) as mock_grant_xp:

            await handle_interact(ws, {"target_id": "chest_1"}, game=game)

            mock_grant_xp.assert_not_called()

    async def test_first_lever_interact_grants_xp(self):
        """First lever toggle grants interaction XP."""
        entity = _make_entity(x=2, y=2)
        game, room = _make_game(entity)

        lever = LeverObject(
            id="lever_1", type="lever", x=3, y=2, category="interactive",
            state_scope="room", config={"target_x": 4, "target_y": 4}, room_key="town_square",
        )
        lever.interact = AsyncMock(return_value={"status": "toggled", "active": True, "target_x": 4, "target_y": 4})
        room.get_object.return_value = lever

        ws = AsyncMock()

        with patch("server.net.handlers.interact.get_player_object_state", new_callable=AsyncMock, return_value={}), \
             patch("server.net.handlers.interact.set_player_object_state", new_callable=AsyncMock) as mock_set_state, \
             patch("server.net.handlers.interact.grant_xp", new_callable=AsyncMock) as mock_grant_xp:

            await handle_interact(ws, {"target_id": "lever_1"}, game=game)

            mock_grant_xp.assert_called_once()
            # Lever should also set player_object_state for tracking
            mock_set_state.assert_called_once()

    async def test_repeat_lever_interact_no_xp(self):
        """Second lever toggle grants no interaction XP."""
        entity = _make_entity(x=2, y=2)
        game, room = _make_game(entity)

        lever = LeverObject(
            id="lever_1", type="lever", x=3, y=2, category="interactive",
            state_scope="room", config={"target_x": 4, "target_y": 4}, room_key="town_square",
        )
        lever.interact = AsyncMock(return_value={"status": "toggled", "active": False, "target_x": 4, "target_y": 4})
        room.get_object.return_value = lever

        ws = AsyncMock()

        with patch("server.net.handlers.interact.get_player_object_state", new_callable=AsyncMock, return_value={"interacted": True}), \
             patch("server.net.handlers.interact.grant_xp", new_callable=AsyncMock) as mock_grant_xp:

            await handle_interact(ws, {"target_id": "lever_1"}, game=game)

            mock_grant_xp.assert_not_called()
