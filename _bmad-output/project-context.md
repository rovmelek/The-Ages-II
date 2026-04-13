---
project_name: 'The-Ages-II'
user_name: 'Kevin'
date: '2026-03-25'
sections_completed:
  ['technology_stack', 'server_architecture', 'performance_rules', 'organization_rules', 'testing_rules', 'platform_rules', 'critical_rules']
status: 'complete'
rule_count: 58
optimized_for_llm: true
---

# Project Context for AI Agents

_Critical rules and patterns for implementing code in The-Ages-II. Focus on unobvious details that agents might otherwise miss._

---

## Technology Stack & Versions

- **Python >=3.11** — `from __future__ import annotations` must be first import in every module
- **FastAPI** — WebSocket-primary for gameplay; REST (`APIRouter`) for admin endpoints only
- **SQLAlchemy[asyncio] + aiosqlite** — All DB async; SQLite at `data/game.db`; no migrations
- **Pydantic v2** + **pydantic-settings** — v2 API only (not v1)
- **bcrypt v4** — Direct API (not passlib)
- **pytest + pytest-asyncio** — `asyncio_mode = "auto"`
- **httpx** — REST endpoint testing (dev only)

**Constraints:**
- All server code is async — never use blocking I/O
- SQLite single-writer — no concurrent write transactions
- Alembic available — `make db-migrate` runs migrations; `create_all` still used at startup alongside Alembic (ADR-14-21)

---

## Critical Implementation Rules

### Server Architecture Rules

**Orchestration:**
- `Game` class (`server/app.py`) is the single orchestrator — all managers are instance attributes
- Module-level `game = Game()` singleton — initialized via `lifespan` async context manager
- Startup order: `init_db()` → NPC templates → rooms → cards → items → handlers → scheduler
- `Game._shutting_down` flag gates shutdown/restart idempotency — check before triggering

**Handler Patterns:**
- All gameplay communication uses WebSocket — REST endpoints are exclusively for admin operations
- WebSocket handlers use `@requires_auth` decorator (`server/net/auth_middleware.py`) which injects `entity_id: str` and `player_info: PlayerSession` as keyword arguments. Only `handle_login` and `handle_register` are NOT decorated (pre-auth handlers).
- Decorated handler signature: `async def handle_X(ws: WebSocket, data: dict, *, game: Game, entity_id: str, player_info: PlayerSession) -> None`
- Outer (decorated) function retains `(websocket, data, *, game)` — lambda registration in `app.py` is unaffected
- REST admin: `APIRouter` with `Depends(verify_admin_secret)` — must use deferred `from server.app import game` inside each function (avoids circular imports)
- Access managers through `game.*` — never import managers directly
- DB access: `async with game.transaction() as session:` — auto-commits on success, rolls back on exception

**Player State — Dual Storage:**
- In-memory: `game.player_manager.get_session(entity_id)` → `PlayerSession(entity, room_key, db_id, inventory, visited_rooms, pending_level_ups)`
- DB: Persisted on disconnect, room transition, combat victory, shutdown
- `PlayerEntity`: `@dataclass` with `id`, `name`, `x`, `y`, `player_db_id`, `stats` dict, `in_combat` bool

**Effect System:**
- `EffectHandler` signature: `async (effect, source, target, context) -> dict` — all dicts
- 6 types: `damage`, `heal`, `shield`, `dot`, `draw`, `restore_energy` — handlers are stateless
- DoT recording (EffectRegistry) and DoT ticking (CombatInstance) are separate concerns

**Energy System (Epic 18):**
- Energy is a persistent player stat (like HP), derived from INT+WIS: `max_energy = DEFAULT_BASE_ENERGY + INT * INT_ENERGY_PER_POINT + WIS * WIS_ENERGY_PER_POINT`
- Cards have `card_type` field: `"physical"` (free, cost=0) or `"magical"` (costs energy). Classification rubric in ADR-18-2.
- Combat energy regen per cycle: `compute_energy_regen(stats)` in `server/combat/instance.py` — `floor(BASE_COMBAT_ENERGY_REGEN + (INT+WIS) * COMBAT_ENERGY_REGEN_FACTOR)`
- Out-of-combat HP/energy regen: `server/core/regen.py` (standalone module, not Scheduler). Sends `stats_update` message via `send_to_player_seq()`. Skips in-combat and full HP+energy players. Error-isolated.
- Energy potion: `restore_energy` effect in `server/core/effects/restore_energy.py`, flat 25 restore, no stat scaling
- `_STATS_WHITELIST` in `player/repo.py` includes `energy`, `max_energy` — they persist to DB
- Combat sync: 4 functions in `combat/service.py` sync energy alongside HP: `sync_combat_stats()`, `clean_player_combat_stats()`, `cleanup_participant()`, `handle_flee_outcome()`
- Items and pass are free (no energy cost); only `play_card()` checks energy for non-physical cards
- Level-up: stacking allowed (no dedup), `max_energy` recalculated from INT+WIS, energy reset to max
- Config in `Settings` (Pydantic BaseSettings) in `server/core/config.py`

