"""Pydantic schemas for all 38 WebSocket outbound (server-to-client) message types.

These serve as machine-readable protocol documentation and optional runtime validation.
Handlers continue using raw dicts; these schemas document the contract.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from starlette.websockets import WebSocket


# ---------------------------------------------------------------------------
# Shared sub-models (payloads used inside multiple message types)
# ---------------------------------------------------------------------------


class PlayerStatsPayload(BaseModel):
    hp: int
    max_hp: int
    attack: int
    xp: int
    level: int
    xp_for_next_level: int
    xp_for_current_level: int
    strength: int
    dexterity: int
    constitution: int
    intelligence: int
    wisdom: int
    charisma: int


class StatsResultPayload(PlayerStatsPayload):
    """Extended stats payload for /stats query — includes legacy xp_next alias."""

    xp_next: int


class EntityPayload(BaseModel):
    """Entity in room_state or entity_entered. Fields vary by entity type."""

    id: str
    name: str
    x: int
    y: int
    level: int | None = None  # present for players (login/transition), absent on respawn
    connected: bool | None = None  # present for players during grace period
    npc_key: str | None = None  # present for NPCs only
    is_alive: bool | None = None  # present for NPCs only


class NpcPayload(BaseModel):
    id: str
    npc_key: str
    name: str
    x: int
    y: int
    is_alive: bool


class NearbyObjectPayload(BaseModel):
    id: str
    type: str
    direction: str


class CombatParticipantPayload(BaseModel):
    entity_id: str
    hp: int
    max_hp: int
    shield: int
    energy: int
    max_energy: int


class CombatMobPayload(BaseModel):
    name: str
    hp: int
    max_hp: int


class CardPayload(BaseModel):
    card_key: str
    name: str
    cost: int
    effects: list[dict[str, Any]]
    description: str


class CombatStatePayload(BaseModel):
    """Shared combat state from CombatInstance.get_state()."""

    instance_id: str
    current_turn: str | None
    participants: list[CombatParticipantPayload]
    mob: CombatMobPayload
    hands: dict[str, list[CardPayload]]


class InventoryItemPayload(BaseModel):
    item_key: str
    name: str
    category: str
    quantity: int
    charges: int | None = None
    description: str


class LookObjectPayload(BaseModel):
    id: str
    type: str
    direction: str


class LookNpcPayload(BaseModel):
    name: str
    alive: bool
    direction: str


class LookPlayerPayload(BaseModel):
    name: str
    direction: str


class WhoPlayerPayload(BaseModel):
    name: str
    x: int
    y: int


class RoomPayload(BaseModel):
    room_key: str
    name: str


class ConnectionPayload(BaseModel):
    from_room: str
    to_room: str
    direction: str


class PartyMemberPayload(BaseModel):
    name: str
    entity_id: str
    is_leader: bool
    room: str | None = None


# ---------------------------------------------------------------------------
# Auth messages
# ---------------------------------------------------------------------------


class LoginSuccessMessage(BaseModel):
    type: str = "login_success"
    protocol_version: str
    player_id: int
    entity_id: str
    username: str
    stats: PlayerStatsPayload
    session_token: str | None = None
    request_id: str | None = None


class LoggedOutMessage(BaseModel):
    type: str = "logged_out"
    request_id: str | None = None


class KickedMessage(BaseModel):
    type: str = "kicked"
    reason: str


# ---------------------------------------------------------------------------
# System messages
# ---------------------------------------------------------------------------


class ErrorMessage(BaseModel):
    type: str = "error"
    code: str | None = None
    detail: str
    request_id: str | None = None


class PingMessage(BaseModel):
    type: str = "ping"


class SeqStatusMessage(BaseModel):
    type: str = "seq_status"
    status: str


class ServerShutdownMessage(BaseModel):
    type: str = "server_shutdown"
    reason: str


class AnnouncementMessage(BaseModel):
    type: str = "announcement"
    message: str
    format: str | None = None


class RespawnMessage(BaseModel):
    type: str = "respawn"
    room_key: str
    x: int
    y: int
    hp: int
    max_hp: int


# ---------------------------------------------------------------------------
# Room messages
# ---------------------------------------------------------------------------


class RoomStateMessage(BaseModel):
    type: str = "room_state"
    room_key: str
    name: str
    width: int
    height: int
    tiles: list[list[int]]
    entities: list[EntityPayload]
    npcs: list[NpcPayload]
    exits: list[dict[str, Any]]
    objects: list[dict[str, Any]]
    request_id: str | None = None


class EntityEnteredMessage(BaseModel):
    type: str = "entity_entered"
    entity: EntityPayload


class EntityLeftMessage(BaseModel):
    type: str = "entity_left"
    entity_id: str


class EntityMovedMessage(BaseModel):
    type: str = "entity_moved"
    entity_id: str
    x: int
    y: int


class NearbyObjectsMessage(BaseModel):
    type: str = "nearby_objects"
    objects: list[NearbyObjectPayload]
    request_id: str | None = None


class TileChangedMessage(BaseModel):
    type: str = "tile_changed"
    x: int
    y: int
    tile_type: int


# ---------------------------------------------------------------------------
# Combat messages
# ---------------------------------------------------------------------------


class CombatStartMessage(CombatStatePayload):
    type: str = "combat_start"


class CombatTurnMessage(CombatStatePayload):
    type: str = "combat_turn"
    result: dict[str, Any]
    seq: int | None = None


class CombatEndMessage(BaseModel):
    type: str = "combat_end"
    victory: bool
    rewards: dict[str, Any]
    loot: list[dict[str, Any]] | None = None
    defeated_npc_id: str | None = None
    seq: int | None = None


class CombatFledMessage(BaseModel):
    type: str = "combat_fled"
    request_id: str | None = None


class CombatUpdateMessage(CombatStatePayload):
    type: str = "combat_update"


# ---------------------------------------------------------------------------
# Chat messages
# ---------------------------------------------------------------------------


class OutboundChatMessage(BaseModel):
    type: str = "chat"
    sender: str
    message: str
    whisper: bool
    format: str | None = None
    request_id: str | None = None  # present on whisper echo to sender


class OutboundPartyChatMessage(BaseModel):
    type: str = "party_chat"
    from_: str = Field(alias="from")
    message: str
    format: str | None = None

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Inventory / Items messages
# ---------------------------------------------------------------------------


class InventoryListMessage(BaseModel):
    type: str = "inventory"
    items: list[InventoryItemPayload]
    request_id: str | None = None


class ItemUsedMessage(BaseModel):
    type: str = "item_used"
    item_key: str
    item_name: str
    effect_results: list[dict[str, Any]]
    request_id: str | None = None


# ---------------------------------------------------------------------------
# Interact messages
# ---------------------------------------------------------------------------


class InteractResultMessage(BaseModel):
    type: str = "interact_result"
    object_id: str
    result: dict[str, Any]
    request_id: str | None = None


# ---------------------------------------------------------------------------
# Trade messages
# ---------------------------------------------------------------------------


class TradeRequestMessage(BaseModel):
    type: str = "trade_request"
    from_player: str
    from_entity_id: str


class TradeUpdateMessage(BaseModel):
    type: str = "trade_update"
    player_a: str
    player_b: str
    offers_a: dict[str, int]
    offers_b: dict[str, int]
    ready_a: bool
    ready_b: bool
    state: str
    seq: int | None = None


class TradeResultMessage(BaseModel):
    type: str = "trade_result"
    status: str
    reason: str
    inventory: list[InventoryItemPayload] | None = None
    request_id: str | None = None


# ---------------------------------------------------------------------------
# Party messages
# ---------------------------------------------------------------------------


class PartyInviteMessage(BaseModel):
    type: str = "party_invite"
    from_player: str
    from_entity_id: str


class PartyInviteResponseMessage(BaseModel):
    type: str = "party_invite_response"
    status: str
    target: str | None = None
    request_id: str | None = None


class PartyUpdateMessage(BaseModel):
    type: str = "party_update"
    action: str
    entity_id: str | None = None
    members: list[str] | None = None
    leader: str | None = None
    new_leader: str | None = None


class PartyStatusMessage(BaseModel):
    type: str = "party_status"
    # In-party shape
    party_id: str | None = None
    members: list[PartyMemberPayload] | None = None
    # Pending-invite shape
    pending_invite: bool | None = None
    from_player: str | None = None
    request_id: str | None = None


# ---------------------------------------------------------------------------
# XP / Level-up messages
# ---------------------------------------------------------------------------


class XpGainedMessage(BaseModel):
    type: str = "xp_gained"
    amount: int
    source: str
    detail: str
    new_total_xp: int
    seq: int | None = None


class LevelUpAvailableMessage(BaseModel):
    type: str = "level_up_available"
    new_level: int
    choose_stats: int
    current_stats: dict[str, int]
    stat_cap: int
    xp_for_next_level: int
    xp_for_current_level: int
    stat_effects: dict[str, str]
    seq: int | None = None


class LevelUpCompleteMessage(BaseModel):
    type: str = "level_up_complete"
    level: int
    stat_changes: dict[str, int]
    new_max_hp: int
    new_hp: int
    skipped_at_cap: list[str] | None = None
    request_id: str | None = None


# ---------------------------------------------------------------------------
# Query messages
# ---------------------------------------------------------------------------


class LookResultMessage(BaseModel):
    type: str = "look_result"
    objects: list[LookObjectPayload]
    npcs: list[LookNpcPayload]
    players: list[LookPlayerPayload]
    request_id: str | None = None


class WhoResultMessage(BaseModel):
    type: str = "who_result"
    room: str
    players: list[WhoPlayerPayload]
    request_id: str | None = None


class StatsResultMessage(BaseModel):
    type: str = "stats_result"
    stats: StatsResultPayload
    request_id: str | None = None


class HelpResultMessage(BaseModel):
    type: str = "help_result"
    categories: dict[str, list[str]]
    request_id: str | None = None


class MapDataMessage(BaseModel):
    type: str = "map_data"
    rooms: list[RoomPayload]
    connections: list[ConnectionPayload]
    request_id: str | None = None


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


async def send_typed(ws: WebSocket, msg: BaseModel) -> None:
    """Send a Pydantic model as JSON via WebSocket.

    Uses exclude_none=True to omit None fields (matching current handler behavior)
    and by_alias=True for fields like party_chat's "from" alias.
    """
    await ws.send_json(msg.model_dump(exclude_none=True, by_alias=True))
