"""Tests for out-of-combat HP/energy regen loop (Epic 18, Task 21-23)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.core.regen import _regen_loop, start_regen_loop, stop_regen_loop


# --- Helpers ---


class FakeEntity:
    def __init__(self, hp=50, max_hp=100, energy=10, max_energy=25, in_combat=False):
        self.in_combat = in_combat
        self.player_db_id = 1
        self.stats = {
            "hp": hp, "max_hp": max_hp,
            "energy": energy, "max_energy": max_energy,
        }


def _make_entity(hp=50, max_hp=100, energy=10, max_energy=25, in_combat=False):
    return FakeEntity(hp=hp, max_hp=max_hp, energy=energy, max_energy=max_energy, in_combat=in_combat)


def _make_player_info(entity):
    pi = MagicMock()
    pi.entity = entity
    pi.db_id = entity.player_db_id
    return pi


def _make_game(sessions=None):
    game = MagicMock()
    game.player_manager = MagicMock()
    game.player_manager.all_sessions.return_value = sessions or []
    game.player_manager.get_session.side_effect = lambda eid: dict(sessions).get(eid) if sessions else None
    game.connection_manager = MagicMock()
    game.connection_manager.get_websocket.return_value = MagicMock()
    game.connection_manager.send_to_player_seq = AsyncMock()
    game.transaction = MagicMock()
    return game


# --- Tests ---


@pytest.mark.asyncio
async def test_regen_ticks_hp_and_energy():
    """Regen loop increases HP and energy for out-of-combat players."""
    entity = _make_entity(hp=50, max_hp=100, energy=10, max_energy=25)
    pi = _make_player_info(entity)
    game = _make_game(sessions=[("p1", pi)])

    with patch("server.core.regen.settings") as mock_settings:
        mock_settings.REGEN_INTERVAL_SECONDS = 0.04
        mock_settings.REGEN_HP_PER_TICK = 3
        mock_settings.REGEN_ENERGY_PER_TICK = 2
        mock_settings.REGEN_PERSIST_INTERVAL = 100  # Don't persist in this test

        task = asyncio.create_task(_regen_loop(game))
        await asyncio.sleep(0.06)  # ~1 tick
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert entity.stats["hp"] == 53
    assert entity.stats["energy"] == 12
    game.connection_manager.send_to_player_seq.assert_called()


@pytest.mark.asyncio
async def test_regen_skips_combat_players():
    """Players in combat are skipped."""
    entity = _make_entity(hp=50, in_combat=True)
    pi = _make_player_info(entity)
    game = _make_game(sessions=[("p1", pi)])

    with patch("server.core.regen.settings") as mock_settings:
        mock_settings.REGEN_INTERVAL_SECONDS = 0.04
        mock_settings.REGEN_HP_PER_TICK = 3
        mock_settings.REGEN_ENERGY_PER_TICK = 2
        mock_settings.REGEN_PERSIST_INTERVAL = 100

        task = asyncio.create_task(_regen_loop(game))
        await asyncio.sleep(0.06)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert entity.stats["hp"] == 50  # Unchanged


@pytest.mark.asyncio
async def test_regen_skips_full_hp_energy():
    """Players at full HP and energy are skipped."""
    entity = _make_entity(hp=100, max_hp=100, energy=25, max_energy=25)
    pi = _make_player_info(entity)
    game = _make_game(sessions=[("p1", pi)])

    with patch("server.core.regen.settings") as mock_settings:
        mock_settings.REGEN_INTERVAL_SECONDS = 0.04
        mock_settings.REGEN_HP_PER_TICK = 3
        mock_settings.REGEN_ENERGY_PER_TICK = 2
        mock_settings.REGEN_PERSIST_INTERVAL = 100

        task = asyncio.create_task(_regen_loop(game))
        await asyncio.sleep(0.06)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # No stats_update sent — player already full
    game.connection_manager.send_to_player_seq.assert_not_called()


@pytest.mark.asyncio
async def test_regen_caps_at_max():
    """Regen doesn't exceed max HP/energy."""
    entity = _make_entity(hp=99, max_hp=100, energy=24, max_energy=25)
    pi = _make_player_info(entity)
    game = _make_game(sessions=[("p1", pi)])

    with patch("server.core.regen.settings") as mock_settings:
        mock_settings.REGEN_INTERVAL_SECONDS = 0.04
        mock_settings.REGEN_HP_PER_TICK = 3
        mock_settings.REGEN_ENERGY_PER_TICK = 2
        mock_settings.REGEN_PERSIST_INTERVAL = 100

        task = asyncio.create_task(_regen_loop(game))
        await asyncio.sleep(0.06)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert entity.stats["hp"] == 100  # Capped
    assert entity.stats["energy"] == 25  # Capped


@pytest.mark.asyncio
async def test_regen_error_isolation():
    """Error in one player's regen doesn't crash the loop for others."""
    entity1 = _make_entity(hp=50)
    entity2 = _make_entity(hp=50)
    pi1 = _make_player_info(entity1)
    pi2 = _make_player_info(entity2)
    game = _make_game(sessions=[("p1", pi1), ("p2", pi2)])

    # Make p1's websocket send raise an exception
    call_count = [0]
    original_send = game.connection_manager.send_to_player_seq

    async def _failing_send(eid, msg):
        call_count[0] += 1
        if eid == "p1":
            raise ConnectionError("WebSocket dead")
        return await original_send(eid, msg)

    game.connection_manager.send_to_player_seq = AsyncMock(side_effect=_failing_send)

    with patch("server.core.regen.settings") as mock_settings:
        mock_settings.REGEN_INTERVAL_SECONDS = 0.04
        mock_settings.REGEN_HP_PER_TICK = 3
        mock_settings.REGEN_ENERGY_PER_TICK = 2
        mock_settings.REGEN_PERSIST_INTERVAL = 100

        task = asyncio.create_task(_regen_loop(game))
        await asyncio.sleep(0.06)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # Both entities should have HP modified (in-place mutation happens before send)
    assert entity1.stats["hp"] == 53
    assert entity2.stats["hp"] == 53


@pytest.mark.asyncio
async def test_start_stop_regen_loop():
    """start/stop lifecycle works cleanly."""
    game = _make_game(sessions=[])

    with patch("server.core.regen.settings") as mock_settings:
        mock_settings.REGEN_INTERVAL_SECONDS = 10  # Won't tick in this test

        await start_regen_loop(game)
        await stop_regen_loop()
        # No crash — clean shutdown
