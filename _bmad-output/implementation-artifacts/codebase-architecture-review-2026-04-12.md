# Codebase Architecture Review — The Ages II

**Date:** 2026-04-12  
**Reviewer:** Claude (Adversarial)  
**Scope:** Full codebase evaluation against 8 architectural criteria  
**Method:** Exhaustive code reading with adversarial verification passes

---

## Evaluation Summary

| # | Criterion | Grade | Verdict |
|---|-----------|-------|---------|
| 1 | Web UX is proof-of-concept only, no game logic | **A-** | Thin client — no combat/damage calculations. Minor: duplicated constants (tile types, effect types, stat descriptions, auth validation lengths) |
| 2 | Server codebase is well organized and structured | **A** | 8 well-scoped packages, clean handler/service/manager layering, no logic file over 505 lines, no runtime circular imports |
| 3 | Easy to add features and plugins | **A-** | Registries for effects, objects, handlers, events. One-step pattern for new message types. No formal plugin API but extension points are clean |
| 4 | Easy to migrate to PostgreSQL | **A** | 100% SQLAlchemy ORM, zero raw SQL, `postgres` optional dependency pre-defined, engine conditionally pools, Alembic migrations are DB-agnostic |
| 5 | Easy to integrate with Godot/Unity/Unreal clients | **A** | Pure JSON/WebSocket protocol, 698-line auto-generated protocol spec, engine-agnostic by design (ADR-16-4) |
| 6 | Network protocol is well-defined and extensible | **A-** | 23 inbound + 40 outbound Pydantic schemas + 17 payload sub-models, router pattern, versioning present, request-response correlation. Gap: domain-level error codes are unstructured |
| 7 | Chat supports markdown | **A** | `CHAT_FORMAT: "markdown"` configurable, server passes through, web demo renders safe subset (bold/italic/code/strikethrough) with XSS protection |
| 8 | Configuration is centralized | **A** | 40+ settings in Pydantic `Settings` class, env-var overridable, validators on key values. Zero hardcoded game balance values in server code |

---

## Criterion 1: Web UX — Proof of Concept Only, No Game Logic

**Files reviewed:** `web-demo/index.html`, `web-demo/js/game.js`, `web-demo/css/style.css`

### Verdict: PASS (A-)

The web demo is a proper thin client. All game actions are sent to the server via `sendAction()` and the client renders server responses. There are **no** damage calculations, combat resolution, HP computations, item effect calculations, or movement validation.

### Findings — Duplicated Constants (Low Severity)

These are display-layer concerns, not game logic, but they duplicate server-side knowledge:

1. **Hardcoded tile type mapping** (`web-demo/js/game.js`, `tileClass()` function) — numeric tile types (0=floor, 1=wall, etc.) are hardcoded. If server changes enum values, client renders wrong tiles.

2. **Hardcoded effect type formatting** (`web-demo/js/game.js`, `formatEffect()` and `handleItemUsed()`) — client knows effect types (damage, heal, shield, dot, draw) and how to display them. Server could send pre-formatted descriptions.

3. **Hardcoded stat descriptions** (`web-demo/js/game.js`, `updateStatsDetailPanel()`) — descriptions like "physical dmg bonus" for STR are hardcoded without server fallback. Level-up modal has server fallback via `serverEffects` but HTML subtitle "Choose up to 3 stats" is always hardcoded.

4. **Hardcoded auth validation lengths** (`web-demo/index.html`) — `minlength="3"` and `minlength="6"` duplicate `settings.MIN_USERNAME_LENGTH` and `settings.MIN_PASSWORD_LENGTH`.

5. **Client-side XP fallback computation** (`web-demo/js/game.js`, `handleXpGained()`) — fallback `(xp || 0) + (amount || 0)` computes XP addition client-side when `new_total_xp` is absent.

6. **Hardcoded object type icons** (`web-demo/js/game.js`, `OBJECT_ICONS`) — adding a new object type server-side shows `?` on client.

