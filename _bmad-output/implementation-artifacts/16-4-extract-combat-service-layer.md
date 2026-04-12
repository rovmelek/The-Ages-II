# Story 16.4: Extract Combat Service Layer

Status: done

## Story

As a **server developer**,
I want combat business logic separated from the WebSocket handler,
So that combat orchestration (XP, loot, NPC outcomes, respawn) is testable independently and the handler only does I/O.

## Acceptance Criteria

1. **Given** `server/net/handlers/combat.py` contains 7 business logic functions (lines 22-38, 53-68, 71-79, 82-119, 142-159, 162-173, 176-251): `_sync_combat_stats`, `_clean_player_combat_stats`, `_award_combat_xp`, `_distribute_combat_loot`, `_handle_npc_combat_outcome`, `_respawn_defeated_players`, `_check_combat_end`,
   **When** Story 16.4 is implemented,
   **Then** all 7 functions are relocated to `server/combat/service.py` (dropping the leading underscore since they are now public module-level functions),
   **And** `finalize_combat` (renamed from `_check_combat_end`) returns per-player data for the handler to send messages.

2. **Given** `_broadcast_combat_state` (lines 41-50) and `_send_combat_end_message` (lines 122-139) do WebSocket I/O,
   **When** Story 16.4 is implemented,
   **Then** they remain in the handler file.

3. **Given** handler functions `handle_play_card`, `handle_pass_turn`, `handle_use_item_combat`, `handle_flee`,
   **When** Story 16.4 is implemented,
   **Then** they call service functions for business logic and handle WebSocket I/O themselves.

4. **Given** 30 references across 4 test files that import or patch `server.net.handlers.combat.*` for business logic functions:
   - `test_party_combat.py`: 10 references (3 direct imports of `_check_combat_end`, 6 patches of `player_repo`/`grant_xp`, 1 import of `handle_flee`)
   - `test_loot.py`: 18 references (6 direct imports of `_check_combat_end`, 12 patches of `player_repo`/`items_repo`)
   - `test_stats_persistence.py`: 1 reference (direct import of `_sync_combat_stats`)
   - `test_integration.py`: 1 reference (patch of `player_repo`)
   **When** functions move to `server.combat.service`,
   **Then** all import/patch targets are updated to new module paths,
   **And** all 959+ tests pass with no assertion value changes.

5. **Given** `handle_flee` (lines 280-321) contains business logic for participant removal (lines 296-301) and NPC release on last-player-fled (lines 315-321),
   **When** Story 16.4 is implemented,
   **Then** that logic moves to `service.handle_flee_outcome(instance, entity_id, game)` in `server/combat/service.py`,
   **And** `handle_flee` in the handler only does validation, calls service, and sends WebSocket messages.

## Tasks / Subtasks

