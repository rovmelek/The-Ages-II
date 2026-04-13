# Story 17.6: Move XP Notifications to Net Layer

Status: done

## Story

As a developer,
I want XP notification functions out of `core/xp.py` so that core has zero network imports,
So that the core package is pure business logic — testable without WebSocket mocking.

## Acceptance Criteria

1. **AC1 — Functions moved:**
   - Given: `notify_xp()`, `send_level_up_available()`, and `grant_xp()` in `core/xp.py` call `game.connection_manager.send_to_player_seq()`
   - Then: All three functions moved to `server/net/xp_notifications.py` (new file)
   - And: `core/xp.py` retains only: `XpResult` dataclass, `calculate_combat_xp()`, `apply_xp()`, `get_pending_level_ups()`
   - And: `core/xp.py` has zero imports from `server/net/`

2. **AC2 — Production call sites updated:**
   - Given: 3 production files import `grant_xp` from `server.core.xp`: `combat/service.py`, `net/handlers/movement.py`, `net/handlers/interact.py`
   - Then: All 3 import from `server.net.xp_notifications` instead
   - And: 3 additional files import `send_level_up_available` from `server.core.xp`: `net/handlers/auth.py`, `player/service.py`, `net/handlers/levelup.py`
   - Then: All 3 import `send_level_up_available` from `server.net.xp_notifications` instead; `get_pending_level_ups` import stays from `server.core.xp`

3. **AC3 — Test imports/patches updated:**
   - Given: Test files reference `grant_xp`, `notify_xp`, `send_level_up_available` from `server.core.xp`
   - Then: Test imports/patches updated to `server.net.xp_notifications` for moved functions
   - And: Tests patching `server.core.xp.player_repo` (used by `apply_xp` which stays) remain unchanged
   - And: Tests patching handler-level `grant_xp` (e.g., `server.net.handlers.interact.grant_xp`) remain valid — handler import changes transparently

4. **AC4 — Tests pass:**
   - All 1066+ tests pass

## Tasks / Subtasks

- [x] Task 1: Create `server/net/xp_notifications.py` (AC: #1)
  - [x] 1.1 Create new file with `from __future__ import annotations` and TYPE_CHECKING guard for `Game`
  - [x] 1.2 Move `send_level_up_available()` from `core/xp.py`
  - [x] 1.3 Move `notify_xp()` from `core/xp.py`
  - [x] 1.4 Move `grant_xp()` wrapper from `core/xp.py` — imports `apply_xp` from `server.core.xp`
  - [x] 1.5 Verify `core/xp.py` retains only `XpResult`, `calculate_combat_xp`, `apply_xp`, `get_pending_level_ups` and has zero `server.net` imports

- [x] Task 2: Update production call sites (AC: #2)
  - [x] 2.1 `server/combat/service.py`: changed import
  - [x] 2.2 `server/net/handlers/movement.py`: changed import
  - [x] 2.3 `server/net/handlers/interact.py`: changed import
  - [x] 2.4 `server/net/handlers/auth.py`: split import
  - [x] 2.5 `server/player/service.py`: split import
  - [x] 2.6 `server/net/handlers/levelup.py`: split import

- [x] Task 3: Update test imports/patches (AC: #3)
  - [x] 3.1 `tests/test_xp.py`: updated imports and 2 patch targets for `send_level_up_available`
  - [x] 3.2 `tests/test_level_up.py`: updated imports
  - [x] 3.3 Verified `test_interaction_xp.py` and `test_exploration_xp.py` patches work (handler-level names)
  - [x] 3.4 Grepped — `test_party_combat.py` imports `calculate_combat_xp` which stays in `core.xp` — no change needed

- [x] Task 4: Run `make test` — all 1066 tests pass (AC: #4)

## Dev Notes

### Architecture Constraints

- `from __future__ import annotations` must be first import in every new module
- Never import `Game` at module level — use `if TYPE_CHECKING: from server.app import Game`
- `core/xp.py` must have ZERO imports from `server/net/` after this story
- `net/xp_notifications.py` imports `apply_xp` from `server.core.xp` — this is the correct dependency direction (net → core)
- Per ADR-17-4: `grant_xp` wrapper is preserved (not deleted) because of 38 test references

### Functions That Move

| Function | Current location | Lines | Moves to |
|----------|-----------------|-------|----------|
| `send_level_up_available(entity_id, player_entity, game)` | `core/xp.py` ~lines 147-171 | ~25 lines | `net/xp_notifications.py` |
| `notify_xp(entity_id, result, player_entity, game)` | `core/xp.py` ~lines 93-108 | ~16 lines | `net/xp_notifications.py` |
| `grant_xp(entity_id, player_entity, amount, source, detail, game, ...)` | `core/xp.py` ~lines 111-130 | ~20 lines | `net/xp_notifications.py` |

### Functions That Stay in `core/xp.py`

| Function | Lines | Notes |
|----------|-------|-------|
| `XpResult` dataclass | ~lines 13-20 | Pure data |
| `calculate_combat_xp(hit_dice, charisma)` | ~lines 25-40 | Pure calculation |
| `apply_xp(...)` | ~lines 43-90 | DB persistence only, no WebSocket |
| `get_pending_level_ups(stats)` | ~lines 133-144 | Pure calculation |

### Test Patch Analysis

Tests that patch `server.core.xp.player_repo` are testing `apply_xp()` which stays in `core/xp.py` — these patches remain valid.

Tests that patch handler-level `grant_xp` (e.g., `server.net.handlers.interact.grant_xp`) remain valid because the handlers still import `grant_xp` by name — the source module changes but the handler's local name doesn't.

Tests in `test_xp.py` that import `grant_xp`/`notify_xp` directly and patch `server.core.xp.send_level_up_available` need their imports and patches updated to the new module path.

### `net/xp_notifications.py` Imports

```python
from server.core.config import settings
from server.core.constants import STAT_NAMES
from server.core.xp import apply_xp, get_pending_level_ups
```
Note: `player_repo` is NOT needed — `grant_xp` only calls `apply_xp` (which imports `player_repo` itself in `core/xp.py`) and `notify_xp`.

### Project Structure Notes

- New file: `server/net/xp_notifications.py` — sits alongside `connection_manager.py`, `message_router.py`, `auth_middleware.py` in the net package
- No new test file needed — existing tests cover all paths

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Story 17.6]
- [Source: server/core/xp.py — current XP module with mixed business logic and notifications]
- [Source: ADR-17-4 — grant_xp wrapper preserved, not deleted]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Completion Notes List
- Created `server/net/xp_notifications.py` (78 lines) with `send_level_up_available`, `notify_xp`, `grant_xp`
- `core/xp.py` shrunk from 172 to 99 lines — retains only pure business logic
- `core/xp.py` has zero `server.net` imports (verified by grep)
- Updated 6 production files and 2 test files
- All 1066 tests pass

### File List
- `server/net/xp_notifications.py` (created)
- `server/core/xp.py` (modified — removed 3 functions)
- `server/combat/service.py` (modified — import change)
- `server/net/handlers/movement.py` (modified — import change)
- `server/net/handlers/interact.py` (modified — import change)
- `server/net/handlers/auth.py` (modified — split import)
- `server/player/service.py` (modified — split import)
- `server/net/handlers/levelup.py` (modified — split import)
- `tests/test_xp.py` (modified — imports and patch targets)
- `tests/test_level_up.py` (modified — imports)
