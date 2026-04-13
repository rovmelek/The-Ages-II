# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**The-Ages-II** is a multiplayer room-based dungeon game with turn-based card combat:
- **Python game server** (Epics 1-18 complete; ~1083 tests passing) — FastAPI + WebSockets
- **Web demo client** (`web-demo/`) — vanilla HTML/CSS/JS proof-of-concept for testing and demos
- **BMAD framework** (v6.2.0) — AI-assisted design, planning, and project management workflows
- **Production client** — planned in Godot (protocol spec delivered, unblocked)

**Key reference documents:**
- `_bmad-output/planning-artifacts/architecture.md` — **Authoritative** architecture spec
- `_bmad-output/project-context.md` — AI agent rules and implementation patterns
- `_bmad-output/implementation-artifacts/tech-spec-energy-system-combat-rebalance.md` — Epic 18 tech spec
- `_bmad-output/planning-artifacts/epic-16-tech-spec.md` — Epic 16 tech spec
- `THE_AGES_SERVER_PLAN.md` — Original blueprint (superseded by architecture.md where conflicts arise)

## Development Principles

These principles govern all development decisions. Follow them in every session.

1. **Web demo is proof-of-concept only** — `web-demo/` must NOT contain any game logic. It is a thin client that renders server state and sends user actions via WebSocket. All game rules, validation, and state management live on the server.

2. **Server codebase is well organized and structured** — Maintain the existing modular architecture under `server/`: `core/`, `net/`, `player/`, `room/`, `combat/`, `items/`, `trade/`, `party/`. Each module has clear boundaries. Handlers are thin routing; business logic lives in service modules. Do not introduce cross-cutting concerns that bypass module boundaries.

3. **Easy to add features and plugins** — New features should follow existing patterns: define data in `data/` JSON files, add handlers in `server/net/handlers/`, add services in the appropriate domain module, register effects via `EffectRegistry`. The `EventBus` enables cross-system communication without tight coupling.

4. **Database-agnostic persistence** — All database access uses SQLAlchemy async ORM with repository pattern (`player_repo`, `room_repo`, `card_repo`, `spawn_repo`). Never write raw SQL. This ensures easy migration to PostgreSQL or any SQLAlchemy-supported backend. Alembic manages schema migrations (`make db-migrate`). See Architecture Constraints for specific DB access rules.

5. **Engine-agnostic client integration** — The server communicates via a well-defined JSON WebSocket protocol. Any client (Godot, Unity, Unreal, browser) can connect. Server must never assume client implementation details. Keep server responses self-contained with all data a client needs to render state.

6. **Well-defined network protocol** — 23 inbound Pydantic schemas (`server/net/schemas.py`), 41 outbound (`server/net/outbound_schemas.py`). Auto-generated spec: `make protocol-doc`. Validation: `make check-protocol`. Protocol version tracked in `server/core/constants.py` (`PROTOCOL_VERSION`). Bump version when adding/changing message types.

7. **Chat supports markdown** — Chat messages include `"format": settings.CHAT_FORMAT` (default `"markdown"`). Server is format-agnostic; clients choose how to render.

8. **Centralized configuration** — All game balance values, constants, and tuning parameters must reference `settings.*` from `server/core/config.py`. Cross-cutting constants live in `server/core/constants.py`. See Architecture Constraints for specific rules.

## AI Assistant Rules

Follow these rules in every interaction. They are non-negotiable.

9. **Never assume — ask if you have questions.** Do not guess at intent, requirements, or implementation approach. If something is ambiguous, ask for clarification before proceeding.

10. **Always show your thought process and logic.** Explain your reasoning, trade-offs considered, and why you chose a particular approach. Make your decision-making transparent.

11. **Adversarial review loop for all analysis and evaluation.** Before presenting any analysis, review, or evaluation:
    1. Read `.claude/skills/bmad-review-adversarial-general/workflow.md` for review criteria.
    2. Perform a full adversarial pass — verify every claim, API reference, file path, and function name against actual code in the codebase. List every finding.
    3. Fix all findings.
    4. Repeat from step 2 on the corrected content. Each repeat must be a full pass against the codebase, not a re-read of your own edits.
    5. Minimum 2 full passes. Print "Pass N: X findings" after each.
    6. Exit only after a pass prints "0 findings."

## BMAD System

- **Agents**: Persona-based AI roles defined in `_bmad/*/agents/`
- **Skills**: Structured task definitions in `.claude/skills/`, `.gemini/skills/`, `.github/skills/`
- **Workflows**: Step-file sequences in `_bmad/*/workflows/` enforcing structured LLM task execution
- **Config**: `_bmad/core/config.yaml` (user_name: Kevin, language: English)
- **Outputs**: `_bmad-output/` — `planning-artifacts/`, `implementation-artifacts/`, `test-artifacts/`

## Game Server

### Tech Stack
- **Python 3.11+**, FastAPI, WebSockets
- **SQLAlchemy async** + SQLite (aiosqlite); Alembic for migrations; `create_all` also runs at startup
- **Pydantic** for message schemas and settings
- **bcrypt** for password hashing
- **pytest** + **pytest-asyncio** for testing (~1083 tests)