### Recommendation

These are acceptable for a proof-of-concept. A production Godot client should receive tile type names, effect descriptions, and stat metadata from the server to avoid this coupling.

---

## Criterion 2: Server Codebase Organization and Structure

**Files reviewed:** All `server/**/*.py` files (60+ files across 8 packages)

### Verdict: PASS (A)

#### Module Organization

| Package | Responsibility | Verdict |
|---------|---------------|---------|
| `server/core/` | Config, database, scheduler, event bus, XP math, constants, effects | Clean — pure infrastructure with zero net-layer imports |
| `server/net/` | WebSocket management, routing, schemas, auth middleware, heartbeat, errors | Clean — network-only concerns |
| `server/net/handlers/` | 11 handler files, one per action domain | Clean — thin routing to services/managers |
| `server/player/` | Player model, repo, entity, session, auth, manager, service | Clean — complete domain encapsulation |
| `server/room/` | Room model, repo, tiles, room instance, NPC entity, spawn repo, objects | Clean — self-contained spatial domain |
| `server/combat/` | Combat instance, manager, service, cards sub-package | Clean — encapsulated combat domain |
| `server/items/` | Item definitions, repo, inventory runtime | Clean — minimal, focused |
| `server/trade/` | Trade manager, session dataclass, service | Clean — small domain with proper isolation |
| `server/party/` | Party manager, party dataclass | Clean — small domain, stateless handler |

#### Handler/Service/Manager Pattern

The three-tier pattern (handler → service → manager) is consistently applied for complex domains:

- **Combat**: `handlers/combat.py` → `combat/service.py` → `combat/manager.py`
- **Auth**: `handlers/auth.py` → `player/service.py` → `player/manager.py`
- **Trade**: `handlers/trade.py` → `trade/service.py` → `trade/manager.py`

Simpler domains (chat, query, inventory) have thin handlers without a service layer — appropriate since they don't have complex business logic.

#### Circular Import Prevention

Zero runtime circular imports. The codebase uses two patterns consistently:
- `TYPE_CHECKING` guards for `Game` type hints
- Deferred imports inside functions for cross-package dependencies

#### Architecture Findings (Low Severity)

1. **Reverse dependency**: `server/combat/service.py:126` imports `make_turn_timeout_callback` from `server/net/handlers/combat.py`. This is a service-to-handler reverse dependency (deferred-imported to avoid cycles). The callback factory should live in the service layer or a shared utility.

2. **Movement handler density**: `server/net/handlers/movement.py` (269 lines) contains substantial business logic in `_handle_exit_transition()` (trade cancellation, room transfer, DB persistence, XP grants). Candidate for a movement service.

3. **Party handler size**: `server/net/handlers/party.py` (505 lines) is the largest handler — but well-organized with 8 private sub-handlers. No `party/service.py` exists, though `PartyManager` effectively serves as both manager and service.

4. **`core/xp.py` imports `player/repo`**: A core module depending on a domain module inverts the expected dependency direction. Not a cycle risk, but a purist concern.

---

## Criterion 3: Ease of Adding Features and Plugins

### Verdict: PASS (A-)

The codebase provides four clean extension points:

#### 1. Effect Registry (Plugin Pattern)

`server/core/effects/registry.py` — `EffectRegistry` class with `register(effect_type, handler)`. Adding a new effect (e.g., "stun"):
- Create `server/core/effects/stun.py` with an `async handle_stun()` function
- Register in `create_default_registry()`
- Add `STUN = "stun"` to `EffectType` StrEnum

#### 2. Object Type Registry (Plugin Pattern)

`server/room/objects/registry.py` — `register_object_type(type_name, cls)`. Adding a new interactive object:
- Create a class extending `InteractiveObject` with an `async interact()` method
- Register it via `register_object_type()`

#### 3. Message Router (Handler Registration)