**Connection/Room Model:**
- `ConnectionManager` maps `entity_id → WebSocket` and `entity_id → room_key`
- On disconnect: `game.player_manager.cleanup_session(entity_id, game)` — trades → combat → party → save to DB → remove from room → disconnect
- Cleanup lives on `PlayerManager` (not in auth.py handler) — test patches target `server.player.manager.player_repo`

**Room Grid:**
- `grid[y][x]` (row-major) — NOT `grid[x][y]`
- Movement directions: `"up"`, `"down"`, `"left"`, `"right"` with delta tuples `(dx, dy)`
- Exit directions: movement dirs + `"ascend"` / `"descend"` for vertical exits — NEVER use `"up"`/`"down"` for stairs (collides with movement directions)
- Tile types: FLOOR=0, WALL=1, EXIT=2, MOB_SPAWN=3, WATER=4, STAIRS_UP=5, STAIRS_DOWN=6
- STAIRS_UP and STAIRS_DOWN are walkable and trigger exit detection (same as EXIT tiles)

**Admin Endpoints:**
- REST-only via `admin_router` (`APIRouter(prefix="/admin")`)
- Auth: `Authorization: Bearer <ADMIN_SECRET>` header; `ADMIN_SECRET` empty = all admin disabled
- Background tasks via `asyncio.create_task()` — endpoint returns immediately, task runs shutdown/restart
- Shutdown: `game.shutdown()` → `os.kill(SIGTERM)`; Restart: `game.shutdown()` → `os.execv()`

### Performance Rules

**Async Event Loop:**
- Never use `time.sleep()` — use `asyncio.sleep()`
- `asyncio.create_task()` for background work
- Handle `asyncio.CancelledError` in all background tasks for clean shutdown

**Database:**
- Keep `async with async_session()` scopes short — single-writer SQLite
- Schema created via `Base.metadata.create_all()` at startup

**Broadcasting:**
- `broadcast_to_room` scans ALL player-room mappings — O(total_players)
- Sequential `await ws.send_json()` — dead connections silently skipped

**Memory:**
- All game state in memory — DB is persistence layer only
- `_ws_to_entity` uses `id(websocket)` — valid for connection lifetime only

### Code Organization Rules

**Module Structure:**
- Every `server/` subdirectory has `__init__.py`
- `TYPE_CHECKING` guard for circular imports (e.g., `Game` class type in submodules)

**Repository Pattern:**
- Repos are module-level async functions, NOT classes
- All take `session: AsyncSession` as first parameter
- Repos do NOT call `session.commit()` — the `Game.transaction()` context manager handles commit/rollback
- `player_repo.create()` and `room_repo.upsert_room()` (insert branch) use `session.flush()` before `session.refresh()` to get auto-increment IDs without committing

**Data Classes vs Dicts:**
- Runtime entities: `@dataclass` — `PlayerEntity`, `RoomObject`, `NpcEntity`
- Combat state: plain dicts — `mob_stats`, `participant_stats`, `active_effects` (effect handlers operate generically on dicts)
- Definitions: dedicated classes — `CardDef`, `ItemDef`
- Inventory: class with `to_dict()` / `from_dict()` serialization

**Object Hierarchy:**
- `RoomObject` → `InteractiveObject` (adds `async interact()`) → `Chest`, `Lever`
- `NpcEntity` is separate — stored in `room._npcs`, not `room.objects`
- NPC templates: `game.npc_templates` is the single source of truth (no module-level global); pass `templates` dict to `create_npc_from_template()`

**Event/Message Patterns:**
- `EventBus`: async callbacks with `**kwargs`
- Server→client messages: `type` field; Client→server: `action` field
- Errors: `{"type": "error", "detail": "..."}`

### Testing Rules

**Two Tiers:**
- Unit tests: Direct class/function testing, no server startup
- Integration tests (`test_integration.py`): Full handler pipeline, in-memory SQLite

