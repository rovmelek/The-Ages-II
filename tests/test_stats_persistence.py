"""Tests for player stats persistence (Story 7.2)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from server.core.database import Base
from server.player.models import Player
from server.player import repo as player_repo
from server.room.room import RoomInstance


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def async_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def test_session_factory(async_engine):
    return async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )


@pytest.fixture
def room_manager():
    from server.room.manager import RoomManager

    mgr = RoomManager()
    room = RoomInstance(
        room_key="town_square",
        name="Town Square",
        width=5,
        height=5,
        tile_data=[[0] * 5 for _ in range(5)],
        exits=[],
    )
    mgr._rooms["town_square"] = room
    return mgr


@pytest.fixture
def connection_manager():
    from server.net.connection_manager import ConnectionManager
    return ConnectionManager()


@pytest.fixture
def client(test_session_factory, room_manager, connection_manager):
    """TestClient matching test_login.py pattern — only patch auth.async_session."""
    from server.app import app, game

    original_rm = game.room_manager
    original_cm = game.connection_manager

    original_sf = game.session_factory
    with TestClient(app) as c:
        game.room_manager = room_manager
        game.connection_manager = connection_manager
        game.session_factory = test_session_factory
        yield c

    game.room_manager = original_rm
    game.connection_manager = original_cm
    game.session_factory = original_sf
    game.player_entities.clear()


# ---------------------------------------------------------------------------
# Unit tests: update_stats whitelist
# ---------------------------------------------------------------------------

class TestUpdateStatsWhitelist:
    """Test that update_stats only persists whitelisted keys."""

    @pytest.mark.asyncio
    async def test_whitelist_filters_keys(self, test_session_factory):
        """Non-whitelisted keys like shield are stripped."""
        async with test_session_factory() as session:
            from server.player.auth import hash_password
            player = await player_repo.create(session, "testuser", hash_password("pass123"))
            pid = player.id
            await session.commit()

        async with test_session_factory() as session:
            await player_repo.update_stats(session, pid, {
                "hp": 80, "max_hp": 100, "attack": 10, "xp": 25,
                "shield": 5, "some_garbage": True,
            })
            await session.commit()

        async with test_session_factory() as session:
            result = await session.execute(select(Player).where(Player.id == pid))
            p = result.scalar_one()
            assert p.stats["hp"] == 80
            assert p.stats["xp"] == 25
            assert "shield" not in p.stats
            assert "some_garbage" not in p.stats

    @pytest.mark.asyncio
    async def test_empty_stats_after_filter(self, test_session_factory):
        """If all keys are non-whitelisted, persist empty dict."""
        async with test_session_factory() as session:
            from server.player.auth import hash_password
            player = await player_repo.create(session, "testuser2", hash_password("pass123"))
            pid = player.id
            await session.commit()

        async with test_session_factory() as session:
            await player_repo.update_stats(session, pid, {"shield": 5, "temp": 99})
            await session.commit()

        async with test_session_factory() as session:
            result = await session.execute(select(Player).where(Player.id == pid))
            p = result.scalar_one()
            assert p.stats == {}


# ---------------------------------------------------------------------------
# First login defaults
# ---------------------------------------------------------------------------

class TestFirstLoginDefaults:
    """Test that first-time players receive default stats."""

    def test_first_login_gets_default_stats(self, client):
        """New player should get CON-derived max_hp, ability scores, level."""
        from server.app import game

        with client.websocket_connect("/ws/game") as ws:
            ws.send_json({"action": "register", "username": "newbie", "password": "secret123"})
            ws.receive_json()

        with client.websocket_connect("/ws/game") as ws:
            ws.send_json({"action": "login", "username": "newbie", "password": "secret123"})
            ws.receive_json()  # login_success
            ws.receive_json()  # room_state

            # Check runtime entity has defaults with CON-derived max_hp
            entity_stats = game.player_entities["player_1"]["entity"].stats
            assert entity_stats["hp"] == 105  # 100 + CON(1) * 5
            assert entity_stats["max_hp"] == 105
            assert entity_stats["attack"] == 10
            assert entity_stats["xp"] == 0
            assert entity_stats["level"] == 1
            assert entity_stats["strength"] == 1
            assert entity_stats["constitution"] == 1


# ---------------------------------------------------------------------------
# Returning player stats restore
# ---------------------------------------------------------------------------

class TestReturningPlayerStats:
    """Test that returning players get their saved stats."""

    def test_saved_stats_restored_on_login(self, client, test_session_factory):
        """Player with saved stats should get those stats, not defaults."""
        from server.app import game

        # Register player
        with client.websocket_connect("/ws/game") as ws:
            ws.send_json({"action": "register", "username": "veteran", "password": "secret123"})
            ws.receive_json()

        # Set custom stats in DB (simulating a previous session)
        async def set_stats():
            async with test_session_factory() as session:
                await session.execute(
                    update(Player).where(Player.username == "veteran").values(
                        stats={"hp": 50, "max_hp": 100, "attack": 15, "xp": 200},
                        current_room_id="town_square",
                    )
                )
                await session.commit()

        asyncio.run(set_stats())

        # Login and check stats
        with client.websocket_connect("/ws/game") as ws:
            ws.send_json({"action": "login", "username": "veteran", "password": "secret123"})
            ws.receive_json()  # login_success
            ws.receive_json()  # room_state

            entity_stats = game.player_entities["player_1"]["entity"].stats
            assert entity_stats["hp"] == 50
            assert entity_stats["max_hp"] == 100
            assert entity_stats["attack"] == 15
            assert entity_stats["xp"] == 200


# ---------------------------------------------------------------------------
# Stats persistence on disconnect
# ---------------------------------------------------------------------------

class TestDisconnectStatsSave:
    """Test that stats are persisted when player disconnects."""

    def test_disconnect_calls_update_stats(self, client):
        """Disconnecting should call update_stats to save entity stats."""
        from server.app import game

        with client.websocket_connect("/ws/game") as ws:
            ws.send_json({"action": "register", "username": "dcer", "password": "secret123"})
            ws.receive_json()

        # Mock update_stats to capture calls
        mock_update = AsyncMock()
        with patch("server.app.player_repo.update_stats", mock_update):
            with client.websocket_connect("/ws/game") as ws:
                ws.send_json({"action": "login", "username": "dcer", "password": "secret123"})
                ws.receive_json()  # login_success
                ws.receive_json()  # room_state

                # Modify entity stats in-memory (simulating combat damage)
                entity = game.player_entities["player_1"]["entity"]
                entity.stats["hp"] = 42
                entity.stats["xp"] = 75

            # WebSocket closed — disconnect handler runs

        # Verify update_stats was called with the entity's stats
        assert mock_update.called
        call_args = mock_update.call_args
        saved_stats = call_args[0][2]  # third positional arg: stats dict
        assert saved_stats["hp"] == 42
        assert saved_stats["xp"] == 75


# ---------------------------------------------------------------------------
# Combat stats sync (unit-level via _sync_combat_stats)
# ---------------------------------------------------------------------------

class TestCombatStatsSync:
    """Test that combat stats sync back to entity after actions."""

    def test_combat_stats_written_back_to_entity(self, client):
        """After a combat action, entity stats should reflect combat changes."""
        from server.app import game
        from server.combat.instance import CombatInstance

        with client.websocket_connect("/ws/game") as ws:
            ws.send_json({"action": "register", "username": "fighter", "password": "secret123"})
            ws.receive_json()

        with client.websocket_connect("/ws/game") as ws:
            ws.send_json({"action": "login", "username": "fighter", "password": "secret123"})
            ws.receive_json()  # login_success
            ws.receive_json()  # room_state

            entity = game.player_entities["player_1"]["entity"]
            assert entity.stats["hp"] == 105  # 100 + CON(1) * 5

            # Simulate combat: create instance, modify participant stats
            instance = CombatInstance(
                mob_name="Test Mob",
                mob_stats={"hp": 50, "max_hp": 50, "attack": 10},
            )
            from server.combat.cards.card_def import CardDef
            card_defs = [
                CardDef(card_key="test_atk", name="Test", cost=1,
                        effects=[{"type": "damage", "value": 10}])
            ]
            instance.add_participant("player_1", dict(entity.stats), card_defs)

            # Simulate taking damage in combat (modify participant stats directly)
            instance.participant_stats["player_1"]["hp"] = 60

            # Call sync — mock the session factory on game
            from server.net.handlers.combat import _sync_combat_stats
            mock_session = AsyncMock()
            mock_ctx = MagicMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_factory = MagicMock(return_value=mock_ctx)
            old_sf = game.session_factory
            game.transaction = mock_factory
            try:
                asyncio.get_event_loop().run_until_complete(
                    _sync_combat_stats(instance, game)
                )
            finally:
                game.session_factory = old_sf

            # Entity stats should be updated
            assert entity.stats["hp"] == 60
