# Codebase Adversarial Review — The Ages II

**Date:** 2026-04-12
**Reviewer:** Claude (Adversarial)
**Scope:** Full codebase evaluation against 8 criteria
**Codebase State:** Epic 16 complete (1062 tests passing), main branch clean

---

## Executive Summary

The Ages II server is a well-architected Python game server with strong fundamentals: clean module separation, centralized configuration, portable database abstraction, and a well-documented WebSocket protocol. The web-demo client is a proper thin client with zero game logic. There are actionable findings in every criterion, but none are blocking — the architecture is sound and extensible.

**Verdict:** Production-ready foundation with room for incremental improvements.

---

## Criterion 1: Web UX Contains No Game Logic

**Rating: PASS (Strong)**

The web-demo client (`web-demo/js/game.js`, ~1900 lines) is a proper thin client. Every game action goes through `sendAction()` as a JSON message to the server. The client never computes damage, XP, loot, stats, or game outcomes.

**Evidence verified:**
- Movement: `sendAction('move', { direction })` — `game.js:930`
- Combat: `sendAction('play_card', { card_key })` — `game.js:1365`
- Level-up: `sendAction('level_up', { stats })` — `game.js:1923`
- Item use: `sendAction('use_item', { item_key })` — `game.js:200`
- All combat results, XP gains, level thresholds come from server messages

**State management** (`gameState` at `game.js:97-113`) is a local cache of server-authoritative state used purely for rendering. The client never mutates game state independently.

**Minor observations (not violations):**
1. **HTML `minlength` on auth forms** (`index.html:26-27`) — browser-level UX hints (`minlength="3"` for username, `minlength="6"` for password). Server validates independently. Standard practice.
2. **Client-side whisper target lookup** (`game.js:172-176`) — checks local entity cache before sending whisper. UX convenience; server would reject invalid targets anyway.
3. **Stat description fallback strings** (`game.js:1657-1673`) — cosmetic tooltip labels like `"physical dmg bonus"`. Server-provided `stat_effects` are preferred (`game.js:1756`). These are display labels, not game logic.
4. **UI-only constants** — `LOG_MAX = 200` (chat trim, `game.js:124`), `MAX_RECONNECT = 5` (reconnect attempts, `game.js:116`), combat-end overlay delay `2000ms` (`game.js:1234`). None affect game balance.

**Conclusion:** ISS-021 through ISS-028 (previous game-logic-in-client fixes) were effective. The web-demo is a proper proof-of-concept thin client.

---

## Criterion 2: Server Codebase Organization & Structure

**Rating: PASS (Good, with identified improvements)**

### What's done well

- **Clean module boundaries**: `server/core/` (infrastructure), `server/net/` (networking), `server/player/` (player domain), `server/room/` (world), `server/combat/` (combat), `server/items/` (items), `server/trade/` (trading), `server/party/` (party system). Each domain is self-contained.
- **TYPE_CHECKING guards**: Used consistently everywhere (`auth.py:22`, `combat.py:17`, `movement.py:18`, `manager.py:11`, `service.py:15`) — zero runtime circular imports.
- **`@requires_auth` decorator** (`server/net/auth_middleware.py`) — centralizes auth boilerplate in a single 35-line file. All handlers except login/register are decorated.
- **Combat service extraction** (`server/combat/service.py`) — excellent example of pulling business logic out of handlers. The combat handler is now thin.
- **MessageRouter** (`server/net/message_router.py`) — 33 lines, admirably simple action-to-handler routing.
- **Clean dataclasses**: `PlayerSession`, `Trade`, `Party`, `CombatEndResult`, `FleeOutcome`, `XpResult` provide typed interfaces.
- **Pydantic inbound schemas** (`server/net/schemas.py`) validate all 23 inbound message types at the WebSocket entry point.

### Findings

