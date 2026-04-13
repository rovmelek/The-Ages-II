# Story 17.9: Extract Combat Initiation + Cleanup to Service

Status: done

## Story

As a developer,
I want combat initiation and cleanup logic extracted to `combat/service.py`,
So that the movement handler and PlayerManager are thin and combat logic is centralized.

## Acceptance Criteria

1. **AC1 — `initiate_combat()` in service:**
   - Given: `_handle_mob_encounter()` (~108 lines) in `movement.py` containing combat initiation business logic (party gathering, card loading, stats map, combat instance creation, turn timeout setup)
   - Then: `initiate_combat()` exists in `server/combat/service.py` containing all combat setup logic
   - And: `movement.py` calls `initiate_combat()` and handles only broadcasting `combat_start` messages to participants

2. **AC2 — `cleanup_participant()` in service:**
   - Given: `PlayerManager._cleanup_combat()` (~39 lines) in `player/manager.py` with combat-specific logic (stat sync, HP restore, participant removal, NPC release, remaining-player notification)
   - Then: `cleanup_participant()` exists in `server/combat/service.py`
   - And: `PlayerManager._cleanup_combat()` becomes a thin delegation (~5 lines)

3. **AC3 — Tests pass:**
   - All 1066+ tests pass with updated patch targets

## Tasks / Subtasks

- [x] Task 1: Extract `initiate_combat()` to `server/combat/service.py` (AC: #1)
  - [x] 1.1 Read `movement.py` `_handle_mob_encounter()` — identified what moves vs stays
  - [x] 1.2 Created `CombatInitResult` dataclass and `initiate_combat()` in `service.py`
  - [x] 1.3 Moved logic: party gathering, trade cancellation, card loading, stats map, `combat_manager.start_combat()`, turn timeout, participant marking
  - [x] 1.4 Refactored `_handle_mob_encounter()` to call `initiate_combat()` then broadcast

- [x] Task 2: Extract `cleanup_participant()` to `server/combat/service.py` (AC: #2)
  - [x] 2.1 Analyzed `_cleanup_combat()` — all logic moves
  - [x] 2.2 Created `cleanup_participant()` in service.py
  - [x] 2.3 Refactored `PlayerManager._cleanup_combat()` to thin delegation (3 lines)

- [x] Task 3: Update tests (AC: #3)
  - [x] 3.1 No patches needed — tests use handler/manager integration, not internal function names
  - [x] 3.2 Cleaned up unused imports: `EffectType` and `_cancel_trade_for` from movement.py, `settings` from manager.py

- [x] Task 4: All 1066 tests pass (AC: #3)

## Dev Notes

### Architecture Constraints

- `from __future__ import annotations` at top of every module
- `if TYPE_CHECKING: from server.app import Game` for Game type hints
- `combat/service.py` already exists (~263 lines) — add new functions, target ~400 lines
- `_cancel_trade_for()` stays in `movement.py` — it's a movement-handler concern (cancelling trade before entering combat)
- `make_turn_timeout_callback` is currently imported from `combat.py` handler inside `_handle_mob_encounter` — this import moves into `initiate_combat()` in service.py

### What Moves to `initiate_combat()`

From `_handle_mob_encounter()` in `movement.py` (lines 131-238):
- NPC lock acquisition and TOCTOU check (`npc._lock`, `npc.is_alive`, `npc.in_combat`)
- Party member gathering (eligible members in same room, not in combat)
- Trade cancellation for all participants (calls `_cancel_trade_for`)
- Card loading from DB
- NPC stats reading, mob HP scaling by party size
- `player_stats_map` construction
- `game.combat_manager.start_combat()` call
- Turn timeout callback registration and timer start
- Marking all participants `in_combat = True`

What stays in `movement.py`:
- Broadcasting `combat_start` to each participant's WebSocket
- The `_cancel_trade_for()` helper (or it can be passed in/called from handler)

### What Moves to `cleanup_participant()`

From `PlayerManager._cleanup_combat()` in `player/manager.py` (lines 121-159):
- Get combat instance via `game.combat_manager.get_player_instance(entity_id)`
- Sync stats back to entity from `participant_stats`
- Restore HP if dead (hp = max_hp or DEFAULT_BASE_HP)
- Set `entity.in_combat = False`
- `combat_instance.remove_participant(entity_id)` and `game.combat_manager.remove_player(entity_id)`
- If last participant: release NPC (`npc.in_combat = False`), remove combat instance
- If participants remain: send `combat_update` to remaining (best-effort)

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Story 17.9]
- [Source: server/net/handlers/movement.py — _handle_mob_encounter() lines 131-238]
- [Source: server/player/manager.py — _cleanup_combat() lines 121-159]
- [Source: server/combat/service.py — existing combat service]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Completion Notes List
- Created `initiate_combat()` + `CombatInitResult` dataclass in `combat/service.py`
- Created `cleanup_participant()` in `combat/service.py`
- Created `_cancel_trade_for_combat()` helper in `combat/service.py` (moved from movement.py)
- `movement.py` `_handle_mob_encounter()` shrunk from ~108 to ~30 lines
- `PlayerManager._cleanup_combat()` shrunk from ~39 to 3 lines (thin delegation)
- Cleaned up unused imports in movement.py and manager.py
- All 1066 tests pass

### File List
- `server/combat/service.py` (modified — added initiate_combat, cleanup_participant, CombatInitResult, _cancel_trade_for_combat)
- `server/net/handlers/movement.py` (modified — shrunk _handle_mob_encounter, removed _cancel_trade_for and unused EffectType import)
- `server/player/manager.py` (modified — _cleanup_combat now delegates to service, removed unused settings import)
