"""WebSocket integration tests — full gameplay loop (Story 6-6).

Tests the complete player journey through register → login → move → interact →
combat → items → chat → disconnect using the real handler pipeline.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from server.core.database import Base
from server.items.item_def import ItemDef
from server.net.connection_manager import ConnectionManager
from server.room.manager import RoomManager
from server.room.npc import NpcEntity
from server.room.room import RoomInstance


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def async_engine():
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
def test_session_factory(async_engine):
    return async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )


@pytest.fixture
def room_manager():
    """RoomManager with town_square (with chest + NPC) and cave."""
    mgr = RoomManager()

    tiles = [[0] * 10 for _ in range(10)]
    tiles[5][9] = 2  # EXIT at (9, 5)

    room = RoomInstance(
        room_key="town_square", name="Town Square", width=10, height=10,
        tile_data=tiles,
        exits=[{"x": 9, "y": 5, "target_room": "cave", "entry_x": 1, "entry_y": 5}],
        objects=[{
            "id": "chest_1", "type": "chest", "category": "interactive",
            "x": 5, "y": 5, "state_scope": "player", "blocking": True,
            "config": {"loot_table": "common_chest"},
        }],
        spawn_points=[{"type": "player", "x": 0, "y": 0}],
    )
    mgr._rooms["town_square"] = room

    npc = NpcEntity(
        id="npc_slime_1", npc_key="slime", name="Slime",
        x=0, y=5, behavior_type="hostile",
        stats={"hp": 1, "max_hp": 1, "attack": 1},
    )
    room.add_npc(npc)

    cave_tiles = [[0] * 10 for _ in range(10)]
    cave = RoomInstance(
        room_key="cave", name="Dark Cave", width=10, height=10,
        tile_data=cave_tiles,
        exits=[{"x": 0, "y": 5, "target_room": "town_square", "entry_x": 8, "entry_y": 5}],
        spawn_points=[{"type": "player", "x": 1, "y": 5}],
    )
    mgr._rooms["cave"] = cave
    return mgr


@pytest.fixture
def connection_manager():
    return ConnectionManager()


@pytest.fixture
def client(test_session_factory, room_manager, connection_manager):
    """TestClient following same pattern as test_login.py — patch handler sessions only."""
    from server.app import app, game

    original_rm = game.room_manager
    original_cm = game.connection_manager
    original_sf = game.session_factory

    with patch("server.net.handlers.movement.player_repo") as mock_player_repo, \
         patch("server.net.handlers.combat.player_repo") as mock_combat_player_repo, \
         patch("server.net.handlers.inventory.player_repo") as mock_inv_player_repo, \
         patch("server.app.player_repo") as mock_app_player_repo:
        mock_player_repo.update_position = AsyncMock()
        mock_app_player_repo.update_position = AsyncMock()
        mock_app_player_repo.update_stats = AsyncMock()
        mock_app_player_repo.update_inventory = AsyncMock()
        mock_combat_player_repo.update_stats = AsyncMock()
        mock_combat_player_repo.update_inventory = AsyncMock()
        mock_inv_player_repo.update_stats = AsyncMock()
        mock_inv_player_repo.update_inventory = AsyncMock()
        with TestClient(app) as c:
            # Swap managers and session factory AFTER startup
            game.room_manager = room_manager
            game.connection_manager = connection_manager
            game.session_factory = test_session_factory
            yield c

    game.room_manager = original_rm
    game.connection_manager = original_cm
    game.session_factory = original_sf
    game.player_manager.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register(client, username="hero", password="secret123"):
    with client.websocket_connect("/ws/game") as ws:
        ws.send_json({"action": "register", "username": username, "password": password})
        return ws.receive_json()


def _login(ws, username="hero", password="secret123"):
    ws.send_json({"action": "login", "username": username, "password": password})
    login_resp = ws.receive_json()
    room_resp = ws.receive_json()
    return login_resp, room_resp


def _reset_npc(room_manager, hp=1, attack=1):
    npc = room_manager._rooms["town_square"].get_npc("npc_slime_1")
    if npc:
        npc.is_alive = True
        npc.x = 0
        npc.y = 5
        npc.stats = {"hp": hp, "max_hp": hp, "attack": attack}


# ---------------------------------------------------------------------------
# Test 1: Register and Login
# ---------------------------------------------------------------------------


class TestRegisterAndLogin:
    def test_register_returns_success(self, client):
        resp = _register(client)
        assert resp["type"] == "login_success"
        assert "player_id" in resp

    def test_login_after_register(self, client):
        _register(client)
        with client.websocket_connect("/ws/game") as ws:
            login_resp, room_resp = _login(ws)
            assert login_resp["type"] == "login_success"
            assert login_resp["username"] == "hero"
            assert room_resp["type"] == "room_state"
            assert room_resp["room_key"] == "town_square"
            assert "entities" in room_resp
            assert "tiles" in room_resp

    def test_login_places_entity_in_room(self, client):
        _register(client)
        with client.websocket_connect("/ws/game") as ws:
            _, room_resp = _login(ws)
            names = [e["name"] for e in room_resp["entities"]]
            assert "hero" in names


# ---------------------------------------------------------------------------
# Test 2: Movement
# ---------------------------------------------------------------------------


class TestMovement:
    def test_valid_move(self, client):
        _register(client)
        with client.websocket_connect("/ws/game") as ws:
            _login(ws)
            ws.send_json({"action": "move", "direction": "right"})
            resp = ws.receive_json()
            assert resp["type"] == "entity_moved"
            assert resp["x"] == 1

    def test_move_out_of_bounds(self, client):
        _register(client)
        with client.websocket_connect("/ws/game") as ws:
            _login(ws)
            ws.send_json({"action": "move", "direction": "left"})
            resp = ws.receive_json()
            assert resp["type"] == "error"

    def test_sequential_moves(self, client):
        _register(client)
        with client.websocket_connect("/ws/game") as ws:
            _login(ws)
            ws.send_json({"action": "move", "direction": "right"})
            r1 = ws.receive_json()
            ws.send_json({"action": "move", "direction": "down"})
            r2 = ws.receive_json()
            assert r1["x"] == 1 and r1["y"] == 0
            assert r2["x"] == 1 and r2["y"] == 1


# ---------------------------------------------------------------------------
# Test 3: Chest interaction
# ---------------------------------------------------------------------------


class TestChestInteraction:
    def _move_to_chest(self, ws):
        """Move player from spawn (0,0) to (4,5), adjacent to chest at (5,5)."""
        for _ in range(4):
            ws.send_json({"action": "move", "direction": "right"})
            ws.receive_json()
        for _ in range(5):
            ws.send_json({"action": "move", "direction": "down"})
            ws.receive_json()

    def _drain_until(self, ws, msg_type):
        """Consume messages until we find the expected type."""
        for _ in range(10):
            msg = ws.receive_json()
            if msg.get("type") == msg_type:
                return msg
        raise AssertionError(f"Never received message type '{msg_type}'")

    def test_loot_chest(self, client):
        _register(client)
        with client.websocket_connect("/ws/game") as ws:
            _login(ws)
            self._move_to_chest(ws)
            ws.send_json({"action": "interact", "target_id": "chest_1"})
            resp = self._drain_until(ws, "interact_result")
            assert resp["result"]["status"] == "looted"
            assert len(resp["result"]["items"]) > 0

    def test_chest_already_looted(self, client):
        _register(client)
        with client.websocket_connect("/ws/game") as ws:
            _login(ws)
            self._move_to_chest(ws)
            ws.send_json({"action": "interact", "target_id": "chest_1"})
            self._drain_until(ws, "interact_result")  # first loot (+ xp_gained)
            ws.send_json({"action": "interact", "target_id": "chest_1"})
            resp = self._drain_until(ws, "interact_result")
            assert resp["result"]["status"] == "already_looted"

    def test_interact_nonexistent_object(self, client):
        _register(client)
        with client.websocket_connect("/ws/game") as ws:
            _login(ws)
            ws.send_json({"action": "interact", "target_id": "nope"})
            resp = ws.receive_json()
            assert resp["type"] == "error"


# ---------------------------------------------------------------------------
# Test 4: Room transition via exit
# ---------------------------------------------------------------------------


class TestRoomTransition:
    def test_exit_to_cave(self, client):
        _register(client)
        with client.websocket_connect("/ws/game") as ws:
            _login(ws)
            for _ in range(9):
                ws.send_json({"action": "move", "direction": "right"})
                ws.receive_json()
            for _ in range(5):
                ws.send_json({"action": "move", "direction": "down"})
                resp = ws.receive_json()
            # Last move hits exit → room_state for cave
            assert resp["type"] == "room_state"
            assert resp["room_key"] == "cave"


# ---------------------------------------------------------------------------
# Test 5: Mob encounter → combat
# ---------------------------------------------------------------------------


class TestMobEncounter:
    def test_encounter_starts_combat(self, client, room_manager):
        _reset_npc(room_manager, hp=1, attack=1)
        _register(client)
        with client.websocket_connect("/ws/game") as ws:
            _login(ws)
            for _ in range(5):
                ws.send_json({"action": "move", "direction": "down"})
                resp = ws.receive_json()
                assert resp["type"] == "entity_moved"
            combat = ws.receive_json()
            assert combat["type"] == "combat_start"
            assert combat["mob"]["name"] == "Slime"
            assert "hands" in combat


# ---------------------------------------------------------------------------
# Test 6: Combat — play card, victory, flee
# ---------------------------------------------------------------------------


class TestCombatFlow:
    def test_play_card_kills_mob(self, client, room_manager):
        _reset_npc(room_manager, hp=1, attack=1)
        _register(client)
        with client.websocket_connect("/ws/game") as ws:
            _login(ws)
            for _ in range(5):
                ws.send_json({"action": "move", "direction": "down"})
                ws.receive_json()
            combat = ws.receive_json()
            assert combat["type"] == "combat_start"

            eid = combat["current_turn"]
            card_key = combat["hands"][eid][0]["card_key"]
            ws.send_json({"action": "play_card", "card_key": card_key})
            turn = ws.receive_json()
            assert turn["type"] == "combat_turn"

            # grant_xp sends xp_gained before combat_end
            xp_msg = ws.receive_json()
            assert xp_msg["type"] == "xp_gained"
            assert xp_msg["source"] == "combat"
            assert xp_msg["amount"] > 0

            end = ws.receive_json()
            assert end["type"] == "combat_end"
            assert end["victory"] is True
            assert end["rewards"]["xp"] > 0  # XP based on hit_dice formula

            # Victory triggers room_state rebroadcast (NPC death state)
            room_update = ws.receive_json()
            assert room_update["type"] == "room_state"

    def test_flee_combat(self, client, room_manager):
        _reset_npc(room_manager, hp=999, attack=1)
        _register(client, "runner", "pass1234")
        with client.websocket_connect("/ws/game") as ws:
            _login(ws, "runner", "pass1234")
            for _ in range(5):
                ws.send_json({"action": "move", "direction": "down"})
                ws.receive_json()
            combat = ws.receive_json()
            assert combat["type"] == "combat_start"
            ws.send_json({"action": "flee"})
            resp = ws.receive_json()
            assert resp["type"] == "combat_fled"

    def test_cannot_move_in_combat(self, client, room_manager):
        _reset_npc(room_manager, hp=999, attack=1)
        _register(client, "stuck", "pass1234")
        with client.websocket_connect("/ws/game") as ws:
            _login(ws, "stuck", "pass1234")
            for _ in range(5):
                ws.send_json({"action": "move", "direction": "down"})
                ws.receive_json()
            ws.receive_json()  # combat_start
            ws.send_json({"action": "move", "direction": "left"})
            resp = ws.receive_json()
            assert resp["type"] == "error"
            assert "combat" in resp["detail"].lower()


# ---------------------------------------------------------------------------
# Test 7: Inventory and item usage
# ---------------------------------------------------------------------------


class TestItemUsage:
    def test_use_healing_potion(self, client):
        _register(client)
        from server.app import game

        with client.websocket_connect("/ws/game") as ws:
            _login(ws)
            eid = [k for k in game.player_manager.all_entity_ids()
                   if game.player_manager.get_session(k).entity.name == "hero"][0]
            info = game.player_manager.get_session(eid)
            potion = ItemDef(
                item_key="healing_potion", name="Healing Potion",
                category="consumable", charges=3,
                effects=[{"type": "heal", "value": 25}],
                usable_in_combat=True, usable_outside_combat=True,
            )
            info.inventory.add_item(potion, quantity=2)
            info.entity.stats["hp"] = 50
            info.entity.stats["max_hp"] = 100

            ws.send_json({"action": "use_item", "item_key": "healing_potion"})
            resp = ws.receive_json()
            assert resp["type"] == "item_used"
            assert resp["item_key"] == "healing_potion"

    def test_inventory_list(self, client):
        _register(client)
        from server.app import game

        with client.websocket_connect("/ws/game") as ws:
            _login(ws)
            eid = [k for k in game.player_manager.all_entity_ids()
                   if game.player_manager.get_session(k).entity.name == "hero"][0]
            inv = game.player_manager.get_session(eid).inventory
            inv.add_item(ItemDef(
                item_key="iron_shard", name="Iron Shard",
                category="material", charges=0, effects=[],
            ), quantity=3)

            ws.send_json({"action": "inventory"})
            resp = ws.receive_json()
            assert resp["type"] == "inventory"
            assert resp["items"][0]["item_key"] == "iron_shard"
            assert resp["items"][0]["quantity"] == 3

    def test_use_item_not_in_inventory(self, client):
        _register(client)
        with client.websocket_connect("/ws/game") as ws:
            _login(ws)
            ws.send_json({"action": "use_item", "item_key": "nonexistent"})
            resp = ws.receive_json()
            assert resp["type"] == "error"


# ---------------------------------------------------------------------------
# Test 8: Chat
# ---------------------------------------------------------------------------


class TestChat:
    def test_room_broadcast(self, client):
        _register(client, "alice", "pass111")
        _register(client, "bob", "pass2222")

        with client.websocket_connect("/ws/game") as ws_a:
            _login(ws_a, "alice", "pass111")
            with client.websocket_connect("/ws/game") as ws_b:
                _login(ws_b, "bob", "pass2222")
                ws_a.receive_json()  # entity_entered for bob

                ws_a.send_json({"action": "chat", "message": "Hello!"})
                a_msg = ws_a.receive_json()
                b_msg = ws_b.receive_json()

                assert a_msg["type"] == "chat"
                assert a_msg["sender"] == "alice"
                assert a_msg["message"] == "Hello!"
                assert b_msg["type"] == "chat"


# ---------------------------------------------------------------------------
# Test 9: Disconnect
# ---------------------------------------------------------------------------


class TestDisconnect:
    def test_disconnect_notifies_others(self, client):
        _register(client, "dan", "pass1111")
        _register(client, "eve", "pass2222")

        with client.websocket_connect("/ws/game") as ws_a, \
             client.websocket_connect("/ws/game") as ws_b:
            _login(ws_a, "dan", "pass1111")
            _login(ws_b, "eve", "pass2222")
            ws_a.receive_json()  # entity_entered
            ws_b.close()
            left = ws_a.receive_json()
            assert left["type"] == "entity_left"

    def test_unauthenticated_disconnect(self, client):
        with client.websocket_connect("/ws/game") as ws:
            pass


# ---------------------------------------------------------------------------
# Test 10: Error cases
# ---------------------------------------------------------------------------


class TestErrorCases:
    def test_move_before_login(self, client):
        with client.websocket_connect("/ws/game") as ws:
            ws.send_json({"action": "move", "direction": "right"})
            resp = ws.receive_json()
            assert resp["type"] == "error"

    def test_chat_before_login(self, client):
        with client.websocket_connect("/ws/game") as ws:
            ws.send_json({"action": "chat", "message": "hello"})
            resp = ws.receive_json()
            assert resp["type"] == "error"

    def test_play_card_not_in_combat(self, client):
        _register(client, "combatless", "pass1234")
        with client.websocket_connect("/ws/game") as ws:
            _login(ws, "combatless", "pass1234")
            ws.send_json({"action": "play_card", "card_key": "x"})
            resp = ws.receive_json()
            assert resp["type"] == "error"

    def test_invalid_json(self, client):
        with client.websocket_connect("/ws/game") as ws:
            ws.send_text("not json {{{")
            resp = ws.receive_json()
            assert resp["type"] == "error"
            assert "json" in resp["detail"].lower()

    def test_missing_action(self, client):
        with client.websocket_connect("/ws/game") as ws:
            ws.send_json({"foo": "bar"})
            resp = ws.receive_json()
            assert resp["type"] == "error"
            assert "action" in resp["detail"].lower()
