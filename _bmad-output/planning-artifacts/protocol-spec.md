# The Ages II — WebSocket Protocol Specification

> **Auto-generated** from Pydantic schemas by `scripts/generate_protocol_doc.py`.
> Do not edit manually — run `make protocol-doc` to regenerate.

## 1. Transport

- **Protocol**: WebSocket (RFC 6455)
- **Endpoint**: `ws://<host>:<port>/ws/game`
- **Frame type**: Text (JSON)
- **Encoding**: UTF-8
- **Default port**: 8000

## 2. Connection Lifecycle

### Initial Connection Sequence

1. Client opens WebSocket to `/ws/game`
2. Client sends `login` or `register` message
3. Server responds with `login_success` (includes player stats)
4. Server sends `room_state` (full room snapshot)
5. Client begins rendering

### Reconnect Sequence (Story 16.9)

1. Client opens WebSocket to `/ws/game`
2. Client sends `reconnect` with `session_token`
3. Server responds with `login_success` + `room_state` + combat state if applicable

## 3. Inbound Messages (Client → Server)

**21 actions** defined.

### `chat`

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `action` | `str` | No | `"chat"` |
| `message` | `str` | Yes | PydanticUndefined |
| `whisper_to` | `str | None` | No | `"—"` |

### `flee`

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `action` | `str` | No | `"flee"` |

### `help_actions`

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `action` | `str` | No | `"help_actions"` |

### `interact`

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `action` | `str` | No | `"interact"` |
| `target_id` | `str` | No | `""` |
| `direction` | `str` | No | `""` |

### `inventory`

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `action` | `str` | No | `"inventory"` |

### `level_up`

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `action` | `str` | No | `"level_up"` |
| `stats` | `list` | Yes | PydanticUndefined |

### `login`

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `action` | `str` | No | `"login"` |
| `username` | `str` | Yes | PydanticUndefined |
| `password` | `str` | Yes | PydanticUndefined |

### `logout`

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `action` | `str` | No | `"logout"` |

### `look`

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `action` | `str` | No | `"look"` |

### `map`

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `action` | `str` | No | `"map"` |

### `move`

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `action` | `str` | No | `"move"` |
| `direction` | `str` | Yes | PydanticUndefined |

### `party`

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `action` | `str` | No | `"party"` |
| `args` | `str` | No | `""` |

### `party_chat`

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `action` | `str` | No | `"party_chat"` |
| `message` | `str` | Yes | PydanticUndefined |

### `pass_turn`

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `action` | `str` | No | `"pass_turn"` |

### `play_card`

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `action` | `str` | No | `"play_card"` |
| `card_key` | `str` | Yes | PydanticUndefined |

### `register`

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `action` | `str` | No | `"register"` |
| `username` | `str` | Yes | PydanticUndefined |
| `password` | `str` | Yes | PydanticUndefined |

### `stats`

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `action` | `str` | No | `"stats"` |

### `trade`

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `action` | `str` | No | `"trade"` |
| `args` | `str` | No | `""` |

### `use_item`

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `action` | `str` | No | `"use_item"` |
| `item_key` | `str` | Yes | PydanticUndefined |

### `use_item_combat`

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `action` | `str` | No | `"use_item_combat"` |
| `item_key` | `str` | Yes | PydanticUndefined |

### `who`

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `action` | `str` | No | `"who"` |

## 4. Outbound Messages (Server → Client)

**40 message types** defined.

### `announcement` (AnnouncementMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `type` | `str` | No | `"announcement"` |
| `message` | `str` | Yes | PydanticUndefined |
| `format` | `str | None` | No | `"—"` |

### `combat_end` (CombatEndMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `type` | `str` | No | `"combat_end"` |
| `victory` | `bool` | Yes | PydanticUndefined |
| `rewards` | `dict` | Yes | PydanticUndefined |
| `loot` | `list[dict[str, Any]] | None` | No | `"—"` |
| `defeated_npc_id` | `str | None` | No | `"—"` |

### `combat_fled` (CombatFledMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `type` | `str` | No | `"combat_fled"` |

### `combat_start` (CombatStartMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `instance_id` | `str` | Yes | PydanticUndefined |
| `current_turn` | `str | None` | Yes | PydanticUndefined |
| `participants` | `list` | Yes | PydanticUndefined |
| `mob` | `CombatMobPayload` | Yes | PydanticUndefined |
| `hands` | `dict` | Yes | PydanticUndefined |
| `type` | `str` | No | `"combat_start"` |

