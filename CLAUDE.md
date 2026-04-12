# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**The-Ages-II** is a multiplayer room-based dungeon game with turn-based card combat. The project combines:
- A **BMAD framework** (v6.2.0) for AI-assisted design, planning, and project management workflows
- A **Python game server** (Epics 1-14 complete; 807 tests passing) built with FastAPI + WebSockets
- A **web demo client** (`web-demo/`) — vanilla HTML/CSS/JS proof-of-concept for testing and demos; production client planned in Godot

**Key reference documents:**
- `_bmad-output/planning-artifacts/architecture.md` — **Authoritative** architecture spec (structure, systems, data models, design decisions)
- `_bmad-output/project-context.md` — AI agent rules and implementation patterns
- `THE_AGES_SERVER_PLAN.md` — Original file-by-file blueprint (superseded by architecture.md where conflicts arise)

## BMAD System Architecture

### Core Concepts

- **Agents**: Persona-based AI roles (Architect, PM, Developer, QA, Tech Writer, Scrum Master) defined in `_bmad/*/agents/` as Markdown files with menus and capabilities
- **Skills**: 100+ structured task definitions in `.claude/skills/`, `.gemini/skills/`, `.github/skills/` — each with a `SKILL.md` metadata file
- **Workflows**: Tri-modal (Create/Edit/Validate) step-file sequences in `_bmad/*/workflows/` that enforce strict LLM compliance through small sequential MD files
- **Configuration Tokens**: Pathless tokens like `{project-root}`, `{user_name}`, `{communication_language}` signal relative paths to consuming agents

### Installed Modules

| Module | Version | Purpose |
|--------|---------|---------|
| core   | 6.2.0   | Base configuration and task system |
| bmm    | 6.2.0   | Agent framework with personas |
| bmb    | 1.1.0   | Workflow building with quality scanning |
| cis    | 0.1.9   | Creative Intelligence (design thinking, innovation, storytelling) |
| gds    | 0.2.2   | Game Dev Studio (game architecture, narrative, playtesting) |
| tea    | 1.7.1   | Test Architecture Enterprise (ATDD, automation, CI, NFR) |
| wds    | 0.3.0   | WDS Expansion (8-phase design workflow) |

### Key Directories

- `_bmad/` — Core BMAD system (agents, skills, workflows, config)
- `_bmad/_config/` — Installation manifest, agent/skill/task/workflow manifests (CSV + YAML)
- `_bmad-output/` — Generated outputs: `planning-artifacts/`, `implementation-artifacts/`, `test-artifacts/`
- `design-artifacts/` — Design phase outputs (A-Product-Brief through G-Product-Development)
- `.claude/skills/` — Claude Code skill definitions (primary IDE integration)

### Configuration

- User config: `_bmad/core/config.yaml` (user_name: Kevin, language: English)
- Module configs: `_bmad/<module>/config.yaml`
- Project context: When created, `project-context.md` serves as the foundational reference for all agents

## Game Server

### Tech Stack
- **Python 3.11+**, FastAPI, WebSockets (real-time game communication)
- **SQLAlchemy async** + SQLite (aiosqlite) for persistence
- **Alembic** for schema migrations (`make db-migrate`); `create_all` still used at startup alongside Alembic
- **Pydantic** for message schemas and settings
- **bcrypt** for password hashing
- **pytest** + **pytest-asyncio** for testing (807 tests)

### Commands
```bash
make install                   # install with dev dependencies
make server                    # start server on port 8000
make test                      # run tests (uses .venv/bin/python)
make test-verbose              # run tests with verbose output
make db-migrate                # run Alembic migrations (alembic upgrade head)
curl localhost:8000/health     # health check
open http://localhost:8000     # web demo client (requires server running)
```

> **Important**: Always use `make test` (or `.venv/bin/python -m pytest`) — never bare `pytest`. The system Python lacks project dependencies.

### Server Architecture

`Game` class in `server/app.py` is the central orchestrator, owning all managers:

- **RoomManager** (`server/room/manager.py`) — loads tile-based rooms from JSON files → SQLite → memory
- **CombatManager** (`server/combat/manager.py`) — creates/tracks `CombatInstance` objects for turn-based card combat (multi-player party combat complete in Epic 12)
- **ConnectionManager** (`server/net/connection_manager.py`) — maps WebSocket connections ↔ player entity IDs + room tracking + name → entity_id index
- **TradeManager** (`server/trade/manager.py`) — mutual exchange trade sessions with state machine, async locks, timeouts
- **PartyManager** (`server/party/manager.py`) — in-memory party groups with leader/member tracking, invite system, succession, party chat
- **MessageRouter** (`server/net/message_router.py`) — routes incoming JSON by `action` field to handler modules in `server/net/handlers/`
- **Scheduler** (`server/core/scheduler.py`) — async scheduling for mob respawns and rare spawn checks
- **EventBus** (`server/core/events.py`) — global announcements, cross-system triggers
- **EffectRegistry** (`server/core/effects/`) — shared card + item effect resolution (damage, heal, shield, dot, draw)

### Key Server Features

