# Codebase Evaluation: The-Ages-II

**Date**: 2026-04-12
**Scope**: Full codebase review across 6 dimensions
**Codebase**: 808 tests passing, Epics 1-15 complete

---

## 1. Web UX: Proof-of-Concept, No Game Logic

**Verdict: PASS — Clean thin client.**

The `web-demo/` directory contains 4 files:
- `index.html` — HTML layout (auth forms, game viewport, combat overlay, level-up modal)
- `js/game.js` — 1900-line WebSocket client (state management, message dispatch, DOM rendering)
- `css/style.css` — 825-line dark-theme styling
- `jsconfig.json` — IDE type-checking config

**Evidence of compliance:**
- Every gameplay action sends `sendAction(action, data)` to the server via WebSocket (e.g., `sendAction('move', { direction })`, `sendAction('play_card', { card_key })`)
- Zero damage calculations, combat resolution, loot generation, stat formulas, or AI behavior in client code
- Movement sends direction to server — no client-side collision detection or validation
- Level-up modal sends `sendAction('level_up', { stats: [...] })` — stat changes validated and applied server-side
- XP thresholds, HP bonuses, and combat effects all arrive from server responses
- ISS-021 through ISS-028 cleanup (completed in prior epics) removed all game logic leaks

**Minor display-only logic (acceptable, not game logic):**
- `tileClass()` — maps tile type integers to CSS class names (visual only)
- `formatEffect()` — formats card effect objects into human-readable strings for card UI
- `setHpBarColor()` — HP bar color based on percentage thresholds (<=25% red, <=50% yellow)
- `showLevelUpModal()` computes `val + 1` for "X -> X+1" preview text (UI convenience; server validates actual changes)

---

## 2. Server Codebase Organization and Structure

**Verdict: STRONG — Well-organized domain-driven modular structure.**

### Module Layout (8 top-level packages under `server/`)

| Package | Responsibility | Key Files |
|---------|---------------|-----------|
| `core/` | Cross-cutting: config, database, scheduler, event bus, effects | `config.py`, `database.py`, `scheduler.py`, `events.py`, `effects/` |
| `net/` | Network: WebSocket connections, message routing, auth middleware, handlers | `connection_manager.py`, `message_router.py`, `auth_middleware.py`, `handlers/` |
| `player/` | Player domain: DB model, repo, entity, session, auth (bcrypt), manager | `models.py`, `repo.py`, `entity.py`, `session.py`, `auth.py`, `manager.py` |
| `room/` | Room domain: DB models, repo, tiles, room instance, manager, NPC, spawn | `models.py`, `repo.py`, `room.py`, `manager.py`, `npc.py`, `provider.py`, `spawn_repo.py`, `tile.py`, `objects/` |
| `combat/` | Combat: instance (turn resolution, DoT, effects), manager, card system | `instance.py`, `manager.py`, `cards/` |
| `items/` | Items: definitions, repo, inventory | `item_def.py`, `item_repo.py`, `inventory.py`, `models.py` |
| `trade/` | Trade: session dataclass, manager (state machine) | `session.py`, `manager.py` |
| `party/` | Party: party dataclass, manager (invite tracking, succession) | `party.py`, `manager.py` |

### Architectural Strengths

1. **No circular imports**: `TYPE_CHECKING` guards used consistently (e.g., `server/player/manager.py:5,11-12`, `server/core/scheduler.py:8,14-15`, `server/net/auth_middleware.py:5,11-12`)
2. **Clean repository pattern**: All repos are module-level async functions taking `AsyncSession` as first arg — testable and database-agnostic (e.g., `player_repo.get_by_username(session, username)` at `server/player/repo.py:10`)
3. **`@requires_auth` decorator** (`server/net/auth_middleware.py:15-35`): Eliminates auth boilerplate across all handlers, injects `entity_id` and `player_info` kwargs
4. **Centralized config**: All game balance values in `Settings(BaseSettings)` (`server/core/config.py:9-137`) — no hardcoded HP, attack, stat defaults, etc.
5. **Error-isolated EventBus**: `emit()` wraps each subscriber in try/except (`server/core/events.py:23-27`)
6. **`PlayerManager` owns session lifecycle**: Well-factored cleanup with clear sub-steps (`server/player/manager.py:55-78`)
7. **Stats whitelist**: `_STATS_WHITELIST` in `server/player/repo.py:85-89` strips non-whitelisted keys before persisting