### `combat_turn` (CombatTurnMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `instance_id` | `str` | Yes | PydanticUndefined |
| `current_turn` | `str | None` | Yes | PydanticUndefined |
| `participants` | `list` | Yes | PydanticUndefined |
| `mob` | `CombatMobPayload` | Yes | PydanticUndefined |
| `hands` | `dict` | Yes | PydanticUndefined |
| `type` | `str` | No | `"combat_turn"` |
| `result` | `dict` | Yes | PydanticUndefined |

### `combat_update` (CombatUpdateMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `instance_id` | `str` | Yes | PydanticUndefined |
| `current_turn` | `str | None` | Yes | PydanticUndefined |
| `participants` | `list` | Yes | PydanticUndefined |
| `mob` | `CombatMobPayload` | Yes | PydanticUndefined |
| `hands` | `dict` | Yes | PydanticUndefined |
| `type` | `str` | No | `"combat_update"` |

### `entity_entered` (EntityEnteredMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `type` | `str` | No | `"entity_entered"` |
| `entity` | `EntityPayload` | Yes | PydanticUndefined |

### `entity_left` (EntityLeftMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `type` | `str` | No | `"entity_left"` |
| `entity_id` | `str` | Yes | PydanticUndefined |

### `entity_moved` (EntityMovedMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `type` | `str` | No | `"entity_moved"` |
| `entity_id` | `str` | Yes | PydanticUndefined |
| `x` | `int` | Yes | PydanticUndefined |
| `y` | `int` | Yes | PydanticUndefined |

### `error` (ErrorMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `type` | `str` | No | `"error"` |
| `detail` | `str` | Yes | PydanticUndefined |

### `help_result` (HelpResultMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `type` | `str` | No | `"help_result"` |
| `categories` | `dict` | Yes | PydanticUndefined |

### `interact_result` (InteractResultMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `type` | `str` | No | `"interact_result"` |
| `object_id` | `str` | Yes | PydanticUndefined |
| `result` | `dict` | Yes | PydanticUndefined |

### `inventory` (InventoryListMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `type` | `str` | No | `"inventory"` |
| `items` | `list` | Yes | PydanticUndefined |

### `item_used` (ItemUsedMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `type` | `str` | No | `"item_used"` |
| `item_key` | `str` | Yes | PydanticUndefined |
| `item_name` | `str` | Yes | PydanticUndefined |
| `effect_results` | `list` | Yes | PydanticUndefined |

### `kicked` (KickedMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `type` | `str` | No | `"kicked"` |
| `reason` | `str` | Yes | PydanticUndefined |

### `level_up_available` (LevelUpAvailableMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `type` | `str` | No | `"level_up_available"` |
| `new_level` | `int` | Yes | PydanticUndefined |
| `choose_stats` | `int` | Yes | PydanticUndefined |
| `current_stats` | `dict` | Yes | PydanticUndefined |
| `stat_cap` | `int` | Yes | PydanticUndefined |
| `xp_for_next_level` | `int` | Yes | PydanticUndefined |
| `xp_for_current_level` | `int` | Yes | PydanticUndefined |
| `stat_effects` | `dict` | Yes | PydanticUndefined |

### `level_up_complete` (LevelUpCompleteMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `type` | `str` | No | `"level_up_complete"` |
| `level` | `int` | Yes | PydanticUndefined |
| `stat_changes` | `dict` | Yes | PydanticUndefined |
| `new_max_hp` | `int` | Yes | PydanticUndefined |
| `new_hp` | `int` | Yes | PydanticUndefined |
| `skipped_at_cap` | `list[str] | None` | No | `"—"` |

### `logged_out` (LoggedOutMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `type` | `str` | No | `"logged_out"` |

### `login_success` (LoginSuccessMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `type` | `str` | No | `"login_success"` |
| `player_id` | `int` | Yes | PydanticUndefined |
| `entity_id` | `str` | Yes | PydanticUndefined |
| `username` | `str` | Yes | PydanticUndefined |
| `stats` | `PlayerStatsPayload` | Yes | PydanticUndefined |

### `PydanticUndefined` (LookObjectPayload)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `id` | `str` | Yes | PydanticUndefined |
| `type` | `str` | Yes | PydanticUndefined |
| `direction` | `str` | Yes | PydanticUndefined |