`server/net/message_router.py` — `router.register(action, handler)`. Adding a new action:
1. Add Pydantic schema to `server/net/schemas.py` + `ACTION_SCHEMAS`
2. Write handler function in appropriate `handlers/` file
3. Register in `Game._register_handlers()`
4. Add outbound schema to `server/net/outbound_schemas.py`

#### 4. Event Bus (Pub/Sub)

`server/core/events.py` — `EventBus` with `subscribe(event_type, callback)` and `emit(event_type, **data)`. Error-isolated (one failing subscriber doesn't crash the emit loop). Any system can subscribe to events without coupling to the emitter.

#### 5. Data-Driven Content

Rooms, NPCs, cards, items, and loot tables are all loaded from JSON files in `data/`. Adding content requires no code changes — just drop a JSON file in the right directory.

#### Limitation

There is no formal plugin API (no plugin discovery, no plugin lifecycle hooks, no hot-loading). Extension requires modifying registration code. This is appropriate for the project's current scale.

---

## Criterion 4: Database Migration to PostgreSQL

### Verdict: PASS (A)

#### What's Already Done

| Aspect | Status |
|--------|--------|
| 100% SQLAlchemy ORM | **Done** — zero raw SQL, zero `sqlite3` imports, zero `PRAGMA` statements |
| `asyncpg` optional dependency | **Done** — `pyproject.toml` line 26-28: `postgres = ["asyncpg>=0.29.0"]` |
| Conditional connection pooling | **Done** — `database.py:11` skips pool config for SQLite, applies it for PostgreSQL |
| Alembic async→sync URL translation | **Done** — `config.py:101-102` handles both `sqlite+aiosqlite→sqlite` and `postgresql+asyncpg→postgresql` |
| Database URL via environment variable | **Done** — Pydantic `BaseSettings` reads `DATABASE_URL` from env |
| Alembic migrations DB-agnostic | **Done** — both migrations use only `sa.*` types and `op.*` operations |
| Repository pattern | **Done** — 5 repo modules accept `AsyncSession` via dependency injection |
| Portable column types | **Done** — `sa.Integer`, `sa.String`, `sa.JSON`, `sa.Boolean`, `sa.DateTime(timezone=True)` |

#### Migration Steps

```bash
pip install ".[postgres]"
DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/theages" make server
```

#### Minor Items

1. **Test fixtures** — 3 test files (`test_database.py`, `test_repos.py`, `test_migration.py`) hardcode `sqlite+aiosqlite://`. Consider extracting to a `TEST_DATABASE_URL` constant for CI against PostgreSQL.
2. **`test_migration.py`** — inherently SQLite-specific (compares `create_all` schema against migration output). Would need a PostgreSQL variant for full CI coverage.

---

## Criterion 5: Client Engine Integration (Godot/Unity/Unreal)

### Verdict: PASS (A)

#### Protocol Characteristics

| Property | Value | Engine Impact |
|----------|-------|---------------|
| Transport | WebSocket (RFC 6455) | All engines have WebSocket libraries |
| Encoding | JSON text frames, UTF-8 | All engines have JSON parsers |
| Inbound discriminator | `"action"` field | Simple string switch |
| Outbound discriminator | `"type"` field | Simple string switch |
| Field naming | `snake_case` | No language-specific conventions |
| Tile grid format | `list[list[int]]` | Native 2D array |
| Binary data | None — all text | No endianness or packing concerns |
| Auth | Username/password + session token | Standard pattern |

#### Protocol Specification

A 698-line auto-generated protocol spec at `_bmad-output/planning-artifacts/protocol-spec.md` provides:
- Complete field-by-field tables for all 23 inbound and 40 outbound messages (plus payload sub-models)
- Connection lifecycle sequences (login, reconnect)
- Combat, trade, and party flow diagrams
- Tile type enum and movement direction reference
- Error handling table

This spec serves as the contract for any client engine implementation.

#### Design Decision: ADR-16-4

The server is client-agnostic. Chat messages include `"format": "markdown"` as metadata — each client decides how to render. The web demo renders a safe markdown subset; a Godot client could use `RichTextLabel` with BBCode; Unity could use TextMeshPro with rich text tags.

---

## Criterion 6: Network Protocol Definition and Extensibility

### Verdict: PASS (A-)

#### Schema Coverage

- **23 inbound schemas** in `server/net/schemas.py` — every action validated with Pydantic at runtime before routing
- **40 outbound message schemas + 17 payload sub-models** in `server/net/outbound_schemas.py` — currently documentation-only (handlers send raw dicts); `send_typed()` utility available for migration

#### Extensibility Pattern

Adding a new message type requires exactly 4 steps — no framework overhead, no code generation, no configuration files:

1. Define inbound Pydantic schema + add to `ACTION_SCHEMAS`
2. Write handler function with `@requires_auth` decorator
3. Register in `Game._register_handlers()`
4. Define outbound schema for documentation

#### Protocol Versioning

`PROTOCOL_VERSION = "1.0"` in `server/core/constants.py:32`, included in `login_success` responses. Currently informational — no client version negotiation or rejection of incompatible clients. Adequate for single-client development; needs enhancement for multi-client support.

#### Request-Response Correlation

`with_request_id()` utility echoes `request_id` from inbound to outbound messages. Per-player `_msg_seq` sequence numbers via `send_to_player_seq()` for ordering.

#### Findings

1. **Outbound schemas not runtime-enforced** — handlers construct raw dicts instead of using `send_typed()`. Outbound messages are not validated against their schemas. This means schema drift is possible.

2. **Domain-level error codes unstructured** — The 5 `ErrorCode` values (INVALID_JSON, MISSING_ACTION, UNKNOWN_ACTION, VALIDATION_ERROR, AUTH_REQUIRED) cover protocol/auth errors. Game logic errors ("not in combat", "not enough energy", "inventory full") are sent as generic `{"type": "error", "detail": "..."}` without machine-readable codes. Clients must parse `detail` strings to react programmatically.

3. **Schema-to-handler sync is manual** — `ACTION_SCHEMAS` dict and `_register_handlers()` must be kept in sync manually. No startup assertion ensures every schema has a handler and vice versa.

4. **Protocol spec rendering bug** — Two sub-models (`LookObjectPayload`, `NearbyObjectPayload`) appear as top-level outbound message types with `type` of `"PydanticUndefined"` in the auto-generated protocol spec.

---

## Criterion 7: Chat Markdown Support

### Verdict: PASS (A)

#### Implementation Chain

1. **Server config**: `CHAT_FORMAT: str = "markdown"` in `server/core/config.py:71` — configurable via env var
2. **Server handler**: `server/net/handlers/chat.py` passes raw message text through with `"format": settings.CHAT_FORMAT` metadata. No server-side markdown processing. Control characters stripped (except `\n`, `\r`), max length enforced (500 chars).
3. **Outbound schema**: `OutboundChatMessage.format: str | None = None` in `server/net/outbound_schemas.py`
4. **Party chat**: Same pattern in `server/net/handlers/party.py:498`
5. **Announcements**: Same pattern in `Game._register_events()` (rare spawn broadcasts)

#### Web Demo Rendering

`renderSafeMarkdown()` in `web-demo/js/game.js` renders a deliberately restricted subset:
- `**bold**` → `<strong>`
- `*italic*` → `<em>`
- `` `code` `` → `<code>`
- `~~strikethrough~~` → `<del>`

**Security**: HTML entities (`&`, `<`, `>`) are escaped before regex replacement. Code spans extracted first to prevent formatting inside code. No links or images rendered — eliminates `javascript:` URI XSS vectors.

**Client-agnostic design**: The server declares format, each client renders as appropriate. A Godot client could use BBCode in `RichTextLabel`; a Unity client could use TextMeshPro rich text.

---

## Criterion 8: Centralized Configuration Management

### Verdict: PASS (A)

#### Configuration System

`server/core/config.py` — Pydantic `Settings` class (extends `BaseSettings`) with 40+ settings covering:

| Category | Settings Count | Examples |
|----------|---------------|----------|
| Server | 3 | HOST, PORT, DEBUG |
| Player defaults | 3 | DEFAULT_BASE_HP, DEFAULT_ATTACK, DEFAULT_STAT_VALUE |
| Game structure | 3 | DEFAULT_SPAWN_ROOM, STAT_CAP, LEVEL_UP_STAT_CHOICES |
| Combat | 5 | COMBAT_HAND_SIZE, COMBAT_MIN_DAMAGE, COMBAT_TURN_TIMEOUT_SECONDS |
| NPC | 4 | NPC_DEFAULT_HP_MULTIPLIER, MOB_RESPAWN_SECONDS |
| Auth | 2 | MIN_USERNAME_LENGTH, MIN_PASSWORD_LENGTH |
| XP & Stats | 8 | XP_CURVE_TYPE, CON_HP_PER_POINT, STAT_SCALING_FACTOR |
| Trade | 4 | TRADE_COOLDOWN_SECONDS, MAX_TRADE_ITEMS |
| Party | 3 | MAX_PARTY_SIZE, PARTY_INVITE_TIMEOUT_SECONDS |
| Chat | 2 | MAX_CHAT_MESSAGE_LENGTH, CHAT_FORMAT |
| Room | 1 | MAX_PLAYERS_PER_ROOM |
| Admin | 1 | ADMIN_SECRET |
| Heartbeat | 2 | HEARTBEAT_INTERVAL_SECONDS, HEARTBEAT_TIMEOUT_SECONDS |
| Session | 2 | SESSION_TOKEN_TTL_SECONDS, DISCONNECT_GRACE_SECONDS |
| Database | 4 | DATABASE_URL, DB_POOL_SIZE, DB_MAX_OVERFLOW, DB_POOL_PRE_PING |

#### Features

- **Environment variable override**: All settings via env vars (Pydantic `BaseSettings`)
- **Validation**: 6 field validators ensure critical values are within valid ranges
- **Single import**: All server code accesses settings via `from server.core.config import settings`
- **No scattered config**: Zero game balance values hardcoded outside the Settings class

#### Content-Level Configuration

Game content (rooms, NPCs, cards, items, loot) is data-driven via JSON files in `data/`:
- `data/rooms/` — room definitions with tile grids, NPCs, objects, exits
- `data/npcs/` — NPC templates with stats, behavior, spawn config
- `data/cards/` — card definitions with effects and costs
- `data/items/` — item definitions
- `data/loot/` — loot table definitions

This separates balance tuning (JSON data) from system configuration (Python settings).

---

## Cross-Cutting Observations

### Strengths

1. **Consistent architectural patterns** — handler/service/manager layering, repository pattern, registry pattern applied throughout
2. **Security-conscious** — `hmac.compare_digest` for admin auth, bcrypt for passwords, XSS-safe markdown rendering, Pydantic validation sanitization
3. **Testability** — 1066 tests, repos accept `AsyncSession` via DI, managers accept deps via constructor, event bus is error-isolated
4. **Data-driven content** — adding rooms/NPCs/cards/items requires no code changes
5. **PostgreSQL-ready by design** — async driver abstraction, optional dependency, conditional pooling

### Opportunities

1. **Outbound schema enforcement** — migrate handlers from raw dicts to `send_typed()` to prevent schema drift
2. **Domain error codes** — extend `ErrorCode` for game logic errors (combat, trade, inventory) to support programmatic client reactions
3. **Protocol version negotiation** — reject incompatible clients at login time
4. **Movement service extraction** — `_handle_exit_transition()` in `handlers/movement.py` is the densest remaining handler logic
5. **Turn timeout callback placement** — move `make_turn_timeout_callback` from `handlers/combat.py` to `combat/service.py` to fix the reverse dependency