### Areas for Improvement

1. **`Game` class is a service locator/god object** (`server/app.py:32-50`): Owns every manager, the session factory, NPC templates, loot tables, and several business methods (`kill_npc`, `respawn_player`, `_reset_player_stats`, `_find_spawn_point`). Acceptable at current scale (74 Python files, 808 tests) but would need decomposition for a much larger codebase.
2. **Combat handler contains ~250 lines of business logic** (`server/net/handlers/combat.py:22-251`): Functions like `_check_combat_end`, `_sync_combat_stats`, `_distribute_combat_loot`, `_award_combat_xp` are business logic living in the handler file. These would be better placed in a combat service layer.
3. **`handle_login` is 167 lines** (`server/net/handlers/auth.py:112-278`): Mixes authentication, entity creation, room placement, inventory hydration, visited room tracking, and session setup. Should be decomposed into smaller functions.
4. **`TradeManager` uses setter injection** (`server/app.py:44`, `server/trade/manager.py:28-30`) while `PartyManager` uses constructor injection (`server/app.py:45`). Minor inconsistency.

---

## 3. Extensibility: Adding Features and Plugins

**Verdict: GOOD — Easy to extend via registry patterns, but no auto-discovery.**

### Handler Registration

The `MessageRouter` (`server/net/message_router.py:9-28`) is a dictionary mapping `action` strings to async callables. Adding a new action requires:
1. Write a handler function with signature `async def handle_foo(websocket, data, *, game, entity_id, player_info)` (with `@requires_auth` decorator)
2. Add one `self.router.register("action_name", lambda ws, d: handler(ws, d, game=self))` line in `Game._register_handlers()` (`server/app.py:142-232`)

### Effect System

The `EffectRegistry` (`server/core/effects/registry.py:13-38`) follows the same pattern. Adding a new combat effect (e.g., "stun", "freeze") requires:
1. Write an async handler function matching `EffectHandler` signature
2. Register it in `create_default_registry()` (`server/core/effects/registry.py:41-55`)

Currently supports: `damage`, `heal`, `shield`, `dot`, `draw`.

### Room Object System

The `RoomObject` registry (`server/room/objects/registry.py:10-15`) maps object type strings to `InteractiveObject` subclasses. Adding a new interactable (e.g., "trap", "portal") requires implementing a subclass and registering it.

### What's Missing

- **No auto-discovery**: All wiring is explicit in `_register_handlers()`. There's no decorator-based self-registration or plugin loading mechanism. This is predictable but requires manual maintenance.
- **No plugin system**: Third-party extensions would need to modify core files. For the current project scope, this is acceptable.

---

## 4. Database Migration Readiness (PostgreSQL)

**Verdict: EXCELLENT — PostgreSQL migration is essentially configuration-only.**

### Current Setup

- SQLAlchemy async with `aiosqlite` driver for SQLite (`server/core/database.py:1-29`)
- 7 DB models across the codebase: `Player` (`server/player/models.py`), `Room`, `RoomState`, `PlayerObjectState` (`server/room/models.py`), `SpawnCheckpoint` (`server/room/spawn_models.py`), `Card` (`server/combat/cards/models.py`), `Item` (`server/items/models.py`)
- Alembic for migrations (2 migrations exist)
- `create_all` also runs at startup (belt-and-suspenders with Alembic, see `server/core/database.py:20-29`)

