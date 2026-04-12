"""Tests for end-to-end startup and gameplay wiring (Story 6-3)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from server.core.database import Base


# --- Fixtures ---


@pytest.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    import server.combat.cards.models  # noqa: F401
    import server.items.models  # noqa: F401
    import server.player.models  # noqa: F401
    import server.room.models  # noqa: F401
    import server.room.spawn_models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def test_session_factory(db_engine):
    return async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )


# --- Story 6-3: End-to-End Startup & Gameplay Wiring ---


class TestHandlerRegistration:
    """Verify all expected handlers are registered after startup."""

    @pytest.mark.asyncio
    async def test_all_handlers_registered(self, test_session_factory):
        from server.app import Game

        game = Game()
        game.session_factory = test_session_factory
        with patch("server.app.init_db", return_value=None), \
             patch("server.app.settings") as mock_settings, \
             patch("server.app.JsonRoomProvider") as MockProvider:
            mock_settings.DATA_DIR = Path("/tmp/nonexistent_data_dir")
            instance = MockProvider.return_value
            instance.load_rooms = AsyncMock(return_value=[])
            await game.startup()

        try:
            expected_handlers = [
                "login", "register", "move", "chat", "interact",
                "play_card", "pass_turn", "flee",
                "inventory", "use_item", "use_item_combat",
            ]
            for handler_name in expected_handlers:
                assert handler_name in game.router._handlers, \
                    f"Handler '{handler_name}' not registered"
        finally:
            await game.shutdown()

    @pytest.mark.asyncio
    async def test_effect_registry_initialized(self, test_session_factory):
        from server.app import Game

        game = Game()
        assert game.effect_registry is not None

    @pytest.mark.asyncio
    async def test_combat_manager_has_effect_registry(self, test_session_factory):
        from server.app import Game

        game = Game()
        assert game.combat_manager._effect_registry is game.effect_registry


class TestStartupDataLoading:
    """Verify startup loads rooms, cards, items, and NPC templates."""

    @pytest.mark.asyncio
    async def test_startup_loads_rooms(self, test_session_factory):
        from server.app import Game
        from server.room.models import Room

        mock_room = MagicMock(spec=Room)
        mock_room.room_key = "town_square"
        mock_room.name = "Town Square"
        mock_room.width = 5
        mock_room.height = 5
        mock_room.tile_data = [[0] * 5 for _ in range(5)]
        mock_room.exits = []
        mock_room.objects = []
        mock_room.spawn_points = []

        game = Game()
        game.session_factory = test_session_factory
        with patch("server.app.init_db", return_value=None), \
             patch("server.app.settings") as mock_settings, \
             patch("server.app.JsonRoomProvider") as MockProvider:
            mock_settings.DATA_DIR = Path("/tmp/nonexistent_data_dir")
            instance = MockProvider.return_value
            instance.load_rooms = AsyncMock(return_value=[mock_room])
            await game.startup()

        try:
            assert game.room_manager.get_room("town_square") is not None
        finally:
            await game.shutdown()

    @pytest.mark.asyncio
    async def test_startup_initializes_scheduler(self, test_session_factory):
        from server.app import Game

        game = Game()
        game.session_factory = test_session_factory
        with patch("server.app.init_db", return_value=None), \
             patch("server.app.settings") as mock_settings, \
             patch("server.app.JsonRoomProvider") as MockProvider:
            mock_settings.DATA_DIR = Path("/tmp/nonexistent_data_dir")
            instance = MockProvider.return_value
            instance.load_rooms = AsyncMock(return_value=[])
            await game.startup()

        assert game.scheduler._running is True
        await game.shutdown()
        assert game.scheduler._running is False


class TestHealthEndpoint:
    def test_health_returns_ok(self):
        from server.app import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestRoomDataIntegration:
    """Verify the actual JSON room files can be loaded by the room system."""

    def test_town_square_loads_as_room_instance(self):
        import json
        from server.room.room import RoomInstance

        with open("data/rooms/town_square.json") as f:
            data = json.load(f)

        room = RoomInstance(
            room_key=data["room_key"],
            name=data["name"],
            width=data["width"],
            height=data["height"],
            tile_data=data["tile_data"],
            exits=data["exits"],
            objects=data["objects"],
            spawn_points=data["spawn_points"],
        )
        assert room.room_key == "town_square"
        assert room.width == 100
        assert room.height == 100
        # Player spawn is accessible
        sx, sy = room.get_player_spawn()
        assert 0 <= sx < 100 and 0 <= sy < 100

    def test_dark_cave_loads_as_room_instance(self):
        import json
        from server.room.room import RoomInstance

        with open("data/rooms/dark_cave.json") as f:
            data = json.load(f)

        room = RoomInstance(
            room_key=data["room_key"],
            name=data["name"],
            width=data["width"],
            height=data["height"],
            tile_data=data["tile_data"],
            exits=data["exits"],
            objects=data["objects"],
            spawn_points=data["spawn_points"],
        )
        assert room.room_key == "dark_cave"
        assert room.width == 100

    def test_dark_cave_npc_spawns_resolve(self):
        """NPCs referenced in dark_cave spawn points can be created from templates."""
        import json
        from server.room.objects.npc import create_npc_from_template, load_npc_templates
        from pathlib import Path

        load_npc_templates(Path("data/npcs"))

        with open("data/rooms/dark_cave.json") as f:
            data = json.load(f)

        npc_spawns = [sp for sp in data["spawn_points"] if sp["type"] == "npc"]
        for sp in npc_spawns:
            npc = create_npc_from_template(
                sp["npc_key"],
                f"test_{sp['npc_key']}",
                sp["x"],
                sp["y"],
            )
            assert npc is not None, f"NPC template '{sp['npc_key']}' not found"
            assert npc.is_alive is True

    def test_room_manager_loads_dark_cave_with_npcs(self):
        """RoomManager.load_room creates NPCs from spawn points."""
        import json
        from pathlib import Path
        from unittest.mock import MagicMock

        from server.room.manager import RoomManager
        from server.room.models import Room
        from server.room.objects.npc import load_npc_templates

        load_npc_templates(Path("data/npcs"))

        with open("data/rooms/dark_cave.json") as f:
            data = json.load(f)

        mock_room = MagicMock(spec=Room)
        mock_room.room_key = data["room_key"]
        mock_room.name = data["name"]
        mock_room.width = data["width"]
        mock_room.height = data["height"]
        mock_room.tile_data = data["tile_data"]
        mock_room.exits = data["exits"]
        mock_room.objects = data["objects"]
        mock_room.spawn_points = data["spawn_points"]

        manager = RoomManager()
        room_instance = manager.load_room(mock_room)
        assert room_instance is not None
        # Should have spawned slime NPCs
        assert len(room_instance._npcs) >= 1
