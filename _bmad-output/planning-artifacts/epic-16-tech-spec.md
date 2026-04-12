# Epic 16: Server Architecture Maturation & Protocol Specification

**Date**: 2026-04-12
**Source**: Codebase review findings (`_bmad-output/implementation-artifacts/codebase-review-2026-04-12.md`)
**Priority**: High — prerequisite for Godot client development
**Estimated Stories**: 14

**No Alembic migrations required** — all 14 stories modify runtime dataclasses, config settings, handlers, and schemas. No DB model changes.

**Recommended sprint split** (epic is too large for one sprint — reordered to unblock Godot client fastest):

| Sprint | Stories | Milestone | Deliverable |
|--------|---------|-----------|-------------|
| Sprint 1 | 16.1, 16.2, 16.3, 16.12 | Protocol formalized | **Godot developer can start client** |
| Sprint 2 | 16.4a, 16.4, 16.5, 16.6, 16.10a | Refactoring + turn timeout | Codebase clean, combat timeout bug fixed |
| Sprint 3a | 16.7, 16.8 | Client polish | Request correlation + heartbeat (lightweight, independent) |
| Sprint 3b | 16.9, 16.10, 16.11 | Resilience layer | Session tokens → grace period → message ack (tightly coupled) |

**Rationale (from War Room)**: The protocol spec (Sprint 1) is the actual blocker for Godot client development. Refactoring (Sprint 2) improves server internals but doesn't enable anything external. 16.10a (turn timeout) moved from Sprint 3 to Sprint 2 because it fixes a real current bug — combat stalls forever when a player disconnects.

Sprint 1 and Sprint 2 can run in parallel if different developers work on them (no file overlap). Sprint 3a can start after Sprint 1 (16.7/16.8 depend on 16.1 for schemas). Sprint 3b must be last (16.9 depends on 16.5 from Sprint 2).

**Merge-order constraint**: Stories with dependency arrows in the graph MUST be implemented and merged sequentially, not in parallel. The dependency graph is a merge-order constraint — parallel development on `auth.py` (16.5 + 16.9) will cause merge conflicts and logic duplication.

---

## Motivation

The server is functionally complete (Epics 1-15, 808 tests passing) but needs architectural refinements before building a production game client. The codebase review identified five actionable improvements:

1. **No formal protocol spec** — any non-trivial client (Godot/Unity/Unreal) needs a machine-readable schema
2. **No message validation** — WebSocket messages validated ad-hoc with `data.get()`, no Pydantic schemas
3. **Combat business logic in handler** — 230 lines of game logic in `server/net/handlers/combat.py` should be in a service layer
4. **`handle_login` too large** — 167 lines mixing 12 concerns in one function
5. **`TradeManager` DI inconsistency** — setter injection while `PartyManager` uses constructor injection

---

## Story 16.1: WebSocket Protocol Pydantic Schemas (Inbound)

**Goal**: Define Pydantic models for all 21 client-to-server actions, replacing ad-hoc `data.get()` validation.

### Current State

All handlers validate input manually:
```python
# server/net/handlers/combat.py:264
card_key = data.get("card_key", "")
if not card_key:
    await websocket.send_json({"type": "error", "detail": "Missing card_key"})
```

### Implementation

**New file**: `server/net/schemas.py`

Define a base class and per-action schemas:
```python
from pydantic import BaseModel, field_validator

class InboundMessage(BaseModel):
    action: str

class LoginMessage(InboundMessage):
    action: str = "login"
    username: str
    password: str

class MoveMessage(InboundMessage):
    action: str = "move"
    direction: str  # "up", "down", "left", "right"

    @field_validator("direction")
    @classmethod
    def validate_direction(cls, v: str) -> str:
        if v not in ("up", "down", "left", "right"):
            raise ValueError(f"Invalid direction: {v}")
        return v

class PlayCardMessage(InboundMessage):
    action: str = "play_card"
    card_key: str

class ChatMessage(InboundMessage):
    action: str = "chat"
    message: str
    whisper_to: str | None = None

class TradeMessage(InboundMessage):
    action: str = "trade"
    args: str = ""

class PartyMessage(InboundMessage):
    action: str = "party"
    args: str = ""

class LevelUpMessage(InboundMessage):
    action: str = "level_up"
    stats: list[str]

class UseItemMessage(InboundMessage):
    action: str = "use_item"
    item_key: str

class InteractMessage(InboundMessage):
    action: str = "interact"
    target_id: str | None = None
    direction: str | None = None

# ... etc for all 21 actions
```

**Action-to-schema mapping** in `server/net/schemas.py`:
```python
ACTION_SCHEMAS: dict[str, type[InboundMessage]] = {
    "login": LoginMessage,
    "register": RegisterMessage,
    "move": MoveMessage,
    # ... etc
}
```

**Parser update** in `server/app.py` websocket_endpoint (lines 386-406):
```python
from server.net.schemas import ACTION_SCHEMAS
# After JSON parse and action extraction:
schema_cls = ACTION_SCHEMAS.get(action)
if schema_cls:
    try:
        validated = schema_cls(**data)
        data = validated.model_dump()
    except ValidationError as e:
        await websocket.send_json({"type": "error", "detail": str(e)})
        continue
```

**Handler updates**: Remove all `data.get()` with default + manual validation — the schema guarantees fields exist and are valid. Handlers can access `data["card_key"]` directly.

### Files Changed
- **New**: `server/net/schemas.py` (~150 lines)
- **Modified**: `server/app.py` (websocket_endpoint, ~10 lines)
- **Modified**: 10 WebSocket handler files in `server/net/handlers/` (remove manual validation, ~3-10 lines each; `admin.py` is REST-only and unchanged)

### Acceptance Criteria
- [ ] Pydantic schema exists for all 21 inbound actions
- [ ] `ValidationError` returns `{"type": "error", "detail": "..."}` to client with specific field errors
- [ ] Field-presence and type validation removed from handlers — schema handles these (no redundant `data.get()` + type checks)
- [ ] Config-dependent range checks REMAIN in handlers — `MAX_CHAT_MESSAGE_LENGTH`, `MIN_USERNAME_LENGTH`, `MIN_PASSWORD_LENGTH` reference runtime `settings.*` values that cannot be baked into class-level schema definitions
- [ ] Actions without required fields (e.g., `inventory`, `pass_turn`, `flee`, `logout`) have schemas with only `action` field
- [ ] All 808+ tests pass unchanged (schemas validate the same rules as before)
- [ ] Direction validation ("up"/"down"/"left"/"right") happens in schema, not handler
- [ ] `InteractMessage` uses `model_validator` to require at least one of `target_id` or `direction` (rejects both-None)

### Test Plan
- Unit tests for each schema: valid input, missing fields, wrong types, invalid enum values
- Integration tests unchanged (existing tests exercise all message paths)

---

## Story 16.2: WebSocket Protocol Pydantic Schemas (Outbound)

**Goal**: Define Pydantic models for all 38 server-to-client message types as documentation and optional runtime validation.

### Current State

All outbound messages are constructed as ad-hoc dicts:
```python
# server/net/handlers/auth.py:232-254
await websocket.send_json({
    "type": "login_success",
    "player_id": player.id,
    "entity_id": entity_id,
    "username": player.username,
    "stats": { ... },
})
```

No formal documentation of field names, types, or optionality.

### Implementation

**New file**: `server/net/outbound_schemas.py`

Define models for all 38 outbound message types. These serve dual purpose:
1. **Documentation** — machine-readable protocol spec
2. **Optional validation** — can be enabled in DEBUG mode for development

Categories:
- **Auth**: `LoginSuccessMessage`, `LoggedOutMessage`, `KickedMessage`
- **Room**: `RoomStateMessage`, `EntityMovedMessage`, `EntityEnteredMessage`, `EntityLeftMessage`, `NearbyObjectsMessage`, `TileChangedMessage`
- **Combat**: `CombatStartMessage`, `CombatTurnMessage`, `CombatEndMessage`, `CombatFledMessage`, `CombatUpdateMessage`
- **Interaction**: `InteractResultMessage`
- **Inventory**: `InventoryMessage`, `ItemUsedMessage`
- **Query**: `LookResultMessage`, `WhoResultMessage`, `StatsResultMessage`, `HelpResultMessage`, `MapDataMessage`
- **XP/Level**: `XpGainedMessage`, `LevelUpAvailableMessage`, `LevelUpCompleteMessage`
- **Trade**: `TradeRequestMessage`, `TradeUpdateMessage`, `TradeResultMessage`
- **Party**: `PartyInviteMessage`, `PartyInviteResponseMessage`, `PartyUpdateMessage`, `PartyStatusMessage`, `PartyChatMessage`
- **System**: `ErrorMessage`, `AnnouncementMessage`, `ServerShutdownMessage`, `RespawnMessage`, `ChatMessage`

Key field definitions (verified against codebase):

```python
class LoginSuccessMessage(BaseModel):
    type: str = "login_success"
    player_id: int
    entity_id: str
    username: str
    stats: PlayerStatsPayload

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

class RoomStateMessage(BaseModel):
    type: str = "room_state"
    room_key: str
    name: str
    width: int
    height: int
    tiles: list[list[int]]
    entities: list[EntityPayload]
    npcs: list[NpcPayload]
    exits: list[dict]
    objects: list[dict]

class CombatTurnMessage(BaseModel):
    type: str = "combat_turn"
    result: dict  # Complex nested structure, documented in detail
    instance_id: str
    current_turn: str
    participants: list[dict]
    mob: dict
    hands: dict[str, list[dict]]

class CombatEndMessage(BaseModel):
    type: str = "combat_end"
    victory: bool
    rewards: dict  # {xp: int}
    loot: list[dict] | None = None
    defeated_npc_id: str | None = None
    mob_name: str | None = None
```

**Helper**: `send_typed(ws, model_instance)` utility that calls `ws.send_json(model.model_dump(exclude_none=True, by_alias=True))`. The `by_alias=True` is critical — `party_chat` uses `Field(alias="from")` for the reserved word `from`, and without this flag, Pydantic serializes as `from_` instead of `from`, breaking the protocol.

**Migration**: Handlers gradually adopt outbound schemas. This story adds the schemas and helper; Story 16.2 does NOT require rewriting all `send_json` calls. Handlers can continue using raw dicts — schemas serve as the authoritative reference.

**Important**: Schemas document the CURRENT protocol state. Do NOT include `format` field on `ChatMessage`, `PartyChatMessage`, or `AnnouncementMessage` — that field is added by Story 16.12 which updates the schemas when it adds the feature.

### Files Changed
- **New**: `server/net/outbound_schemas.py` (~300 lines)
- **Modified**: `server/net/__init__.py` (re-export if needed)

### Acceptance Criteria
- [ ] Pydantic model exists for all 38 outbound message types
- [ ] Each model documents field names, types, and optionality
- [ ] `model_json_schema()` produces valid JSON Schema for each model
- [ ] All 808+ tests pass unchanged (schemas are additive, no handler changes required)
- [ ] `send_typed(ws, msg)` utility uses `model_dump(exclude_none=True, by_alias=True)` — `by_alias=True` required for `party_chat`'s `from` field (Python reserved word, uses `Field(alias="from")`)