### Why PostgreSQL Migration Is Ready

1. **Config already handles it**: `DATABASE_URL` accepts any SQLAlchemy URL via environment variable (`server/core/config.py:79`). The `ALEMBIC_DATABASE_URL` property (`server/core/config.py:86-92`) strips async drivers for Alembic, handling both `sqlite+aiosqlite -> sqlite` and `postgresql+asyncpg -> postgresql`.

2. **Conditional connection pooling**: Pool settings only applied when URL is NOT SQLite (`server/core/database.py:10-14`), which is correct since SQLite doesn't support connection pooling.

3. **No SQLite-specific SQL**: All queries use SQLAlchemy ORM constructs (`select()`, `update()`) — no raw SQL, no `sqlite3`-specific functions.

4. **JSON columns work natively**: `Mapped[dict]` and `Mapped[list]` use SQLAlchemy's `JSON` type, which maps to PostgreSQL's `JSON` column type. For `JSONB` (better indexing and performance), a migration would need to use `sqlalchemy.dialects.postgresql.JSONB`, but the existing `JSON` type works without changes.

5. **Alembic in place**: Migration infrastructure exists. The `alembic/env.py` uses the same config settings.

### Migration Steps

1. Change `DATABASE_URL` env var to `postgresql+asyncpg://...`
2. Install `asyncpg` (`pip install asyncpg`)
3. Run `alembic upgrade head`

### Minor Considerations

- **Stats stored as JSON blobs** (`server/player/models.py:16`): Works fine in PostgreSQL (JSONB is fast), but at scale, normalized stat columns would enable SQL-level aggregation and indexing.
- **`visited_rooms` as JSON list** (`server/player/models.py:22`): Comment in code already notes "Consider PlayerRoomVisit table for production scale."

---

## 5. Game Engine Client Integration (Godot, Unity, Unreal)

**Verdict: GOOD — Standard WebSocket + JSON protocol, engine-agnostic.**

### Connection Flow

1. Open WebSocket to `ws://<host>:8000/ws/game`
2. Send `{"action": "login", "username": "...", "password": "..."}` or `{"action": "register", ...}`
3. On `login_success`, store `entity_id` and `stats`
4. Server immediately follows with `room_state` containing full tile grid, entities, NPCs, exits, objects
5. Listen for server-pushed messages (`entity_moved`, `combat_start`, `chat`, etc.)
6. Send actions as JSON with the `action` field

### Engine Integration Strengths

- **Transport-agnostic**: WebSocket + JSON is universally supported (Godot `WebSocketPeer`, Unity `NativeWebSocket`/`ClientWebSocket`, Unreal `IWebSocket`)
- **No client-side game logic required**: Server is fully authoritative — client is a renderer + input sender
- **Simple message format**: `{"action": "...", ...fields}` inbound, `{"type": "...", ...fields}` outbound
- **No session tokens/cookies**: Auth lives for WebSocket lifetime, simplifying game engine integration
- **Combat is inline**: Same WebSocket for all features (movement, combat, trade, party, chat) — no separate connections needed

### Integration Considerations

1. **No heartbeat/ping mechanism**: The protocol has no keep-alive. Game clients on spotty connections (mobile) would need WebSocket-level ping/pong handling.
2. **No request-response correlation**: Messages have no `request_id`. Clients must track state transitions (e.g., after sending `move`, expect `entity_moved` or `error`). This complicates async networking in engines.
3. **Push-based architecture**: Many messages arrive unsolicited (other players moving, combat triggered by movement, trade requests, party invites). Clients must handle all message types at all times.
4. **Large tile grids**: `room_state.tiles` is a 2D integer array. For a 100x100 room, that's 10,000 integers in JSON. A binary format or delta updates would reduce bandwidth.
5. **Tile type mapping**: Clients need to map integer tile types (defined in `server/room/tile.py`) to visual representations. This mapping is currently only documented in client code.

