# Story 16.2: WebSocket Outbound Schemas

Status: done

## Story

As a game engine client developer,
I want all 38 server-to-client message types documented as Pydantic models,
so that I have a machine-readable protocol reference and can auto-generate client-side types.

## Acceptance Criteria

1. Pydantic model exists for all 38 outbound message types in `server/net/outbound_schemas.py`
2. Each model documents field names, types, and optionality
3. `model_json_schema()` produces valid JSON Schema for each model
4. All existing tests pass unchanged (schemas are additive, no handler changes required)
5. `send_typed(ws, msg)` utility uses `model_dump(exclude_none=True, by_alias=True)` — `by_alias=True` required for `party_chat`'s `from` field (Python reserved word, uses `Field(alias="from")`)
6. Schemas document the CURRENT protocol — `ChatMessage`, `PartyChatMessage`, and `AnnouncementMessage` do NOT include `format` field (added by Story 16.12)

## Tasks / Subtasks

- [x] Task 1: Create `server/net/outbound_schemas.py` with all 38 schemas (AC: 1, 2, 6)
  - [x] 1.1 Auth: `LoginSuccessMessage`, `LoggedOutMessage`, `KickedMessage`
  - [x] 1.2 System: `ErrorMessage`, `ServerShutdownMessage`, `AnnouncementMessage`, `RespawnMessage`
  - [x] 1.3 Room: `RoomStateMessage`, `EntityEnteredMessage`, `EntityLeftMessage`, `EntityMovedMessage`, `NearbyObjectsMessage`, `TileChangedMessage`
  - [x] 1.4 Combat: `CombatStartMessage`, `CombatTurnMessage`, `CombatEndMessage`, `CombatFledMessage`, `CombatUpdateMessage`
  - [x] 1.5 Chat: `OutboundChatMessage`, `OutboundPartyChatMessage`
  - [x] 1.6 Inventory: `InventoryListMessage`, `ItemUsedMessage`
  - [x] 1.7 Interact: `InteractResultMessage`
  - [x] 1.8 Trade: `TradeRequestMessage`, `TradeUpdateMessage`, `TradeResultMessage`
  - [x] 1.9 Party: `PartyInviteMessage`, `PartyInviteResponseMessage`, `PartyUpdateMessage`, `PartyStatusMessage`
  - [x] 1.10 XP/Level: `XpGainedMessage`, `LevelUpAvailableMessage`, `LevelUpCompleteMessage`
  - [x] 1.11 Query: `LookResultMessage`, `WhoResultMessage`, `StatsResultMessage`, `HelpResultMessage`, `MapDataMessage`
  - [x] 1.12 Shared sub-models: `PlayerStatsPayload`, `EntityPayload`, `NpcPayload`, `CardPayload`, `CombatParticipantPayload`, etc.
- [x] Task 2: Add `send_typed()` utility function (AC: 5)
- [x] Task 3: Write unit tests (AC: 1, 3, 5)
  - [x] 3.1 Construct each schema with sample data, verify `model_dump()` output
  - [x] 3.2 Verify `model_json_schema()` returns valid dict for each schema
  - [x] 3.3 Test `send_typed()` uses `exclude_none=True, by_alias=True`
  - [x] 3.4 Test `PartyChatMessage` serializes `from_` as `"from"` via alias
- [x] Task 4: Run full test suite (AC: 4)

## Dev Notes

### Architecture Constraints

- **New file only**: `server/net/outbound_schemas.py` — additive, no handler modifications
- **Documentation purpose**: Schemas serve as machine-readable protocol reference. Handlers continue using raw dicts.
- **No handler rewrites**: Do NOT rewrite `send_json` calls to use schemas — that's gradual migration, not this story
- **Current protocol only**: Do NOT add `format` field to chat schemas — Story 16.12 does that

### All 38 Outbound Message Types