### Test Plan
- Unit tests: construct each outbound schema with sample data, verify `model_dump()` output
- Snapshot tests: `model_json_schema()` for each schema matches expected output

---

## Story 16.3: Protocol Specification Document

**Goal**: Generate a human-readable protocol specification document from the Pydantic schemas.

### Implementation

**New file**: `_bmad-output/planning-artifacts/protocol-spec.md`

A Markdown document containing:
1. **Transport**: WebSocket endpoint, JSON text frames, connection lifecycle
2. **Authentication flow**: Exact initial connection sequence with full message shapes — step-by-step from WebSocket open through first render (login → login_success → room_state, and reconnect → login_success → room_state + combat_state)
3. **Inbound message reference**: Table for each action with fields, types, required/optional, validation rules
4. **Outbound message reference**: Table for each type with fields, types, delivery scope (single/room/all/combat/party/trade)
5. **Delivery scopes**: Definition of each broadcast pattern
6. **Error handling**: Framework-level errors (invalid JSON, missing action, unknown action, auth errors)
7. **Combat flow**: State machine from `combat_start` → `combat_turn` (loop) → `combat_end`/`combat_fled`
8. **Trade flow**: State machine from `trade_request` → negotiate → `trade_result`
9. **Party flow**: invite → accept/reject → member management → disband
10. **Tile type enum**: Integer values and their meanings (from `server/room/tile.py:5-13`)

### Generation

A script `scripts/generate_protocol_doc.py` reads the Pydantic schemas from Stories 16.1 and 16.2 and generates the Markdown. This ensures the doc stays in sync with the schemas.

### Files Changed
- **New**: `_bmad-output/planning-artifacts/protocol-spec.md` (~400-500 lines)
- **New**: `scripts/generate_protocol_doc.py` (~100 lines) — `scripts/` directory does not exist yet, must be created
- **Modified**: `Makefile` (add `protocol-doc` and `check-protocol` targets)

### Acceptance Criteria
- [ ] Protocol spec covers all 21 inbound + 38 outbound message types
- [ ] Each message type lists: fields, types, required/optional, delivery scope
- [ ] Tile type enum documented with all 7 values (FLOOR=0 through STAIRS_DOWN=6)
- [ ] Combat, trade, and party state machines documented
- [ ] Script generates the doc from schema imports (not hand-written)
- [ ] `make protocol-doc` target regenerates protocol-spec.md from current schemas
- [ ] `make check-protocol` target compares generated doc with committed version, fails if out of date (prevents stale documentation when later stories modify schemas)
- [ ] Document is sufficient for a Godot developer to implement a client without reading server code
- [ ] Initial connection sequence documented step-by-step with exact message shapes: (1) open WebSocket, (2) send login/register, (3) receive login_success, (4) receive room_state, (5) start rendering — including reconnect variant with session_token
- [ ] Movement directions documented as `up/down/left/right` only; vertical transitions (`ascend/descend`) are exit-triggered when stepping onto `STAIRS_UP`/`STAIRS_DOWN` tiles, not player-input directions (see `DIRECTION_DELTAS` at `server/room/room.py:16-21`)

### Test Plan
- Run script and verify output is valid Markdown
- Cross-reference every message type in doc against handler code

---

## Story 16.4a: Refactor `grant_xp` — Separate Business Logic from Messaging

**Goal**: Split `grant_xp` (`server/core/xp.py:29-82`) into `apply_xp` (business logic + DB persistence) and `notify_xp` (WebSocket messaging), keeping a backward-compatible `grant_xp` wrapper. This is a prerequisite for Story 16.4 (combat service extraction) — it allows the combat service to call business logic without triggering WebSocket side effects.

### Current State

`grant_xp` (`server/core/xp.py:29-82`) mixes three layers in one function:

| Lines | Layer | What it does |
|-------|-------|-------------|
| 47-53 | Business | Apply CHA bonus, calculate final XP, update `player_entity.stats["xp"]` |
| 55-59 | Persistence | Write stats to DB via `player_repo.update_stats()` |
| 61-72 | Messaging | Send `xp_gained` WebSocket message to client |
| 74-81 | Messaging | Detect level-up threshold, send `level_up_available` via `send_level_up_available()` (`xp.py:99-133`) |

**3 call sites** (all pass through the mixed function):
- `server/net/handlers/combat.py:79` — combat victory XP
- `server/net/handlers/movement.py:326` — exploration XP (first room visit)
- `server/net/handlers/interact.py:112` — interaction XP (first object interaction)

**41 test references** across 7 test files.

### Implementation

**1. Result dataclass** — Add to `server/core/xp.py`:
```python
from dataclasses import dataclass

@dataclass
class XpResult:
    final_xp: int
    source: str
    detail: str
    new_total_xp: int
    level_up_available: bool
    new_level: int | None = None
```

**2. `apply_xp`** — Pure business logic + DB persistence, no WebSocket. Takes `entity_id` as a parameter (same as current `grant_xp` signature) — never reconstructs it from `player_db_id`:
```python
async def apply_xp(
    entity_id: str, player_entity, amount: int, source: str, detail: str,
    game, apply_cha_bonus: bool = True, session=None,
) -> XpResult:
    """Calculate XP, update entity stats, persist to DB. Returns result for caller to notify."""
    # CHA bonus (lines 47-51 of current grant_xp)
    if apply_cha_bonus:
        cha = player_entity.stats.get("charisma", 0)
        cha_multiplier = 1 + cha * settings.XP_CHA_BONUS_PER_POINT
        final_xp = math.floor(amount * cha_multiplier)
    else:
        final_xp = amount
    player_entity.stats["xp"] = player_entity.stats.get("xp", 0) + final_xp

    # Persist (lines 55-59 of current grant_xp)
    if session is not None:
        await player_repo.update_stats(session, player_entity.player_db_id, player_entity.stats)
    else:
        async with game.transaction() as s:
            await player_repo.update_stats(s, player_entity.player_db_id, player_entity.stats)

    # Level-up detection (lines 74-81 of current grant_xp, logic only)
    player_info = game.player_manager.get_session(entity_id)
    level_up = False
    new_level = None
    if player_info is not None:
        new_pending = get_pending_level_ups(player_entity.stats)
        old_pending = player_info.pending_level_ups
        if new_pending > old_pending:
            player_info.pending_level_ups = new_pending
            level_up = True
            new_level = player_entity.stats.get("level", 1) + 1

    return XpResult(
        final_xp=final_xp, source=source, detail=detail,
        new_total_xp=player_entity.stats["xp"],
        level_up_available=level_up, new_level=new_level,
    )
```

**3. `notify_xp`** — WebSocket messaging only:
```python
async def notify_xp(entity_id: str, result: XpResult, player_entity, game) -> None:
    """Send xp_gained and optional level_up_available messages."""
    ws = game.connection_manager.get_websocket(entity_id)
    if ws:
        try:
            await ws.send_json({
                "type": "xp_gained",
                "amount": result.final_xp,
                "source": result.source,
                "detail": result.detail,
                "new_total_xp": result.new_total_xp,
            })
        except Exception:
            pass
    if result.level_up_available:
        await send_level_up_available(entity_id, player_entity, game)
```

**4. Backward-compatible wrapper** — `grant_xp` stays, calls both:
```python
async def grant_xp(
    entity_id, player_entity, amount, source, detail, game,
    apply_cha_bonus=True, session=None,
) -> int:
    """Apply XP and notify. Backward-compatible wrapper."""
    result = await apply_xp(entity_id, player_entity, amount, source, detail, game, apply_cha_bonus, session)
    await notify_xp(entity_id, result, player_entity, game)
    return result.final_xp
```

All 3 call sites and 41 test references continue using `grant_xp` unchanged. After Story 16.4, the combat service can call `apply_xp` directly and let the handler call `notify_xp`.

### Files Changed
- **Modified**: `server/core/xp.py` (add `XpResult` dataclass, `apply_xp`, `notify_xp`; refactor `grant_xp` to call both)

### Acceptance Criteria
- [ ] `apply_xp` takes `entity_id` as first parameter (same as `grant_xp`) — never reconstructs entity_id from `player_db_id`
- [ ] `apply_xp` performs XP calculation + DB persistence, returns `XpResult`, sends NO WebSocket messages
- [ ] `notify_xp` sends `xp_gained` and optional `level_up_available` messages from `XpResult`
- [ ] `grant_xp` wrapper calls `apply_xp` then `notify_xp` — identical behavior to current implementation
- [ ] All 3 existing call sites (`combat.py:79`, `movement.py:326`, `interact.py:112`) unchanged
- [ ] All 808+ tests pass unchanged (41 references across 7 test files use `grant_xp` wrapper)
- [ ] `XpResult` dataclass has: `final_xp`, `source`, `detail`, `new_total_xp`, `level_up_available`, `new_level`

### Test Plan
- Unit tests for `apply_xp`: verify XP math, CHA bonus, DB persistence, no WebSocket calls
- Unit tests for `notify_xp`: verify `xp_gained` message sent, `level_up_available` conditionally sent
- Existing `grant_xp` tests pass unchanged (wrapper behavior identical)

---

## Story 16.4: Extract Combat Service Layer

**Goal**: Move 230 lines of combat business logic from `server/net/handlers/combat.py` (lines 22-251) into a dedicated `server/combat/service.py`.

### Current State

The combat handler file contains 7 business logic functions that belong in a service layer:

| Function | Lines | Responsibility |
|----------|-------|----------------|
| `_sync_combat_stats` | 22-38 | Sync combat stats to entity + DB |
| `_clean_player_combat_stats` | 53-68 | Clear transient stats, return alive status |
| `_award_combat_xp` | 71-79 | XP distribution wrapper |
| `_distribute_combat_loot` | 82-119 | Loot roll, DB persist, inventory update |
| `_handle_npc_combat_outcome` | 142-159 | Kill NPC or release from combat |
| `_respawn_defeated_players` | 162-173 | Respawn dead players on defeat |
| `_check_combat_end` | 176-251 | Combat-end orchestration hub |

Two message-construction functions stay in the handler:

| Function | Lines | Responsibility |
|----------|-------|----------------|
| `_broadcast_combat_state` | 41-50 | WebSocket broadcast of combat state |
| `_send_combat_end_message` | 122-139 | Build per-player combat_end message |

### Implementation

**New file**: `server/combat/service.py`