**Setup Patterns:**
- Simple tests: `_make_*()` factory functions — no fixtures, no DB
- Handler tests: Create `Game()`, register entities, `AsyncMock` for WebSocket
- DB tests: `@pytest.fixture` with `create_async_engine("sqlite+aiosqlite:///:memory:")`
- REST endpoint tests: `httpx.ASGITransport(app=app)` + `AsyncClient(transport=transport, base_url="http://test")` — use `monkeypatch` for config settings (e.g., `ADMIN_SECRET`), `patch` background tasks to prevent real shutdown

**Critical Mock Rules:**
- Async functions MUST use `AsyncMock` — awaiting `MagicMock` raises `TypeError`
- For unit tests: mock `game.transaction = MagicMock(return_value=mock_ctx)` where `mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)` and `mock_ctx.__aexit__ = AsyncMock(return_value=False)`
- For integration tests with real DB: assign `game.session_factory = test_session_factory` — `Game.transaction()` wraps `session_factory` so the real transaction path is tested
- Import ALL model modules before `create_all()` — SQLAlchemy only creates tables for registered models

### Platform & Build Rules

- Pure Python — no compilation; `make install` (or `.venv/bin/pip install -e ".[dev]"`)
- Entry point: `make server` (or `.venv/bin/python run.py`) → uvicorn with hot reload in DEBUG mode
- Run tests: `make test` — always use this, never bare `pytest` (system Python lacks dependencies)
- `data/game.db` auto-created, gitignored — JSON data files committed
- Web client: `web-demo/index.html` at `/`, `web-demo/` mounted at `/static`
- Client is vanilla HTML/CSS/JS — no bundler, no npm
- WebSocket: `ws://host:port/ws/game`
- No Docker, no CI/CD, no required env vars
- Optional: `ADMIN_SECRET` env var enables admin REST endpoints (empty = disabled)

### Critical Don't-Miss Rules

**Anti-Patterns:**
- NEVER import `Game` at module level — use `TYPE_CHECKING` guard
- NEVER persist `shield` or `active_effects` — combat-only transient data
- NEVER generate custom entity IDs — always `f"player_{db_id}"`
- NEVER use `MagicMock` for async — always `AsyncMock`
- NEVER call `session.commit()` outside `Game.transaction()` — repos and handlers must not commit directly
- NEVER modify `game.npc_templates` after startup
- NEVER use `==` for secret comparison — always `hmac.compare_digest()`
- NEVER hardcode game balance values (HP, attack, stat defaults, spawn room, auth lengths, etc.) — always reference `settings.*` from `server/core/config.py` (Story 14.1)
- NEVER add module-level mutable state (dicts, lists, globals) to handler files — all state belongs on manager classes owned by `Game`

**Easy-to-Forget:**
- New player stats MUST be added to `_STATS_WHITELIST` in `player/repo.py` — unlisted stats are silently dropped on save. Current whitelist: `hp`, `max_hp`, `energy`, `max_energy`, `xp`, `level`, + 6 D&D abilities. Excluded: `attack` (always DEFAULT_ATTACK), `shield`/`active_effects` (combat-only transient).
- Stairs exits use `"ascend"`/`"descend"` — NOT `"up"`/`"down"` (collision with movement directions)

**State Synchronization:**
- Combat stats sync `hp`, `max_hp`, `energy`, `max_energy` back to `PlayerEntity.stats` after every action AND at combat end (4 sync functions in `combat/service.py`)
- Strip `shield` at combat end: `entity.stats.pop("shield", None)` — but keep `energy`/`max_energy` (persistent)
- XP applied in `_check_combat_end`, NOT in `CombatInstance`
- Inventory persists immediately after combat item use
- On disconnect/kick: save to DB BEFORE removing from room/combat
- On flee: sync stats BEFORE `remove_participant()` (ISS-033 fix)

**Combat Flow Order:**
1. Process DoT effects (mob + current player)
2. Check `is_finished` — early return if DoT killed
3. Check `card_type` — physical cards skip energy check; magical cards check energy cost — reject if insufficient
4. Resolve card/item effects
5. Advance turn (may trigger cycle-end mob attack + energy regen via `compute_energy_regen()`)
6. `_broadcast_combat_state()` — sync stats + send to participants
7. `_check_combat_end()` — victory/defeat cleanup, XP, respawn

**NPC Lifecycle:**
- Dead NPCs stay in room with `is_alive=False` — not removed; respawn restores from template
- `is_alive` / `in_combat` are runtime flags — not persisted

