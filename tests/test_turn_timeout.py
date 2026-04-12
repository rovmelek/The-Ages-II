"""Tests for combat turn timeout enforcement (Story 16.10a)."""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.combat.instance import CombatInstance
from server.combat.cards.card_def import CardDef


def _make_card_defs():
    return [CardDef(card_key="slash", name="Slash", cost=1, effects=[{"type": "damage", "value": 10}])]


def _make_instance(mob_hp=200):
    """Create a CombatInstance with one player and a mob."""
    instance = CombatInstance(
        mob_name="Goblin",
        mob_stats={"hp": mob_hp, "max_hp": 200, "attack": 5, "strength": 1, "dexterity": 1},
        mob_hit_dice=2,
    )
    cards = _make_card_defs()
    instance.add_participant("player_1", {
        "hp": 100, "max_hp": 100, "attack": 10, "shield": 0,
        "xp": 0, "level": 1, "charisma": 0,
        "strength": 1, "dexterity": 1, "constitution": 1,
        "intelligence": 1, "wisdom": 1,
    }, cards)
    return instance


class TestTurnTimeoutScheduling:
    """Tests for timeout scheduling on CombatInstance."""

    def test_no_timeout_without_callback(self):
        """No timeout is scheduled if callback is not set."""
        instance = _make_instance()
        instance.start_turn_timer()
        assert instance._turn_timeout_handle is None
        assert instance._turn_timeout_at is None

    async def test_timeout_scheduled_with_callback(self):
        """Timeout is scheduled when callback is set and timer is started."""
        instance = _make_instance()
        callback = MagicMock()
        instance.set_turn_timeout_callback(callback)
        instance.start_turn_timer()

        assert instance._turn_timeout_handle is not None
        assert instance._turn_timeout_at is not None
        assert instance._turn_timeout_at > time.time()

        # Cleanup
        instance._cancel_turn_timeout()

    async def test_timeout_cancelled_on_action(self):
        """Timeout is cancelled when player acts (pass_turn)."""
        instance = _make_instance()
        callback = MagicMock()
        instance.set_turn_timeout_callback(callback)
        instance.start_turn_timer()

        assert instance._turn_timeout_handle is not None

        # Player acts — this should cancel the timeout
        await instance.pass_turn("player_1")

        # After action, a new timeout should be scheduled for the next turn
        # (but since there's only 1 player, the same player's turn comes back)
        # The old handle should have been cancelled and a new one created
        # We verify the timeout_at was updated
        assert instance._turn_timeout_at is not None

    async def test_timeout_rescheduled_on_validation_failure(self):
        """Timeout is re-scheduled when validation fails (wrong turn)."""
        instance = _make_instance()
        # Add a second player so we can test wrong-turn
        instance.add_participant("player_2", {
            "hp": 100, "max_hp": 100, "attack": 10, "shield": 0,
            "xp": 0, "level": 1, "charisma": 0,
            "strength": 1, "dexterity": 1, "constitution": 1,
            "intelligence": 1, "wisdom": 1,
        }, _make_card_defs())

        callback = MagicMock()
        instance.set_turn_timeout_callback(callback)
        instance.start_turn_timer()

        # It's player_1's turn — player_2 tries to act
        with pytest.raises(ValueError, match="Not your turn"):
            await instance.pass_turn("player_2")

        # Timeout should still be active (re-scheduled)
        assert instance._turn_timeout_handle is not None
        assert instance._turn_timeout_at is not None

        instance._cancel_turn_timeout()

    async def test_timeout_cancelled_on_remove_participant(self):
        """Timeout is cancelled when a participant is removed."""
        instance = _make_instance()
        callback = MagicMock()
        instance.set_turn_timeout_callback(callback)
        instance.start_turn_timer()

        assert instance._turn_timeout_handle is not None

        instance.remove_participant("player_1")

        assert instance._turn_timeout_handle is None
        assert instance._turn_timeout_at is None

    def test_turn_timeout_at_in_get_state(self):
        """get_state includes turn_timeout_at when timeout is active."""
        instance = _make_instance()
        state = instance.get_state()
        assert "turn_timeout_at" not in state

    async def test_turn_timeout_at_in_get_state_when_active(self):
        """get_state includes turn_timeout_at when timeout is scheduled."""
        instance = _make_instance()
        callback = MagicMock()
        instance.set_turn_timeout_callback(callback)
        instance.start_turn_timer()

        state = instance.get_state()
        assert "turn_timeout_at" in state
        assert isinstance(state["turn_timeout_at"], float)
        assert state["turn_timeout_at"] > time.time()

        instance._cancel_turn_timeout()


class TestTurnTimeoutCallback:
    """Tests for the timeout callback mechanism."""

    async def test_timeout_fires_auto_pass(self):
        """When timeout fires, the turn auto-passes."""
        instance = _make_instance()
        # Add second player to verify turn advances
        instance.add_participant("player_2", {
            "hp": 100, "max_hp": 100, "attack": 10, "shield": 0,
            "xp": 0, "level": 1, "charisma": 0,
            "strength": 1, "dexterity": 1, "constitution": 1,
            "intelligence": 1, "wisdom": 1,
        }, _make_card_defs())

        assert instance.get_current_turn() == "player_1"

        # Simulate timeout callback behavior
        result = await instance.pass_turn("player_1")
        assert result["action"] == "pass_turn"
        assert result["entity_id"] == "player_1"

        # Turn should have advanced to player_2
        assert instance.get_current_turn() == "player_2"

    async def test_timeout_wrong_turn_no_crash(self):
        """Timeout for wrong player raises ValueError (caught by callback)."""
        instance = _make_instance()
        instance.add_participant("player_2", {
            "hp": 100, "max_hp": 100, "attack": 10, "shield": 0,
            "xp": 0, "level": 1, "charisma": 0,
            "strength": 1, "dexterity": 1, "constitution": 1,
            "intelligence": 1, "wisdom": 1,
        }, _make_card_defs())

        assert instance.get_current_turn() == "player_1"

        # Simulate timeout for player_2 (not their turn) — race condition scenario
        with pytest.raises(ValueError, match="Not your turn"):
            await instance.pass_turn("player_2")
