# The Ages II — Game Server Execution Plan

## Context

Implementing the game server using the BMAD GDS module workflow. The architecture has been redesigned from the original `THE_AGES_SERVER_PLAN.md` through collaborative design sessions — all decisions are captured in `architecture.md`.

### Key Documents

| Document | Purpose |
|----------|---------|
| `architecture.md` | **Authoritative** architecture spec — directory structure, systems, data models, design decisions |
| `THE_AGES_SERVER_PLAN.md` (project root) | Original file-by-file code blueprint — still useful as implementation reference, but `architecture.md` takes precedence on structure |
| `epics.md` | Epic and story breakdown (created by `/gds-create-epics-and-stories`) |

### Decisions Made

- **Skip GDS Phases 1–2** (Game Brief, GDD) — architecture designed directly in planning sessions
- **Architecture designed in Phase 3** — captured in `architecture.md`
- **No storyline/narrative** for now — focus on playable gameplay core
- **Web demo client implemented** (`web-demo/`) — vanilla HTML/CSS/JS proof-of-concept for testing and demos; production client planned in Godot
- **Story-by-story granularity** — one story per session for easier verification
- **Domain-driven directory structure** — `core/`, `net/`, `player/`, `room/`, `combat/`, `items/`, `web/`
- **JSON-driven game content** — rooms, cards, items, NPCs defined in JSON config files
- **Deferred features** identified with hook points preserved in prototype

### Scope Priority (Prototype)

1. Project foundation (scaffolding, database, config, core services)
2. Room/zone system (100x100 tiles, objects, NPC spawning)
3. Player system + WebSocket networking (auth, movement, room transitions)
4. Combat system (cards with multi-effect chains, turn-based, one action per turn)
5. Items & inventory (consumables usable in and out of combat, materials for future upgrades)
6. Integration (Game orchestrator, sample data, global announcements, tests)

### Deferred Features (Not in Prototype)

- Card skill tree (multi-branching upgrade system)
- Web-based room editor (full level editor for player-created rooms)
- NPC dialogue, shops, quests (prototype NPCs are hostile only)
- Material drops from combat (loot tables exist for chests, combat rewards added later)
- Card respec system
- REST API endpoints (trades, filters, profiles)
- Range-based update broadcasting (optimization)

---

## Workflow Sequence

Each step should be run in a **fresh context window** per BMAD best practice.

### Step 1: Create Epics and Stories [DONE]

- **Command**: `/gds-create-epics-and-stories`
- **Input**: `architecture.md` + `THE_AGES_SERVER_PLAN.md`
- **Goal**: Break the architecture into epics and stories focused on the gameplay core
- **Epic scope** (6 epics):
  - Epic 1: Project Foundation — scaffolding, database, config, core services
  - Epic 2: Room & World System — tiles, objects, NPCs, spawning, provider pattern
  - Epic 3: Player & Networking — auth, WebSocket, connections, movement, room transitions
  - Epic 4: Combat System — cards with effect chains, combat instance, turn resolution
  - Epic 5: Items & Inventory — item definitions, inventory, in-combat and out-of-combat usage
  - Epic 6: Integration & Sample Data — Game orchestrator, handler wiring, sample data, announcements, tests

### Step 2: Sprint Planning

- **Command**: `/gds-sprint-planning`
- **Goal**: Prioritize stories into a sprint targeting the core gameplay loop

### Step 3: Story Implementation Cycle (repeat per story)

1. `/gds-create-story` — Prepare the next story with full context
2. `/gds-dev-story` — Implement the story, write tests
3. `/gds-code-review` — (optional) Review if the story is complex
4. Move to next story

### Optional: Sprint Status Checks

- **Command**: `/gds-sprint-status`
- **When**: Between stories to check progress and surface risks

---

## Verification

- **After each story**: `pytest tests/`
- **After networking stories**: `websocat ws://localhost:8000/ws/game`
- **After full sprint**: `curl localhost:8000/health` + end-to-end WebSocket gameplay test
- **Web demo client**: Open `http://localhost:8000/` to test visually in browser