### Commands
```bash
make install          # Install with dev dependencies
make server           # Start server on port 8000
make test             # Run tests (uses .venv/bin/python)
make test-verbose     # Run tests with verbose output
make db-migrate       # Run Alembic migrations
make protocol-doc     # Generate protocol spec
make check-protocol   # Validate protocol spec is up to date
```

> **Important**: Always use `make test` (or `.venv/bin/python -m pytest`) — never bare `pytest`. The system Python lacks project dependencies.

### Architecture

`Game` class (`server/app.py`) is the central orchestrator with thin delegation — business logic lives in service modules.

**Managers:**
| Manager | Location | Purpose |
|---------|----------|---------|
| RoomManager | `server/room/manager.py` | Tile-based rooms from JSON → SQLite → memory |
| CombatManager | `server/combat/manager.py` | Turn-based card combat instances |
| ConnectionManager | `server/net/connection_manager.py` | WebSocket ↔ player entity ID mapping |
| PlayerManager | `server/player/manager.py` | Session lifecycle + disconnect cleanup |
| PartyManager | `server/party/manager.py` | Party groups, invites, leader succession |
| TradeManager | `server/trade/manager.py` | Trade sessions with state machine + locks |
| MessageRouter | `server/net/message_router.py` | Routes JSON by `action` field to handlers |
| Scheduler | `server/core/scheduler.py` | Async mob respawns + rare spawn checks |
| EventBus | `server/core/events.py` | Cross-system triggers (error-isolated) |
| EffectRegistry | `server/core/effects/registry.py` | Shared card + item effect resolution |

**Service Layer** (handlers are thin routing — logic lives here):
| Service | Location | Key Functions |
|---------|----------|---------------|
| Player Service | `server/player/service.py` | `setup_full_session`, `build_stats_payload`, `kill_npc`, `respawn_player`, `find_spawn_point` |
| Combat Service | `server/combat/service.py` | `initiate_combat`, `finalize_combat`, `cleanup_participant`, `handle_flee_outcome` |
| Trade Service | `server/trade/service.py` | `execute_trade` |
| XP Notifications | `server/net/xp_notifications.py` | `grant_xp`, `notify_xp`, `send_level_up_available` |
| Heartbeat | `server/net/heartbeat.py` | `start_heartbeat`, `cancel_heartbeat` |
| Errors | `server/net/errors.py` | `ErrorCode` (StrEnum), `send_error`, `sanitize_validation_error` |

### Key Features

- **Combat**: Turn-based card combat with DoT ticking (poison/bleed per turn), shield absorption, multi-player party combat
- **Energy System**: Persistent player stat derived from INT+WIS (`max_energy = DEFAULT_BASE_ENERGY + INT * INT_ENERGY_PER_POINT + WIS * WIS_ENERGY_PER_POINT`). Cards have `card_type` field: `"physical"` (free) or `"magical"` (costs energy). Combat energy regens per cycle via `compute_energy_regen()` in `server/combat/instance.py`. Out-of-combat HP/energy regen via `server/core/regen.py` (standalone module). Energy potion uses `restore_energy` effect type (`server/core/effects/restore_energy.py`).
- **Persistence**: Player stats (hp, max_hp, energy, max_energy, attack, xp, 6 D&D abilities, level), position, inventory, visited rooms — saved on disconnect, room transition, combat end, and shutdown
- **Death & Respawn**: Defeated players respawn in `town_square` with full HP/energy; `active_effects` cleared
- **NPC Spawning**: Three-tier system (persistent, timed, rare with chance roll + global announcements)
- **Duplicate Login Protection**: Old session kicked (state saved) when same account re-logs
- **Graceful Shutdown**: All states saved, clients notified, WebSockets closed
- **Vertical Exits**: Stairs tiles (`STAIRS_UP`/`STAIRS_DOWN`) with `"ascend"`/`"descend"` exit directions
- **Admin REST API**: `/admin/status`, `/admin/shutdown`, `/admin/restart` — protected by `ADMIN_SECRET` env var with `hmac.compare_digest`
- **Session Tokens**: `TokenStore` (`server/player/tokens.py`) in-memory, 300s TTL. Grace period: `DISCONNECT_GRACE_SECONDS=120`, deferred cleanup
- **Message Sequence Numbers**: `send_to_player_seq()` on `ConnectionManager` with per-player `_msg_seq` counter
- **Combat Turn Timeout**: `COMBAT_TURN_TIMEOUT_SECONDS: 30` enforced via `loop.call_later`

### Architecture Constraints

These are hard rules. Violating them causes regressions.

