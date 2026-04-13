"""Unit tests for WebSocket outbound Pydantic schemas."""

import pytest
from unittest.mock import AsyncMock

from server.net.outbound_schemas import (
    AnnouncementMessage,
    CombatEndMessage,
    CombatFledMessage,
    CombatStartMessage,
    CombatTurnMessage,
    CombatUpdateMessage,
    EntityEnteredMessage,
    EntityLeftMessage,
    EntityMovedMessage,
    EntityPayload,
    ErrorMessage,
    HelpResultMessage,
    InteractResultMessage,
    InventoryItemPayload,
    InventoryListMessage,
    ItemUsedMessage,
    KickedMessage,
    LevelUpAvailableMessage,
    LevelUpCompleteMessage,
    LoggedOutMessage,
    LoginSuccessMessage,
    LookResultMessage,
    MapDataMessage,
    NearbyObjectsMessage,
    OutboundChatMessage,
    OutboundPartyChatMessage,
    PartyInviteMessage,
    PartyInviteResponseMessage,
    PartyStatusMessage,
    PartyUpdateMessage,
    PlayerStatsPayload,
    RespawnMessage,
    RoomStateMessage,
    SeqStatusMessage,
    ServerShutdownMessage,
    StatsResultMessage,
    StatsResultPayload,
    StatsUpdateMessage,
    TileChangedMessage,
    TradeRequestMessage,
    TradeResultMessage,
    TradeUpdateMessage,
    WhoResultMessage,
    XpGainedMessage,
    send_typed,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sample_stats():
    return PlayerStatsPayload(
        hp=100, max_hp=100, energy=25, max_energy=25,
        attack=10, xp=0, level=1,
        xp_for_next_level=100, xp_for_current_level=0,
        strength=10, dexterity=10, constitution=10,
        intelligence=10, wisdom=10, charisma=10,
    )


def _sample_combat_state():
    return {
        "instance_id": "combat_1",
        "current_turn": "player_1",
        "participants": [{"entity_id": "player_1", "hp": 80, "max_hp": 100,
                          "shield": 0, "energy": 25, "max_energy": 25, "energy_regen": 2}],
        "mob": {"name": "Goblin", "hp": 50, "max_hp": 50},
        "hands": {"player_1": [{"card_key": "slash", "name": "Slash",
                                "cost": 1, "card_type": "physical",
                                "effects": [], "description": "Basic attack"}]},
    }


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class TestAuth:
    def test_login_success(self):
        m = LoginSuccessMessage(
            protocol_version="1.0",
            player_id=1, entity_id="player_1", username="hero",
            stats=_sample_stats(),
        )
        d = m.model_dump()
        assert d["type"] == "login_success"
        assert d["player_id"] == 1
        assert d["stats"]["hp"] == 100

    def test_logged_out(self):
        m = LoggedOutMessage()
        assert m.model_dump() == {"type": "logged_out", "request_id": None}

    def test_kicked(self):
        m = KickedMessage(reason="Logged in from another location")
        assert m.model_dump()["reason"] == "Logged in from another location"


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------


class TestSystem:
    def test_error(self):
        m = ErrorMessage(detail="Something went wrong")
        assert m.model_dump() == {"type": "error", "code": None, "detail": "Something went wrong", "request_id": None}

    def test_server_shutdown(self):
        m = ServerShutdownMessage(reason="Maintenance")
        assert m.model_dump()["type"] == "server_shutdown"

    def test_announcement(self):
        m = AnnouncementMessage(message="A rare creature appeared!")
        assert m.model_dump()["message"] == "A rare creature appeared!"

    def test_respawn(self):
        m = RespawnMessage(room_key="town_square", x=5, y=5, hp=100, max_hp=100, energy=25, max_energy=25)
        d = m.model_dump()
        assert d["room_key"] == "town_square"
        assert d["hp"] == 100
        assert d["energy"] == 25


# ---------------------------------------------------------------------------
# Room
# ---------------------------------------------------------------------------


class TestRoom:
    def test_room_state(self):
        m = RoomStateMessage(
            room_key="town_square", name="Town Square", width=100, height=100,
            tiles=[[0, 0], [0, 0]],
            entities=[{"id": "player_1", "name": "hero", "x": 5, "y": 5, "level": 1}],
            npcs=[{"id": "npc_1", "npc_key": "goblin", "name": "Goblin", "x": 10, "y": 10, "is_alive": True}],
            exits=[{"direction": "right", "target_room": "dark_cave"}],
            objects=[],
        )
        d = m.model_dump()
        assert d["type"] == "room_state"
        assert d["width"] == 100

    def test_entity_entered_player_with_level(self):
        m = EntityEnteredMessage(entity=EntityPayload(id="player_1", name="hero", x=5, y=5, level=3))
        d = m.model_dump(exclude_none=True)
        assert d["entity"]["level"] == 3

    def test_entity_entered_player_without_level(self):
        m = EntityEnteredMessage(entity=EntityPayload(id="player_1", name="hero", x=5, y=5))
        d = m.model_dump(exclude_none=True)
        assert "level" not in d["entity"]

    def test_entity_entered_npc(self):
        m = EntityEnteredMessage(entity=EntityPayload(
            id="npc_1", name="Goblin", x=10, y=10, npc_key="goblin", is_alive=True,
        ))
        d = m.model_dump(exclude_none=True)
        assert d["entity"]["npc_key"] == "goblin"
        assert "level" not in d["entity"]

    def test_entity_left(self):
        m = EntityLeftMessage(entity_id="player_1")
        assert m.model_dump()["entity_id"] == "player_1"

    def test_entity_moved(self):
        m = EntityMovedMessage(entity_id="player_1", x=6, y=5)
        d = m.model_dump()
        assert d["x"] == 6

    def test_nearby_objects(self):
        m = NearbyObjectsMessage(objects=[{"id": "chest_01", "type": "chest", "direction": "up"}])
        assert len(m.model_dump()["objects"]) == 1

    def test_tile_changed(self):
        m = TileChangedMessage(x=3, y=4, tile_type=0)
        d = m.model_dump()
        assert d["tile_type"] == 0


# ---------------------------------------------------------------------------
# Combat
# ---------------------------------------------------------------------------


class TestCombat:
    def test_combat_start(self):
        m = CombatStartMessage(**_sample_combat_state())
        d = m.model_dump()
        assert d["type"] == "combat_start"
        assert d["instance_id"] == "combat_1"

    def test_combat_turn(self):
        m = CombatTurnMessage(result={"action": "play_card"}, **_sample_combat_state())
        d = m.model_dump()
        assert d["type"] == "combat_turn"
        assert d["result"]["action"] == "play_card"

    def test_combat_end_victory(self):
        m = CombatEndMessage(
            victory=True, rewards={"xp": 50},
            loot=[{"item_key": "potion", "name": "Health Potion"}],
            defeated_npc_id="npc_1",
        )
        d = m.model_dump(exclude_none=True)
        assert d["victory"] is True
        assert d["defeated_npc_id"] == "npc_1"

    def test_combat_end_defeat_no_optional(self):
        m = CombatEndMessage(victory=False, rewards={"xp": 0})
        d = m.model_dump(exclude_none=True)
        assert "loot" not in d
        assert "defeated_npc_id" not in d

    def test_combat_fled(self):
        m = CombatFledMessage()
        assert m.model_dump() == {"type": "combat_fled", "request_id": None}

    def test_combat_update(self):
        m = CombatUpdateMessage(**_sample_combat_state())
        assert m.model_dump()["type"] == "combat_update"


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


class TestChat:
    def test_chat_message(self):
        m = OutboundChatMessage(sender="hero", message="hello", whisper=False)
        d = m.model_dump()
        assert d["sender"] == "hero"
        assert d["whisper"] is False

    def test_party_chat_from_alias(self):
        m = OutboundPartyChatMessage(from_="hero", message="team msg")
        d = m.model_dump(by_alias=True)
        assert "from" in d
        assert d["from"] == "hero"
        assert "from_" not in d

    def test_party_chat_exclude_none_by_alias(self):
        m = OutboundPartyChatMessage(from_="hero", message="hi")
        d = m.model_dump(exclude_none=True, by_alias=True)
        assert d == {"type": "party_chat", "from": "hero", "message": "hi"}


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------


class TestInventory:
    def test_inventory_list(self):
        m = InventoryListMessage(items=[
            InventoryItemPayload(item_key="potion", name="Health Potion",
                                 category="consumable", quantity=3, description="Heals 20 HP"),
        ])
        d = m.model_dump()
        assert len(d["items"]) == 1
        assert d["items"][0]["item_key"] == "potion"

    def test_item_used(self):
        m = ItemUsedMessage(item_key="potion", item_name="Health Potion",
                            effect_results=[{"type": "heal", "value": 20, "target_hp": 100}])
        d = m.model_dump()
        assert d["item_name"] == "Health Potion"


# ---------------------------------------------------------------------------
# Interact
# ---------------------------------------------------------------------------


class TestInteract:
    def test_interact_result(self):
        m = InteractResultMessage(object_id="chest_01",
                                  result={"status": "looted", "items": [{"item_key": "potion", "quantity": 1}]})
        d = m.model_dump()
        assert d["object_id"] == "chest_01"
        assert d["result"]["status"] == "looted"


# ---------------------------------------------------------------------------
# Trade
# ---------------------------------------------------------------------------


class TestTrade:
    def test_trade_request(self):
        m = TradeRequestMessage(from_player="hero", from_entity_id="player_1")
        assert m.model_dump()["from_player"] == "hero"

    def test_trade_update(self):
        m = TradeUpdateMessage(
            player_a="hero", player_b="villain",
            offers_a={"potion": 1}, offers_b={},
            ready_a=False, ready_b=False, state="negotiating",
        )
        d = m.model_dump()
        assert d["state"] == "negotiating"

    def test_trade_result_success(self):
        m = TradeResultMessage(status="success", reason="Trade completed",
                               inventory=[InventoryItemPayload(
                                   item_key="potion", name="Health Potion",
                                   category="consumable", quantity=2, description="Heals")])
        d = m.model_dump(exclude_none=True)
        assert d["status"] == "success"
        assert "inventory" in d

    def test_trade_result_no_inventory(self):
        m = TradeResultMessage(status="rejected", reason="Player rejected trade")
        d = m.model_dump(exclude_none=True)
        assert "inventory" not in d


# ---------------------------------------------------------------------------
# Party
# ---------------------------------------------------------------------------


class TestParty:
    def test_party_invite(self):
        m = PartyInviteMessage(from_player="hero", from_entity_id="player_1")
        assert m.model_dump()["from_player"] == "hero"

    def test_party_invite_response_with_target(self):
        m = PartyInviteResponseMessage(status="sent", target="player_2")
        d = m.model_dump(exclude_none=True)
        assert d["target"] == "player_2"

    def test_party_invite_response_without_target(self):
        m = PartyInviteResponseMessage(status="rejected")
        d = m.model_dump(exclude_none=True)
        assert "target" not in d

    def test_party_update(self):
        m = PartyUpdateMessage(action="member_joined", entity_id="player_2",
                               members=["player_1", "player_2"], leader="player_1")
        d = m.model_dump(exclude_none=True)
        assert d["action"] == "member_joined"

    def test_party_status_in_party(self):
        m = PartyStatusMessage(
            party_id="party_abc",
            members=[{"name": "hero", "entity_id": "player_1", "is_leader": True, "room": "town_square"}],
        )
        d = m.model_dump(exclude_none=True)
        assert d["party_id"] == "party_abc"

    def test_party_status_pending_invite(self):
        m = PartyStatusMessage(pending_invite=True, from_player="hero")
        d = m.model_dump(exclude_none=True)
        assert d["pending_invite"] is True
        assert "party_id" not in d


# ---------------------------------------------------------------------------
# XP / Level-up
# ---------------------------------------------------------------------------


class TestXpLevel:
    def test_xp_gained(self):
        m = XpGainedMessage(amount=50, source="combat", detail="Defeated Goblin", new_total_xp=150,
                            xp_for_next_level=1000, xp_for_current_level=0)
        d = m.model_dump()
        assert d["amount"] == 50
        assert d["xp_for_next_level"] == 1000
        assert d["xp_for_current_level"] == 0

    def test_level_up_available(self):
        m = LevelUpAvailableMessage(
            new_level=2, choose_stats=3,
            current_stats={"strength": 10, "dexterity": 10, "constitution": 10,
                           "intelligence": 10, "wisdom": 10, "charisma": 10},
            stat_cap=20, xp_for_next_level=200, xp_for_current_level=100,
            stat_effects={"strength": "+1 physical damage per point", "dexterity": "+1 dodge",
                          "constitution": "+5 max HP", "intelligence": "+1 magic damage",
                          "wisdom": "+1 healing", "charisma": "+5% XP"},
        )
        d = m.model_dump()
        assert d["new_level"] == 2
        assert d["choose_stats"] == 3

    def test_level_up_complete(self):
        m = LevelUpCompleteMessage(level=2, stat_changes={"strength": 1}, new_max_hp=105, new_hp=105,
                                   xp_for_next_level=2000, xp_for_current_level=1000)
        d = m.model_dump(exclude_none=True)
        assert "skipped_at_cap" not in d
        assert d["xp_for_next_level"] == 2000
        assert d["xp_for_current_level"] == 1000

    def test_level_up_complete_with_skipped(self):
        m = LevelUpCompleteMessage(level=2, stat_changes={"strength": 1}, new_max_hp=105, new_hp=105,
                                   xp_for_next_level=2000, xp_for_current_level=1000,
                                   skipped_at_cap=["dexterity"])
        d = m.model_dump(exclude_none=True)
        assert d["skipped_at_cap"] == ["dexterity"]


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


class TestQuery:
    def test_look_result(self):
        m = LookResultMessage(
            objects=[{"id": "chest_01", "type": "chest", "direction": "up"}],
            npcs=[{"name": "Goblin", "alive": True, "direction": "right"}],
            players=[{"name": "hero", "direction": "left"}],
        )
        d = m.model_dump()
        assert len(d["objects"]) == 1

    def test_who_result(self):
        m = WhoResultMessage(room="town_square", players=[{"name": "hero", "x": 5, "y": 5}])
        d = m.model_dump()
        assert d["room"] == "town_square"

    def test_stats_result(self):
        m = StatsResultMessage(stats=StatsResultPayload(
            hp=100, max_hp=100, energy=25, max_energy=25,
            attack=10, xp=50, xp_next=100,
            xp_for_next_level=100, xp_for_current_level=0, level=1,
            strength=10, dexterity=10, constitution=10,
            intelligence=10, wisdom=10, charisma=10,
        ))
        d = m.model_dump()
        assert d["stats"]["xp_next"] == 100
        assert d["stats"]["xp_for_next_level"] == 100

    def test_help_result(self):
        m = HelpResultMessage(categories={"Movement": ["move"], "Combat": ["play_card"]})
        d = m.model_dump()
        assert "Movement" in d["categories"]

    def test_map_data(self):
        m = MapDataMessage(
            rooms=[{"room_key": "town_square", "name": "Town Square"}],
            connections=[{"from_room": "town_square", "to_room": "Dark Cave", "direction": "right"}],
        )
        d = m.model_dump()
        assert len(d["rooms"]) == 1


# ---------------------------------------------------------------------------
# JSON Schema generation
# ---------------------------------------------------------------------------


class TestJsonSchema:
    """Verify model_json_schema() produces valid output for all 38 types."""

    ALL_SCHEMAS = [
        ErrorMessage, LoginSuccessMessage, LoggedOutMessage, KickedMessage,
        ServerShutdownMessage, AnnouncementMessage, RespawnMessage,
        StatsUpdateMessage,
        RoomStateMessage, EntityEnteredMessage, EntityLeftMessage,
        EntityMovedMessage, NearbyObjectsMessage, TileChangedMessage,
        CombatStartMessage, CombatTurnMessage, CombatEndMessage,
        CombatFledMessage, CombatUpdateMessage,
        OutboundChatMessage, OutboundPartyChatMessage,
        InventoryListMessage, ItemUsedMessage, InteractResultMessage,
        TradeRequestMessage, TradeUpdateMessage, TradeResultMessage,
        PartyInviteMessage, PartyInviteResponseMessage, PartyUpdateMessage,
        PartyStatusMessage, XpGainedMessage, LevelUpAvailableMessage,
        LevelUpCompleteMessage, LookResultMessage, WhoResultMessage,
        StatsResultMessage, HelpResultMessage, MapDataMessage,
        SeqStatusMessage,
    ]

    def test_schema_count(self):
        assert len(self.ALL_SCHEMAS) == 40

    @pytest.mark.parametrize("schema_cls", ALL_SCHEMAS, ids=lambda c: c.__name__)
    def test_json_schema_valid(self, schema_cls):
        schema = schema_cls.model_json_schema()
        assert isinstance(schema, dict)
        assert "properties" in schema


# ---------------------------------------------------------------------------
# send_typed utility
# ---------------------------------------------------------------------------


class TestSendTyped:
    @pytest.mark.asyncio
    async def test_send_typed_basic(self):
        ws = AsyncMock()
        msg = ErrorMessage(detail="test error")
        await send_typed(ws, msg)
        ws.send_json.assert_called_once_with({"type": "error", "detail": "test error"})

    @pytest.mark.asyncio
    async def test_send_typed_excludes_none(self):
        ws = AsyncMock()
        msg = CombatEndMessage(victory=True, rewards={"xp": 50})
        await send_typed(ws, msg)
        call_data = ws.send_json.call_args[0][0]
        assert "loot" not in call_data
        assert "defeated_npc_id" not in call_data

    @pytest.mark.asyncio
    async def test_send_typed_by_alias(self):
        ws = AsyncMock()
        msg = OutboundPartyChatMessage(from_="hero", message="hi team")
        await send_typed(ws, msg)
        call_data = ws.send_json.call_args[0][0]
        assert "from" in call_data
        assert call_data["from"] == "hero"
        assert "from_" not in call_data
