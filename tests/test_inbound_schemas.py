"""Unit tests for WebSocket inbound Pydantic schemas."""

import pytest
from pydantic import ValidationError

from server.net.schemas import (
    ACTION_SCHEMAS,
    ChatMessage,
    FleeMessage,
    HelpMessage,
    InboundMessage,
    InteractMessage,
    InventoryMessage,
    LevelUpMessage,
    LoginMessage,
    LogoutMessage,
    LookMessage,
    MapMessage,
    MoveMessage,
    PartyMessage,
    PartyChatMessage,
    PassTurnMessage,
    PlayCardMessage,
    RegisterMessage,
    StatsMessage,
    TradeMessage,
    UseItemCombatMessage,
    UseItemMessage,
    WhoMessage,
)


# ---------------------------------------------------------------------------
# ACTION_SCHEMAS mapping
# ---------------------------------------------------------------------------


def test_action_schemas_has_21_entries():
    assert len(ACTION_SCHEMAS) == 21


def test_action_schemas_keys():
    expected = {
        "login", "register", "logout", "move", "chat", "party_chat",
        "play_card", "pass_turn", "flee", "use_item_combat",
        "inventory", "use_item", "interact", "look", "who", "stats",
        "help_actions", "map", "level_up", "trade", "party",
    }
    assert set(ACTION_SCHEMAS.keys()) == expected


# ---------------------------------------------------------------------------
# Valid input
# ---------------------------------------------------------------------------


class TestValidInput:
    def test_login(self):
        m = LoginMessage(action="login", username="hero", password="secret")
        assert m.username == "hero"
        assert m.password == "secret"

    def test_register(self):
        m = RegisterMessage(action="register", username="hero", password="secret")
        assert m.username == "hero"

    def test_logout(self):
        m = LogoutMessage(action="logout")
        assert m.action == "logout"

    def test_move(self):
        for d in ("up", "down", "left", "right"):
            m = MoveMessage(action="move", direction=d)
            assert m.direction == d

    def test_chat(self):
        m = ChatMessage(action="chat", message="hello")
        assert m.message == "hello"
        assert m.whisper_to is None

    def test_chat_with_whisper(self):
        m = ChatMessage(action="chat", message="hi", whisper_to="player_1")
        assert m.whisper_to == "player_1"

    def test_party_chat(self):
        m = PartyChatMessage(action="party_chat", message="hello team")
        assert m.message == "hello team"

    def test_play_card(self):
        m = PlayCardMessage(action="play_card", card_key="fireball")
        assert m.card_key == "fireball"

    def test_pass_turn(self):
        m = PassTurnMessage(action="pass_turn")
        assert m.action == "pass_turn"

    def test_flee(self):
        m = FleeMessage(action="flee")
        assert m.action == "flee"

    def test_use_item_combat(self):
        m = UseItemCombatMessage(action="use_item_combat", item_key="potion")
        assert m.item_key == "potion"

    def test_inventory(self):
        m = InventoryMessage(action="inventory")
        assert m.action == "inventory"

    def test_use_item(self):
        m = UseItemMessage(action="use_item", item_key="potion")
        assert m.item_key == "potion"

    def test_interact_with_target_id(self):
        m = InteractMessage(action="interact", target_id="chest_01")
        assert m.target_id == "chest_01"
        assert m.direction == ""

    def test_interact_with_direction(self):
        m = InteractMessage(action="interact", direction="up")
        assert m.direction == "up"
        assert m.target_id == ""

    def test_interact_with_both(self):
        m = InteractMessage(action="interact", target_id="chest_01", direction="up")
        assert m.target_id == "chest_01"
        assert m.direction == "up"

    def test_look(self):
        m = LookMessage(action="look")
        assert m.action == "look"

    def test_who(self):
        m = WhoMessage(action="who")
        assert m.action == "who"

    def test_stats(self):
        m = StatsMessage(action="stats")
        assert m.action == "stats"

    def test_help(self):
        m = HelpMessage(action="help_actions")
        assert m.action == "help_actions"

    def test_map(self):
        m = MapMessage(action="map")
        assert m.action == "map"

    def test_level_up(self):
        m = LevelUpMessage(action="level_up", stats=["strength", "dexterity"])
        assert m.stats == ["strength", "dexterity"]

    def test_trade(self):
        m = TradeMessage(action="trade", args="@hero")
        assert m.args == "@hero"

    def test_trade_no_args(self):
        m = TradeMessage(action="trade")
        assert m.args == ""

    def test_party(self):
        m = PartyMessage(action="party", args="invite hero")
        assert m.args == "invite hero"

    def test_party_no_args(self):
        m = PartyMessage(action="party")
        assert m.args == ""


# ---------------------------------------------------------------------------
# Missing required fields
# ---------------------------------------------------------------------------