| # | Severity | Finding | Location |
|---|----------|---------|----------|
| F1 | Medium | **`core/xp.py` sends WebSocket messages** — `notify_xp()` (line 99) and `send_level_up_available()` (line 152) call `game.connection_manager.send_to_player_seq()`. A "core" module pushing to the network layer is a layering violation. The `apply_xp()`/`notify_xp()` split (Story 16.4a) was done correctly, but `notify_xp()` and `send_level_up_available()` still live in `core/xp.py` rather than in a handler helper or `server/net/` module. | `server/core/xp.py:99,152` |
| F2 | Medium | **Fat auth handler** (475 lines) — `handle_login` (lines 239-304) and `handle_reconnect` (lines 307-475) contain extensive session setup, room placement, inventory hydration, entity construction, and broadcast logic. Helper functions `_resolve_stats`, `_resolve_room_and_place`, `_hydrate_inventory` help but remain in the handler file rather than a service module. | `server/net/handlers/auth.py` |
| F3 | Medium | **Fat movement handler** (354 lines) — `_handle_mob_encounter()` (lines 130-237) contains full combat initiation logic: party member gathering, card loading, stats map construction, combat instance creation, and broadcasting. This is business logic in a handler. | `server/net/handlers/movement.py:130-237` |
| F4 | Medium | **Fat trade handler** (485 lines) — `_execute_trade()` (lines 372-485) contains atomic trade swap logic: pre-validation, inventory computation, DB transaction, in-memory mutation. A full service-layer operation in a handler. | `server/net/handlers/trade.py:372-485` |
| F5 | Medium | **Login vs. Reconnect duplication** — `handle_login` (lines 239-304) and `handle_reconnect` Case 2 (lines 402-475) share ~30 lines of identical session setup: entity construction, room resolution, session creation, room_state broadcast, entity_entered broadcast, pending level-up check, heartbeat start. | `server/net/handlers/auth.py` |
| F6 | Low | **Stats payload construction repeated 3 times** — `_build_login_response()` (auth.py:100-132), `handle_register()` inline (auth.py:194-218), and `handle_stats()` (query.py:93-113) all construct the same stats dict with `settings.DEFAULT_STAT_VALUE` fallback for 6 abilities. | `auth.py`, `query.py` |
| F7 | Low | **Spawn point finding duplicated** — `Game._find_spawn_point()` (app.py:299-309) and `_resolve_room_and_place()` (auth.py:61-87) contain the same spawn-with-fallback logic. | `app.py`, `auth.py` |
| F8 | Low | **`Game` class is a partial God Object** (spans lines 37-483, ~447 lines) — owns all managers AND contains respawn logic, disconnect handling, heartbeat management, and NPC kill logic. Some of these (especially respawn and heartbeat) could be delegated. | `server/app.py:37-483` |
| F9 | Low | **Cross-domain cleanup** — `PlayerManager._cleanup_combat()` (player/manager.py:121-159) contains 39 lines of combat-specific logic (syncing stats, removing participants, releasing NPCs, notifying remaining players). | `server/player/manager.py:121-159` |
| F10 | Low | **Domain managers coupled to network** — `PartyManager` (party/manager.py:10) and `TradeManager` (trade/manager.py constructor) directly import/take `ConnectionManager` for timeout notification callbacks. | `party/manager.py`, `trade/manager.py` |

---

## Criterion 3: Extensibility — Easy to Add Features and Plugins

**Rating: PASS (Good)**

### Adding a new action requires 4 steps:

1. Add inbound schema in `server/net/schemas.py` (create Pydantic model, add to `ACTION_SCHEMAS` dict at line 184-208)
2. Write handler function in `server/net/handlers/`
3. Register handler in `Game._register_handlers()` at `server/app.py:161` via `self.router.register("action_name", lambda ws, d: handle_fn(ws, d, game=self))`
4. Add outbound schema (optional) in `server/net/outbound_schemas.py`

### Adding game content requires zero code changes:
- **Rooms**: Add JSON to `data/rooms/`
- **Cards**: Add to `data/cards/starter_cards.json`
- **Items**: Add to `data/items/base_items.json`
- **NPCs**: Add to `data/npcs/base_npcs.json`
- **Loot tables**: Add to `data/loot/loot_tables.json`

### Findings

| # | Severity | Finding | Location |
|---|----------|---------|----------|
| F11 | Medium | **Handler registration boilerplate** — 23 lambda registrations in `_register_handlers()` (~73 lines of identical `lambda ws, d: handle_fn(ws, d, game=self)` patterns at lines 185-257). A decorator-based auto-registration or a registry dict would scale better. | `server/app.py:161-257` |
| F12 | Low | **No plugin/hook system** — Adding a new game system requires touching `Game._register_handlers()`, `schemas.py`, and creating a handler. There's no plugin discovery or auto-registration mechanism. The `EventBus` (core/events.py) provides inter-system hooks, but new action types require manual wiring. Acceptable for current scale. | Architecture |
| F13 | Low | **Room object registry** (`server/room/objects/registry.py`) is a good extension point — new interactable object types can be registered. This pattern could be replicated for other extensible systems. | `server/room/objects/registry.py` |

