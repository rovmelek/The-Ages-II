# Story 16.4a: Refactor grant_xp — Separate Business from Messaging

Status: done

## Story

As a **server developer**,
I want `grant_xp` split into `apply_xp` (business + DB) and `notify_xp` (WebSocket messaging),
So that the combat service (Story 16.4) can apply XP without triggering WebSocket side effects.

## Acceptance Criteria

1. **Given** `grant_xp` currently mixes XP calculation, DB persistence, and WebSocket messaging in one function (`server/core/xp.py:29-82`),
   **When** Story 16.4a is implemented,
   **Then** `apply_xp(entity_id, player_entity, amount, source, detail, game, apply_cha_bonus=True, session=None)` performs XP math + DB write and returns an `XpResult` dataclass,
   **And** `notify_xp(entity_id, result, player_entity, game)` sends `xp_gained` and optional `level_up_available` messages,
   **And** `grant_xp` wrapper calls `apply_xp` then `notify_xp` — identical behavior to current implementation.

2. **Given** `apply_xp` takes `entity_id` as its first parameter,
   **When** it looks up the player session for level-up detection,
   **Then** it uses the passed `entity_id` directly via `game.player_manager.get_session(entity_id)` — never reconstructs it from `player_db_id`.

3. **Given** all 3 existing call sites and all test references,
   **When** Story 16.4a is implemented,
   **Then** all use the unchanged `grant_xp` wrapper and pass without modification.

4. **Given** `XpResult` dataclass,
   **When** defined,
   **Then** it has fields: `final_xp: int`, `source: str`, `detail: str`, `new_total_xp: int`, `level_up_available: bool`, `new_level: int | None = None`.

5. **Given** all 808+ existing tests,
   **When** Story 16.4a is implemented,
   **Then** all tests pass unchanged.

## Tasks / Subtasks