- **Config**: All tunable values via `settings.*` from `server/core/config.py` — never hardcode
- **NPC Templates**: `game.npc_templates` is the single source of truth — no module-level global. Pass `templates` dict to `create_npc_from_template()` in `server/room/npc.py`
- **Tile Modification**: Use `RoomInstance.set_tile(x, y, tile_type)` — never access `_grid` directly
- **Spawn Checkpoints**: All DB access via `server/room/spawn_repo.py` (`get_checkpoint`, `upsert_checkpoint`, `get_all_checkpoints`) — never inline queries
- **Auth Middleware**: All WebSocket handlers (except `handle_login`, `handle_register`, and `handle_reconnect`) use `@requires_auth` from `server/net/auth_middleware.py`. It injects `entity_id` and `player_info` kwargs. Never duplicate auth-check boilerplate.
- **Party Invite State**: Lives on `PartyManager` — party handler (`server/net/handlers/party.py`) is stateless. `PartyManager` takes `connection_manager` via constructor injection. No module-level mutable state in handlers.
- **Database Access**: All queries go through repository modules (`player_repo`, `room_repo`, `card_repo`, `spawn_repo`). Never inline `select()` outside repositories.
- **StrEnum Pattern**: Type constants use `StrEnum` — compares equal to plain strings, JSON wire protocol unchanged
- **Dual-Patch Test Pattern**: When a repo module is imported by both handler and service, tests must patch both import paths with the same mock
- **Constants**: Cross-cutting constants in `server/core/constants.py` (`STAT_NAMES`, `EffectType`, `SPAWN_PERSISTENT`, `SPAWN_RARE`, `PROTOCOL_VERSION`). Domain-specific constants stay in their modules (`TradeState` in `server/trade/session.py`, `BEHAVIOR_HOSTILE` in `server/room/npc.py`).

### Directory Structure
```
server/
├── core/          # Config, database, scheduler, event bus, effects, constants, xp, regen
├── net/           # Connection manager, message router, auth middleware, heartbeat, xp notifications, errors
│   └── handlers/  # auth, movement, chat, combat, inventory, interact, trade, party, admin, levelup, query
├── player/        # Player model, repo, entity, auth (bcrypt), manager, service, tokens
├── room/          # Room model, repo, tile system, room instance, manager, provider, npc, spawn repo
│   └── objects/   # Chest, lever, base classes, registry, state
├── combat/        # Combat instance, manager, service
│   └── cards/     # Card definitions, hand management, card repo
├── items/         # Item definitions, item repo, inventory
├── trade/         # Trade manager, session, service
├── party/         # Party manager, party dataclass, leader succession
data/
├── rooms/         # Room definitions (town_square, dark_cave, test_room, other_room)
├── cards/         # Card set definitions (JSON)
├── items/         # Item definitions (JSON)
└── npcs/          # NPC template definitions (JSON)
alembic/           # Schema migrations
tests/             # pytest test files (flat structure)
web-demo/          # Browser-based demo client (vanilla HTML/CSS/JS)
```

**Room Topology**: 4 rooms in circular loop — `town_square ↔ test_room ↔ other_room ↔ dark_cave ↔ town_square`. Default spawn: `town_square`.

### Endpoints
- `GET /` — serves `web-demo/index.html`
- `GET /health` — health check
- `/static/*` — serves `web-demo/` directory
- `/ws/game` — WebSocket (JSON with `action` field)
- `/admin/status`, `/admin/shutdown`, `/admin/restart` — REST, requires `Authorization: Bearer <ADMIN_SECRET>`

## Working With This Project

### Skills & Slash Commands

Invoke BMAD workflows through slash commands:
- `/bmad-help` — Guidance on which workflow to use next
- `/gds-create-game-brief` — Game brief creation
- `/gds-create-gdd` — Game Design Document
- `/gds-game-architecture` — Game architecture design
- `/gds-create-epics-and-stories` — Break requirements into epics/stories
- `/gds-dev-story` — Execute story implementation from spec
- `/gds-quick-dev` — Flexible dev workflow
- `/gds-code-review` — Code review
- `/gds-sprint-planning` — Sprint plans from epics
- `/gds-sprint-status` — Sprint progress and risks

### Bug Fix Procedure (ISS)

When fixing any bug, warning, or issue (whether found during testing, code review, or user report):

1. **Document first**: Create `_bmad-output/implementation-artifacts/issues/ISS-NNN-<slug>.md` with severity, root cause, proposed fix, and impact. Find the next ISS number by checking existing files in that directory.
2. **Review**: Verify the issue doc's claims (file paths, function names, root cause) against the actual codebase before implementing.
3. **Fix**: Implement the fix.
4. **Track**: Add entry to `_bmad-output/implementation-artifacts/sprint-status.yaml` with status `done`.

**Never fix a bug without creating the ISS doc first.** This applies even for trivial fixes.

### Story Specification Guidelines

When creating story files (via `/gds-create-story` or manually):

- **Use function/class names as the primary code reference** — never line numbers alone. Function names are stable; line numbers shift. Write `in _broadcast_combat_state()` rather than `at combat.py:41-50`.
- Line numbers may be included parenthetically (e.g., `in _broadcast_combat_state() (~line 41)`) but never as the only identifier.
- When creating story specs with adversarial review, verify all function name references exist in the current codebase.