---

## Criterion 4: Database Migration Readiness (PostgreSQL)

**Rating: PASS (Strong)**

The codebase was **intentionally designed for database portability**. Migration to PostgreSQL requires adding one dependency and setting one environment variable.

### What's done well

- **All models use portable SQLAlchemy types**: `Integer`, `String`, `JSON`, `Boolean`, `DateTime(timezone=True)` — all map cleanly to PostgreSQL. (`server/player/models.py`, `server/room/models.py`, `server/room/spawn_models.py`, `server/combat/cards/models.py`, `server/items/models.py`)
- **Clean repository pattern**: 6 repo modules with zero raw SQL. All queries use ORM constructs (`select()`, `update()`, `.where()`).
- **Dual-mode engine configuration** (`server/core/database.py:10-16`): conditionally enables connection pooling for non-SQLite databases. Already PostgreSQL-aware.
- **`ALEMBIC_DATABASE_URL` property** (`server/core/config.py:97-103`): explicitly handles `postgresql+asyncpg` → `postgresql` conversion. Intentionally designed.
- **Centralized transaction pattern** (`server/app.py:60-69`): single `game.transaction()` context manager used everywhere. Portable.
- **`DATABASE_URL` as Pydantic field** (`config.py:90`): overridable via environment variable.

### Findings

| # | Severity | Finding | Location |
|---|----------|---------|----------|
| F14 | Low | **`asyncpg` not in dependencies** — `pyproject.toml` only lists `aiosqlite>=0.19.0`. To use PostgreSQL, add `asyncpg>=0.29.0`. Engine config already handles it; just needs the package. | `pyproject.toml:10` |
| F15 | Low | **Alembic migration uses `sqlite.JSON()`** — the `downgrade()` in `alembic/versions/70a9c771b610_*.py:12,31` references `sqlalchemy.dialects.sqlite.JSON()`. The `upgrade()` is portable; only the downgrade path would fail on PostgreSQL. Historical migration, unlikely to matter. | `alembic/versions/70a9c771b610_*` |
| F16 | Informational | **`_ensure_aware()` helper** (`server/core/scheduler.py:21-24`) exists for SQLite's naive datetime handling. Becomes a harmless no-op on PostgreSQL (which preserves timezone info natively). Not a blocker. | `server/core/scheduler.py:21-24` |

---

## Criterion 5: Engine Integration (Godot, Unity, Unreal)

**Rating: PASS (Strong)**

The protocol has zero browser-specific features.

### Compatibility evidence

- **Transport**: Standard RFC 6455 WebSocket, text frames only. Natively supported by Godot (`WebSocketPeer`), Unity (`NativeWebSocket`/`websocket-sharp`), and Unreal (`WebSocket` plugin).
- **Data format**: Plain JSON — universally parseable. No DOM events, no HTML, no browser APIs.
- **Client-agnostic design**: Per ADR-16-4, the server does NOT strip HTML or sanitize chat for a specific renderer. Each client handles its own rendering security.
- **Reconnection support**: Session tokens + 120s grace period (configurable via `DISCONNECT_GRACE_SECONDS`) — critical for mobile/console network drops.
- **Sequence numbers**: `seq` field on state-critical messages enables ordered delivery verification.
- **Heartbeat**: Server sends `{"type":"ping"}`, client responds `{"action":"pong"}` — standard keep-alive compatible with any WebSocket client.
- **Protocol specification**: Auto-generated `_bmad-output/planning-artifacts/protocol-spec.md` (620 lines) explicitly designed so "a Godot developer can implement a client without reading server code."

### Findings

| # | Severity | Finding | Location |
|---|----------|---------|----------|
| F17 | Medium | **No protocol versioning** — no version field in messages, no version negotiation on connect, no version header in WebSocket handshake. Once multiple client implementations exist, protocol changes require coordinated client-server releases. | Architecture |
| F18 | Low | **JSON-only, no binary support** — `websocket.receive_text()` at `app.py:514`. Room tiles sent as `list[list[int]]` (e.g., 100×100 = 10,000 integers, ~40KB JSON). Adequate for current room sizes but could become a bandwidth concern for larger maps. | `server/app.py:514` |