### `look_result` (LookResultMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `type` | `str` | No | `"look_result"` |
| `objects` | `list` | Yes | PydanticUndefined |
| `npcs` | `list` | Yes | PydanticUndefined |
| `players` | `list` | Yes | PydanticUndefined |

### `map_data` (MapDataMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `type` | `str` | No | `"map_data"` |
| `rooms` | `list` | Yes | PydanticUndefined |
| `connections` | `list` | Yes | PydanticUndefined |

### `PydanticUndefined` (NearbyObjectPayload)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `id` | `str` | Yes | PydanticUndefined |
| `type` | `str` | Yes | PydanticUndefined |
| `direction` | `str` | Yes | PydanticUndefined |

### `nearby_objects` (NearbyObjectsMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `type` | `str` | No | `"nearby_objects"` |
| `objects` | `list` | Yes | PydanticUndefined |

### `chat` (OutboundChatMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `type` | `str` | No | `"chat"` |
| `sender` | `str` | Yes | PydanticUndefined |
| `message` | `str` | Yes | PydanticUndefined |
| `whisper` | `bool` | Yes | PydanticUndefined |
| `format` | `str | None` | No | `"—"` |

### `party_chat` (OutboundPartyChatMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `type` | `str` | No | `"party_chat"` |
| `from_` | `str` | Yes | PydanticUndefined |
| `message` | `str` | Yes | PydanticUndefined |
| `format` | `str | None` | No | `"—"` |

### `party_invite` (PartyInviteMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `type` | `str` | No | `"party_invite"` |
| `from_player` | `str` | Yes | PydanticUndefined |
| `from_entity_id` | `str` | Yes | PydanticUndefined |

### `party_invite_response` (PartyInviteResponseMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `type` | `str` | No | `"party_invite_response"` |
| `status` | `str` | Yes | PydanticUndefined |
| `target` | `str | None` | No | `"—"` |

### `party_status` (PartyStatusMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `type` | `str` | No | `"party_status"` |
| `party_id` | `str | None` | No | `"—"` |
| `members` | `list[PartyMemberPayload] | None` | No | `"—"` |
| `pending_invite` | `bool | None` | No | `"—"` |
| `from_player` | `str | None` | No | `"—"` |

### `party_update` (PartyUpdateMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `type` | `str` | No | `"party_update"` |
| `action` | `str` | Yes | PydanticUndefined |
| `entity_id` | `str | None` | No | `"—"` |
| `members` | `list[str] | None` | No | `"—"` |
| `leader` | `str | None` | No | `"—"` |
| `new_leader` | `str | None` | No | `"—"` |

### `respawn` (RespawnMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `type` | `str` | No | `"respawn"` |
| `room_key` | `str` | Yes | PydanticUndefined |
| `x` | `int` | Yes | PydanticUndefined |
| `y` | `int` | Yes | PydanticUndefined |
| `hp` | `int` | Yes | PydanticUndefined |
| `max_hp` | `int` | Yes | PydanticUndefined |

### `room_state` (RoomStateMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `type` | `str` | No | `"room_state"` |
| `room_key` | `str` | Yes | PydanticUndefined |
| `name` | `str` | Yes | PydanticUndefined |
| `width` | `int` | Yes | PydanticUndefined |
| `height` | `int` | Yes | PydanticUndefined |
| `tiles` | `list` | Yes | PydanticUndefined |
| `entities` | `list` | Yes | PydanticUndefined |
| `npcs` | `list` | Yes | PydanticUndefined |
| `exits` | `list` | Yes | PydanticUndefined |
| `objects` | `list` | Yes | PydanticUndefined |

### `server_shutdown` (ServerShutdownMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `type` | `str` | No | `"server_shutdown"` |
| `reason` | `str` | Yes | PydanticUndefined |

### `stats_result` (StatsResultMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `type` | `str` | No | `"stats_result"` |
| `stats` | `StatsResultPayload` | Yes | PydanticUndefined |

### `tile_changed` (TileChangedMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `type` | `str` | No | `"tile_changed"` |
| `x` | `int` | Yes | PydanticUndefined |
| `y` | `int` | Yes | PydanticUndefined |
| `tile_type` | `int` | Yes | PydanticUndefined |

### `trade_request` (TradeRequestMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `type` | `str` | No | `"trade_request"` |
| `from_player` | `str` | Yes | PydanticUndefined |
| `from_entity_id` | `str` | Yes | PydanticUndefined |

