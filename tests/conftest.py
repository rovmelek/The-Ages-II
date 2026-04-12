"""Shared test fixtures."""
from __future__ import annotations

import bcrypt
import pytest
from unittest.mock import MagicMock

from server.core.config import settings

_original_gensalt = bcrypt.gensalt


@pytest.fixture(autouse=True, scope="session")
def _fast_bcrypt():
    """Use minimum bcrypt rounds (4) during tests for speed.

    Default 12 rounds make each hash/verify ~0.2s.  With ~101 bcrypt
    operations across the test suite this adds ~21s of wall-clock time.
    4 rounds reduce each operation to <0.001s while still exercising the
    real bcrypt algorithm (hash/verify roundtrip is preserved).
    """
    original = bcrypt.gensalt
    bcrypt.gensalt = lambda rounds=4: _original_gensalt(rounds=4)
    yield
    bcrypt.gensalt = original


@pytest.fixture(autouse=True, scope="session")
def _zero_grace_period():
    """Set DISCONNECT_GRACE_SECONDS=0 for all tests.

    This preserves immediate-cleanup behavior for existing tests.
    New grace-period tests override with non-zero values via monkeypatch.
    """
    original = settings.DISCONNECT_GRACE_SECONDS
    settings.DISCONNECT_GRACE_SECONDS = 0
    yield
    settings.DISCONNECT_GRACE_SECONDS = original


def make_bare_game(**overrides):
    """Create a Game with all __init__ attrs set to safe defaults.

    Uses Game.__new__ to skip real __init__ (avoids DB/manager setup),
    then sets every attribute to a MagicMock or empty default.
    When Game.__init__ gains new fields, update THIS function only.

    Usage:
        game = make_bare_game()  # all defaults
        game = make_bare_game(npc_templates={"goblin": {...}})  # override specific attrs
    """
    from server.app import Game

    game = Game.__new__(Game)
    game.router = MagicMock()
    game.connection_manager = MagicMock()
    game.room_manager = MagicMock()
    game.scheduler = MagicMock()
    game.event_bus = MagicMock()
    game.effect_registry = MagicMock()
    game.combat_manager = MagicMock()
    game.trade_manager = MagicMock()
    game.party_manager = MagicMock()
    game.player_manager = MagicMock()
    game.session_factory = MagicMock()
    game._shutting_down = False
    game.loot_tables = {}
    game.npc_templates = {}
    game._heartbeat_tasks = {}
    game._pong_events = {}
    game.token_store = MagicMock()
    game._cleanup_handles = {}
    for key, value in overrides.items():
        setattr(game, key, value)
    return game
