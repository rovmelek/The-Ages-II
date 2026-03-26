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
- No Alembic — schema changes require deleting `game.db`

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
- WebSocket: `async def handle_X(ws: WebSocket, data: dict, game: Game)` — `game` passed via lambda closure at registration
- REST admin: `APIRouter` with `Depends(verify_admin_secret)` — must use deferred `from server.app import game` inside each function (avoids circular imports)
- Access managers through `game.*` — never import managers directly

**Player State — Dual Storage:**
- In-memory: `game.player_entities[entity_id]` → `{"entity": PlayerEntity, "room_key": str, "inventory": Inventory}`
- DB: Persisted on disconnect, room transition, combat victory, shutdown
- `PlayerEntity`: `@dataclass` with `id`, `name`, `x`, `y`, `player_db_id`, `stats` dict, `in_combat` bool

**Effect System:**
- `EffectHandler` signature: `async (effect, source, target, context) -> dict` — all dicts
- 5 types: `damage`, `heal`, `shield`, `dot`, `draw` — handlers are stateless
- DoT recording (EffectRegistry) and DoT ticking (CombatInstance) are separate concerns

**Combat Energy:**
- Cards cost energy (start: `COMBAT_STARTING_ENERGY`, regen per cycle: `COMBAT_ENERGY_REGEN`); items and pass are free
- Config in `Settings` (Pydantic BaseSettings) in `server/core/config.py`

**Connection/Room Model:**
- `ConnectionManager` maps `entity_id → WebSocket` and `entity_id → room_key`
- On disconnect: remove from combat → save to DB → remove from room → broadcast → disconnect

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
- Repos call `session.commit()` internally — callers don't commit

**Data Classes vs Dicts:**
- Runtime entities: `@dataclass` — `PlayerEntity`, `RoomObject`, `NpcEntity`
- Combat state: plain dicts — `mob_stats`, `participant_stats`, `active_effects` (effect handlers operate generically on dicts)
- Definitions: dedicated classes — `CardDef`, `ItemDef`
- Inventory: class with `to_dict()` / `from_dict()` serialization

**Object Hierarchy:**
- `RoomObject` → `InteractiveObject` (adds `async interact()`) → `Chest`, `Lever`
- `NpcEntity` is separate — stored in `room._npcs`, not `room.objects`
- NPC templates: module-level `_NPC_TEMPLATES` dict loaded once at startup

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
- `patch("server.app.async_session")` for Game-level DB mocking
- Import ALL model modules before `create_all()` — SQLAlchemy only creates tables for registered models

**Known Issues:**
- 2 tests hang: `test_disconnect_notifies_others`, `test_register_returns_player_id` — always exclude via `-k` filter

### Platform & Build Rules

- Pure Python — no compilation; `pip install -e ".[dev]"`
- Entry point: `python run.py` → uvicorn with hot reload in DEBUG mode
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
- NEVER call `session.commit()` outside repos
- NEVER modify `_NPC_TEMPLATES` after startup
- NEVER use `==` for secret comparison — always `hmac.compare_digest()`

**Easy-to-Forget:**
- New player stats MUST be added to `_STATS_WHITELIST` in `player/repo.py` — unlisted stats are silently dropped on save
- Stairs exits use `"ascend"`/`"descend"` — NOT `"up"`/`"down"` (collision with movement directions)

**State Synchronization:**
- Combat stats sync back to `PlayerEntity.stats` after every action AND at combat end
- Strip `shield` at combat end: `entity.stats.pop("shield", None)`
- XP applied in `_check_combat_end`, NOT in `CombatInstance`
- Inventory persists immediately after combat item use
- On disconnect/kick: save to DB BEFORE removing from room/combat

**Combat Flow Order:**
1. Process DoT effects (mob + current player)
2. Check `is_finished` — early return if DoT killed
3. Check energy cost (cards only — items are free) — reject if insufficient
4. Resolve card/item effects
5. Advance turn (may trigger cycle-end mob attack + energy regen)
6. `_broadcast_combat_state()` — sync stats + send to participants
7. `_check_combat_end()` — victory/defeat cleanup, XP, respawn

**NPC Lifecycle:**
- Dead NPCs stay in room with `is_alive=False` — not removed; respawn restores from template
- `is_alive` / `in_combat` are runtime flags — not persisted

**Login Flow:**
- Duplicate login: kick old session (save → combat cleanup → room cleanup → close WS)
- Inventory: `Inventory.from_dict(db_data, item_lookup)` — requires loaded item defs

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

Last Updated: 2026-03-25