**Login Flow:**
- Duplicate login: kick old session (save → combat cleanup → room cleanup → close WS)
- Inventory: `Inventory.from_dict(db_data, item_lookup)` — requires loaded item defs

### Epic 12: Social Systems (Complete)

**New Managers (owned by `Game` class):**
- `TradeManager` (`server/trade/manager.py`) — mutual exchange trade sessions, async lock, state machine
- `PartyManager` (`server/party/manager.py`) — in-memory party groups, leader succession

**Key Patterns:**
- Trade and party state are **ephemeral** (in-memory only) — dissolved on server restart
- `ConnectionManager` gains name → entity_id index for `/trade @player` and `/party invite @player`
- Disconnect cleanup order: cancel trades → remove from combat → handle party departure → save state → remove from room → notify
- `ItemDef` gains `tradeable: bool = True` field (defaults `True` when missing from JSON)
- `CombatInstance` supports N players (round-robin turns, random mob targeting of alive players only)
- `CombatManager.start_combat()` accepts single entity_id or list — convenience method wrapping create+add flow
- Party combat scales mob HP by party size; `XP_PARTY_BONUS_PERCENT` (config, default 10) applies when 2+ members at victory
- `/trade` and `/party` use subcommand pattern — handler parses first arg as subcommand
- `/party <message>` (unknown subcommand) routes to party chat when in a party; `party_chat` is also a dedicated action
- `MAX_CHAT_MESSAGE_LENGTH` enforced on party chat messages
- World map reuses existing `visited_rooms` field — no new DB schema

**Config Values (all implemented):**
- `TRADE_SESSION_TIMEOUT_SECONDS = 60`
- `TRADE_REQUEST_TIMEOUT_SECONDS = 30`
- `MAX_TRADE_ITEMS = 10`
- `MAX_PARTY_SIZE = 4`
- `MAX_CHAT_MESSAGE_LENGTH = 500`
- `XP_PARTY_BONUS_PERCENT = 10`

---

## Usage Guidelines

**For AI Agents:**
- Read this file before implementing any game code
- Follow ALL rules exactly as documented
- When in doubt, prefer the more restrictive option
- Update this file if new patterns emerge

**For Humans:**
- Keep this file lean and focused on agent needs
- Update when technology stack changes
- Review periodically for outdated rules
- Remove rules that become obvious over time

### Epic 15: Server Architecture Refinement (Complete)