class TestMissingFields:
    def test_login_missing_username(self):
        with pytest.raises(ValidationError) as exc_info:
            LoginMessage(action="login", password="secret")
        assert "username" in str(exc_info.value).lower()

    def test_login_missing_password(self):
        with pytest.raises(ValidationError) as exc_info:
            LoginMessage(action="login", username="hero")
        assert "password" in str(exc_info.value).lower()

    def test_move_missing_direction(self):
        with pytest.raises(ValidationError) as exc_info:
            MoveMessage(action="move")
        assert "direction" in str(exc_info.value).lower()

    def test_chat_missing_message(self):
        with pytest.raises(ValidationError) as exc_info:
            ChatMessage(action="chat")
        assert "message" in str(exc_info.value).lower()

    def test_play_card_missing_card_key(self):
        with pytest.raises(ValidationError) as exc_info:
            PlayCardMessage(action="play_card")
        assert "card_key" in str(exc_info.value).lower()

    def test_use_item_missing_item_key(self):
        with pytest.raises(ValidationError) as exc_info:
            UseItemMessage(action="use_item")
        assert "item_key" in str(exc_info.value).lower()

    def test_level_up_missing_stats(self):
        with pytest.raises(ValidationError) as exc_info:
            LevelUpMessage(action="level_up")
        assert "stats" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Empty string rejection (min_length=1)
# ---------------------------------------------------------------------------


class TestEmptyStringRejection:
    def test_login_empty_username(self):
        with pytest.raises(ValidationError):
            LoginMessage(action="login", username="", password="secret")

    def test_login_empty_password(self):
        with pytest.raises(ValidationError):
            LoginMessage(action="login", username="hero", password="")

    def test_move_empty_direction(self):
        with pytest.raises(ValidationError):
            MoveMessage(action="move", direction="")

    def test_chat_empty_message(self):
        with pytest.raises(ValidationError):
            ChatMessage(action="chat", message="")

    def test_play_card_empty_card_key(self):
        with pytest.raises(ValidationError):
            PlayCardMessage(action="play_card", card_key="")

    def test_use_item_empty_item_key(self):
        with pytest.raises(ValidationError):
            UseItemMessage(action="use_item", item_key="")


# ---------------------------------------------------------------------------
# Wrong types
# ---------------------------------------------------------------------------


class TestWrongTypes:
    def test_login_username_not_string(self):
        with pytest.raises(ValidationError):
            LoginMessage(action="login", username=123, password="secret")

    def test_move_direction_not_string(self):
        with pytest.raises(ValidationError):
            MoveMessage(action="move", direction=42)

    def test_level_up_stats_not_list(self):
        with pytest.raises(ValidationError):
            LevelUpMessage(action="level_up", stats="strength")


# ---------------------------------------------------------------------------
# Direction validator
# ---------------------------------------------------------------------------


class TestDirectionValidator:
    def test_invalid_direction(self):
        with pytest.raises(ValidationError) as exc_info:
            MoveMessage(action="move", direction="diagonal")
        assert "Invalid direction" in str(exc_info.value)

    def test_ascend_is_not_valid_direction(self):
        with pytest.raises(ValidationError):
            MoveMessage(action="move", direction="ascend")

    def test_descend_is_not_valid_direction(self):
        with pytest.raises(ValidationError):
            MoveMessage(action="move", direction="descend")


# ---------------------------------------------------------------------------
# InteractMessage model_validator
# ---------------------------------------------------------------------------


class TestInteractValidator:
    def test_rejects_both_empty(self):
        with pytest.raises(ValidationError) as exc_info:
            InteractMessage(action="interact")
        assert "target_id or direction" in str(exc_info.value).lower()

    def test_rejects_explicit_both_empty(self):
        with pytest.raises(ValidationError):
            InteractMessage(action="interact", target_id="", direction="")


# ---------------------------------------------------------------------------
# model_dump output
# ---------------------------------------------------------------------------


class TestModelDump:
    def test_login_dump(self):
        m = LoginMessage(action="login", username="hero", password="secret")
        d = m.model_dump()
        assert d == {"action": "login", "username": "hero", "password": "secret"}

    def test_chat_dump_no_whisper(self):
        m = ChatMessage(action="chat", message="hi")
        d = m.model_dump()
        assert d["whisper_to"] is None

    def test_interact_dump_with_target(self):
        m = InteractMessage(action="interact", target_id="chest_01")
        d = m.model_dump()
        assert d["target_id"] == "chest_01"
        assert d["direction"] == ""

    def test_trade_dump_no_args(self):
        m = TradeMessage(action="trade")
        d = m.model_dump()
        assert d["args"] == ""

    def test_extra_fields_stripped(self):
        m = LoginMessage(action="login", username="hero", password="secret", evil="payload")
        d = m.model_dump()
        assert "evil" not in d