| # | type | Category | Key Fields |
|---|------|----------|------------|
| 1 | `error` | System | `detail: str` |
| 2 | `login_success` | Auth | `player_id: int`, `entity_id: str`, `username: str`, `stats: PlayerStatsPayload` |
| 3 | `logged_out` | Auth | (type only) |
| 4 | `kicked` | Auth | `reason: str` |
| 5 | `server_shutdown` | System | `reason: str` |
| 6 | `room_state` | Room | `room_key`, `name`, `width`, `height`, `tiles`, `entities`, `npcs`, `exits`, `objects` |
| 7 | `entity_entered` | Room | `entity: dict` (polymorphic — player login/transition has `level`, respawn at `app.py:349` omits `level`, NPC has `npc_key`/`is_alive`; all optional) |
| 8 | `entity_left` | Room | `entity_id: str` |
| 9 | `entity_moved` | Room | `entity_id: str`, `x: int`, `y: int` |
| 10 | `nearby_objects` | Room | `objects: list[NearbyObjectPayload]` |
| 11 | `tile_changed` | Room | `x: int`, `y: int`, `tile_type: int` |
| 12 | `respawn` | Room | `room_key: str`, `x: int`, `y: int`, `hp: int`, `max_hp: int` |
| 13 | `combat_start` | Combat | spread of `CombatInstance.get_state()` |
| 14 | `combat_turn` | Combat | `result: dict`, spread of `CombatInstance.get_state()` |
| 15 | `combat_end` | Combat | `victory: bool`, `rewards: dict`, `loot?`, `defeated_npc_id?` |
| 16 | `combat_fled` | Combat | (type only) |
| 17 | `combat_update` | Combat | spread of `CombatInstance.get_state()` |
| 18 | `chat` | Chat | `sender: str`, `message: str`, `whisper: bool` |
| 19 | `party_chat` | Chat | `from: str` (alias), `message: str` |
| 20 | `announcement` | Chat | `message: str` |
| 21 | `inventory` | Items | `items: list[InventoryItemPayload]` |
| 22 | `item_used` | Items | `item_key: str`, `item_name: str`, `effect_results: list[dict]` |
| 23 | `interact_result` | Interact | `object_id: str`, `result: dict` |
| 24 | `trade_request` | Trade | `from_player: str`, `from_entity_id: str` |
| 25 | `trade_update` | Trade | `player_a`, `player_b`, `offers_a`, `offers_b`, `ready_a`, `ready_b`, `state` |
| 26 | `trade_result` | Trade | `status: str`, `reason: str`, `inventory?: list` |
| 27 | `party_invite` | Party | `from_player: str`, `from_entity_id: str` |
| 28 | `party_invite_response` | Party | `status: str`, `target?: str` |
| 29 | `party_update` | Party | `action: str`, `entity_id?`, `members?`, `leader?`, `new_leader?` |
| 30 | `party_status` | Party | `party_id?`, `members?`, `pending_invite?`, `from_player?` |
| 31 | `xp_gained` | XP | `amount: int`, `source: str`, `detail: str`, `new_total_xp: int` |
| 32 | `level_up_available` | XP | `new_level`, `choose_stats`, `current_stats`, `stat_cap`, `xp_for_next_level`, `xp_for_current_level`, `stat_effects` |
| 33 | `level_up_complete` | XP | `level: int`, `stat_changes: dict`, `new_max_hp: int`, `new_hp: int`, `skipped_at_cap?: list` |
| 34 | `look_result` | Query | `objects`, `npcs`, `players` (each list of payload dicts) |
| 35 | `who_result` | Query | `room: str`, `players: list` |
| 36 | `stats_result` | Query | `stats: dict` (full stat block including legacy `xp_next` alias for `xp_for_next_level`) |
| 37 | `help_result` | Query | `categories: dict[str, list[str]]` |
| 38 | `map_data` | Query | `rooms: list`, `connections: list` |

### Key Design Decisions

- **`party_chat` uses `"from"` key**: Python reserved word — use `from_: str = Field(alias="from")` and `by_alias=True` in `model_dump()`
- **`entity_entered` is polymorphic**: Entity dict has different shapes for players (with `level`) vs NPCs (with `npc_key`, `is_alive`). Use optional fields on a single `EntityPayload`.
- **Combat state fields**: Use `dict` or `Any` for complex nested structures like `result` in `combat_turn` — documenting structure in docstrings rather than deeply nested models
- **Conditional fields use `| None = None`**: e.g., `loot` on `CombatEndMessage`, `target` on `PartyInviteResponseMessage`, `inventory` on `TradeResultMessage`
- **`model_dump(exclude_none=True)`**: Strips None fields to match current handler behavior (handlers only add fields when they have values)

### Source References for Field Verification

- `RoomInstance.get_state()`: `server/room/room.py:185-203`
- `CombatInstance.get_state()`: `server/combat/instance.py:380-408`
- `NpcEntity.to_dict()`: `server/room/npc.py:29-38`
- `CardDef.to_dict()`: `server/combat/cards/card_def.py:32-40`
- `Inventory.get_inventory()`: `server/items/inventory.py:92-105`
- `_send_combat_end_message()`: `server/net/handlers/combat.py:122-139`
- `_send_trade_update()`: `server/net/handlers/trade.py:41-52`
- Party status: `server/net/handlers/party.py:447,458`
- `notify_xp` / `send_level_up_available()`: `server/core/xp.py:92-185`
- Level-up complete: `server/net/handlers/levelup.py:83-92`

### Previous Story Learnings (from 16.1)

- Pydantic is already in the project (used for `Settings` + inbound schemas)
- `min_length=1` on `Field` rejects empty strings at schema level
- Schema validation at framework level changes error messages — document behavioral changes
- Tests that call handlers directly bypass schema validation — keep defensive guards
- `model_dump()` includes all fields including defaults — use `exclude_none=True` for optional fields

### What NOT To Do

- Do NOT rewrite handler `send_json()` calls to use outbound schemas
- Do NOT add `format` field to chat/party_chat/announcement schemas (Story 16.12)
- Do NOT add `session_token` to `LoginSuccessMessage` (Story 16.9)
- Do NOT add `turn_timeout_at` to combat schemas (Story 16.10a)
- Do NOT add `seq` field to any schema (Story 16.11)
- Do NOT add `connected` field to entity payloads (Story 16.10)

### References

- [Source: _bmad-output/planning-artifacts/epic-16-tech-spec.md#Story 16.2]
- [Source: server/room/room.py#get_state]
- [Source: server/combat/instance.py#get_state]
- [Source: server/core/xp.py#send_level_up_available]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Created `server/net/outbound_schemas.py` with 38 Pydantic schemas for all outbound message types
- Includes 15+ shared sub-models (PlayerStatsPayload, EntityPayload, CombatStatePayload, etc.)
- `send_typed()` utility with `exclude_none=True, by_alias=True`
- `OutboundPartyChatMessage` correctly uses `Field(alias="from")` for Python reserved word
- `StatsResultPayload` includes legacy `xp_next` field
- `EntityPayload` has optional `level`, `npc_key`, `is_alive` for polymorphic entity types
- Created `tests/test_outbound_schemas.py` with 88 unit tests (all schemas, JSON Schema, send_typed)
- All 959 tests pass (871 existing + 88 new)

### File List

- **New**: `server/net/outbound_schemas.py`
- **New**: `tests/test_outbound_schemas.py`