**Refactoring patterns established:**
- `PlayerManager` (`server/player/manager.py`) — owns session lifecycle (get/set/remove/has/iterate) and cleanup orchestration. Access via `game.player_manager`, never raw dict
- `@requires_auth` decorator (`server/net/auth_middleware.py`) — wraps all WebSocket handlers except login/register; injects `entity_id` and `player_info` kwargs. Outer function retains `(websocket, data, *, game)` signature
- Party invite state (pending, outgoing, timeouts, cooldowns) lives on `PartyManager` — handler is stateless. `PartyManager(connection_manager=...)` constructor injection
- `NpcEntity` and template functions at `server/room/npc.py` — NOT in `objects/` (NpcEntity doesn't extend RoomObject/InteractiveObject)
- `Trade` dataclass at `server/trade/session.py`, `Party` dataclass at `server/party/party.py` — separated from manager files
- `EventBus.emit()` wraps each subscriber in try/except — one failing callback doesn't crash the loop
- `RARE_CHECK_INTERVAL_SECONDS` in Settings — environment-overridable
- `SpawnCheckpoint` access via `server/room/spawn_repo.py` — never inline queries in scheduler
- `CombatInstance._resolve_effect_targets()` — single method for effect source/target resolution (no duplication)
- `RoomState.mob_states` column removed (never used) — Alembic migration drops it

**Config Values (added in Epic 15):**
- `RARE_CHECK_INTERVAL_SECONDS = 60`

### Epic 16: Server Architecture Maturation & Protocol Specification (Complete)

**Protocol & Schemas:**
- All 21 inbound actions validated via Pydantic schemas in `server/net/schemas.py` — `ACTION_SCHEMAS` dict maps action name to schema class (23 entries including `reconnect`)
- All 38 outbound message types documented as Pydantic models in `server/net/outbound_schemas.py` — documentation/validation only, handlers still use raw dicts
- Protocol spec auto-generated via `make protocol-doc`, verified via `make check-protocol`
- `with_request_id(response, data)` in `server/net/schemas.py` echoes `request_id` from inbound to outbound for request correlation

**Session Tokens & Reconnection:**
- `game.token_store` — `TokenStore` (`server/player/tokens.py`), in-memory with TTL (`SESSION_TOKEN_TTL_SECONDS: 300`). `issue(db_id)` returns token, `validate(token)` returns `db_id | None`, `revoke(token)`, `revoke_for_player(db_id)`. ADR-16-2: not DB-backed (server restart kills all state anyway)
- `handle_reconnect` (`server/net/handlers/auth.py`) — NOT decorated with `@requires_auth` (pre-auth handler, same as login/register). Three cases: Case 1 (grace period resume), Case 2 (full DB restore using Story 16.5 helpers), Case 3 (invalid token → error)
- `_build_login_response` accepts optional `session_token` param — used by both `handle_login` and `handle_reconnect`
- Token is single-use: consumed on reconnect, new token issued in response
- Logout revokes token via `token_store.revoke_for_player(db_id)`

**Disconnect Grace Period:**
- `handle_disconnect` defers cleanup for `DISCONNECT_GRACE_SECONDS` (default 120). WebSocket mapping removed immediately, trades cancelled, but combat/party/room presence preserved during grace period
- `session.disconnected_at` set to `time.time()`, `entity.connected` set to `False` on disconnect
- `Game._cleanup_handles: dict[str, asyncio.TimerHandle]` stores deferred cleanup timers — cancelled on reconnect or shutdown
- `PlayerManager.deferred_cleanup(entity_id, game)` — PUBLIC method for grace-period expiry. Skips trade + WS disconnect (already done in `handle_disconnect`). `Game._deferred_cleanup` delegates to it
- `PlayerManager.cancel_trade(entity_id, game)` — PUBLIC wrapper for immediate trade cancellation on disconnect
- If `DISCONNECT_GRACE_SECONDS == 0`, cleanup runs immediately (test mode via autouse fixture in `tests/conftest.py`)
- `handle_disconnect` checks `self._shutting_down` and returns early — shutdown handles all cleanup directly
- `handle_login` checks `player_manager.get_session(entity_id)` for grace-period sessions (WS gone, session alive) — cancels timer + cleans up before creating new session
- `RoomInstance.get_state()` includes `"connected": getattr(e, "connected", True)` in entity dict — clients render disconnected players as "away"

**Message Acknowledgment:**
- `ConnectionManager._msg_seq: dict[str, int]` — per-player outbound sequence counter
- `send_to_player_seq(entity_id, message)` — creates dict copy (`{**message, "seq": seq}`), increments counter even without WebSocket (grace period consistency). Includes try/except error guard
- `connect()` uses `setdefault(entity_id, 0)` — preserves counter on reconnect, initializes on first login
- `disconnect()` does NOT remove `_msg_seq` — grace period needs it. Only `clear_msg_seq()` removes it (called in `cleanup_session` and `deferred_cleanup`)
- Critical messages using `send_to_player_seq`: `combat_turn`, `combat_end`, `trade_update`, `xp_gained`, `level_up_available`
- Cosmetic messages (entity_moved, chat, broadcasts) do NOT include seq — ADR-16-3
- `ReconnectMessage` accepts optional `last_seq`; Case 1 reconnect sends `seq_status: up_to_date` if matching

**Combat & Heartbeat:**
- `CombatInstance` turn timeout via `loop.call_later` — `COMBAT_TURN_TIMEOUT_SECONDS: 30` now enforced. Auto-passes on timeout. Timer cancelled at START of action (before validation, prevents race)
- Combat service layer at `server/combat/service.py` — business logic extracted from handler
- `apply_xp` / `notify_xp` split in `server/core/xp.py` — `XpResult` dataclass decouples business from messaging. `grant_xp` is backward-compatible wrapper
- Heartbeat: `Game._heartbeat_tasks` + `Game._pong_events` — `asyncio.Task` + `asyncio.Event` pattern. Ping/pong at `HEARTBEAT_INTERVAL_SECONDS: 30`, timeout at `HEARTBEAT_TIMEOUT_SECONDS: 10`
- Chat messages include `"format": settings.CHAT_FORMAT` (default `"markdown"`) — server is client-agnostic per ADR-16-4

**Config Values (added in Epic 16):**
- `SESSION_TOKEN_TTL_SECONDS = 300`
- `DISCONNECT_GRACE_SECONDS = 120`
- `HEARTBEAT_INTERVAL_SECONDS = 30`
- `HEARTBEAT_TIMEOUT_SECONDS = 10`
- `CHAT_FORMAT = "markdown"`

Last Updated: 2026-04-12 (Epic 16 complete — all 14 stories done, 1062 tests passing)
