# Story 17.8: Decompose Game Class

Status: done

## Story

As a developer,
I want the Game class decomposed so that business logic lives in service modules,
So that the Game class is a thin orchestrator and code is testable in isolation.

## Acceptance Criteria

1. **AC1 — Player lifecycle methods → `player/service.py`:**
   - `kill_npc()`, `_reset_player_stats()`, `respawn_player()` moved to `server/player/service.py`
   - Game retains thin delegation wrappers per ADR-17-3

2. **AC2 — Heartbeat methods → `net/heartbeat.py`:**
   - `_start_heartbeat()`, `_cancel_heartbeat()`, `_heartbeat_loop()` moved to `server/net/heartbeat.py` (new file)
   - Game retains thin delegation wrappers

3. **AC3 — Tests pass:**
   - All 1066+ tests pass

## Tasks / Subtasks

- [x] Task 1: Extract heartbeat to `server/net/heartbeat.py` (AC: #2)
  - [x] 1.1 Created `net/heartbeat.py` with `start_heartbeat`, `cancel_heartbeat`, `_heartbeat_loop`
  - [x] 1.2 Game `_start_heartbeat` and `_cancel_heartbeat` become 1-line delegation wrappers

- [x] Task 2: Extract NPC/respawn to `server/player/service.py` (AC: #1)
  - [x] 2.1 Moved `kill_npc()`, `_reset_player_stats()`, `respawn_player()` to service.py
  - [x] 2.2 Game `kill_npc` and `respawn_player` become 1-line delegation wrappers

- [x] Task 3: Clean up imports and update tests (AC: #3)
  - [x] 3.1 Removed `SPAWN_PERSISTENT` and `find_spawn_point` imports from `app.py`
  - [x] 3.2 Updated `test_heartbeat.py` to import `_heartbeat_loop` from `server.net.heartbeat`

- [x] Task 4: All 1066 tests pass (AC: #3)

## Dev Notes

### References
- [Source: _bmad-output/planning-artifacts/epics.md — Story 17.8]
- [Source: ADR-17-3 — Game retains thin delegation wrappers]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Completion Notes List
- `app.py` shrunk from 495 to 370 lines (Game class ~290 lines)
- `player/service.py` grew from 214 to 314 lines
- Created `net/heartbeat.py` (59 lines)
- Zero patch target changes for production code mocks — delegation preserves mock surface
- Updated 2 heartbeat loop tests to call module-level function
- All 1066 tests pass

### File List
- `server/net/heartbeat.py` (created)
- `server/app.py` (modified — methods replaced with thin delegation)
- `server/player/service.py` (modified — added kill_npc, _reset_player_stats, respawn_player)
- `tests/test_heartbeat.py` (modified — updated _heartbeat_loop references)
