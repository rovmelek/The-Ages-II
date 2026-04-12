"""Tests for level-up threshold detection and stat choice handler."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from server.core.xp import get_pending_level_ups, send_level_up_available, grant_xp
from server.net.handlers.levelup import handle_level_up, _VALID_LEVEL_UP_STATS
from server.player.entity import PlayerEntity


from server.player.manager import PlayerManager
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
# get_pending_level_ups
# ---------------------------------------------------------------------------

def test_get_pending_level_ups_none():
    """No level-up available when XP is below threshold."""
    assert get_pending_level_ups({"level": 1, "xp": 500}) == 0


def test_get_pending_level_ups_one():
    """One level-up available at exactly the threshold."""
    assert get_pending_level_ups({"level": 1, "xp": 1000}) == 1


def test_get_pending_level_ups_multiple():
    """Multiple level-ups when XP crosses several thresholds."""
    # level=1: thresholds at 1000, 2000, 3000; xp=3500 crosses 3
    assert get_pending_level_ups({"level": 1, "xp": 3500}) == 3


def test_get_pending_level_ups_higher_level():
    """Pending level-ups respect current level."""
    # level=3: threshold at 3000; xp=3000 → 1 pending
    assert get_pending_level_ups({"level": 3, "xp": 3000}) == 1
    # level=3: threshold at 3000; xp=2999 → 0 pending
    assert get_pending_level_ups({"level": 3, "xp": 2999}) == 0


def test_get_pending_level_ups_defaults():
    """Defaults to level=1 and xp=0 when missing."""
    assert get_pending_level_ups({}) == 0


def test_get_pending_level_ups_zero_multiplier(monkeypatch):
    """Returns 0 when XP_LEVEL_THRESHOLD_MULTIPLIER is 0 (prevents infinite loop)."""
    from server.core import config
    monkeypatch.setattr(config.settings, "XP_LEVEL_THRESHOLD_MULTIPLIER", 0)
    assert get_pending_level_ups({"level": 1, "xp": 9999}) == 0


# ---------------------------------------------------------------------------
# send_level_up_available
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_level_up_available():
    """Sends level_up_available message with correct payload."""
    entity = PlayerEntity(
        id="player_1", name="hero", x=0, y=0, player_db_id=1,
        stats={"level": 1, "strength": 2, "dexterity": 1, "constitution": 3,
               "intelligence": 1, "wisdom": 1, "charisma": 1},
    )
    ws = AsyncMock()
    game = MagicMock()
    game.connection_manager.get_websocket.return_value = ws
    game.connection_manager.send_to_player_seq = AsyncMock()

    await send_level_up_available("player_1", entity, game)

    seq_mock = game.connection_manager.send_to_player_seq
    seq_mock.assert_called_once()
    _, msg = seq_mock.call_args[0]
    assert msg["type"] == "level_up_available"
    assert msg["new_level"] == 2
    assert msg["choose_stats"] == 3
    assert msg["stat_cap"] == 10
    assert msg["current_stats"]["strength"] == 2
    assert msg["current_stats"]["constitution"] == 3


# ---------------------------------------------------------------------------
# handle_level_up
# ---------------------------------------------------------------------------

def _mock_transaction():
    """Create a mock async context manager for game.transaction."""
    mock_session = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_factory = MagicMock(return_value=mock_ctx)
    return mock_factory, mock_session


def _make_game_with_entity(stats: dict, pending: int = 1) -> tuple:
    """Create a mock game with a player entity and return (game, ws, entity)."""
    entity = PlayerEntity(
        id="player_1", name="hero", x=5, y=5, player_db_id=1,
        stats=dict(stats),
    )
    ws = AsyncMock()
    game = MagicMock()
    factory, _ = _mock_transaction()
    game.transaction = factory
    game.connection_manager.get_entity_id.return_value = "player_1"
    game.connection_manager.get_websocket.return_value = ws
    game.connection_manager.send_to_player_seq = AsyncMock()
    game.player_manager = PlayerManager()
    game.player_manager.set_session("player_1", _ps({
        "entity": entity,
        "room_key": "town_square",
        "db_id": 1,
        "inventory": None,
        "visited_rooms": [],
        "pending_level_ups": pending,
    }))
    return game, ws, entity


@pytest.mark.asyncio
async def test_handle_level_up_valid():
    """Valid level-up: stats boosted, level incremented, max_hp recalculated, hp full."""
    stats = {
        "hp": 50, "max_hp": 105, "xp": 1200, "level": 1,
        "strength": 1, "dexterity": 1, "constitution": 1,
        "intelligence": 1, "wisdom": 1, "charisma": 1,
    }
    game, ws, entity = _make_game_with_entity(stats, pending=1)

    await handle_level_up(ws, {"stats": ["strength", "dexterity", "constitution"]}, game=game)

    # Verify stats
    assert entity.stats["strength"] == 2
    assert entity.stats["dexterity"] == 2
    assert entity.stats["constitution"] == 2
    assert entity.stats["level"] == 2
    assert entity.stats["max_hp"] == 100 + 2 * 5  # CON=2, CON_HP_PER_POINT=5
    assert entity.stats["hp"] == entity.stats["max_hp"]  # full heal

    # Verify response
    msg = ws.send_json.call_args[0][0]
    assert msg["type"] == "level_up_complete"
    assert msg["level"] == 2
    assert msg["stat_changes"] == {"strength": 2, "dexterity": 2, "constitution": 2}
    assert msg["new_max_hp"] == 110


@pytest.mark.asyncio
async def test_handle_level_up_no_pending():
    """Error when no level-up is pending."""
    stats = {"hp": 100, "max_hp": 105, "xp": 500, "level": 1,
             "strength": 1, "dexterity": 1, "constitution": 1,
             "intelligence": 1, "wisdom": 1, "charisma": 1}
    game, ws, _ = _make_game_with_entity(stats, pending=0)

    await handle_level_up(ws, {"stats": ["strength"]}, game=game)

    msg = ws.send_json.call_args[0][0]
    assert msg["type"] == "error"
    assert "No level-up available" in msg["detail"]


@pytest.mark.asyncio
async def test_handle_level_up_empty_stats():
    """Error when no stats are chosen."""
    stats = {"hp": 105, "max_hp": 105, "xp": 1200, "level": 1,
             "strength": 1, "dexterity": 1, "constitution": 1,
             "intelligence": 1, "wisdom": 1, "charisma": 1}
    game, ws, _ = _make_game_with_entity(stats, pending=1)

    await handle_level_up(ws, {"stats": []}, game=game)

    msg = ws.send_json.call_args[0][0]
    assert msg["type"] == "error"
    assert "Must choose at least 1 stat" in msg["detail"]


@pytest.mark.asyncio
async def test_handle_level_up_blocked_in_combat():
    """Error when player tries to level up during combat."""
    stats = {"hp": 105, "max_hp": 105, "xp": 1200, "level": 1,
             "strength": 1, "dexterity": 1, "constitution": 1,
             "intelligence": 1, "wisdom": 1, "charisma": 1}
    game, ws, entity = _make_game_with_entity(stats, pending=1)
    entity.in_combat = True

    await handle_level_up(ws, {"stats": ["strength"]}, game=game)

    msg = ws.send_json.call_args[0][0]
    assert msg["type"] == "error"
    assert "Cannot level up during combat" in msg["detail"]


@pytest.mark.asyncio
async def test_handle_level_up_invalid_stat():
    """Error when invalid stat name is provided."""
    stats = {"hp": 105, "max_hp": 105, "xp": 1200, "level": 1,
             "strength": 1, "dexterity": 1, "constitution": 1,
             "intelligence": 1, "wisdom": 1, "charisma": 1}
    game, ws, _ = _make_game_with_entity(stats, pending=1)

    await handle_level_up(ws, {"stats": ["mana"]}, game=game)

    msg = ws.send_json.call_args[0][0]
    assert msg["type"] == "error"
    assert "Invalid stat: mana" in msg["detail"]


@pytest.mark.asyncio
async def test_handle_level_up_duplicate_stats():
    """Duplicate stats are deduplicated — only unique stats boosted."""
    stats = {"hp": 105, "max_hp": 105, "xp": 1200, "level": 1,
             "strength": 1, "dexterity": 1, "constitution": 1,
             "intelligence": 1, "wisdom": 1, "charisma": 1}
    game, ws, entity = _make_game_with_entity(stats, pending=1)

    await handle_level_up(
        ws, {"stats": ["strength", "strength", "dexterity"]}, game=game
    )

    # Only STR+1 and DEX+1 (strength deduplicated)
    assert entity.stats["strength"] == 2
    assert entity.stats["dexterity"] == 2
    assert entity.stats["constitution"] == 1  # unchanged

    msg = ws.send_json.call_args[0][0]
    assert msg["stat_changes"] == {"strength": 2, "dexterity": 2}


@pytest.mark.asyncio
async def test_handle_level_up_stat_at_cap():
    """Stats at cap (10) are skipped and reported."""
    stats = {"hp": 105, "max_hp": 105, "xp": 1200, "level": 1,
             "strength": 10, "dexterity": 1, "constitution": 1,
             "intelligence": 1, "wisdom": 1, "charisma": 1}
    game, ws, entity = _make_game_with_entity(stats, pending=1)

    await handle_level_up(
        ws, {"stats": ["strength", "dexterity", "constitution"]}, game=game
    )

    assert entity.stats["strength"] == 10  # unchanged (cap)
    assert entity.stats["dexterity"] == 2
    assert entity.stats["constitution"] == 2

    msg = ws.send_json.call_args[0][0]
    assert msg["type"] == "level_up_complete"
    assert "strength" not in msg["stat_changes"]
    assert msg["skipped_at_cap"] == ["strength"]


@pytest.mark.asyncio
async def test_handle_level_up_queued():
    """After first level-up, queued level-up sends new level_up_available."""
    # XP=3500 at level 1 → 3 pending level-ups
    stats = {"hp": 105, "max_hp": 105, "xp": 3500, "level": 1,
             "strength": 1, "dexterity": 1, "constitution": 1,
             "intelligence": 1, "wisdom": 1, "charisma": 1}
    game, ws, entity = _make_game_with_entity(stats, pending=3)

    await handle_level_up(
        ws, {"stats": ["strength", "dexterity", "constitution"]}, game=game
    )

    # Level incremented to 2
    assert entity.stats["level"] == 2

    # level_up_complete via ws.send_json, level_up_available via send_to_player_seq
    ws_calls = ws.send_json.call_args_list
    assert len(ws_calls) == 1
    assert ws_calls[0][0][0]["type"] == "level_up_complete"
    seq_calls = game.connection_manager.send_to_player_seq.call_args_list
    assert len(seq_calls) == 1
    assert seq_calls[0][0][1]["type"] == "level_up_available"
    assert seq_calls[0][0][1]["new_level"] == 3

    # Remaining pending should be 2 (thresholds at 2000, 3000)
    assert game.player_manager.get_session("player_1").pending_level_ups == 2


# ---------------------------------------------------------------------------
# grant_xp triggers level-up detection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_grant_xp_triggers_level_up():
    """grant_xp sends level_up_available when XP crosses threshold."""
    entity = PlayerEntity(
        id="player_1", name="hero", x=0, y=0, player_db_id=1,
        stats={"hp": 105, "max_hp": 105, "xp": 900, "level": 1,
               "strength": 1, "dexterity": 1, "constitution": 1,
               "intelligence": 1, "wisdom": 1, "charisma": 0},
    )
    ws = AsyncMock()
    game = MagicMock()
    factory, _ = _mock_transaction()
    game.transaction = factory
    game.connection_manager.get_websocket.return_value = ws
    game.connection_manager.send_to_player_seq = AsyncMock()
    game.player_manager = PlayerManager()
    game.player_manager.set_session("player_1", _ps({
        "entity": entity,
        "room_key": "town_square",
        "db_id": 1,
        "pending_level_ups": 0,
    }))

    await grant_xp("player_1", entity, 200, "combat", "goblin", game, apply_cha_bonus=False)

    # XP should be 1100 (900 + 200) → crosses 1000 threshold
    assert entity.stats["xp"] == 1100

    # Should have sent xp_gained AND level_up_available via send_to_player_seq
    seq_calls = game.connection_manager.send_to_player_seq.call_args_list
    msg_types = [c[0][1]["type"] for c in seq_calls]
    assert "xp_gained" in msg_types
    assert "level_up_available" in msg_types
    assert game.player_manager.get_session("player_1").pending_level_ups == 1


# ---------------------------------------------------------------------------
# Login re-check
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_login_recheck_level_up_available():
    """get_pending_level_ups correctly identifies pending level-ups for login re-check."""
    # Player saved with xp=1500, level=1 → 1 pending
    stats = {"xp": 1500, "level": 1}
    assert get_pending_level_ups(stats) == 1

    # Player saved with xp=500, level=1 → 0 pending
    stats = {"xp": 500, "level": 1}
    assert get_pending_level_ups(stats) == 0


# ---------------------------------------------------------------------------
# stats_result includes xp_next
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stats_result_includes_xp_next():
    """handle_stats includes xp_next in the response."""
    from server.net.handlers.query import handle_stats

    entity = PlayerEntity(
        id="player_1", name="hero", x=0, y=0, player_db_id=1,
        stats={"hp": 105, "max_hp": 105, "xp": 500, "level": 2,
               "strength": 2, "dexterity": 1, "constitution": 1,
               "intelligence": 1, "wisdom": 1, "charisma": 1,
               "attack": 10},
    )
    ws = AsyncMock()
    game = MagicMock()
    game.connection_manager.get_entity_id.return_value = "player_1"
    game.player_manager = PlayerManager()
    game.player_manager.set_session("player_1", _ps({"entity": entity, "room_key": "town_square"}))

    await handle_stats(ws, {}, game=game)

    msg = ws.send_json.call_args[0][0]
    assert msg["type"] == "stats_result"
    assert msg["stats"]["xp_next"] == 2000  # level 2 × 1000


# ---------------------------------------------------------------------------
# Level-up persists stats
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("server.net.handlers.levelup.player_repo.update_stats", new_callable=AsyncMock)
async def test_level_up_persists_stats(mock_update_stats):
    """Level-up persists updated stats to DB."""
    stats = {"hp": 105, "max_hp": 105, "xp": 1200, "level": 1,
             "strength": 1, "dexterity": 1, "constitution": 1,
             "intelligence": 1, "wisdom": 1, "charisma": 1}
    game, ws, entity = _make_game_with_entity(stats, pending=1)

    await handle_level_up(ws, {"stats": ["strength"]}, game=game)

    # Get the mock session from the factory
    mock_ctx = game.transaction.return_value.__aenter__.return_value
    mock_update_stats.assert_called_once_with(
        mock_ctx, entity.player_db_id, entity.stats
    )