---

## Criterion 6: Network Protocol Definition & Extensibility

**Rating: PASS (Good)**

### Protocol structure

- **Inbound**: 23 Pydantic-validated message types in `server/net/schemas.py`, keyed by `"action"` field. Optional `"request_id"` for request-response correlation.
- **Outbound**: 40 documented message types in `server/net/outbound_schemas.py`, keyed by `"type"` field. State-critical messages include `"seq"` for ordered delivery.
- **Validation pipeline** (`app.py:508-543`): `receive_text()` → `json.loads()` → check `"action"` → Pydantic validation → `MessageRouter.route()`.
- **Auto-generated spec**: `scripts/generate_protocol_doc.py` introspects schemas. `make protocol-doc` regenerates, `make check-protocol` verifies freshness.

### Findings

| # | Severity | Finding | Location |
|---|----------|---------|----------|
| F19 | Medium | **Outbound schemas not enforced at runtime** — handlers construct raw dicts, not schema instances. The `send_typed()` utility exists in `outbound_schemas.py` but is unused. Handlers could silently drift from documented schemas. | `server/net/outbound_schemas.py:1-5` |
| F20 | Medium | **Error messages are human-readable strings, not machine-parseable codes** — `{"type": "error", "detail": "..."}` requires clients to string-match to distinguish error types. No structured error codes (e.g., `"code": "AUTH_REQUIRED"`). | `server/app.py:518-541` |
| F21 | Low | **Pydantic validation errors exposed raw** — `str(e)` sent to client (`app.py:539`) leaks internal schema structure (field names, validation rules). Verbose but functional. | `server/app.py:539` |

---

## Criterion 7: Chat Markdown Support

**Rating: PASS (Good)**

### Server side

- Chat handler (`server/net/handlers/chat.py:58,69`) includes `"format": settings.CHAT_FORMAT` in every chat message.
- `CHAT_FORMAT` defaults to `"markdown"` (`server/core/config.py:71`), configurable via env var.
- Server deliberately does NOT parse or sanitize markdown (per ADR-16-4). Each client handles rendering.
- Control characters stripped (null bytes etc.) but `\n` and `\r` preserved (`chat.py:31`).
- Max length enforced: `settings.MAX_CHAT_MESSAGE_LENGTH` (default 500).

### Client side (web-demo)

- `appendChat()` (`game.js:1067-1077`) checks `format === 'markdown'` and renders via `renderSafeMarkdown()`.
- `renderSafeMarkdown()` (`game.js:1046-1064`):
  1. HTML-escapes first (XSS prevention): `&`, `<`, `>`
  2. Extracts code spans (`` `code` ``)
  3. Applies bold (`**bold**`), italic (`*italic*`), strikethrough (`~~strike~~`)
  4. Reinserts code spans
  5. Deliberately excludes links and images (eliminates `javascript:` URI XSS vectors)

### Findings

| # | Severity | Finding | Location |
|---|----------|---------|----------|
| F22 | Low | **Limited markdown subset** — only bold, italic, code, strikethrough supported. No headers, lists, blockquotes, or line breaks (`\n` → `<br>`). Sufficient for a chat system but not full markdown. | `web-demo/js/game.js:1046-1064` |
| F23 | Informational | **Party chat also includes format field** — `chat.py` handles room chat and whisper; party chat in `party.py` also sends `"format": settings.CHAT_FORMAT` (`server/net/handlers/party.py`). Consistent. | `server/net/handlers/party.py` |

---

## Criterion 8: Centralized Configuration Management

**Rating: PASS (Good)**

### Central config

`server/core/config.py` defines a `Settings` class (Pydantic `BaseSettings`) with **50 configurable fields** across 16 categories. Module-level singleton `settings = Settings()`. All fields auto-support env var overrides via Pydantic BaseSettings. Six validators enforce constraints on critical fields.

### Config access

All 25 modules that need config use `from server.core.config import settings` — consistent direct import pattern.

### Game data externalized

All game content in JSON files under `data/`: rooms (4 files), cards, items, NPCs, loot tables. Loaded dynamically via `settings.DATA_DIR`.