---

## 6. Protocol Definition and Extensibility

**Verdict: FUNCTIONAL but UNDOCUMENTED — Protocol works well, but lacks formal specification.**

### Protocol Structure

**Inbound (client → server):** JSON with mandatory `action` field
```json
{"action": "move", "direction": "up"}
{"action": "play_card", "card_key": "fireball_1"}
{"action": "trade", "args": "@PlayerName"}
```

**Outbound (server → client):** JSON with `type` field
```json
{"type": "room_state", "room_key": "town_square", "tiles": [...], ...}
{"type": "combat_turn", "result": {...}, "participants": [...], ...}
{"type": "error", "detail": "Not logged in"}
```

### Message Catalog

- **21 client-to-server actions**: `login`, `register`, `logout`, `move`, `chat`, `interact`, `play_card`, `pass_turn`, `flee`, `inventory`, `use_item`, `use_item_combat`, `look`, `who`, `stats`, `help_actions`, `map`, `level_up`, `trade`, `party`, `party_chat`
- **30+ server-to-client types**: `login_success`, `error`, `room_state`, `entity_moved`, `entity_entered`, `entity_left`, `combat_start`, `combat_turn`, `combat_end`, `combat_fled`, `combat_update`, `chat`, `party_chat`, `interact_result`, `inventory`, `item_used`, `look_result`, `who_result`, `stats_result`, `help_result`, `map_data`, `xp_gained`, `level_up_available`, `level_up_complete`, `trade_request`, `trade_result`, `trade_update`, `party_invite`, `party_invite_response`, `party_update`, `party_status`, `respawn`, `server_shutdown`, `announcement`, `kicked`, `logged_out`, `nearby_objects`, `tile_changed`

### Adding New Features

Adding a new message type is straightforward:
1. Define the handler function
2. Register it with `router.register("action_name", ...)` in `server/app.py`
3. Send responses as JSON dicts with a `type` field

The protocol naturally extends — new `action`/`type` values don't break existing clients (they simply ignore unknown types).

### What's Missing

1. **No formal protocol specification document**: The protocol is implicitly defined by handler implementations and the web-demo client. There's no standalone spec file.
2. **No Pydantic schemas for WebSocket messages**: Pydantic is only used for server configuration (`Settings(BaseSettings)` in `server/core/config.py`). All WebSocket message validation is manual `data.get("field", default)` in each handler. This means:
   - No auto-generated documentation
   - No compile-time type safety for messages
   - Malformed messages may silently fail rather than returning validation errors
3. **No message versioning**: If the protocol changes, there's no way for client and server to negotiate compatibility.
4. **No acknowledgment mechanism**: No sequence numbers or message IDs for reliable delivery tracking.

---

## Summary Scorecard

| Dimension | Rating | Notes |
|-----------|--------|-------|
| 1. Web UX (no game logic) | **A** | Clean thin client; all game logic server-side |
| 2. Server organization | **A-** | Well-organized; minor god-object concern with `Game` class |
| 3. Extensibility | **B+** | Easy to add handlers/effects; no auto-discovery or plugin system |
| 4. Database migration | **A** | PostgreSQL ready via config change + `asyncpg` |
| 5. Engine integration | **B+** | Standard WebSocket+JSON; needs heartbeat and request correlation |
| 6. Protocol definition | **B** | Functional and extensible; lacks formal spec and Pydantic schemas |

### Top Recommendations

1. **Create a protocol specification document** — Formal JSON schema for all message types, required for any non-trivial client implementation
2. **Add Pydantic models for WebSocket messages** — Enables validation, auto-documentation, and type safety
3. **Add request-response correlation** — A `request_id` field echoed in responses simplifies client-side state management
4. **Consider heartbeat/ping** — Essential for game engine clients on unreliable connections
5. **Decompose combat handler business logic** — Move `_check_combat_end` and related functions to a combat service layer