- [x] Task 1: Create `server/combat/service.py` with relocated business logic (AC: #1)
  - [x] 1.1: Create `server/combat/service.py` with `from __future__ import annotations`
  - [x] 1.2: Move `_sync_combat_stats` → `sync_combat_stats` (unchanged logic)
  - [x] 1.3: Move `_clean_player_combat_stats` → `clean_player_combat_stats` (unchanged logic)
  - [x] 1.4: Move `_award_combat_xp` → `award_combat_xp` (unchanged logic)
  - [x] 1.5: Move `_distribute_combat_loot` → `distribute_combat_loot` (unchanged logic)
  - [x] 1.6: Move `_handle_npc_combat_outcome` → `handle_npc_combat_outcome` (unchanged logic)
  - [x] 1.7: Move `_respawn_defeated_players` → `respawn_defeated_players` (unchanged logic)
  - [x] 1.8: Move `_check_combat_end` → `finalize_combat`, returns `CombatEndResult` dataclass (or `None`). Post-combat actions (NPC outcome, respawn, instance removal) moved to handler to preserve message ordering.

- [x] Task 2: Add `handle_flee_outcome` to service (AC: #5)
  - [x] 2.1: Extract participant removal logic into `handle_flee_outcome`
  - [x] 2.2: Extract last-player-fled NPC release logic into `handle_flee_outcome`
  - [x] 2.3: `handle_flee_outcome` returns `FleeOutcome(participants_remain=bool)`

- [x] Task 3: Update `server/net/handlers/combat.py` to delegate to service (AC: #2, #3)
  - [x] 3.1: Remove all 7 business logic functions from handler
  - [x] 3.2: Add `from server.combat import service` import
  - [x] 3.3: Update `_broadcast_combat_state` to call `service.sync_combat_stats`
  - [x] 3.4: Handler `_check_combat_end` calls `service.finalize_combat`, sends messages, then calls `service.handle_npc_combat_outcome`, `service.respawn_defeated_players`, `remove_instance`
  - [x] 3.5: Update `handle_flee` to call `service.handle_flee_outcome`
  - [x] 3.6: Keep `_broadcast_combat_state` and `_send_combat_end_message` in handler
  - [x] 3.7: Removed unused imports (`math`, `settings`, `grant_xp`, `ItemDef`, `items_repo`); kept `player_repo` (used by `handle_use_item_combat`)

- [x] Task 4: Update test patch targets (AC: #4)
  - [x] 4.1: `test_party_combat.py`: 3 imports + 6 patches retargeted to `server.combat.service`
  - [x] 4.2: `test_loot.py`: 6 imports + 12 patches retargeted; 3 tests updated to check returned `CombatEndResult` instead of WebSocket messages
  - [x] 4.3: `test_stats_persistence.py`: 1 import retargeted
  - [x] 4.4: `test_integration.py`: added `patch("server.combat.service.player_repo")` alongside existing handler patch

- [x] Task 5: Run full test suite (AC: #4)
  - [x] 5.1: Run `make test` — 959 passed, 0 failures

## Dev Notes

### Current Combat Handler Structure (server/net/handlers/combat.py, 389 lines)

**Business logic functions (move to service.py):**

| Function | Lines | What it does |
|----------|-------|-------------|
| `_sync_combat_stats` | 22-38 | Sync combat HP/max_hp back to entity + DB persist |
| `_clean_player_combat_stats` | 53-68 | Clear shield/energy, sync final stats, return alive bool |
| `_award_combat_xp` | 71-79 | Award XP via `grant_xp` to surviving victors |
| `_distribute_combat_loot` | 82-119 | Roll loot, persist to DB, update runtime inventory |
| `_handle_npc_combat_outcome` | 142-159 | Kill NPC on victory (+ room broadcast), release on defeat |
| `_respawn_defeated_players` | 162-173 | On defeat, respawn dead players in town_square |
| `_check_combat_end` | 176-251 | Combat-end orchestration hub (XP, loot, stats, messages) |

**WebSocket I/O functions (stay in handler):**

| Function | Lines | What it does |
|----------|-------|-------------|
| `_broadcast_combat_state` | 41-50 | Broadcast `combat_turn` to all participants |
| `_send_combat_end_message` | 122-139 | Build per-player `combat_end` message |

**Handler functions (stay, but delegate to service):**

| Function | Lines | What it does |
|----------|-------|-------------|
| `handle_play_card` | 253-277 | Play card → broadcast → check end |
| `handle_flee` | 280-321 | Flee → remove participant → broadcast/cleanup |
| `handle_use_item_combat` | 324-365 | Use item → broadcast → check end |
| `handle_pass_turn` | 368-389 | Pass → broadcast → check end |

### Key Refactoring Details

**`finalize_combat` return value**: Instead of calling `_send_combat_end_message` inline (current line 246), the service function returns a dict:
```python
{
    "participant_ids": list[str],
    "end_result": dict,
    "rewards_per_player": dict,
    "player_loot": dict[str, list[dict]],
}
```
The handler iterates this to send messages. Returns `None` if combat continues.

**`handle_flee_outcome` return value**: Returns a dict or namedtuple indicating whether participants remain and what cleanup was done, so the handler knows what messages to send.

### Import Changes

**service.py needs these imports** (moved from handler):
- `math`, `logging`
- `from server.core.config import settings`
- `from server.core.xp import grant_xp`
- `from server.items.item_def import ItemDef`
- `from server.items import item_repo as items_repo`
- `from server.player import repo as player_repo`

**handler.py removes**: `math`, `settings`, `grant_xp`, `ItemDef`, `items_repo`, `player_repo`
**handler.py adds**: `from server.combat import service`
**handler.py keeps**: `logging`, `WebSocket`, `requires_auth`, `PlayerSession`, `TYPE_CHECKING`, `Game`

### Test Patch Impact Summary

| Test File | References | What changes |
|-----------|-----------|--------------|
| `test_party_combat.py` | 10 | 3 imports + 6 patches retarget to `server.combat.service`; 1 `handle_flee` import unchanged |
| `test_loot.py` | 18 | 6 imports + 12 patches retarget to `server.combat.service` |
| `test_stats_persistence.py` | 1 | 1 import retargets to `server.combat.service` |
| `test_integration.py` | 1 | 1 patch may need retargeting (depends on whether handler still imports `player_repo`) |

### Previous Story Intelligence (16.4a)

- `grant_xp` was split into `apply_xp` + `notify_xp` in Story 16.4a
- The service file should import `grant_xp` (the wrapper), not `apply_xp`/`notify_xp` directly — callers don't need the split yet
- `PlayerSession` constructor: `PlayerSession(entity=..., room_key=..., db_id=...)`

### Architecture Compliance

- **New file**: `server/combat/service.py` — in existing `server/combat/` package
- **Pattern**: Business/handler separation matches Story 14.5 pattern
- **No new dependencies** — imports are relocated, not added
- **Testing**: Use `make test` (never bare `pytest`)
- **Pure refactor**: Zero gameplay behavior changes

### References

- [Source: _bmad-output/planning-artifacts/epic-16-tech-spec.md#Story-16.4] — Full implementation spec
- [Source: _bmad-output/planning-artifacts/epics.md#Story-16.4] — Acceptance criteria
- [Source: server/net/handlers/combat.py] — Current implementation (390 lines)
- [Source: CLAUDE.md] — Project conventions

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Completion Notes List

- Created `server/combat/service.py` with 7 relocated business logic functions + 2 new dataclasses (`CombatEndResult`, `FleeOutcome`) + `handle_flee_outcome`
- `finalize_combat` returns `CombatEndResult` data; handler sends messages then calls post-combat actions (NPC outcome, respawn, instance removal) — preserves message ordering (combat_end before room_state)
- Handler reduced from 389 to ~170 lines — only validation, I/O, and delegation remain
- Handler keeps `player_repo` import (needed by `handle_use_item_combat` for inventory persistence)
- 30 test references across 4 files retargeted from `server.net.handlers.combat` to `server.combat.service`
- 3 loot tests updated to check returned `CombatEndResult` instead of WebSocket messages
- `test_integration.py` gets additional `server.combat.service.player_repo` mock
- 959 tests pass, 0 failures

### File List

- `server/combat/service.py` — New: 7 business logic functions + `CombatEndResult`, `FleeOutcome` dataclasses + `handle_flee_outcome`
- `server/net/handlers/combat.py` — Modified: removed business logic, delegates to service
- `tests/test_party_combat.py` — Modified: retargeted imports and patches
- `tests/test_loot.py` — Modified: retargeted imports/patches + updated 3 tests for returned data
- `tests/test_stats_persistence.py` — Modified: retargeted import
- `tests/test_integration.py` — Modified: added service player_repo mock