### Findings

| # | Severity | Finding | Location |
|---|----------|---------|----------|
| F24 | High | **Hardcoded NPC fallback stats** — `{"hp": 50, "max_hp": 50, "attack": 10}` when NPC has no stats. Should use `settings.DEFAULT_BASE_HP` and `settings.DEFAULT_ATTACK`. | `server/net/handlers/movement.py:193` |
| F25 | High | **Hardcoded mob attack fallback** — `self.mob_stats.get("attack", 10)`. Should use `settings.DEFAULT_ATTACK`. | `server/combat/instance.py:406` |
| F26 | High | **Hardcoded fallback combat cards** — damage value `10`, cost `1`, count `10` when no cards in DB. Damage should reference `settings.DEFAULT_ATTACK`. | `server/net/handlers/movement.py:186-189` |
| F27 | Medium | **D&D stat names scattered across 7+ files** — `"strength"`, `"dexterity"`, `"constitution"`, `"intelligence"`, `"wisdom"`, `"charisma"` are string literals in `levelup.py:18-20` (`_VALID_LEVEL_UP_STATS`), `repo.py:85-89` (`_STATS_WHITELIST`), `npc.py:78-86`, `auth.py:42-45`, `xp.py:156-163`, `query.py:106-111`, and more. Should be a single `STAT_NAMES` tuple defined once. | Multiple files |
| F28 | Medium | **Direction strings duplicated 3 times** — `DIRECTION_DELTAS` in `room.py:16-21`, `_SCAN_OFFSETS` in `query.py:19-25`, and schema validator in `schemas.py:44` all independently define `"up"`, `"down"`, `"left"`, `"right"`. Should import from a single source. | `room.py`, `query.py`, `schemas.py` |
| F29 | Medium | **Trade state machine uses raw strings** — `"request_pending"`, `"negotiating"`, `"one_ready"`, `"both_ready"`, `"executing"`, `"cancelled"`, `"complete"` scattered across `trade/manager.py` (lines 89, 137, 144, 169, 181, 204, 239, 249, 261, 270, 274). Should be an Enum. | `server/trade/manager.py` |
| F30 | Low | **Behavior type `"hostile"` hardcoded** in 2 locations: `room.py:177` and `npc.py:110`. | `room.py`, `npc.py` |
| F31 | Low | **Spawn type strings `"persistent"` / `"rare"` hardcoded** in `app.py:287` and `scheduler.py:130`. | `app.py`, `scheduler.py` |
| F32 | Low | **Effect type strings hardcoded** — `"heal"`, `"shield"`, `"draw"`, `"damage"`, `"dot"` in `instance.py:131` and `registry.py:50-54`. | `instance.py`, `registry.py` |
| F33 | Low | **Help categories fully hardcoded** — action-to-category mapping in `query.py:122-128`. Will drift as actions are added. | `server/net/handlers/query.py:122-128` |

---

## Summary: All Findings by Severity

| Severity | Count | IDs |
|----------|-------|-----|
| High | 3 | F24, F25, F26 |
| Medium | 12 | F1, F2, F3, F4, F5, F11, F17, F19, F20, F27, F28, F29 |
| Low | 15 | F6, F7, F8, F9, F10, F12, F14, F15, F18, F21, F22, F30, F31, F32, F33 |
| Informational | 3 | F13, F16, F23 |
| **Total** | **33** | |

---

## Top Priority Recommendations

1. **Fix hardcoded game-balance fallbacks** (F24-F26) — replace `50`, `10` literals with `settings.DEFAULT_BASE_HP`, `settings.DEFAULT_ATTACK` references.
2. **Add protocol versioning** (F17) — include `"protocol_version"` in `login_success` response before shipping Godot client.
3. **Define string constants centrally** (F27-F29) — `STAT_NAMES` tuple, import `DIRECTION_DELTAS` from `room.py`, convert trade states to Enum.
4. **Move `notify_xp()`/`send_level_up_available()` out of `core/`** (F1) — they belong in a handler helper or `server/net/` module.
5. **Add structured error codes** (F20) — `"code": "AUTH_REQUIRED"` alongside human-readable `"detail"` for machine-parseable error handling.
6. **Extract service functions from fat handlers** (F2-F4) — auth session setup, combat initiation, trade execution belong in service modules.