### `trade_result` (TradeResultMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `type` | `str` | No | `"trade_result"` |
| `status` | `str` | Yes | PydanticUndefined |
| `reason` | `str` | Yes | PydanticUndefined |
| `inventory` | `list[InventoryItemPayload] | None` | No | `"—"` |

### `trade_update` (TradeUpdateMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `type` | `str` | No | `"trade_update"` |
| `player_a` | `str` | Yes | PydanticUndefined |
| `player_b` | `str` | Yes | PydanticUndefined |
| `offers_a` | `dict` | Yes | PydanticUndefined |
| `offers_b` | `dict` | Yes | PydanticUndefined |
| `ready_a` | `bool` | Yes | PydanticUndefined |
| `ready_b` | `bool` | Yes | PydanticUndefined |
| `state` | `str` | Yes | PydanticUndefined |

### `who_result` (WhoResultMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `type` | `str` | No | `"who_result"` |
| `room` | `str` | Yes | PydanticUndefined |
| `players` | `list` | Yes | PydanticUndefined |

### `xp_gained` (XpGainedMessage)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `type` | `str` | No | `"xp_gained"` |
| `amount` | `int` | Yes | PydanticUndefined |
| `source` | `str` | Yes | PydanticUndefined |
| `detail` | `str` | Yes | PydanticUndefined |
| `new_total_xp` | `int` | Yes | PydanticUndefined |

## 5. Delivery Scopes

| Scope | Description |
|-------|-------------|
| **single** | Sent only to the requesting player |
| **room** | Broadcast to all players in the same room |
| **room-exclude** | Broadcast to room, excluding the acting player |
| **combat** | Sent to all combat participants |
| **party** | Sent to all party members |
| **trade** | Sent to both trade participants |
| **all** | Broadcast to all connected players |

## 6. Error Handling

All errors use the same format: `{"type": "error", "detail": "<message>"}`

| Error | Trigger |
|-------|---------|
| Invalid JSON | Client sends non-JSON text |
| Missing action field | JSON object without `action` key |
| Unknown action | `action` value not in registered handlers |
| Validation error | Message fields fail Pydantic schema validation |
| Not logged in | Action requires auth but player not authenticated |

## 7. Tile Type Enum

| Name | Value | Walkable |
|------|-------|----------|
| `FLOOR` | 0 | Yes |
| `WALL` | 1 | No |
| `EXIT` | 2 | Yes |
| `MOB_SPAWN` | 3 | Yes |
| `WATER` | 4 | No |
| `STAIRS_UP` | 5 | Yes |
| `STAIRS_DOWN` | 6 | Yes |

## 8. Movement Directions

Player movement uses four directions: `up`, `down`, `left`, `right`.

Vertical transitions (`ascend`/`descend`) are **exit-triggered** — they fire
automatically when a player steps onto `STAIRS_UP` or `STAIRS_DOWN` tiles.
They are NOT player-input directions.

## 9. Combat Flow

```
Player steps on MOB_SPAWN with alive NPC
  → Server sends combat_start to all participants
  → Turn loop:
      Current player sends: play_card / pass_turn / use_item_combat / flee
      Server broadcasts: combat_turn (with result + updated state)
  → Combat ends:
      Victory/Defeat → combat_end (per-player, with rewards/loot)
      Flee → combat_fled (to fleeing player) + combat_update (to remaining)
```

## 10. Trade Flow

```
Player A: trade @PlayerB  → trade_request to B, trade_result(request_sent) to A
Player B: trade accept    → trade_update to both (negotiating)
Either:   trade offer X N → trade_update to both
Either:   trade ready     → trade_update to both
Both ready:               → trade_result(success) + inventory to both
Either:   trade cancel    → trade_result(cancelled) to both
Player B: trade reject    → trade_result(rejected) to both
Timeout:                  → trade_result(timeout) to both
```

## 11. Party Flow

```
Player A: party invite B  → party_invite to B, party_invite_response(sent) to A
Player B: party accept    → party_update(member_joined) to all members
Player B: party reject    → party_invite_response(rejected) to A
Member:   party leave     → party_update(member_left) to remaining
Leader:   party kick X    → party_update(member_kicked) to all
Leader:   party disband   → party_update(disbanded) to all
Any:      party           → party_status (current state)
```