```python
"""Combat service — business logic for combat resolution and end-of-combat orchestration."""
from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any

from server.core.config import settings
from server.core.xp import grant_xp
from server.items.item_def import ItemDef
from server.items import item_repo as items_repo
from server.player import repo as player_repo

if TYPE_CHECKING:
    from server.app import Game

logger = logging.getLogger(__name__)


def clean_player_combat_stats(entity: Any, instance: Any, eid: str) -> bool:
    """Clear combat flags, sync final stats, return whether player is alive."""
    # ... (moved from combat.py:53-68, unchanged)


async def sync_combat_stats(instance: Any, game: Game) -> None:
    """Sync combat participant stats back to entities and persist to DB."""
    # ... (moved from combat.py:22-38, unchanged)


async def award_combat_xp(
    eid: str, entity: Any, rewards_per_player: dict,
    end_result: dict, game: Game, session: Any = None,
) -> None:
    """Award XP to a surviving victor."""
    # ... (moved from combat.py:71-79, unchanged)


async def distribute_combat_loot(
    eid: str, player_info: Any, loot_table_key: str,
    item_defs: dict[str, ItemDef], game: Game, session: Any = None,
) -> list[dict]:
    """Roll loot for a participant, persist to DB, update runtime inventory."""
    # ... (moved from combat.py:82-119, unchanged)


async def handle_npc_combat_outcome(instance: Any, end_result: dict, game: Game) -> None:
    """Kill NPC on victory, release on defeat."""
    # ... (moved from combat.py:142-159, unchanged)


async def respawn_defeated_players(
    participant_ids: list[str], end_result: dict, game: Game,
) -> None:
    """On defeat, respawn all dead players in town_square."""
    # ... (moved from combat.py:162-173, unchanged)


async def finalize_combat(instance: Any, game: Game) -> dict | None:
    """Check if combat is finished and handle end-of-combat orchestration.

    Returns per-player data dict for message construction, or None if combat continues.
    """
    # ... (moved from combat.py:176-251, refactored to return data instead of sending messages directly)
```

**Key refactoring in `finalize_combat`**: The current `_check_combat_end` calls `_send_combat_end_message` inline (line 246). The service version returns a structured result dict containing `participant_ids`, `end_result`, `rewards_per_player`, and `player_loot`. The handler is responsible for iterating and calling `_send_combat_end_message`.

**Handler update** (`server/net/handlers/combat.py`):
- Remove all 7 business functions
- Import from `server.combat.service`
- `handle_play_card`, `handle_pass_turn`, `handle_use_item_combat` call `service.sync_combat_stats()` then broadcast, then `service.finalize_combat()` then send messages
- `handle_flee` delegates flee-outcome logic to a new `service.handle_flee_outcome(instance, entity_id, game)` function

**Handler also updates for `handle_flee`**: Lines 302-306 (participant removal, in_combat flag) and 319-326 (NPC release, instance cleanup) move to `service.handle_flee_outcome`.

### Files Changed
- **New**: `server/combat/service.py` (~200 lines)
- **Modified**: `server/net/handlers/combat.py` (remove ~230 lines of business logic, add ~15 lines of service calls)
- **Modified**: `server/player/manager.py` (optional: `_cleanup_combat` could call service functions instead of inlining similar logic at lines 98-136)

### Acceptance Criteria
- [ ] All 7 business logic functions moved to `server/combat/service.py`
- [ ] `server/net/handlers/combat.py` contains only handler functions (input parsing, validation, response sending)
- [ ] `_broadcast_combat_state` and `_send_combat_end_message` remain in handler (they do WebSocket I/O)
- [ ] `finalize_combat` returns data; handler sends messages based on returned data
- [ ] `handle_flee` delegates outcome logic to `service.handle_flee_outcome`
- [ ] All 808+ tests pass — **known test patch impact**: 30 references across 3 files patch combat handler internals (`test_party_combat.py`:15, `test_loot.py`:12, `test_stats_persistence.py`:3). Patch targets change from `server.net.handlers.combat._check_combat_end` etc. to `server.combat.service.finalize_combat` etc. when functions move to service module.
- [ ] No new dependencies introduced — imports are the same, just relocated

### Test Plan
- All existing combat tests pass (tests exercise handlers, which now delegate to service)
- Optional: Add unit tests for service functions with mocked `game` object

---

## Story 16.5: Decompose `handle_login`

**Goal**: Break the 167-line `handle_login` function (`server/net/handlers/auth.py:112-278`) into focused helper functions.

### Current State

`handle_login` performs 12 distinct operations in a single function:
1. Input validation (lines 114-121)
2. DB lookup + password verification (lines 123-129)
3. Duplicate session handling (lines 132-142)
4. Stats resolution with defaults (lines 144-162)
5. Entity creation (lines 164-171)
6. Room resolution and placement (lines 173-201)
7. Room + connection registration (lines 203-205)
8. Inventory hydration from DB (lines 207-214)
9. Visited rooms restoration (lines 216-219)
10. Session creation (lines 222-229)
11. Response construction + broadcast (lines 231-268)
12. Pending level-up check (lines 271-278)

Additionally: `_DEFAULT_STATS` dict (lines 145-151) is reconstructed on every call. This is inefficient but safe for monkeypatching — a module-level constant would capture `settings.*` values at import time, breaking tests that patch settings.

### Implementation

Extract into focused helpers within the same file:

```python
def _default_stats() -> dict[str, int]:
    """Build default stats from current settings. Function (not constant) to support test monkeypatching."""
    return {
        "hp": settings.DEFAULT_BASE_HP, "max_hp": settings.DEFAULT_BASE_HP,
        "attack": settings.DEFAULT_ATTACK, "xp": 0, "level": 1,
        "strength": settings.DEFAULT_STAT_VALUE, "dexterity": settings.DEFAULT_STAT_VALUE,
        "constitution": settings.DEFAULT_STAT_VALUE, "intelligence": settings.DEFAULT_STAT_VALUE,
        "wisdom": settings.DEFAULT_STAT_VALUE, "charisma": settings.DEFAULT_STAT_VALUE,
    }


async def _resolve_stats(player: Player, session: AsyncSession) -> dict:
    """Resolve player stats: apply defaults for first-time, restore for returning."""
    db_stats = player.stats or {}
    if not db_stats:
        stats = _default_stats()
        stats["max_hp"] = settings.DEFAULT_BASE_HP + stats["constitution"] * settings.CON_HP_PER_POINT
        stats["hp"] = stats["max_hp"]
        await player_repo.update_stats(session, player.id, stats)
    else:
        stats = {**_default_stats(), **db_stats}
    return stats


async def _resolve_room_and_place(
    entity: PlayerEntity, player: Player, room_key: str,
    game: Game, session: AsyncSession,
) -> tuple[str, RoomInstance]:
    """Load room if needed, find safe spawn position, update DB if relocated."""
    room = game.room_manager.get_room(room_key)
    if room is None:
        room_db = await room_repo.get_by_key(session, room_key)
        if room_db is None:
            raise ValueError("Room not found")  # Caller must catch and send error JSON
        room = game.room_manager.load_room(room_db)

    is_first_login = player.current_room_id is None
    needs_relocation = is_first_login or not room.is_walkable(entity.x, entity.y)
    if needs_relocation:
        sx, sy = room.get_player_spawn()
        if not room.is_walkable(sx, sy):
            sx, sy = room.find_first_walkable()
        entity.x = sx
        entity.y = sy
        await player_repo.update_position(session, player.id, room_key, sx, sy)
    return room_key, room


async def _hydrate_inventory(player: Player, session: AsyncSession) -> Inventory:
    """Rebuild runtime Inventory from DB state."""
    db_inventory = player.inventory or {}
    if db_inventory:
        all_items = await item_repo.get_all(session)
        item_defs = {i.item_key: ItemDef.from_db(i) for i in all_items}
        return Inventory.from_dict(db_inventory, lambda k: item_defs.get(k))
    return Inventory()


def _build_login_response(db_id: int, entity_id: str, username: str, stats: dict,
                          session_token: str | None = None) -> dict:
    """Construct the login_success JSON payload.

    Uses field parameters (not Player DB model) so it works for both:
    - handle_login: pass player.id, player.username
    - handle_reconnect Case 1: pass session.db_id, entity.name
    """
    result = {
        "type": "login_success",
        "player_id": db_id,
        "entity_id": entity_id,
        "username": username,
        "stats": {
            "hp": stats.get("hp", settings.DEFAULT_BASE_HP),
            "max_hp": stats.get("max_hp", settings.DEFAULT_BASE_HP),
            "attack": stats.get("attack", settings.DEFAULT_ATTACK),
            "xp": stats.get("xp", 0),
            "level": stats.get("level", 1),
            "xp_for_next_level": stats.get("level", 1) * settings.XP_LEVEL_THRESHOLD_MULTIPLIER,
            "xp_for_current_level": (stats.get("level", 1) - 1) * settings.XP_LEVEL_THRESHOLD_MULTIPLIER,
            "strength": stats.get("strength", settings.DEFAULT_STAT_VALUE),
            "dexterity": stats.get("dexterity", settings.DEFAULT_STAT_VALUE),
            "constitution": stats.get("constitution", settings.DEFAULT_STAT_VALUE),
            "intelligence": stats.get("intelligence", settings.DEFAULT_STAT_VALUE),
            "wisdom": stats.get("wisdom", settings.DEFAULT_STAT_VALUE),
            "charisma": stats.get("charisma", settings.DEFAULT_STAT_VALUE),
        },
    }
    if session_token is not None:
        result["session_token"] = session_token
    return result
```

**Refactored `handle_login`** becomes ~50-60 lines: validation, auth, duplicate handling, then calls to helpers, ending with response + broadcast. The transaction scope remains the same.

### Known Issue: Variable Shadowing

Line 274 of the current code shadows the DB `session` variable with `session = game.player_manager.get_session(entity_id)`. The refactored version renames this to `player_session` to eliminate the shadow.

### Files Changed
- **Modified**: `server/net/handlers/auth.py` (~same total lines, refactored into 4-5 helpers + smaller `handle_login`)

### Acceptance Criteria
- [ ] `handle_login` is ≤60 lines
- [ ] `_default_stats()` is a module-level function (not a constant) — reads `settings.*` on each call to support test monkeypatching
- [ ] `_resolve_stats`, `_resolve_room_and_place`, `_hydrate_inventory`, `_build_login_response` are separate functions
- [ ] `_build_login_response` takes field parameters (`db_id`, `entity_id`, `username`, `stats`, `session_token`) — NOT a `Player` DB model, enabling reuse in `handle_reconnect` (Story 16.9)
- [ ] Variable shadowing of `session` on line 274 is eliminated
- [ ] All 808+ tests pass unchanged

### Test Plan
- Existing login/auth tests exercise all paths
- No new tests needed unless helpers are independently testable

---

## Story 16.6: TradeManager Constructor Injection

**Goal**: Replace `TradeManager.set_connection_manager()` setter with constructor injection, matching `PartyManager` pattern.

### Current State

```python
# server/app.py:43-44
self.trade_manager = TradeManager()
self.trade_manager.set_connection_manager(self.connection_manager)

# server/app.py:45 (PartyManager uses constructor injection)
self.party_manager = PartyManager(connection_manager=self.connection_manager)
```

`TradeManager.__init__` (`server/trade/manager.py:21-26`) takes no arguments. `set_connection_manager` (`server/trade/manager.py:28-30`) stores the reference. There is no circular dependency preventing constructor injection — `ConnectionManager` is already created on line 37 of `server/app.py`, before both `TradeManager` and `PartyManager`.

### Implementation

**`server/trade/manager.py`**:
```python
class TradeManager:
    def __init__(self, *, connection_manager: ConnectionManager) -> None:
        self._trades: dict[str, Trade] = {}
        self._player_trade: dict[str, str] = {}
        self._cooldowns: dict[str, float] = {}
        self._trade_locks: dict[str, asyncio.Lock] = {}
        self._connection_manager = connection_manager
```

Remove `set_connection_manager` method entirely (lines 28-30).

