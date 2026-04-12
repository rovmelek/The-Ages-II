"""Tests for Story 12.5: Party Chat."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from server.net.handlers.party import handle_party, handle_party_chat


def _make_game():
    """Create a minimal mock Game with party, connection, and combat managers."""
    game = MagicMock()
    game.party_manager = MagicMock()
    game.connection_manager = MagicMock()
    game.connection_manager.send_to_player = AsyncMock()
    game.combat_manager = MagicMock()
    game.player_entities = {}
    return game


def _make_ws(entity_id: str | None = "player_1"):
    """Create a mock WebSocket that returns entity_id."""
    ws = AsyncMock()
    ws._entity_id = entity_id
    return ws


def _register_player(game, entity_id: str, name: str, room_key: str = "town_square"):
    """Register a player in game state."""
    entity = MagicMock()
    entity.name = name
    entity.id = entity_id
    game.player_entities[entity_id] = {
        "entity": entity,
        "room_key": room_key,
    }
    game.connection_manager.get_entity_id.return_value = entity_id
    return entity


def _make_party(members: list[str], leader: str | None = None):
    """Create a mock Party object."""
    party = MagicMock()
    party.members = list(members)
    party.leader = leader or members[0]
    party.party_id = "test-party-id"
    return party


# =========================================================================
# handle_party_chat — direct action tests
# =========================================================================


@pytest.mark.asyncio
async def test_party_chat_delivers_to_all_members():
    """Party chat sends message to all party members."""
    game = _make_game()
    ws = _make_ws("player_1")
    _register_player(game, "player_1", "Alice", "town_square")
    _register_player(game, "player_2", "Bob", "dark_cave")
    _register_player(game, "player_3", "Carol", "other_room")

    party = _make_party(["player_1", "player_2", "player_3"])
    game.party_manager.get_party.return_value = party

    game.connection_manager.get_entity_id.return_value = "player_1"

    await handle_party_chat(ws, {"message": "Hello team!"}, game=game)

    expected_msg = {"type": "party_chat", "from": "Alice", "message": "Hello team!"}
    assert game.connection_manager.send_to_player.call_count == 3
    for call in game.connection_manager.send_to_player.call_args_list:
        assert call[0][1] == expected_msg


@pytest.mark.asyncio
async def test_party_chat_sender_receives_own_message():
    """Sender is included in the delivery list."""
    game = _make_game()
    ws = _make_ws("player_1")
    _register_player(game, "player_1", "Alice")

    party = _make_party(["player_1", "player_2"])
    game.party_manager.get_party.return_value = party
    game.connection_manager.get_entity_id.return_value = "player_1"

    await handle_party_chat(ws, {"message": "test"}, game=game)

    sent_to = [c[0][0] for c in game.connection_manager.send_to_player.call_args_list]
    assert "player_1" in sent_to


@pytest.mark.asyncio
async def test_party_chat_not_in_party_error():
    """Players not in a party get an error."""
    game = _make_game()
    ws = _make_ws("player_1")
    _register_player(game, "player_1", "Alice")

    game.party_manager.get_party.return_value = None
    game.connection_manager.get_entity_id.return_value = "player_1"

    await handle_party_chat(ws, {"message": "hello"}, game=game)

    ws.send_json.assert_called_once()
    msg = ws.send_json.call_args[0][0]
    assert msg["type"] == "error"
    assert "not in a party" in msg["detail"]


@pytest.mark.asyncio
async def test_party_chat_empty_message_ignored():
    """Empty messages are silently ignored."""
    game = _make_game()
    ws = _make_ws("player_1")
    _register_player(game, "player_1", "Alice")
    game.connection_manager.get_entity_id.return_value = "player_1"

    await handle_party_chat(ws, {"message": ""}, game=game)

    ws.send_json.assert_not_called()
    game.connection_manager.send_to_player.assert_not_called()


@pytest.mark.asyncio
async def test_party_chat_whitespace_only_ignored():
    """Whitespace-only messages are silently ignored."""
    game = _make_game()
    ws = _make_ws("player_1")
    _register_player(game, "player_1", "Alice")
    game.connection_manager.get_entity_id.return_value = "player_1"

    await handle_party_chat(ws, {"message": "   "}, game=game)

    ws.send_json.assert_not_called()
    game.connection_manager.send_to_player.assert_not_called()


@pytest.mark.asyncio
async def test_party_chat_message_too_long():
    """Messages exceeding MAX_CHAT_MESSAGE_LENGTH are rejected."""
    game = _make_game()
    ws = _make_ws("player_1")
    _register_player(game, "player_1", "Alice")
    game.connection_manager.get_entity_id.return_value = "player_1"

    long_msg = "x" * 501

    await handle_party_chat(ws, {"message": long_msg}, game=game)

    ws.send_json.assert_called_once()
    msg = ws.send_json.call_args[0][0]
    assert msg["type"] == "error"
    assert "too long" in msg["detail"]
    assert "500" in msg["detail"]


@pytest.mark.asyncio
async def test_party_chat_exact_max_length_accepted():
    """Messages at exactly MAX_CHAT_MESSAGE_LENGTH are accepted."""
    game = _make_game()
    ws = _make_ws("player_1")
    _register_player(game, "player_1", "Alice")

    party = _make_party(["player_1"])
    game.party_manager.get_party.return_value = party
    game.connection_manager.get_entity_id.return_value = "player_1"

    exact_msg = "x" * 500

    await handle_party_chat(ws, {"message": exact_msg}, game=game)

    # Should have sent to party member, not an error
    game.connection_manager.send_to_player.assert_called_once()
    ws.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_party_chat_sender_name_from_entity():
    """Sender name comes from server-side entity, not client data."""
    game = _make_game()
    ws = _make_ws("player_1")
    _register_player(game, "player_1", "ServerName")
    game.connection_manager.get_entity_id.return_value = "player_1"

    party = _make_party(["player_1"])
    game.party_manager.get_party.return_value = party

    await handle_party_chat(ws, {"message": "hi", "from": "Impersonator"}, game=game)

    sent_msg = game.connection_manager.send_to_player.call_args[0][1]
    assert sent_msg["from"] == "ServerName"


@pytest.mark.asyncio
async def test_party_chat_graceful_disconnect():
    """Disconnected member doesn't block delivery to others."""
    game = _make_game()
    ws = _make_ws("player_1")
    _register_player(game, "player_1", "Alice")
    _register_player(game, "player_2", "Bob")
    _register_player(game, "player_3", "Carol")

    party = _make_party(["player_1", "player_2", "player_3"])
    game.party_manager.get_party.return_value = party
    game.connection_manager.get_entity_id.return_value = "player_1"

    # Second member's send raises an exception
    call_count = 0

    async def side_effect(entity_id, msg):
        nonlocal call_count
        call_count += 1
        if entity_id == "player_2":
            raise ConnectionError("WebSocket disconnected")

    game.connection_manager.send_to_player.side_effect = side_effect

    # Should not raise
    await handle_party_chat(ws, {"message": "test"}, game=game)

    # All three sends were attempted
    assert call_count == 3


