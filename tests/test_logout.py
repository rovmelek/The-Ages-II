"""Tests for player logout (Story 10.1)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from server.combat.cards.card_def import CardDef
from server.combat.instance import CombatInstance
from server.player.entity import PlayerEntity
from server.room.room import RoomInstance


def _mock_transaction():
    """Create a mock async context manager for game.transaction."""
    from unittest.mock import MagicMock
    mock_session = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_factory = MagicMock(return_value=mock_ctx)
    return mock_factory, mock_session


def _make_game():
    """Create a Game instance with a test room."""
    from server.app import Game

    game = Game()
    factory, _ = _mock_transaction()
    game.transaction = factory
    room = RoomInstance("test_room", "Test", 5, 5, [[0] * 5 for _ in range(5)])
    game.room_manager._rooms["test_room"] = room
    return game, room


def _add_player(game, room, entity_id="player_1", name="hero", x=2, y=2, db_id=1):
    """Add a player entity to the game."""
    entity = PlayerEntity(
        id=entity_id, name=name, x=x, y=y, player_db_id=db_id,
        stats={"hp": 100, "max_hp": 100, "attack": 10, "xp": 0},
    )
    room.add_entity(entity)
    ws = AsyncMock()
    game.connection_manager.connect(entity_id, ws, "test_room")
    game.player_entities[entity_id] = {
        "entity": entity,
        "room_key": "test_room",
        "db_id": db_id,
    }
    return entity, ws


# ---------------------------------------------------------------------------
# AC #1: Basic logout
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_logout_saves_state_and_removes_player():
    """Logout saves state, removes entity from room, cleans up tracking."""
    from server.net.handlers.auth import handle_logout

    game, room = _make_game()
    entity, ws = _add_player(game, room)

    with patch("server.net.handlers.auth.player_repo", new_callable=AsyncMock) as mock_repo:
        await handle_logout(ws, {}, game=game)

        # State saved
        mock_repo.update_position.assert_called_once()
        mock_repo.update_stats.assert_called_once()

    # Entity removed from room
    assert len(room._entities) == 0

    # Player removed from tracking
    assert "player_1" not in game.player_entities
    assert game.connection_manager.get_entity_id(ws) is None

    # Received logged_out message
    ws.send_json.assert_called_with({"type": "logged_out"})


# ---------------------------------------------------------------------------
# AC #2: Logout while in combat
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_logout_in_combat_removes_from_combat_and_syncs_stats():
    """Logout while in combat syncs stats, clears in_combat, removes from instance."""
    from server.net.handlers.auth import handle_logout

    game, room = _make_game()
    entity, ws = _add_player(game, room)

    # Set up combat
    instance = CombatInstance(mob_name="Slime", mob_stats={"hp": 50, "max_hp": 50, "attack": 5})
    card = CardDef(card_key="strike", name="Strike", cost=1, effects=[{"type": "damage", "value": 10}])
    instance.add_participant("player_1", entity.stats, [card])
    # Simulate combat damage — HP reduced in participant_stats
    instance.participant_stats["player_1"]["hp"] = 60
    game.combat_manager._instances[instance.instance_id] = instance
    game.combat_manager._player_to_instance["player_1"] = instance.instance_id
    entity.in_combat = True

    with patch("server.net.handlers.auth.player_repo", new_callable=AsyncMock):
        await handle_logout(ws, {}, game=game)

    # Combat stats synced to entity before save
    assert entity.stats["hp"] == 60
    # in_combat cleared
    assert entity.in_combat is False
    # Removed from combat
    assert game.combat_manager.get_player_instance("player_1") is None


# ---------------------------------------------------------------------------
# AC #3: Logout while dead in combat
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_logout_dead_in_combat_restores_hp():
    """Logout while dead (HP=0) restores HP to max_hp before save."""
    from server.net.handlers.auth import handle_logout

    game, room = _make_game()
    entity, ws = _add_player(game, room)
    entity.stats = {"hp": 100, "max_hp": 100, "attack": 10}

    # Set up combat with player dead
    instance = CombatInstance(mob_name="Slime", mob_stats={"hp": 50, "max_hp": 50, "attack": 5})
    card = CardDef(card_key="strike", name="Strike", cost=1, effects=[{"type": "damage", "value": 10}])
    instance.add_participant("player_1", entity.stats, [card])
    instance.participant_stats["player_1"]["hp"] = 0  # Dead
    game.combat_manager._instances[instance.instance_id] = instance
    game.combat_manager._player_to_instance["player_1"] = instance.instance_id
    entity.in_combat = True

    with patch("server.net.handlers.auth.player_repo", new_callable=AsyncMock) as mock_repo:
        await handle_logout(ws, {}, game=game)

        # HP restored to max_hp (not saved as 0)
        assert entity.stats["hp"] == 100
        # Stats saved with restored HP
        mock_repo.update_stats.assert_called_once()
        saved_stats = mock_repo.update_stats.call_args[0][2]
        assert saved_stats["hp"] == 100


# ---------------------------------------------------------------------------
# AC #2: Last player logout releases NPC
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_logout_last_player_releases_npc():
    """When the last player logs out of combat, NPC in_combat is cleared."""
    from server.net.handlers.auth import handle_logout
    from server.room.objects.npc import NpcEntity

    game, room = _make_game()
    entity, ws = _add_player(game, room)

    # Add NPC to room
    npc = NpcEntity(id="npc_1", npc_key="slime", name="Slime", x=3, y=3, behavior_type="hostile", stats={"hp": 50, "max_hp": 50, "attack": 5})
    npc.in_combat = True
    room.add_npc(npc)

    # Set up combat
    instance = CombatInstance(
        mob_name="Slime",
        mob_stats={"hp": 50, "max_hp": 50, "attack": 5},
        npc_id="npc_1",
        room_key="test_room",
    )
    card = CardDef(card_key="strike", name="Strike", cost=1, effects=[{"type": "damage", "value": 10}])
    instance.add_participant("player_1", entity.stats, [card])
    game.combat_manager._instances[instance.instance_id] = instance
    game.combat_manager._player_to_instance["player_1"] = instance.instance_id
    entity.in_combat = True

    with patch("server.net.handlers.auth.player_repo", new_callable=AsyncMock):
        await handle_logout(ws, {}, game=game)

    # NPC released from combat
    assert npc.in_combat is False
    # NPC is_alive NOT reset (match flee behavior)
    assert npc.is_alive is True
    # Combat instance removed
    assert instance.instance_id not in game.combat_manager._instances


# ---------------------------------------------------------------------------
# AC #2: Remaining participants continue combat
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_logout_remaining_participants_receive_combat_update():
    """When one player logs out of multi-player combat, others receive combat_update."""
    from server.net.handlers.auth import handle_logout

    game, room = _make_game()
    entity1, ws1 = _add_player(game, room, "player_1", "alice", 1, 1, 1)
    entity2, ws2 = _add_player(game, room, "player_2", "bob", 2, 2, 2)

    # Set up combat with both players
    instance = CombatInstance(mob_name="Slime", mob_stats={"hp": 50, "max_hp": 50, "attack": 5})
    card = CardDef(card_key="strike", name="Strike", cost=1, effects=[{"type": "damage", "value": 10}])
    instance.add_participant("player_1", entity1.stats, [card])
    instance.add_participant("player_2", entity2.stats, [card])
    game.combat_manager._instances[instance.instance_id] = instance
    game.combat_manager._player_to_instance["player_1"] = instance.instance_id
    game.combat_manager._player_to_instance["player_2"] = instance.instance_id
    entity1.in_combat = True
    entity2.in_combat = True

    with patch("server.net.handlers.auth.player_repo", new_callable=AsyncMock):
        await handle_logout(ws1, {}, game=game)

    # Player 2 received combat_update
    combat_update_calls = [
        call for call in ws2.send_json.call_args_list
        if call[0][0].get("type") == "combat_update"
    ]
    assert len(combat_update_calls) == 1
    # Combat continues — player 2 still in instance
    assert "player_2" in instance.participants


# ---------------------------------------------------------------------------
# AC #4: Not logged in
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_logout_not_logged_in_returns_error():
    """Logout when not logged in returns error."""
    from server.net.handlers.auth import handle_logout

    game, _ = _make_game()
    ws = AsyncMock()

    await handle_logout(ws, {}, game=game)

    ws.send_json.assert_called_with(
        {"type": "error", "detail": "Not logged in"}
    )


# ---------------------------------------------------------------------------
# Double logout
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_double_logout_returns_error():
    """Second logout returns 'Not logged in' after first succeeds."""
    from server.net.handlers.auth import handle_logout

    game, room = _make_game()
    _, ws = _add_player(game, room)

    with patch("server.net.handlers.auth.player_repo", new_callable=AsyncMock):
        await handle_logout(ws, {}, game=game)
        # Reset mock to check second call
        ws.send_json.reset_mock()
        await handle_logout(ws, {}, game=game)

    ws.send_json.assert_called_with(
        {"type": "error", "detail": "Not logged in"}
    )


# ---------------------------------------------------------------------------
# AC #5: Re-login on same WebSocket after logout
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_relogin_same_socket_after_logout():
    """After logout, player can login again on the same WebSocket."""
    from server.net.handlers.auth import handle_login, handle_logout

    game, room = _make_game()
    entity, ws = _add_player(game, room)

    with patch("server.net.handlers.auth.player_repo", new_callable=AsyncMock) as mock_repo:
        # Logout first
        await handle_logout(ws, {}, game=game)

        assert "player_1" not in game.player_entities
        assert game.connection_manager.get_entity_id(ws) is None

        # Set up mock for login
        mock_player = AsyncMock()
        mock_player.id = 1
        mock_player.username = "hero"
        mock_player.password_hash = "hashed"
        mock_player.stats = {"hp": 100, "max_hp": 100, "attack": 10}
        mock_player.current_room_id = "test_room"
        mock_player.position_x = 2
        mock_player.position_y = 2
        mock_player.inventory = {}
        mock_player.visited_rooms = []
        mock_repo.get_by_username.return_value = mock_player

        with patch("server.net.handlers.auth.verify_password", return_value=True), \
             patch("server.net.handlers.auth.room_repo"):
            await handle_login(ws, {"username": "hero", "password": "secret123"}, game=game)

    # Player is logged in again
    assert "player_1" in game.player_entities
    assert game.connection_manager.get_entity_id(ws) == "player_1"
    # Received login_success
    login_calls = [
        call for call in ws.send_json.call_args_list
        if isinstance(call[0][0], dict) and call[0][0].get("type") == "login_success"
    ]
    assert len(login_calls) >= 1


# ---------------------------------------------------------------------------
# AC #5: Re-login on same WebSocket WITHOUT logout first
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_relogin_same_socket_without_logout():
    """Re-login on same WebSocket without logout performs inline cleanup."""
    from server.net.handlers.auth import handle_login

    game, room = _make_game()
    entity, ws = _add_player(game, room)

    with patch("server.net.handlers.auth.player_repo", new_callable=AsyncMock) as mock_repo:
        mock_player = AsyncMock()
        mock_player.id = 1
        mock_player.username = "hero"
        mock_player.password_hash = "hashed"
        mock_player.stats = {"hp": 100, "max_hp": 100, "attack": 10}
        mock_player.current_room_id = "test_room"
        mock_player.position_x = 2
        mock_player.position_y = 2
        mock_player.inventory = {}
        mock_player.visited_rooms = []
        mock_repo.get_by_username.return_value = mock_player

        with patch("server.net.handlers.auth.verify_password", return_value=True), \
             patch("server.net.handlers.auth.room_repo"):
            await handle_login(ws, {"username": "hero", "password": "secret123"}, game=game)

    # Player is re-logged in (not disconnected)
    assert "player_1" in game.player_entities
    assert game.connection_manager.get_entity_id(ws) == "player_1"
    # WebSocket was NOT closed
    ws.close.assert_not_called()


# ---------------------------------------------------------------------------
# entity_left broadcast
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_logout_broadcasts_entity_left_to_others():
    """Logout broadcasts entity_left to other players in the room."""
    from server.net.handlers.auth import handle_logout

    game, room = _make_game()
    _, ws1 = _add_player(game, room, "player_1", "alice", 1, 1, 1)
    _, ws2 = _add_player(game, room, "player_2", "bob", 2, 2, 2)

    with patch("server.net.handlers.auth.player_repo", new_callable=AsyncMock):
        await handle_logout(ws1, {}, game=game)

    # Player 2 should receive entity_left for player_1
    entity_left_calls = [
        call for call in ws2.send_json.call_args_list
        if call[0][0].get("type") == "entity_left"
    ]
    assert len(entity_left_calls) == 1
    assert entity_left_calls[0][0][0]["entity_id"] == "player_1"


# ---------------------------------------------------------------------------
# Inventory save
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_logout_saves_inventory():
    """Logout saves inventory to DB when inventory exists."""
    from server.items.inventory import Inventory
    from server.net.handlers.auth import handle_logout

    game, room = _make_game()
    entity, ws = _add_player(game, room)

    # Add inventory to player_entities
    inventory = Inventory()
    game.player_entities["player_1"]["inventory"] = inventory

    with patch("server.net.handlers.auth.player_repo", new_callable=AsyncMock) as mock_repo:
        await handle_logout(ws, {}, game=game)

        mock_repo.update_inventory.assert_called_once()
