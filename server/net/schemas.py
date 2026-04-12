"""Pydantic schemas for all 21 WebSocket inbound (client-to-server) actions."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator


class InboundMessage(BaseModel):
    """Base class for all inbound WebSocket messages."""

    action: str
    request_id: str | None = None


# --- Auth ---


class LoginMessage(InboundMessage):
    action: str = "login"
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class RegisterMessage(InboundMessage):
    action: str = "register"
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class LogoutMessage(InboundMessage):
    action: str = "logout"


# --- Movement ---


class MoveMessage(InboundMessage):
    action: str = "move"
    direction: str = Field(min_length=1)

    @field_validator("direction")
    @classmethod
    def validate_direction(cls, v: str) -> str:
        if v not in ("up", "down", "left", "right"):
            raise ValueError(f"Invalid direction: {v}")
        return v


# --- Chat ---


class ChatMessage(InboundMessage):
    action: str = "chat"
    message: str = Field(min_length=1)
    whisper_to: str | None = None


class PartyChatMessage(InboundMessage):
    action: str = "party_chat"
    message: str = Field(min_length=1)


# --- Combat ---


class PlayCardMessage(InboundMessage):
    action: str = "play_card"
    card_key: str = Field(min_length=1)


class PassTurnMessage(InboundMessage):
    action: str = "pass_turn"


class FleeMessage(InboundMessage):
    action: str = "flee"


class UseItemCombatMessage(InboundMessage):
    action: str = "use_item_combat"
    item_key: str = Field(min_length=1)


# --- Inventory ---


class InventoryMessage(InboundMessage):
    action: str = "inventory"


class UseItemMessage(InboundMessage):
    action: str = "use_item"
    item_key: str = Field(min_length=1)


# --- Interact ---


class InteractMessage(InboundMessage):
    action: str = "interact"
    target_id: str = ""
    direction: str = ""

    @model_validator(mode="after")
    def require_target_or_direction(self) -> InteractMessage:
        if not self.target_id and not self.direction:
            raise ValueError("Missing target_id or direction")
        return self


# --- Query ---


class LookMessage(InboundMessage):
    action: str = "look"


class WhoMessage(InboundMessage):
    action: str = "who"


class StatsMessage(InboundMessage):
    action: str = "stats"


class HelpMessage(InboundMessage):
    action: str = "help_actions"


class MapMessage(InboundMessage):
    action: str = "map"


# --- Level-up ---


class LevelUpMessage(InboundMessage):
    action: str = "level_up"
    stats: list[str]


# --- Social ---


class TradeMessage(InboundMessage):
    action: str = "trade"
    args: str = ""


class PartyMessage(InboundMessage):
    action: str = "party"
    args: str = ""


# --- Heartbeat ---


class PongMessage(InboundMessage):
    action: str = "pong"


# --- Reconnect ---


class ReconnectMessage(InboundMessage):
    action: str = "reconnect"
    session_token: str = Field(min_length=1)
    last_seq: int | None = None


# --- Utility ---


def with_request_id(response: dict, data: dict) -> dict:
    """Echo request_id from inbound data to outbound response if present."""
    rid = data.get("request_id")
    if rid is not None:
        response["request_id"] = rid
    return response


# --- Action-to-schema mapping ---

ACTION_SCHEMAS: dict[str, type[InboundMessage]] = {
    "login": LoginMessage,
    "register": RegisterMessage,
    "logout": LogoutMessage,
    "move": MoveMessage,
    "chat": ChatMessage,
    "party_chat": PartyChatMessage,
    "play_card": PlayCardMessage,
    "pass_turn": PassTurnMessage,
    "flee": FleeMessage,
    "use_item_combat": UseItemCombatMessage,
    "inventory": InventoryMessage,
    "use_item": UseItemMessage,
    "interact": InteractMessage,
    "look": LookMessage,
    "who": WhoMessage,
    "stats": StatsMessage,
    "help_actions": HelpMessage,
    "map": MapMessage,
    "level_up": LevelUpMessage,
    "trade": TradeMessage,
    "party": PartyMessage,
    "pong": PongMessage,
    "reconnect": ReconnectMessage,
}