@pytest.mark.asyncio
async def test_party_chat_not_logged_in():
    """Not-logged-in players get an error."""
    game = _make_game()
    ws = _make_ws(None)
    game.connection_manager.get_entity_id.return_value = None

    await handle_party_chat(ws, {"message": "hello"}, game=game)

    ws.send_json.assert_called_once()
    msg = ws.send_json.call_args[0][0]
    assert msg["type"] == "error"
    assert "Not logged in" in msg["detail"]


@pytest.mark.asyncio
async def test_party_chat_no_player_entities():
    """Players with no player_entities entry get a not-logged-in error."""
    game = _make_game()
    ws = _make_ws("player_1")
    game.connection_manager.get_entity_id.return_value = "player_1"
    # player_entities is empty — player_1 not registered

    await handle_party_chat(ws, {"message": "hello"}, game=game)

    ws.send_json.assert_called_once()
    msg = ws.send_json.call_args[0][0]
    assert msg["type"] == "error"
    assert "Not logged in" in msg["detail"]


# =========================================================================
# handle_party fallback routing tests
# =========================================================================


@pytest.mark.asyncio
async def test_party_fallback_routes_to_chat_when_in_party():
    """Unknown subcommand routes to party chat for party members."""
    game = _make_game()
    ws = _make_ws("player_1")
    _register_player(game, "player_1", "Alice")

    party = _make_party(["player_1", "player_2"])
    game.party_manager.get_party.return_value = party
    game.party_manager.is_in_party.return_value = True
    game.connection_manager.get_entity_id.return_value = "player_1"

    await handle_party(ws, {"args": "hello everyone"}, game=game)

    # Should have sent party_chat to members
    assert game.connection_manager.send_to_player.call_count >= 1
    sent_msg = game.connection_manager.send_to_player.call_args[0][1]
    assert sent_msg["type"] == "party_chat"
    assert sent_msg["message"] == "hello everyone"
    assert sent_msg["from"] == "Alice"


