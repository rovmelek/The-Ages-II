"""Tests for exploration XP — first-visit room discovery rewards."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.net.handlers.movement import _handle_exit_transition
from server.player.manager import PlayerManager
from server.player.session import PlayerSession


def _make_entity(entity_id="player_1", name="TestPlayer", x=0, y=0, db_id=1):
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


def _make_room(room_key="test_room", name="Test Room", width=5, height=5):
    room = MagicMock()
    room.name = name
    room.width = width
    room.height = height
    room.is_walkable.return_value = True
    room.get_player_spawn.return_value = (2, 2)
    room.find_first_walkable.return_value = (0, 0)
    room.get_state.return_value = {"room_key": room_key, "tiles": [], "entities": [], "objects": []}
    return room


def _mock_transaction():
    """Create a mock async context manager for game.transaction."""
    mock_session = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_factory = MagicMock(return_value=mock_ctx)
    return mock_factory, mock_session


def _make_game(entity, room_key="town_square", target_room=None, visited_rooms=None):
    game = MagicMock()
    factory, _ = _mock_transaction()
    game.transaction = factory
    player_info = PlayerSession(
        entity=entity,
        room_key=room_key,
        db_id=entity.player_db_id,
        inventory=MagicMock(),
        visited_rooms=set(visited_rooms) if visited_rooms is not None else set(),
    )
    game.player_manager = PlayerManager()
    game.player_manager.set_session(entity.id, player_info)
    game.connection_manager.broadcast_to_room = AsyncMock()
    game.connection_manager.send_to_player = AsyncMock()
    game.room_manager.get_room.return_value = target_room
    game.trade_manager.cancel_trades_for.return_value = None
    return game, player_info


class TestExplorationXP:
    """Tests for exploration XP on room transitions."""

    async def test_first_visit_grants_xp(self):
        """First visit to a room grants exploration XP."""
        entity = _make_entity()
        target_room = _make_room(room_key="dark_cave", name="Dark Cave")
        old_room = _make_room(room_key="town_square", name="Town Square")
        game, player_info = _make_game(entity, room_key="town_square", target_room=target_room)

        ws = AsyncMock()
        exit_info = {"target_room": "dark_cave", "entry_x": 2, "entry_y": 2}

        with patch("server.net.handlers.movement.player_repo") as mock_repo, \
             patch("server.net.handlers.movement.grant_xp", new_callable=AsyncMock) as mock_grant_xp:
            mock_repo.update_position = AsyncMock()
            mock_repo.update_visited_rooms = AsyncMock()

            await _handle_exit_transition(
                ws, game, entity.id, entity, player_info,
                old_room, "town_square", exit_info, 0, 0,
            )

            mock_grant_xp.assert_called_once()
            call_args = mock_grant_xp.call_args
            assert call_args[0][2] == 50  # XP_EXPLORATION_REWARD default
            assert call_args[0][3] == "exploration"
            assert "Dark Cave" in call_args[0][4]

            # visited_rooms updated
            assert "dark_cave" in player_info.visited_rooms
            mock_repo.update_visited_rooms.assert_called_once()

    async def test_repeat_visit_no_xp(self):
        """Revisiting an already-visited room grants no XP."""
        entity = _make_entity()
        target_room = _make_room(room_key="dark_cave", name="Dark Cave")
        old_room = _make_room(room_key="town_square", name="Town Square")
        game, player_info = _make_game(
            entity, room_key="town_square", target_room=target_room,
            visited_rooms=["dark_cave"],  # already visited
        )

        ws = AsyncMock()
        exit_info = {"target_room": "dark_cave", "entry_x": 2, "entry_y": 2}

        with patch("server.net.handlers.movement.player_repo") as mock_repo, \
             patch("server.net.handlers.movement.grant_xp", new_callable=AsyncMock) as mock_grant_xp:
            mock_repo.update_position = AsyncMock()

            await _handle_exit_transition(
                ws, game, entity.id, entity, player_info,
                old_room, "town_square", exit_info, 0, 0,
            )

            mock_grant_xp.assert_not_called()

    async def test_visited_rooms_persisted_on_cleanup(self):
        """visited_rooms saved to DB during player cleanup."""
        from server.net.handlers.auth import _cleanup_player

        entity = _make_entity()
        game = MagicMock()
        factory, mock_session = _mock_transaction()
        game.transaction = factory
        game.player_manager = PlayerManager()
        game.player_manager.set_session(entity.id, PlayerSession(
            entity=entity,
            room_key="town_square",
            db_id=entity.player_db_id,
            inventory=MagicMock(),
            visited_rooms={"town_square", "dark_cave"},
        ))
        game.combat_manager.get_player_instance.return_value = None
        game.trade_manager.cancel_trades_for.return_value = None
        game.party_manager.handle_disconnect.return_value = (None, None)
        game.room_manager.get_room.return_value = MagicMock()
        game.connection_manager.broadcast_to_room = AsyncMock()
        game.connection_manager.disconnect = MagicMock()

        with patch("server.net.handlers.auth.player_repo") as mock_repo:
            mock_repo.update_position = AsyncMock()
            mock_repo.update_stats = AsyncMock()
            mock_repo.update_inventory = AsyncMock()
            mock_repo.update_visited_rooms = AsyncMock()

            await _cleanup_player(entity.id, game)

            mock_repo.update_visited_rooms.assert_called_once()
            call_args = mock_repo.update_visited_rooms.call_args[0]
            assert call_args[0] is mock_session
            assert call_args[1] == entity.player_db_id
            assert set(call_args[2]) == {"town_square", "dark_cave"}

    async def test_visited_rooms_restored_on_login(self):
        """visited_rooms loaded from DB on login and stored in player_info."""
        from server.net.handlers.auth import handle_login

        ws = AsyncMock()
        game = MagicMock()
        factory, _ = _mock_transaction()
        game.transaction = factory
        game.connection_manager.get_entity_id.return_value = None
        game.connection_manager.get_websocket.return_value = None
        game.player_manager = PlayerManager()

        player_db = MagicMock()
        player_db.id = 1
        player_db.username = "testuser"
        player_db.password_hash = "hashed"
        player_db.stats = {"hp": 100, "max_hp": 100, "xp": 0, "level": 1,
                           "strength": 1, "dexterity": 1, "constitution": 1,
                           "intelligence": 1, "wisdom": 1, "charisma": 1}
        player_db.inventory = {}
        player_db.current_room_id = "town_square"
        player_db.position_x = 2
        player_db.position_y = 2
        player_db.visited_rooms = ["town_square", "dark_cave"]

        room = _make_room(room_key="town_square", name="Town Square")

        with patch("server.net.handlers.auth.player_repo") as mock_repo, \
             patch("server.net.handlers.auth.verify_password", return_value=True), \
             patch("server.net.handlers.auth.room_repo") as mock_room_repo:
            mock_repo.get_by_username = AsyncMock(return_value=player_db)
            mock_repo.update_stats = AsyncMock()
            mock_repo.update_position = AsyncMock()
            game.room_manager.get_room.return_value = room
            game.connection_manager.broadcast_to_room = AsyncMock()

            await handle_login(ws, {"username": "testuser", "password": "123456"}, game=game)

            # Check visited_rooms in player_info
            assert game.player_manager.has_session("player_1")
            assert game.player_manager.get_session("player_1").visited_rooms == {"town_square", "dark_cave"}