- **Combat**: Turn-based card combat with DoT effect ticking (poison/bleed tick each turn), shield absorption; multi-player party combat in-progress (Epic 12)
- **Persistence**: Player stats (`hp`, `max_hp`, `attack`, `xp`, 6 D&D abilities, level), position, inventory, and visited rooms saved on disconnect, room transition, combat end, and server shutdown
- **Death & Respawn**: Defeated players respawn in `town_square` with full HP
- **Duplicate Login Protection**: Old session kicked (state saved) when same account logs in from another connection
- **Graceful Shutdown**: All player states saved, clients notified, WebSockets closed cleanly
- **NPC Spawning**: Three-tier system (persistent, timed, rare with chance roll + global announcements)
- **Card Energy System**: Cards cost energy to play (configurable starting energy + per-cycle regen); items and pass are free
- **Vertical Exits**: Stairs tiles (`STAIRS_UP`/`STAIRS_DOWN`) with `"ascend"`/`"descend"` exit directions (distinct from movement `"up"`/`"down"`)
- **Admin REST API**: Authenticated endpoints (`/admin/status`, `/admin/shutdown`, `/admin/restart`) protected by `ADMIN_SECRET` env var with `hmac.compare_digest`
- **Centralized Config**: All game balance values must reference `settings.*` from `server/core/config.py` — never hardcode HP, attack, stat defaults, spawn room, auth lengths, etc.
- **NPC Templates**: `game.npc_templates` is the single source of truth — no module-level global. Pass `templates` dict to `create_npc_from_template()`.
- **Tile Modification**: Use `RoomInstance.set_tile(x, y, tile_type)` — never access `_grid` directly from outside `room.py`.
- **Handler Auth Middleware**: All WebSocket handlers (except `handle_login`/`handle_register`) use `@requires_auth` decorator from `server/net/auth_middleware.py`. The decorator injects `entity_id: str` and `player_info: PlayerSession` as keyword arguments. Never duplicate the auth-check boilerplate manually.
- **Party Invite State**: All invite tracking (pending, outgoing, timeouts, cooldowns) lives on `PartyManager` — the party handler (`server/net/handlers/party.py`) is stateless. `PartyManager` takes `connection_manager` via constructor injection. Never add module-level mutable state to handler files.

### Directory Structure
```
server/
├── core/          # Config, database, scheduler, event bus, shared effect registry
├── net/           # WebSocket connection manager, message router, auth middleware
│   └── handlers/  # auth, movement, chat, combat, inventory, interact, trade, party, admin
├── player/        # Player model, repo (stats whitelist), entity, auth (bcrypt)
├── room/          # Room model, repo, tile system, room instance, manager, provider
│   └── objects/   # NPC entity, chest, lever, base classes, registry, state
├── combat/        # Combat instance (DoT ticking, turn resolution), manager
│   └── cards/     # Card definitions, hand management, card repo
├── items/         # Item definitions, item repo, inventory (serialization)
├── trade/         # TradeManager, trade session state machine
├── party/         # PartyManager, party dataclass, leader succession
data/
├── rooms/         # Room definitions (4 rooms: town_square, dark_cave, test_room, other_room)
├── cards/         # Card set definitions (JSON)
├── items/         # Item definitions (JSON)
└── npcs/          # NPC template definitions (JSON)
alembic/           # Alembic migrations (env.py, versions/)
tests/             # pytest — 49 test files (flat structure)
web-demo/          # Browser-based test/demo client (vanilla HTML/CSS/JS)
├── index.html     # Auth, game viewport, combat overlay
├── css/style.css  # Dark theme, tiles, cards
├── js/game.js     # WebSocket client, state, all UI
└── jsconfig.json  # IDE type-checking
```

### Endpoints
- **Web Demo**: `GET /` — serves `web-demo/index.html` (test client)
- **Static Assets**: `/static/*` — serves `web-demo/` directory
- **WebSocket**: `/ws/game` — JSON messages with `action` field (login, register, move, chat, play_card, pass_turn, flee, use_item, use_item_combat, interact, inventory, look, who, stats, help, logout, trade, party, party_chat, map)
- **Admin REST**: `/admin/status`, `/admin/shutdown`, `/admin/restart` — requires `Authorization: Bearer <ADMIN_SECRET>` header
- **Health**: `GET /health` — basic health check

### Room Topology
4 rooms connected in a circular loop (each room has 2 exits):
```
town_square ←→ test_room ←→ other_room ←→ dark_cave ←→ town_square
```
Default player spawn room: `town_square` (100x100)

## Working With This Project

### Skills & Slash Commands

Invoke BMAD workflows through slash commands. Key workflows:

- `/bmad-help` — Get guidance on which workflow or agent to use next
- `/gds-create-game-brief` — Start game brief creation
- `/gds-create-gdd` — Create Game Design Document
- `/gds-game-architecture` — Design game architecture
- `/gds-create-epics-and-stories` — Break requirements into epics/stories
- `/gds-dev-story` — Execute story implementation from a spec file
- `/gds-quick-dev` — Flexible dev workflow for direct instructions or tech-specs
- `/gds-code-review` — Thorough code review
- `/gds-sprint-planning` — Generate sprint plans from epics
- `/gds-sprint-status` — Check sprint progress and risks

### Bug Fix Procedure (ISS)

When fixing any bug, warning, or issue (whether found during testing, code review, or user report):

1. **Document first**: Create `_bmad-output/implementation-artifacts/issues/ISS-NNN-<slug>.md` with severity, root cause, proposed fix, and impact. Find the next ISS number by checking existing files in that directory.
2. **Review**: Verify the issue doc's claims (file paths, line numbers, root cause) against the actual codebase before implementing.
3. **Fix**: Implement the fix.
4. **Track**: Add entry to `sprint-status.yaml` with status `done`.

**Never fix a bug without creating the ISS doc first.** This applies even for trivial fixes like test warnings.

### Design Workflow Phases (WDS)

The project follows an 8-phase design workflow:
0. Project Setup → 1. Project Brief → 2. Trigger Mapping → 3. UX Scenarios → 4. UX Design → 5. Agentic Development → 6. Asset Generation → 7. Design System → 8. Product Evolution