- [x] Task 1: Add `XpResult` dataclass to `server/core/xp.py` (AC: #4)
  - [x] 1.1: Import `dataclass` from `dataclasses`
  - [x] 1.2: Define `XpResult` with fields: `final_xp`, `source`, `detail`, `new_total_xp`, `level_up_available`, `new_level`

- [x] Task 2: Create `apply_xp` function in `server/core/xp.py` (AC: #1, #2)
  - [x] 2.1: Extract lines 47-59 (CHA bonus + stats update + DB persist) from current `grant_xp`
  - [x] 2.2: Extract lines 74-81 (level-up detection logic only — no messaging) from current `grant_xp`
  - [x] 2.3: Return `XpResult` with all computed values
  - [x] 2.4: Signature matches `grant_xp`: `(entity_id, player_entity, amount, source, detail, game, apply_cha_bonus=True, session=None)`
  - [x] 2.5: Use `entity_id` parameter directly for `game.player_manager.get_session(entity_id)` — never reconstruct from `player_db_id`

- [x] Task 3: Create `notify_xp` function in `server/core/xp.py` (AC: #1)
  - [x] 3.1: Extract lines 61-72 (send `xp_gained` WebSocket message) from current `grant_xp`
  - [x] 3.2: Call `send_level_up_available` when `result.level_up_available` is True (lines 80-81 of current code)
  - [x] 3.3: Signature: `(entity_id, result: XpResult, player_entity, game)`

- [x] Task 4: Refactor `grant_xp` to wrapper (AC: #1, #3)
  - [x] 4.1: Replace body with: `result = await apply_xp(...)` then `await notify_xp(...)`
  - [x] 4.2: Return `result.final_xp` (preserves existing `int` return type)
  - [x] 4.3: Keep identical function signature — all 3 call sites unchanged

- [x] Task 5: Add unit tests for `apply_xp` and `notify_xp` (AC: #1, #5)
  - [x] 5.1: Test `apply_xp` performs XP math + DB persist + returns `XpResult` — does NOT send WebSocket messages
  - [x] 5.2: Test `notify_xp` sends `xp_gained` message using `XpResult` fields
  - [x] 5.3: Test `notify_xp` calls `send_level_up_available` when `result.level_up_available` is True
  - [x] 5.4: Test `notify_xp` does NOT call `send_level_up_available` when `result.level_up_available` is False

- [x] Task 6: Verify all existing tests pass (AC: #3, #5)
  - [x] 6.1: Run `make test` — 816 passed (808 original + 8 new), 1 pre-existing flaky failure in test_integration.py

## Dev Notes

### Current `grant_xp` Structure (server/core/xp.py:29-82)

The function mixes three layers:

| Lines | Layer | What it does |
|-------|-------|-------------|
| 47-52 | Business | Apply CHA bonus, calculate `final_xp` (includes else branch) |
| 53 | Business | Update `player_entity.stats["xp"]` in-memory |
| 55-59 | Persistence | Write stats to DB via `player_repo.update_stats()` (inline or with provided session) |
| 61-72 | Messaging | Send `xp_gained` WebSocket message (best-effort, exception swallowed) |
| 74-81 | Messaging | Detect level-up threshold, send `level_up_available` via `send_level_up_available()` |

### Call Sites (all use `grant_xp` — unchanged by this story)

1. `server/net/handlers/combat.py:79` — combat victory XP (`apply_cha_bonus=False, session=session`)
2. `server/net/handlers/movement.py:326` — exploration XP (first room visit)
3. `server/net/handlers/interact.py:112` — interaction XP (first object interaction)

### Test References (all use `grant_xp` — unchanged by this story)

7 test files reference `grant_xp`:
- `tests/test_xp.py` — `TestGrantXp` class (4 test methods that call `grant_xp` directly)
- `tests/test_level_up.py` — `test_grant_xp_triggers_level_up` (calls `grant_xp` directly)
- `tests/test_party_combat.py` — 3 tests patch `server.net.handlers.combat.grant_xp`
- `tests/test_interaction_xp.py` — 4 tests patch `server.net.handlers.interact.grant_xp`
- `tests/test_exploration_xp.py` — 2 tests patch `server.net.handlers.movement.grant_xp`
- `tests/test_room_transition.py` — 2 tests patch `server.net.handlers.movement.grant_xp`
- `tests/test_integration.py` — 1 comment reference only

### Existing Helper Functions (DO NOT MODIFY)

- `calculate_combat_xp(hit_dice, charisma)` at `xp.py:11-26` — standalone XP calc, not involved
- `get_pending_level_ups(stats)` at `xp.py:85-96` — used by `apply_xp` for level-up detection
- `send_level_up_available(entity_id, player_entity, game)` at `xp.py:99-133` — called by `notify_xp`

### Architecture Compliance

- **File**: Only `server/core/xp.py` is modified — no new files needed
- **Pattern**: Follows the business/messaging separation pattern used in other refactors (e.g., Story 14.5)
- **Import**: `from dataclasses import dataclass` — stdlib, no new dependencies
- **Testing**: Use `make test` (never bare `pytest`) — see CLAUDE.md
- **Config**: All XP settings already come from `settings.*` in `server/core/config.py` — no new config needed

### Critical Constraints

- `grant_xp` return type MUST remain `int` (the `final_xp` value) — callers depend on this
- `apply_xp` MUST NOT import or call anything from `server.net` — it's pure business logic
- `notify_xp` WebSocket sends are best-effort (wrap in try/except, swallow exceptions) — matches current behavior
- Level-up detection (`player_info.pending_level_ups` mutation) belongs in `apply_xp` (it's state mutation, not messaging) — `notify_xp` only reads `result.level_up_available` to decide whether to call `send_level_up_available`
- The `old_pending == 0` guard in current code (line 80) controls when to send the level-up notification — this logic must be preserved: `notify_xp` calls `send_level_up_available` only when `result.level_up_available` is True

### Project Structure Notes

- Alignment: Single-file modification in `server/core/xp.py` — matches existing module structure
- No new modules, packages, or directories needed
- `XpResult` dataclass is internal to `xp.py` — no external consumers until Story 16.4

### References

- [Source: _bmad-output/planning-artifacts/epic-16-tech-spec.md#Story-16.4a] — Full implementation spec with code samples
- [Source: _bmad-output/planning-artifacts/epics.md#Story-16.4a] — Acceptance criteria and story definition
- [Source: server/core/xp.py] — Current implementation (134 lines)
- [Source: CLAUDE.md] — Project conventions (make test, centralized config, etc.)

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Completion Notes List

- Split `grant_xp` into `apply_xp` (business + DB) and `notify_xp` (WebSocket messaging)
- Added `XpResult` dataclass with 6 fields for decoupling
- `grant_xp` wrapper preserved — all 3 call sites and 41+ test references unchanged
- Level-up detection stays in `apply_xp` (state mutation); `notify_xp` only reads `level_up_available` flag
- `old_pending == 0` guard preserved via `level_up = old_pending == 0` in `apply_xp`
- 8 new tests: 5 for `apply_xp`, 4 for `notify_xp` (including no-websocket verification)
- 816 tests pass (808 original + 8 new); 1 pre-existing flaky integration test

### File List

- `server/core/xp.py` — Modified: added `XpResult` dataclass, `apply_xp`, `notify_xp`; refactored `grant_xp` to wrapper
- `tests/test_xp.py` — Modified: added `TestApplyXp` (5 tests) and `TestNotifyXp` (4 tests) classes