@pytest.mark.asyncio
async def test_party_fallback_error_when_not_in_party():
    """Unknown subcommand returns 'not in a party' for non-party players."""
    game = _make_game()
    ws = _make_ws("player_1")
    _register_player(game, "player_1", "Alice")

    game.party_manager.get_party.return_value = None
    game.party_manager.is_in_party.return_value = False
    game.connection_manager.get_entity_id.return_value = "player_1"

    await handle_party(ws, {"args": "hello everyone"}, game=game)

    ws.send_json.assert_called()
    last_msg = ws.send_json.call_args[0][0]
    assert last_msg["type"] == "error"
    assert "not in a party" in last_msg["detail"]


@pytest.mark.asyncio
async def test_party_known_subcommands_not_routed_to_chat():
    """Known subcommands are NOT routed to party chat."""
    game = _make_game()
    ws = _make_ws("player_1")
    _register_player(game, "player_1", "Alice")
    game.connection_manager.get_entity_id.return_value = "player_1"

    # 'leave' is a known subcommand — should NOT be treated as chat
    game.party_manager.is_in_party.return_value = False

    await handle_party(ws, {"args": "leave"}, game=game)

    # Should get a "not in party" error from leave handler, not a party_chat message
    ws.send_json.assert_called()
    msg = ws.send_json.call_args[0][0]
    assert msg["type"] == "error"
    # Should not be a party_chat message
    game.connection_manager.send_to_player.assert_not_called()


@pytest.mark.asyncio
async def test_party_chat_across_multiple_rooms():
    """Party chat delivers to members in different rooms."""
    game = _make_game()
    ws = _make_ws("player_1")
    _register_player(game, "player_1", "Alice", "town_square")
    _register_player(game, "player_2", "Bob", "dark_cave")
    _register_player(game, "player_3", "Carol", "test_room")
    _register_player(game, "player_4", "Dave", "other_room")

    party = _make_party(["player_1", "player_2", "player_3", "player_4"])
    game.party_manager.get_party.return_value = party
    game.connection_manager.get_entity_id.return_value = "player_1"

    await handle_party_chat(ws, {"message": "Meet at dark_cave"}, game=game)

    # All 4 members should receive the message
    assert game.connection_manager.send_to_player.call_count == 4
    sent_to = {c[0][0] for c in game.connection_manager.send_to_player.call_args_list}
    assert sent_to == {"player_1", "player_2", "player_3", "player_4"}


@pytest.mark.asyncio
async def test_party_chat_dedicated_action():
    """party_chat is a dedicated action, not overloading chat."""
    game = _make_game()
    ws = _make_ws("player_1")
    _register_player(game, "player_1", "Alice")

    party = _make_party(["player_1"])
    game.party_manager.get_party.return_value = party
    game.connection_manager.get_entity_id.return_value = "player_1"

    await handle_party_chat(ws, {"message": "test"}, game=game)

    sent_msg = game.connection_manager.send_to_player.call_args[0][1]
    assert sent_msg["type"] == "party_chat"
    # Should NOT be "chat" type
    assert sent_msg["type"] != "chat"


@pytest.mark.asyncio
async def test_party_chat_missing_message_key():
    """No 'message' key in data is treated as empty."""
    game = _make_game()
    ws = _make_ws("player_1")
    _register_player(game, "player_1", "Alice")
    game.connection_manager.get_entity_id.return_value = "player_1"

    await handle_party_chat(ws, {}, game=game)

    ws.send_json.assert_not_called()
    game.connection_manager.send_to_player.assert_not_called()
