"""Tests for room chat and whispers (Story 2.4)."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from server.net.handlers.chat import handle_chat
from server.player.entity import PlayerEntity
from server.room.room import RoomInstance


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

def _make_game():
    from server.app import Game
    return Game()


def _setup_two_players(game):
    """Set up two players in the same room."""
    room = RoomInstance("test", "Test Room", 5, 5, [[0] * 5 for _ in range(5)])
    game.room_manager._rooms["test"] = room

    e1 = PlayerEntity(id="player_1", name="alice", x=0, y=0, player_db_id=1)
    e2 = PlayerEntity(id="player_2", name="bob", x=1, y=1, player_db_id=2)
    room.add_entity(e1)
    room.add_entity(e2)

    ws1 = AsyncMock()
    ws2 = AsyncMock()
    game.connection_manager.connect("player_1", ws1, "test")
    game.connection_manager.connect("player_2", ws2, "test")
    game.player_manager.set_session("player_1", _ps({"entity": e1, "room_key": "test", "db_id": 1}))
    game.player_manager.set_session("player_2", _ps({"entity": e2, "room_key": "test", "db_id": 2}))

    return ws1, ws2


# ---------------------------------------------------------------------------
# Room chat
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_broadcasts_to_room():
    game = _make_game()
    ws1, ws2 = _setup_two_players(game)

    await handle_chat(ws1, {"action": "chat", "message": "Hello!"}, game=game)

    expected = {"type": "chat", "sender": "alice", "message": "Hello!", "whisper": False}
    ws1.send_json.assert_called_with(expected)
    ws2.send_json.assert_called_with(expected)


@pytest.mark.asyncio
async def test_chat_message_format():
    game = _make_game()
    ws1, ws2 = _setup_two_players(game)

    await handle_chat(ws1, {"action": "chat", "message": "Test msg"}, game=game)

    msg = ws1.send_json.call_args.args[0]
    assert msg["type"] == "chat"
    assert msg["sender"] == "alice"
    assert msg["message"] == "Test msg"
    assert msg["whisper"] is False


# ---------------------------------------------------------------------------
# Whisper
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_whisper_to_specific_player():
    game = _make_game()
    ws1, ws2 = _setup_two_players(game)

    await handle_chat(
        ws1,
        {"action": "chat", "message": "Secret", "whisper_to": "player_2"},
        game=game,
    )

    expected = {"type": "chat", "sender": "alice", "message": "Secret", "whisper": True}
    # Target receives whisper
    ws2.send_json.assert_called_with(expected)
    # Sender receives copy
    ws1.send_json.assert_called_with(expected)


@pytest.mark.asyncio
async def test_whisper_not_sent_to_other_players():
    """Whisper should only go to target and sender, not other room members."""
    game = _make_game()
    ws1, ws2 = _setup_two_players(game)

    # Add a third player
    e3 = PlayerEntity(id="player_3", name="charlie", x=2, y=2, player_db_id=3)
    game.room_manager.get_room("test").add_entity(e3)
    ws3 = AsyncMock()
    game.connection_manager.connect("player_3", ws3, "test")
    game.player_manager.set_session("player_3", _ps({"entity": e3, "room_key": "test", "db_id": 3}))

    await handle_chat(
        ws1,
        {"action": "chat", "message": "Secret", "whisper_to": "player_2"},
        game=game,
    )

    # Player 3 should NOT receive the whisper
    ws3.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_whisper_to_nonexistent_player():
    game = _make_game()
    ws1, _ = _setup_two_players(game)

    await handle_chat(
        ws1,
        {"action": "chat", "message": "Hello", "whisper_to": "player_99"},
        game=game,
    )

    ws1.send_json.assert_called_with(
        {"type": "error", "detail": "Player not found"}
    )


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_empty_message_ignored():
    game = _make_game()
    ws1, ws2 = _setup_two_players(game)

    await handle_chat(ws1, {"action": "chat", "message": ""}, game=game)

    ws1.send_json.assert_not_called()
    ws2.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_chat_whitespace_only_ignored():
    game = _make_game()
    ws1, ws2 = _setup_two_players(game)

    await handle_chat(ws1, {"action": "chat", "message": "   "}, game=game)

    ws1.send_json.assert_not_called()
    ws2.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_chat_not_logged_in():
    game = _make_game()
    mock_ws = AsyncMock()

    await handle_chat(mock_ws, {"action": "chat", "message": "Hello"}, game=game)

    mock_ws.send_json.assert_called_with(
        {"type": "error", "detail": "Not logged in"}
    )


@pytest.mark.asyncio
async def test_chat_missing_message_field():
    game = _make_game()
    ws1, ws2 = _setup_two_players(game)

    await handle_chat(ws1, {"action": "chat"}, game=game)

    ws1.send_json.assert_not_called()
    ws2.send_json.assert_not_called()