**`server/app.py`**:
```python
# Replace lines 43-44:
self.trade_manager = TradeManager(connection_manager=self.connection_manager)
```

### Files Changed
- **Modified**: `server/trade/manager.py` (change `__init__`, remove `set_connection_manager`)
- **Modified**: `server/app.py` (change line 43-44 to single constructor call)
- **Modified**: Test files that construct `TradeManager` (need to pass `connection_manager` or a mock)

### Acceptance Criteria
- [ ] `TradeManager.__init__` takes `connection_manager` as keyword argument
- [ ] `set_connection_manager` method is removed
- [ ] `server/app.py` creates `TradeManager` with constructor injection (single line, like `PartyManager`)
- [ ] All 808+ tests pass (test patches updated if needed)

### Test Plan
- Existing trade tests cover all paths
- Verify tests that mock/construct `TradeManager` are updated

---

## Story 16.7: Request-Response Correlation (Optional `request_id`)

**Goal**: Add optional `request_id` echo-back to the WebSocket protocol for client-side async correlation.

### Motivation

Game engine clients (Godot, Unity, Unreal) use async networking. Without request-response correlation, a client sending `{"action": "move", "direction": "up"}` cannot easily determine which incoming message is the response (could be `entity_moved`, `error`, `combat_start`, or `nearby_objects`). A `request_id` field allows the client to match responses.

### Implementation

**Protocol change**: If the client includes a `request_id` field in any inbound message, the server echoes it back in the *direct* response (not in broadcasts to other players).

**Schema change** (`server/net/schemas.py`):
```python
class InboundMessage(BaseModel):
    action: str
    request_id: str | None = None
```

**Router change** (`server/net/message_router.py`):
The router already passes the full `data` dict to handlers. Handlers that send a direct response to the acting player include `request_id` if present:
```python
# Utility in server/net/message_router.py or schemas.py:
def with_request_id(response: dict, data: dict) -> dict:
    """Add request_id to response if it was present in the request."""
    rid = data.get("request_id")
    if rid is not None:
        response["request_id"] = rid
    return response
```

Handlers that send direct responses (not broadcasts) call `with_request_id(response, data)` before `send_json`.

**Framework-level errors** in `server/app.py` websocket_endpoint (lines 392-403):
- "Invalid JSON" error: `data` doesn't exist, so no `request_id` can be extracted. This is correct — unparseable input has no correlation ID.
- "Missing action field" error: `data` exists and may contain `request_id`. Apply `with_request_id` here.

**Scope**: Only direct responses to the requesting player include `request_id`. Broadcasts (`entity_moved` to other players, `entity_entered`, etc.) never include it. This keeps the protocol clean — `request_id` is a client convenience, not a protocol requirement.

**Backward-compatible**: `request_id` is optional. Clients that don't send it see no change. The web-demo client does not need to be updated.

### Files Changed
- **Modified**: `server/net/schemas.py` (add `request_id` to `InboundMessage` base)
- **New utility**: `with_request_id()` function (in `server/net/schemas.py` or `server/net/message_router.py`)
- **Modified**: All WebSocket handler files that send direct responses (10 handler files; `admin.py` is REST-only and unchanged)

### Acceptance Criteria
- [ ] `request_id` is an optional string field on all inbound messages
- [ ] Direct responses to the requesting player echo `request_id` when present
- [ ] Broadcasts to other players never include `request_id`
- [ ] Requests without `request_id` produce responses without `request_id` (no `null` field)
- [ ] All 808+ tests pass unchanged (they don't send `request_id`)
- [ ] Framework "Missing action field" error includes `request_id` when present in `data`
- [ ] Framework "Invalid JSON" error correctly omits `request_id` (data unavailable)
- [ ] Web-demo client works unchanged

### Test Plan
- New tests: send messages with `request_id`, verify echo in response
- New tests: send messages without `request_id`, verify no `request_id` in response
- New tests: verify broadcasts to other players don't include `request_id`

---

## Story 16.8: Heartbeat / Connection Health

**Goal**: Add WebSocket ping/pong heartbeat to detect dead connections and enable client-side connection health monitoring.

### Motivation

Game engine clients on unreliable connections (mobile, Wi-Fi transitions) may silently disconnect. Without heartbeat, the server holds stale sessions until the next WebSocket I/O fails. This delays cleanup (player remains "in room" as a ghost) and wastes resources.

### Current State

The WebSocket endpoint (`server/app.py:386-406`) has no keep-alive mechanism. Stale connections are only detected when `WebSocketDisconnect` is raised on the next `receive_text()` call, which only happens when the client sends a message.

### Implementation

**Approach**: Use a server-sent `ping` message (application-level, not WebSocket-layer ping/pong) on a configurable interval. If the client does not respond with `pong` within a timeout, the server closes the connection.

**Config** (`server/core/config.py`):
```python
HEARTBEAT_INTERVAL_SECONDS: int = 30
HEARTBEAT_TIMEOUT_SECONDS: int = 10
```

**Server-side**: After successful login or reconnect (NOT at WebSocket accept — unauthenticated connections have no entity_id and would be disconnected by heartbeat timeout before the player can type credentials), spawn a background `asyncio.Task` stored in `Game._heartbeat_tasks: dict[str, asyncio.Task]` (keyed by entity_id). The task:
1. Sends `{"type": "ping"}` every `HEARTBEAT_INTERVAL_SECONDS`
2. Expects `{"action": "pong"}` within `HEARTBEAT_TIMEOUT_SECONDS`
3. If no pong received, closes the WebSocket (triggers `handle_disconnect`)

**Lifecycle management** — Add to `Game.__init__`:
```python
self._heartbeat_tasks: dict[str, asyncio.Task] = {}  # entity_id -> heartbeat Task
```

Cancellation:
- **On disconnect** (`handle_disconnect`): Cancel and remove the heartbeat task before any other cleanup
- **On shutdown** (`Game.shutdown`): Cancel all heartbeat tasks before session iteration
- **On reconnect** (`handle_reconnect`): Cancel old task, start new one for the new WebSocket

**Client-side**: Clients respond to `{"type": "ping"}` with `{"action": "pong"}`. The web-demo client adds a simple handler in `dispatchMessage()`.

**Alternative considered**: WebSocket-layer ping/pong (Starlette supports this via `WebSocket.send({"type": "websocket.ping"})`). However, application-level ping is more debuggable, visible in message logs, and works consistently across all game engine WebSocket implementations.

### Files Changed
- **Modified**: `server/core/config.py` (add `HEARTBEAT_INTERVAL_SECONDS`, `HEARTBEAT_TIMEOUT_SECONDS`)
- **Modified**: `server/app.py` (`Game.__init__` adds `_heartbeat_tasks` dict, cancellation in `handle_disconnect` and `shutdown`)
- **Modified**: `server/net/handlers/auth.py` (heartbeat task spawned after successful login/reconnect, stored in `game._heartbeat_tasks[entity_id]`)
- **Modified**: `server/net/schemas.py` (add `PongMessage` inbound schema)
- **Modified**: `server/net/outbound_schemas.py` (add `PingMessage` outbound schema)
- **Modified**: `server/app.py` (register `pong` handler)
- **Modified**: `web-demo/js/game.js` (add `ping` handler in `dispatchMessage()`)

### Acceptance Criteria
- [ ] Server sends `{"type": "ping"}` every `HEARTBEAT_INTERVAL_SECONDS` to each connected client
- [ ] Client responds with `{"action": "pong"}`
- [ ] `pong` handler uses `@requires_auth` — unauthenticated connections never receive pings (heartbeat starts after login), stray pongs rejected
- [ ] Server closes WebSocket if pong not received within `HEARTBEAT_TIMEOUT_SECONDS`
- [ ] `handle_disconnect` fires normally on heartbeat-timeout close (session cleanup, state save, broadcast)
- [ ] Heartbeat interval and timeout are configurable via `Settings`
- [ ] Web-demo client handles ping/pong
- [ ] All 808+ tests pass (tests don't trigger heartbeat timeouts)
- [ ] Heartbeat task starts AFTER successful login/reconnect (not at WebSocket accept) — unauthenticated connections must not be timed out
- [ ] Heartbeat tasks stored in `Game._heartbeat_tasks[entity_id]` for lifecycle management
- [ ] `handle_disconnect` cancels heartbeat task BEFORE any other cleanup
- [ ] `Game.shutdown()` cancels all heartbeat tasks before session iteration
- [ ] Reconnect cancels old heartbeat task and starts new one for new WebSocket

### Test Plan
- Unit test: heartbeat task sends ping at interval
- Integration test: client that responds to pong stays connected
- Integration test: client that ignores pong gets disconnected after timeout
- Verify shutdown cleans up heartbeat tasks

---

## Story 16.9: Session Tokens for Reconnection

**Goal**: Issue a server-generated session token on login so clients can reconnect without re-sending credentials. This is mandatory for mobile support where OS backgrounding kills WebSocket connections.

### Motivation

Currently, when a WebSocket connection drops (`server/app.py:405-406`, `WebSocketDisconnect`), `handle_disconnect` calls `player_manager.cleanup_session()` (`server/player/manager.py:55-78`), which immediately:
1. Cancels trades (line 71)
2. Removes from combat (line 72)
3. Removes from party (line 73)
4. Saves state to DB (line 74)
5. Removes entity from room + broadcasts `entity_left` (line 75)
6. Disconnects from `ConnectionManager` (line 77)
7. Removes session from `PlayerManager` (line 78)

After this, the player is fully gone. Reconnection requires a fresh login with username/password, which re-creates everything from scratch via `handle_login` (`server/net/handlers/auth.py:112-278`).

The web-demo already stores credentials and auto-resends on reconnect (`web-demo/js/game.js:314-316`), but this requires the client to hold the plaintext password in memory — unacceptable for a production game client.

### Current State: `PlayerSession` dataclass

```python
# server/player/session.py:11-20
@dataclass
class PlayerSession:
    entity: PlayerEntity
    room_key: str
    db_id: int
    inventory: Inventory | None = None
    visited_rooms: set[str] = field(default_factory=set)
    pending_level_ups: int = 0
```

No token field exists. No token generation/validation infrastructure exists.

### Implementation

**1. Token generation** — New file `server/player/tokens.py`:
```python
"""Session token generation and validation."""
import secrets
import time

from server.core.config import settings


def generate_session_token() -> str:
    """Generate a cryptographically random session token."""
    return secrets.token_urlsafe(32)


class TokenStore:
    """In-memory token-to-player mapping with expiry."""

    def __init__(self) -> None:
        self._tokens: dict[str, tuple[int, float]] = {}  # token -> (db_id, expires_at)

    def issue(self, db_id: int) -> str:
        """Issue a new token for a player DB ID. Invalidates any previous token."""
        self._purge_expired()  # Prevent unbounded memory growth
        # Revoke existing tokens for this db_id
        self._tokens = {
            t: v for t, v in self._tokens.items() if v[0] != db_id
        }
        token = generate_session_token()
        expires_at = time.time() + settings.SESSION_TOKEN_TTL_SECONDS
        self._tokens[token] = (db_id, expires_at)
        return token

    def _purge_expired(self) -> None:
        """Remove all expired tokens from the store."""
        now = time.time()
        self._tokens = {t: v for t, v in self._tokens.items() if v[1] > now}

    def validate(self, token: str) -> int | None:
        """Return db_id if token is valid and not expired, else None."""
        entry = self._tokens.get(token)
        if entry is None:
            return None
        db_id, expires_at = entry
        if time.time() > expires_at:
            self._tokens.pop(token, None)
            return None
        return db_id

    def revoke(self, token: str) -> None:
        """Revoke a specific token."""
        self._tokens.pop(token, None)

    def revoke_for_player(self, db_id: int) -> None:
        """Revoke all tokens for a player."""
        self._tokens = {
            t: v for t, v in self._tokens.items() if v[0] != db_id
        }
```

**2. Config** — Add to `server/core/config.py`:
```python
SESSION_TOKEN_TTL_SECONDS: int = 300  # 5 minutes
```

**3. Game integration** — Add `TokenStore` to `Game.__init__` (`server/app.py:35-50`):
```python
from server.player.tokens import TokenStore
# In __init__:
self.token_store = TokenStore()
```

**4. Login response** — Modify `handle_login` (`server/net/handlers/auth.py`) to include `session_token` in the `login_success` response:
```python
token = game.token_store.issue(player.id)
# Add to login_success message:
"session_token": token,
```

**5. Reconnect action** — New handler `handle_reconnect` in `server/net/handlers/auth.py`:
```python
async def handle_reconnect(websocket: WebSocket, data: dict, *, game: Game) -> None:
    """Handle the 'reconnect' action: validate token, restore session."""
    token = data.get("session_token", "")
    if not token:
        await websocket.send_json({"type": "error", "detail": "Missing session_token"})
        return

    db_id = game.token_store.validate(token)
    if db_id is None:
        await websocket.send_json({"type": "error", "detail": "Invalid or expired token"})
        return

    # Consume old token, issue new one
    game.token_store.revoke(token)
    entity_id = f"player_{db_id}"
    new_token = game.token_store.issue(db_id)

    # SECURITY: If this WebSocket already has a different player logged in,
    # clean up that session first (prevents session hijacking via stolen token
    # on an already-authenticated connection — same pattern as handle_login:134-142)
    existing_entity = game.connection_manager.get_entity_id(websocket)
    if existing_entity is not None and existing_entity != entity_id:
        await game.player_manager.cleanup_session(existing_entity, game)

    # THREE OUTCOMES:
    #
    # Case 1: Session exists with disconnected_at set → GRACE PERIOD RESUME
    #   Player disconnected recently, session still alive in memory.
    #   Cancel deferred cleanup timer, clear disconnected_at, re-register WebSocket.
    #   Send login_success + room_state + combat_state (if in combat).
    #   Skip DB restore — session already has everything.
    #
    # Case 2: No session exists → FULL RESTORE FROM DB
    #   Grace period expired (session cleaned up) or server restarted.
    #   Token proves identity — treat like handle_login but skip password check.
    #   Use Story 16.5's helper functions: _resolve_stats, _resolve_room_and_place,
    #   _hydrate_inventory, _build_login_response.
    #
    # Case 3: Token invalid/expired → handled above (returns error)

    existing_session = game.player_manager.get_session(entity_id)

    if existing_session and existing_session.disconnected_at is not None:
        # Case 1: Grace period resume
        handle = game._cleanup_handles.pop(entity_id, None)
        if handle is not None:
            handle.cancel()
        existing_session.disconnected_at = None
        existing_session.entity.connected = True  # Mark entity as connected (see Fix 2 below)
        game.connection_manager.connect(entity_id, websocket, existing_session.room_key, name=...)
        # Send login_success (with new_token) + room_state + combat_state if applicable
        # Broadcast entity_entered to room so other players see the player is back
        await game.connection_manager.broadcast_to_room(
            existing_session.room_key,
            {"type": "entity_entered", "entity": {
                "id": entity_id, "name": existing_session.entity.name,
                "x": existing_session.entity.x, "y": existing_session.entity.y,
                "level": existing_session.entity.stats.get("level", 1),
            }},
            exclude=entity_id,
        )
    else:
        # Case 2: Full restore from DB (reuses 16.5's helpers)
        async with game.transaction() as session:
            player = await player_repo.get_by_id(session, db_id)
            if player is None:
                await websocket.send_json({"type": "error", "detail": "Player not found"})
                return
            # Same restore flow as handle_login: _resolve_stats, _resolve_room_and_place, etc.
```

**6. Register handler** — Add to `Game._register_handlers()` (`server/app.py:142-232`):
```python
self.router.register(
    "reconnect", lambda ws, d: handle_reconnect(ws, d, game=self)
)
```

**7. Revoke on logout** — In `handle_logout` (`server/net/handlers/auth.py:27-39`), revoke the player's token:
```python
game.token_store.revoke_for_player(player_info.db_id)
```

### Files Changed
- **New**: `server/player/tokens.py` (~60 lines)
- **Modified**: `server/core/config.py` (add `SESSION_TOKEN_TTL_SECONDS`)
- **Modified**: `server/app.py` (add `TokenStore` to `Game.__init__`, register `reconnect` handler)
- **Modified**: `server/net/handlers/auth.py` (add `session_token` to login response, add `handle_reconnect`, revoke on logout)
- **Modified**: `server/net/outbound_schemas.py` (add `session_token: str | None` to `LoginSuccessMessage`)

### Acceptance Criteria
- [ ] `login_success` response includes a `session_token` field (string)
- [ ] Client can send `{"action": "reconnect", "session_token": "..."}` to resume a session
- [ ] Reconnect outcome 1 (grace period resume): valid token + disconnected session → restore connection, cancel cleanup timer, send full state
- [ ] Reconnect outcome 2 (full DB restore): valid token + no session → restore from DB using Story 16.5 helpers (like login, skip password)
- [ ] Reconnect outcome 3 (invalid): invalid/expired token → error message
- [ ] Successful reconnect returns `login_success` (with new token) + `room_state` + combat state if applicable
- [ ] Token is single-use (consumed on reconnect, new token issued)
- [ ] Token expires after `SESSION_TOKEN_TTL_SECONDS` (default 300s / 5 min)
- [ ] Explicit logout revokes the token
- [ ] If WebSocket already has a different player's session, clean it up before reconnecting (prevents session hijacking via stolen token)
- [ ] Invalid/expired tokens return `{"type": "error", "detail": "Invalid or expired token"}`
- [ ] `TokenStore._purge_expired()` called on every `issue()` — prevents unbounded memory growth from abandoned tokens
- [ ] All 808+ existing tests pass unchanged
- [ ] Web-demo client can use token for reconnection instead of stored credentials

### Test Plan
- Unit tests for `TokenStore`: issue, validate, revoke, expiry, revoke_for_player, single-use
- Integration tests: login → get token → disconnect → reconnect with token → verify session restored
- Integration tests: token expiry, double-use rejection, logout revocation

---

## Story 16.10a: Combat Turn Timeout Enforcement

**Goal**: Implement the combat turn timeout so that inactive or disconnected players' turns auto-pass after `COMBAT_TURN_TIMEOUT_SECONDS` (default 30s). This is a prerequisite for Story 16.10 (grace period) — without it, a disconnected player blocks all other combat participants indefinitely.

### Current State

`COMBAT_TURN_TIMEOUT_SECONDS: int = 30` exists in config (`server/core/config.py:32`) but **no code reads or enforces it**. The setting was scaffolded in Epic 1 (Story 1.1) but never wired into combat. `CombatInstance` (`server/combat/instance.py`) and `CombatManager` (`server/combat/manager.py`) have zero timeout/timer references.

Currently, if it's a player's turn and they don't act, combat waits forever.

### Implementation

**Approach**: Use `loop.call_later()` pattern (consistent with `TradeManager` timeouts in `server/trade/manager.py:96-103`). When a turn begins, schedule a timeout. If the player acts before the timeout, cancel it. If it fires, auto-pass the turn.

**1. Turn timer on CombatInstance** — Add to `server/combat/instance.py`:
```python
import asyncio

class CombatInstance:
    def __init__(self, ...):
        # ... existing fields ...
        self._turn_timeout_handle: asyncio.TimerHandle | None = None
        self._turn_timeout_callback: Callable | None = None  # set by caller
```

**2. Timeout scheduling** — New methods on `CombatInstance`:
```python
def set_turn_timeout_callback(self, callback: Callable[[str, CombatInstance], None]) -> None:
    """Set the callback invoked when a turn times out. Called once by Game setup."""
    self._turn_timeout_callback = callback

def _schedule_turn_timeout(self) -> None:
    """Schedule auto-pass for the current turn. Called after each turn advance."""
    self._cancel_turn_timeout()
    if not self.participants or self._turn_timeout_callback is None:
        return
    current = self.get_current_turn()
    if current is None:
        return
    loop = asyncio.get_running_loop()
    self._turn_timeout_handle = loop.call_later(
        settings.COMBAT_TURN_TIMEOUT_SECONDS,
        self._turn_timeout_callback,
        current,
        self,
    )

def _cancel_turn_timeout(self) -> None:
    """Cancel any pending turn timeout."""
    if self._turn_timeout_handle is not None:
        self._turn_timeout_handle.cancel()
        self._turn_timeout_handle = None
```

**3. Wire into turn lifecycle** — Separate setup from activation to avoid chicken-and-egg ordering:
- `_schedule_turn_timeout()` called inside `_advance_turn()` only (after each turn transition)
- `_cancel_turn_timeout()` called at the **START** of `play_card()`, `pass_turn()`, `use_item()`, `flee()` — **before validation** (prevents race where timeout fires between action start and turn advance). Also called in `remove_participant()` and when combat ends. If the action fails validation (wrong turn, insufficient energy), `_schedule_turn_timeout()` is called again to restart the timer.
- **NOT** called from `add_participant()` — participants are added during setup before the callback is registered
- New public method `start_turn_timer()` explicitly kicks off the first timeout after setup is complete

```python
def start_turn_timer(self) -> None:
    """Activate turn timeout for the current turn. Call AFTER set_turn_timeout_callback."""
    self._schedule_turn_timeout()
```

**4. Timeout callback** — Placement depends on sprint ordering:
- **If implemented after 16.4** (Sprint 2, 16.4 done first): callback lives in `server/combat/service.py`
- **If implemented before 16.4** (Sprint 2, 16.10a runs independently): callback lives in `server/net/handlers/combat.py`, then moves to `service.py` when 16.4 extracts the service

The callback auto-passes the turn:
```python
# In server/combat/service.py (or combat.py if service doesn't exist yet):
def on_turn_timeout(entity_id: str, instance: CombatInstance) -> None:
    """Auto-pass when a player's turn times out."""
    loop = asyncio.get_running_loop()
    loop.create_task(_handle_turn_timeout(entity_id, instance, game))

async def _handle_turn_timeout(entity_id: str, instance: CombatInstance, game: Game) -> None:
    """Execute auto-pass and broadcast result."""
    try:
        result = await instance.pass_turn(entity_id)
    except ValueError:
        return  # Not their turn anymore (race with reconnect action)
    await _broadcast_combat_state(instance, result, game)
    await _check_combat_end(instance, game)
```

**5. Register callback AND start timer on combat start** — In `server/net/handlers/movement.py` where combat is initiated (the `_handle_mob_encounter` flow), after `combat_manager.start_combat()`:
```python
# Import from wherever the callback lives (service.py if 16.4 done, combat.py if not)
from server.combat.service import on_turn_timeout  # or from server.net.handlers.combat

# Order matters: register callback FIRST, then start timer
instance.set_turn_timeout_callback(on_turn_timeout)
instance.start_turn_timer()  # Activates first turn timeout
```

This ordering guarantees the callback exists before any timeout fires. `_advance_turn()` handles subsequent turns automatically.

**6. Turn timeout timestamp in combat state** — Include `turn_timeout_at` (Unix timestamp, float) in `combat_start` and `combat_turn` outbound messages so clients can render a countdown timer ("Player B's turn — 23s remaining"):

```python
# In CombatInstance.get_state() — add field:
"turn_timeout_at": self._turn_timeout_at  # float (time.time() + COMBAT_TURN_TIMEOUT_SECONDS), or None if no timeout
```

Store `self._turn_timeout_at = time.time() + settings.COMBAT_TURN_TIMEOUT_SECONDS` in `_schedule_turn_timeout()`, clear to `None` in `_cancel_turn_timeout()`.

### Files Changed
- **Modified**: `server/combat/instance.py` (add `_turn_timeout_handle`, `_turn_timeout_at`, `_schedule_turn_timeout`, `_cancel_turn_timeout`, `set_turn_timeout_callback`; `get_state()` includes `turn_timeout_at`)
- **Modified**: `server/combat/service.py` OR `server/net/handlers/combat.py` (add `on_turn_timeout` callback + `_handle_turn_timeout` async handler — if 16.4 has completed, lives in service.py; if not yet, lives in combat.py handler and moves to service.py when 16.4 runs)
- **Modified**: `server/net/handlers/movement.py` (register callback on combat start)

### Acceptance Criteria
- [ ] When a player's turn begins (via `_advance_turn` or `start_turn_timer`), a timeout is scheduled for `COMBAT_TURN_TIMEOUT_SECONDS` (default 30)
- [ ] `start_turn_timer()` is called AFTER `set_turn_timeout_callback()` — ordering enforced at call site, not inside CombatInstance
- [ ] `add_participant()` does NOT schedule a timeout (avoids chicken-and-egg with callback registration)
- [ ] Timer cancelled at the START of play_card/pass_turn/use_item/flee — before action validation, not after (prevents race condition in party combat where timeout fires between action start and turn advance)
- [ ] If action validation fails (wrong turn, insufficient energy), timer is re-scheduled
- [ ] If the timeout fires, the turn auto-passes (same behavior as `pass_turn`)
- [ ] All combat participants receive the `combat_turn` broadcast after auto-pass (same as manual pass)
- [ ] Timer is cancelled when combat ends or participant is removed
- [ ] Timer pattern uses `loop.call_later` + `loop.create_task` consistent with `TradeManager._handle_timeout`
- [ ] `COMBAT_TURN_TIMEOUT_SECONDS` setting (already at `server/core/config.py:32`) is now actually enforced
- [ ] `combat_start` and `combat_turn` messages include `turn_timeout_at` (Unix timestamp float) — enables client-side countdown UI
- [ ] All 808+ existing tests pass (combat tests may need timeout handling in setup)

### Test Plan
- Unit test: turn timeout fires after configured seconds, auto-passes the turn
- Unit test: player action cancels pending timeout
- Unit test: timeout during disconnected player's turn auto-passes correctly
- Integration test: combat with 2 players, one goes idle — turn auto-passes, other player can continue
- Integration test: rapid actions don't leave orphan timers

---

## Story 16.10: Disconnected Player Grace Period

**Goal**: When a WebSocket drops, keep the player's in-game state (room presence, combat participation, party membership) for a configurable grace period instead of immediately cleaning up.

### Motivation

Currently `handle_disconnect` (`server/app.py:353-359`) immediately calls `cleanup_session` which removes the player from combat, trade, party, room, and memory. On mobile, iOS kills WebSocket connections after 5-30 seconds of backgrounding. A player checking a text message during their combat turn would lose their combat, party, and room position.

The grace period keeps the player "present" in the game world. If they reconnect within the window (via Story 16.9's token), they seamlessly resume. If the timer expires, full cleanup runs.

### Current State: Immediate cleanup

```python
# server/app.py:353-359
async def handle_disconnect(self, websocket: WebSocket) -> None:
    entity_id = self.connection_manager.get_entity_id(websocket)
    if entity_id is None:
        return
    await self.player_manager.cleanup_session(entity_id, self)
```

### Implementation

**1. Config** — Add to `server/core/config.py`:
```python
DISCONNECT_GRACE_SECONDS: int = 120  # 2 minutes
```

**2. PlayerSession state** — Add `disconnected_at` field to `PlayerSession` (`server/player/session.py:11-20`):
```python
@dataclass
class PlayerSession:
    entity: PlayerEntity
    room_key: str
    db_id: int
    inventory: Inventory | None = None
    visited_rooms: set[str] = field(default_factory=set)
    pending_level_ups: int = 0
    disconnected_at: float | None = None  # timestamp, None = connected
```

**3. Track deferred cleanup handles** — Add to `Game.__init__` (`server/app.py:35-50`):
```python
self._cleanup_handles: dict[str, asyncio.TimerHandle] = {}  # entity_id -> pending cleanup timer
```

**4. Modify `handle_disconnect`** — Instead of immediate cleanup, mark session as disconnected and schedule deferred cleanup. Store the `TimerHandle` for cancellation on reconnect. Uses `loop.create_task` pattern consistent with `TradeManager._handle_timeout` (`server/trade/manager.py:110-133`):
```python
# server/app.py — modified handle_disconnect
async def handle_disconnect(self, websocket: WebSocket) -> None:
    entity_id = self.connection_manager.get_entity_id(websocket)
    if entity_id is None:
        return

    # During shutdown, let shutdown() handle cleanup — don't schedule deferred timers
    if self._shutting_down:
        return

    session = self.player_manager.get_session(entity_id)
    if session is None:
        self.connection_manager.disconnect(entity_id)
        return

    # Disconnect WebSocket mapping but keep session alive
    self.connection_manager.disconnect(entity_id)

    # Mark as disconnected
    session.disconnected_at = time.time()
    session.entity.connected = False  # Visible to other players in room_state

    # Cancel trades immediately (can't hold other players hostage)
    await self.player_manager._cleanup_trade(entity_id, self)

    # Cancel any existing deferred cleanup timer (defensive: handles disconnect→reconnect→disconnect)
    old_handle = self._cleanup_handles.pop(entity_id, None)
    if old_handle is not None:
        old_handle.cancel()

    # Schedule deferred full cleanup (store handle for cancellation on reconnect)
    loop = asyncio.get_running_loop()

    def _on_grace_expired() -> None:
        loop.create_task(self._deferred_cleanup(entity_id))

    handle = loop.call_later(settings.DISCONNECT_GRACE_SECONDS, _on_grace_expired)
    self._cleanup_handles[entity_id] = handle
```

**5. Deferred cleanup** — New method on `Game`:
```python
async def _deferred_cleanup(self, entity_id: str) -> None:
    """Run full cleanup if player hasn't reconnected within grace period."""
    self._cleanup_handles.pop(entity_id, None)  # Remove handle reference

    session = self.player_manager.get_session(entity_id)
    if session is None:
        return  # Already cleaned up (reconnected then logged out, etc.)
    if session.disconnected_at is None:
        return  # Player reconnected — no cleanup needed

    # Grace period expired — delegate to PlayerManager's public method
    # (trade already cleaned up in handle_disconnect)
    await self.player_manager.deferred_cleanup(entity_id, self)
```

**6. Reconnect cancels deferred cleanup** — In `handle_reconnect` (Story 16.9), when the player reconnects, cancel the pending cleanup timer:
```python
existing_session = game.player_manager.get_session(entity_id)
if existing_session and existing_session.disconnected_at is not None:
    # Cancel pending deferred cleanup timer
    handle = game._cleanup_handles.pop(entity_id, None)
    if handle is not None:
        handle.cancel()

    # Player is within grace period — restore connection
    existing_session.disconnected_at = None  # Mark as connected
    game.connection_manager.connect(entity_id, websocket, existing_session.room_key, name=player.username)
    # Send full state resync (login_success + room_state + combat_state if in combat)
    # Skip room placement, inventory hydration, etc. — session already has everything
```

**7. Shutdown cancels all pending cleanup timers** — Modify `Game.shutdown()` (`server/app.py:112-140`) to cancel all deferred cleanup timers before iterating sessions:
```python
async def shutdown(self) -> None:
    await self.scheduler.stop()

    # Cancel all pending deferred cleanup timers
    for handle in self._cleanup_handles.values():
        handle.cancel()
    self._cleanup_handles.clear()

    # ... rest of existing shutdown logic (iterate sessions, save, notify, close)
```

**6. Combat turn timeout interaction** — When a disconnected player's combat turn arrives, the turn timeout (Story 16.10a) auto-passes after `COMBAT_TURN_TIMEOUT_SECONDS` (default 30s, `server/core/config.py:32`). **Note:** The config setting exists but is not currently implemented in `server/combat/` — Story 16.10a adds the enforcement. Story 16.10 depends on 16.10a.

**7. Disconnected entity visibility** — During grace period, the entity remains in `RoomInstance._entities` but has no WebSocket. To avoid confusing UX, add a `connected: bool` field to `PlayerEntity` (`server/player/entity.py:5-15`):

```python
@dataclass
class PlayerEntity:
    id: str
    name: str
    x: int
    y: int
    player_db_id: int
    stats: dict = field(default_factory=dict)
    in_combat: bool = False
    connected: bool = True  # NEW — set False on disconnect, True on reconnect/login
```

Set `entity.connected = False` in `handle_disconnect` (after marking `disconnected_at`).
Set `entity.connected = True` in reconnect Case 1 and fresh login.

`RoomInstance.get_state()` reads `entity.connected` directly — **no signature change needed**, no `connection_manager` dependency:

```python
# In RoomInstance.get_state() — entity serialization (server/room/room.py:187-190):
{"id": e.id, "name": e.name, "x": e.x, "y": e.y,
 "level": e.stats.get("level", 1) if hasattr(e, "stats") else 1,
 "connected": getattr(e, "connected", True)}
```

Using `getattr` with default `True` ensures backward compatibility — existing `PlayerEntity` instances without the field (if any) default to connected.

### What Gets Cleaned Up Immediately vs. Deferred

| System | Immediate (on disconnect) | Deferred (after grace period) |
|--------|--------------------------|-------------------------------|
| Trade | Yes — can't hold other player hostage | N/A |
| WebSocket mapping | Yes — connection is dead | N/A |
| Combat | No — player stays in combat | Yes — removed from instance |
| Party | No — player stays in party | Yes — removed, succession handled |
| Room presence | No — entity stays in room (with `connected: false`) | Yes — removed, `entity_left` broadcast |
| Session/stats | No — kept in memory | Yes — saved to DB, session removed |

**8. Fresh login during grace period** — If a player disconnects (grace period starts) and then logs in from another device via `handle_login` (not reconnect), `handle_login` must detect the grace-period session. Currently `handle_login` only checks `connection_manager.get_websocket(entity_id)` (line 135), which returns `None` during grace period (WebSocket mapping removed). The fix: `handle_login` must ALSO check `player_manager.has_session(entity_id)`. If a session exists, cancel the deferred cleanup timer and run full cleanup before creating the new session:

```python
# In handle_login, after entity_id = f"player_{player.id}" (line 132):

# Check for grace-period session (WebSocket gone, session still alive)
existing_session = game.player_manager.get_session(entity_id)
if existing_session is not None and game.connection_manager.get_websocket(entity_id) is None:
    # Cancel deferred cleanup timer
    cleanup_handle = game._cleanup_handles.pop(entity_id, None)
    if cleanup_handle is not None:
        cleanup_handle.cancel()
    # Cancel heartbeat task if any
    hb_task = game._heartbeat_tasks.pop(entity_id, None)
    if hb_task is not None:
        hb_task.cancel()
    # Full cleanup of old session (combat, party, save, room removal)
    await game.player_manager.cleanup_session(entity_id, game)
```

Without this, a fresh login during grace period silently overwrites the session without cleaning up combat/party state — leaking dangling references in `combat_manager` and `party_manager`.

**9. Public `deferred_cleanup` method on `PlayerManager`** — `Game._deferred_cleanup` currently calls private methods (`_cleanup_combat`, `_cleanup_party`, `_save_player_state`, `_remove_from_room`) on `PlayerManager`. This violates the convention from Epic 15 where managers expose public APIs. Fix: add a public `deferred_cleanup` method:

```python
# server/player/manager.py — new public method
async def deferred_cleanup(self, entity_id: str, game: Game) -> None:
    """Deferred cleanup after grace period — skips trade (already cleaned) and WS disconnect."""
    session = self.get_session(entity_id)
    if session is None:
        return
    entity = session.entity
    room_key = session.room_key
    await self._cleanup_combat(entity_id, entity, game)
    await self._cleanup_party(entity_id, game)
    await self._save_player_state(entity_id, session, game)
    await self._remove_from_room(entity_id, room_key, game)
    self.remove_session(entity_id)
```

Then `Game._deferred_cleanup` calls `self.player_manager.deferred_cleanup(entity_id, self)` — no private method access from outside `PlayerManager`.

### Files Changed
- **Modified**: `server/player/entity.py` (add `connected: bool = True` field)
- **Modified**: `server/player/session.py` (add `disconnected_at` field)
- **Modified**: `server/player/manager.py` (add public `deferred_cleanup` method)
- **Modified**: `server/app.py` (`Game.__init__` adds `_cleanup_handles`, `handle_disconnect` → deferred cleanup + sets `entity.connected = False`, `_deferred_cleanup` calls `player_manager.deferred_cleanup`, `shutdown` cancels pending timers)
- **Modified**: `server/core/config.py` (add `DISCONNECT_GRACE_SECONDS`)
- **Modified**: `server/net/handlers/auth.py` (`handle_login` checks `player_manager.has_session()` for grace-period sessions; `handle_reconnect` cancels timer, sets `entity.connected = True`, broadcasts `entity_entered` to room)
- **Modified**: `server/room/room.py` (`get_state()` includes `connected` from `PlayerEntity.connected` — no signature change)

### Acceptance Criteria
- [ ] WebSocket drop does NOT immediately remove player from room, combat, or party
- [ ] Trades ARE cancelled immediately on disconnect (prevent blocking other players)
- [ ] Player entity remains visible in room to other players during grace period
- [ ] `room_state` entity data includes `connected: bool` field — `false` for disconnected players, enabling client-side "away" rendering
- [ ] If player reconnects within grace period: session seamlessly restored, `disconnected_at` cleared
- [ ] If grace period expires: full cleanup runs (combat, party, room, DB save)
- [ ] Combat turns auto-pass for disconnected players via Story 16.10a's turn timeout
- [ ] `DISCONNECT_GRACE_SECONDS` is configurable (default 120)
- [ ] Deferred cleanup timer handle stored on `Game._cleanup_handles[entity_id]` for cancellation
- [ ] Reconnecting player cancels their pending cleanup timer
- [ ] `Game.shutdown()` cancels all pending cleanup timers before session iteration
- [ ] Uses `loop.create_task` pattern consistent with `TradeManager._handle_timeout` (`server/trade/manager.py:110-133`)
- [ ] `handle_disconnect` checks `self._shutting_down` and returns early if true — prevents stray deferred timers during shutdown
- [ ] `handle_disconnect` cancels any existing timer for the entity before storing a new one (idempotent for disconnect→reconnect→disconnect)
- [ ] `handle_login` checks `player_manager.has_session()` for grace-period sessions — cancels timer + runs full cleanup before creating new session (prevents combat/party state leak on login from another device)
- [ ] `PlayerManager.deferred_cleanup()` is a PUBLIC method — `Game._deferred_cleanup` does not call private `PlayerManager` methods directly
- [ ] **FIRST SUB-TASK before any code changes**: Add `autouse` fixture to `tests/conftest.py` that sets `DISCONNECT_GRACE_SECONDS=0` — this preserves immediate-cleanup behavior for all 808+ existing tests. Only new grace-period-specific tests override to non-zero values.
- [ ] All 808+ existing tests pass — **known test impact**: `test_game.py` (11 refs), `test_party.py` (9 refs), `test_combat_multiplayer.py` (3 refs), `test_exploration_xp.py` (2 refs) — all protected by the `autouse` fixture above

### Test Plan
- Unit test: disconnect → verify session still exists with `disconnected_at` set
- Unit test: disconnect → reconnect within grace → verify session restored, `disconnected_at` cleared
- Unit test: disconnect → wait past grace → verify full cleanup ran
- Unit test: disconnect → verify trade cancelled immediately, combat/party/room preserved
- Integration test: player in combat disconnects → reconnects → can still play cards
- Integration test: player in combat disconnects → grace expires → removed from combat, others notified
- Integration test: player in combat disconnects → fresh login from another device → old combat state cleaned up, new session works correctly

---

## Story 16.11: Message Acknowledgment IDs

**Goal**: Add sequence numbers to outbound messages so clients can detect missed messages after reconnection and request resync.

### Motivation

When a WebSocket drops mid-combat-turn, the client doesn't know if the server received its last action. After reconnecting (Story 16.9), the client needs to know: "What was the last message I successfully received?" and "Did the server process my last action?"

Without acknowledgment, the client must assume the worst and request a full state resync every time — even if nothing was missed.

### Implementation

**1. Per-player message sequence counter on `ConnectionManager`** — Add to `server/net/connection_manager.py`. The counter lives on `ConnectionManager` (not `PlayerSession`) because message sequencing is a networking concern. This preserves the existing architecture where `ConnectionManager` has zero dependencies on player/combat/trade modules:

```python
class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}
        self._player_rooms: dict[str, str] = {}
        self._ws_to_entity: dict[int, str] = {}
        self._name_to_entity: dict[str, str] = {}
        self._entity_to_name: dict[str, str] = {}
        self._msg_seq: dict[str, int] = {}  # entity_id -> outbound sequence counter

    def connect(self, entity_id, websocket, room_key, name=""):
        # ... existing logic ...
        self._msg_seq.setdefault(entity_id, 0)  # Initialize on first login; preserve on reconnect

    def disconnect(self, entity_id):
        # ... existing logic ...
        # NOTE: do NOT remove _msg_seq here — grace period needs it to survive disconnect

    def get_msg_seq(self, entity_id: str) -> int:
        """Return the current outbound sequence number for a player."""
        return self._msg_seq.get(entity_id, 0)

    def clear_msg_seq(self, entity_id: str) -> None:
        """Remove sequence tracking for a player (on full cleanup after grace period)."""
        self._msg_seq.pop(entity_id, None)

    async def send_to_player_seq(self, entity_id: str, message: dict) -> None:
        """Send a JSON message with a sequence number attached."""
        seq = self._msg_seq.get(entity_id, 0) + 1
        self._msg_seq[entity_id] = seq
        message["seq"] = seq
        ws = self._connections.get(entity_id)
        if ws:
            await ws.send_json(message)
```

**2. Reconnect includes `last_seq`** — The reconnect action accepts an optional `last_seq`:
```json
{"action": "reconnect", "session_token": "...", "last_seq": 42}
```

The server compares `last_seq` with `connection_manager.get_msg_seq(entity_id)`. If they match, the client is up to date. If they differ, the server sends a full state resync (which it already does on reconnect).

**3. Clean up `_msg_seq` on full session cleanup** — In `PlayerManager._remove_from_room` or `cleanup_session`, call `connection_manager.clear_msg_seq(entity_id)` when the session is fully removed (not during grace period disconnect).

**4. Gradual adoption** — Not all `send_json` calls need to use `send_to_player_seq` immediately. Priority messages:
- `combat_turn` — most important (did my card play go through?)
- `combat_end` — was the combat resolved?
- `trade_update` — was my offer registered?
- `xp_gained`, `level_up_available` — was XP awarded?

Other messages (`entity_moved`, `chat`, `entity_entered`) are cosmetic and will be corrected by the full state resync on reconnect. No sequence number needed for those.

### Files Changed
- **Modified**: `server/net/connection_manager.py` (add `_msg_seq` dict, `get_msg_seq`, `clear_msg_seq`, `send_to_player_seq` methods)
- **Modified**: `server/net/handlers/auth.py` (reconnect handler checks `last_seq`)
- **Modified**: `server/player/manager.py` (call `clear_msg_seq` in full cleanup)
- **Modified**: `server/core/xp.py` (`notify_xp` switches from `ws.send_json` to `connection_manager.send_to_player_seq` for `xp_gained` and `level_up_available` — priority messages per gradual adoption list)
- **Modified**: Key handlers that send critical state changes (combat, trade — gradual adoption)

### Acceptance Criteria
- [ ] Critical outbound messages include a `seq` field (integer, monotonically increasing per player)
- [ ] `ConnectionManager._msg_seq[entity_id]` tracks the counter (initialized via `setdefault` on connect — preserves value on reconnect, starts at 0 on first login)
- [ ] `ConnectionManager` has no new dependencies on `PlayerManager` or any game logic module
- [ ] Reconnect action accepts optional `last_seq` field
- [ ] If `last_seq` matches `msg_seq`, server responds with "up to date" indication
- [ ] If `last_seq` differs or is missing, server sends full state resync
- [ ] Sequence counter resets on fresh login via `clear_msg_seq` in logout/full-cleanup path (not on reconnect — `setdefault` preserves it)
- [ ] Broadcasts to other players do NOT include `seq` (only direct messages to the acting player)
- [ ] All 808+ existing tests pass unchanged (seq field is additive)

### Test Plan
- Unit test: `send_to_player_seq` increments `msg_seq` and attaches `seq` to message
- Integration test: login → receive messages with seq → disconnect → reconnect with `last_seq` → verify resync behavior
- Integration test: reconnect without `last_seq` → verify full resync sent

---

## Story 16.12: Chat Markdown Support

**Goal**: Enable markdown-formatted text in chat messages. The server remains **fully client-agnostic** — it passes message content through as-is. Rendering and sanitization are **client concerns**.

### Design Principles

1. **Server is markdown-agnostic** — treats chat messages as opaque strings. Does NOT strip HTML tags or modify printable content. Rationale: Godot uses BBCode, Unity uses TMP tags, web uses HTML — server-side HTML stripping is an HTML-specific defense that corrupts legitimate messages (e.g., `x < y` becomes `x  y`) and provides zero protection for non-HTML clients.
2. **Each client owns its rendering security** — web-demo HTML-escapes before markdown substitution; Godot escapes BBCode; Unity escapes TMP tags.
3. **Server adds a `format` metadata field** — read from configurable `settings.CHAT_FORMAT`, signals clients to apply markdown rendering. Clients that don't support markdown ignore the field.
4. **Server does content-neutral validation only** — max length (existing `MAX_CHAT_MESSAGE_LENGTH: 500` at `server/core/config.py:70`), strip control characters (null bytes, etc.). These are game rules, not rendering rules.

### Implementation

**1. Config** — Add to `server/core/config.py`:
```python
CHAT_FORMAT: str = "markdown"  # "plain" or "markdown"
```

**2. Server: content-neutral validation** — Add control character stripping to `server/net/handlers/chat.py` (before existing length check at line 29):
```python
message = message.translate({i: None for i in range(32) if i not in (10, 13)})
```

**3. Protocol change** — Add `"format": settings.CHAT_FORMAT` to:
- `chat` messages (`server/net/handlers/chat.py:47-52, 57-62`)
- `party_chat` messages (`server/net/handlers/party.py:497`)
- `announcement` messages (`server/app.py:238-242`)

**4. Web-demo client** — Update `appendChat()` (`web-demo/js/game.js:1023-1029`):
- HTML-escape **first** (`<` → `&lt;`, `>` → `&gt;`, `&` → `&amp;`)
- Process code spans **first** (replace with placeholders to prevent formatting inside code)
- Then apply bold/italic/strikethrough regex
- Reinsert code spans
- **NO link or image markdown** (eliminates `javascript:` URI XSS vectors)
- Set `div.innerHTML` with the safe result

### Files Changed
- **Modified**: `server/core/config.py` (add `CHAT_FORMAT`)
- **Modified**: `server/net/handlers/chat.py` (control char strip, add `format` to messages)
- **Modified**: `server/net/handlers/party.py` (add `format` to `party_chat`)
- **Modified**: `server/app.py` (add `format` to `announcement`)
- **Modified**: `server/net/outbound_schemas.py` (add `format` field to chat/party_chat/announcement schemas)
- **Modified**: `web-demo/js/game.js` (safe markdown rendering in `appendChat`)

### Acceptance Criteria
- [ ] Chat messages include `"format"` field from `settings.CHAT_FORMAT` (default `"markdown"`)
- [ ] `CHAT_FORMAT` configurable — set to `"plain"` to disable markdown signaling
- [ ] Server does NOT strip HTML tags or modify printable message content
- [ ] Server strips control characters (null bytes, etc.) — content-neutral validation
- [ ] Web-demo: HTML-escapes BEFORE markdown regex (XSS prevention)
- [ ] Web-demo: code spans processed FIRST (prevents formatting inside code)
- [ ] Web-demo: safe subset only — bold, italic, code, strikethrough. NO links, NO images
- [ ] Clients that ignore `format` field see plain text (backward compatible)
- [ ] All 808+ existing tests pass unchanged

### Test Plan
- Unit test: control character stripping removes null bytes, preserves `\n`
- Unit test: `<script>alert(1)</script>` passes through server unmodified
- Integration test: `format` field matches `settings.CHAT_FORMAT`
- Web-demo: `**bold**` renders bold, `` `code` `` renders monospace
- Web-demo: `<script>` in chat renders as escaped text, not executed
- Web-demo: `` `**not bold**` `` renders literally in code span

---

## Dependency Graph

```
--- Sprint 1: Protocol (unblocks Godot client) ---
16.1 (Inbound schemas) ──┐
                         ├── 16.3 (Protocol doc)
16.2 (Outbound schemas) ─┘
16.2 ── 16.12 (Chat markdown)

--- Sprint 2: Refactoring + Bug Fix (parallel with Sprint 1 if 2 devs) ---
16.4a (grant_xp refactor) → 16.4 (Combat service)
16.5 (Login decompose) ── independent
16.6 (Trade DI) ───────── independent
16.10a (Turn timeout) ─── independent (callback in combat.py if before 16.4; in service.py if after)

--- Sprint 3: Resilience (depends on Sprints 1+2) ---
16.1 ──┬── 16.7 (request_id)
       └── 16.8 (Heartbeat)
16.5 ──── 16.9 (Session tokens) ──┐
                                   ├── 16.10 (Grace period)
16.10a ────────────────────────────┘
16.10 ── 16.11 (Message ack)
```

**Sprint 1** (protocol — Godot blocker): 16.1 → 16.2 → 16.3, 16.12
**Sprint 2** (refactoring + bug fix): 16.4a → 16.4, 16.5, 16.6, 16.10a (all independent after 16.4a→16.4)
**Sprint 3a** (client polish — depends on Sprint 1): 16.7, 16.8 (independent, can be parallel)
**Sprint 3b** (resilience — depends on Sprints 2+3a): 16.9 → 16.10 → 16.11 (sequential chain)

**Sprint 1 + Sprint 2 can run in parallel** if different developers work on them (no file overlap between protocol schemas and server refactoring).

**16.10a placement note**: If 16.10a runs in Sprint 2 before 16.4, the timeout callback lives in `server/net/handlers/combat.py`. When 16.4 later extracts the combat service, the callback moves to `server/combat/service.py`. Both placements are specified in Story 16.10a.

---

## Risk Assessment

| Story | Risk | Mitigation |
|-------|------|------------|
| 16.1 | Schema validation may reject messages that previously passed silently | Run full test suite; review any test failures as potential real bugs |
| 16.2 | Outbound schemas may miss fields in rare code paths | Generate schemas from actual `send_json` calls, verify completeness |
| 16.4a | `grant_xp` wrapper must be exactly equivalent to current behavior | Wrapper calls `apply_xp` then `notify_xp` in sequence — same order as current inline code. 41 test references verify behavior. |
| 16.4 | Combat service extraction touches many files | Story 16.4a handles the `grant_xp` concern first. Service extraction is a pure move — no logic changes, just relocation. |
| 16.7 | `request_id` in broadcasts would break the "no correlation in pushes" principle | Strict rule: only direct responses include `request_id` |
| 16.8 | Heartbeat tasks may leak if not properly cancelled during shutdown | Test shutdown path explicitly; use `asyncio.TaskGroup` or manual cancellation |
| 16.9 | Token leakage if `TokenStore` is not cleaned up | Tokens auto-expire; `revoke_for_player` called on logout; single-use on reconnect |
| 16.10 | Deferred cleanup timer leaks on shutdown | `Game.shutdown()` must clean up all sessions regardless of grace period — iterate all sessions and run cleanup |
| 16.10a | Turn timeout callback races with player action | `pass_turn` raises `ValueError` if not player's turn — timeout handler catches this and exits cleanly |
| 16.10 | Combat turns blocked by disconnected player | Story 16.10a implements turn timeout enforcement — prerequisite dependency ensures this is resolved before grace period |
| 16.11 | Sequence numbers add complexity without solving the fundamental problem (full resync needed anyway) | Keep implementation minimal — `seq` on critical messages only, full resync as fallback. Don't over-engineer. |
| 16.12 | Future developer adds link/image markdown to web-demo client, reintroducing XSS | Spec explicitly forbids link/image markdown. Only bold/italic/code/strikethrough allowed. Document this as a security constraint. |

---

## Architecture Decision Records

### ADR-16-1: WebSocket Retained as Primary Transport
WebSocket + JSON is the only transport satisfying all constraints (Godot, Unity, Unreal, web browser, existing FastAPI server). Raw TCP/UDP disqualified by browser requirement. gRPC disqualified by lack of bidirectional streaming in `grpc-web`. MQTT rejected for poor game engine support and awkward request-response model. HTTP SSE+POST viable as fallback but adds unnecessary channel-splitting complexity.
**Trade-offs accepted**: Mobile OS kills WebSocket on backgrounding (mitigated by 16.9+16.10); no built-in session resumption (mitigated by 16.9+16.11); single-process ceiling ~5-8K connections (accepted at current scale). Future binary serialization (MessagePack/Protobuf) is a serialization change, not a transport change.

### ADR-16-2: In-Memory TokenStore, Not DB-Backed
Token TTL is 300s — too short-lived for DB persistence. Server restart kills all in-memory state (rooms, combat, parties) anyway, so a surviving DB token points to nothing. `_purge_expired()` on `issue()` prevents memory leak. Zero Alembic migration needed. DB-backed tokens would add latency, transaction complexity, and migration for no benefit.

### ADR-16-3: `msg_seq` on ConnectionManager, Not PlayerSession
Message sequencing is a networking concern. `ConnectionManager` has zero game-logic imports (hardened in Epics 14-15). Putting `msg_seq` on `PlayerSession` would require `send_to_player_seq` to accept `PlayerManager` — introducing cross-layer coupling. Counter survives grace-period via `setdefault` on `connect()`. Cleanup direction is correct: game layer (`PlayerManager`) tells network layer to `clear_msg_seq`.

### ADR-16-4: Server Client-Agnostic for Chat — No HTML Stripping
Godot uses BBCode, Unity uses TMP tags, web uses HTML. Server-side HTML stripping corrupts legitimate `<`/`>` in messages, provides no protection against markdown-based XSS (`[click](javascript:...)`), and is meaningless for non-HTML clients. Server does content-neutral validation only (max length, control character stripping). Each client handles its own rendering security.

### ADR-16-5: `PlayerEntity.connected` Field, Not `get_state()` Signature Change
Adding `connected: bool` to `PlayerEntity` avoids changing `get_state()`'s zero-parameter signature (5 call sites) and prevents `RoomInstance` from depending on `ConnectionManager`. The `connected` status is a property of entity state, not computed from network state. Set explicitly in `handle_disconnect` (False) and login/reconnect (True).

### ADR-16-6: Deferred Cleanup via `call_later` + Public `PlayerManager.deferred_cleanup()`
Timer pattern matches `TradeManager._handle_timeout` (consistency). Handles stored in `Game._cleanup_handles` for cancellation on reconnect/shutdown. Cancel-before-store prevents orphaned timers. Public `deferred_cleanup()` respects module boundary — `Game._deferred_cleanup` does not call private `PlayerManager` methods. Trade cleanup is immediate (can't hold other player hostage). `_shutting_down` check prevents stray timers during shutdown. `autouse` test fixture with `DISCONNECT_GRACE_SECONDS=0` preserves all 808 existing tests.

### ADR-16-7: `_default_stats()` as Function, Not Module-Level Constant
Module-level constants capture `settings.*` at import time. Tests use `monkeypatch.setattr(settings, ...)` pattern (verified in `test_stat_combat.py:365,383,401,418`). A constant would freeze values and break patching. Function call overhead (small dict construction) is negligible — login happens once per session.
