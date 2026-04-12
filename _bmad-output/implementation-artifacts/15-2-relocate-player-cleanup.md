# Story 15.2: Relocate Player Cleanup to Game Layer

Status: done

## Story

As a developer,
I want the player cleanup orchestration function to live at the game layer rather than in a handler module,
So that the dependency direction is correct (orchestrator -> handlers, not handlers -> orchestrator).

## Acceptance Criteria

1. **Given** `_cleanup_player` is defined in `server/net/handlers/auth.py` (line 146) with sub-functions `_cleanup_trade` (line 26), `_cleanup_combat` (line 45), `_cleanup_party` (line 86), `_save_player_state` (line 107), `_remove_from_room` (line 134), **When** Story 15.2 is implemented, **Then** the cleanup orchestration is a method on `PlayerManager`: `async def cleanup_session(self, entity_id: str, game: Game) -> None` in `server/player/manager.py`.

2. **Given** `_cleanup_player` is called from `app.py` via deferred imports at lines 114 (in `shutdown()`) and 359 (in `handle_disconnect()`), **When** Story 15.2 is implemented, **Then** both call `self.player_manager.cleanup_session(entity_id, self)` directly with no deferred imports.

3. **Given** `handle_logout` (auth.py:181), `_kick_old_session` (auth.py:245), and `handle_login` (auth.py:287) call `_cleanup_player(entity_id, game)`, **When** Story 15.2 is implemented, **Then** they call `game.player_manager.cleanup_session(entity_id, game)` instead.

4. **Given** `_cleanup_party` (auth.py:102) does a deferred import of `cleanup_pending_invites` from `server.net.handlers.party`, **When** Story 15.2 is implemented, **Then** the deferred import is preserved in `cleanup_session()` (temporary debt cleaned up by Story 15.4 when invite state moves to `PartyManager`).

5. **Given** all existing tests (807+), **When** Story 15.2 is implemented, **Then** all tests pass with no assertion value changes.

## Tasks / Subtasks

### Task 1: Move cleanup functions to PlayerManager (AC: #1)

- [x] 1.1: Add `cleanup_session()` method to `PlayerManager` in `server/player/manager.py`
  - Signature: `async def cleanup_session(self, entity_id: str, game: Game) -> None`
  - Use `TYPE_CHECKING` guard for `Game` import (same pattern as auth.py line 20-21)
  - Move the body of `_cleanup_player` (auth.py lines 146-169) into this method
- [x] 1.2: Move sub-functions as private methods on `PlayerManager`:
  - `async def _cleanup_trade(self, entity_id: str, game: Game) -> None` — from auth.py lines 26-42
  - `async def _cleanup_combat(self, entity_id: str, entity, game: Game) -> None` — from auth.py lines 45-83
  - `async def _cleanup_party(self, entity_id: str, game: Game) -> None` — from auth.py lines 86-104
  - `async def _save_player_state(self, entity_id: str, player_info: PlayerSession, game: Game) -> None` — from auth.py lines 107-131
  - `async def _remove_from_room(self, entity_id: str, room_key: str, game: Game) -> None` — from auth.py lines 134-143
- [x] 1.3: Add required imports to `server/player/manager.py`:
  - `import logging` (for `logger.exception` in `_save_player_state`)
  - `from server.player import repo as player_repo` (for DB persistence in `_save_player_state`)
  - `from server.core.config import settings` (for `DEFAULT_BASE_HP` in `_cleanup_combat`)
  - `from typing import TYPE_CHECKING` and `if TYPE_CHECKING: from server.app import Game`
- [x] 1.4: In sub-methods, replace `game.player_manager.get_session()` / `game.player_manager.remove_session()` with `self.get_session()` / `self.remove_session()` — since cleanup is now on `PlayerManager`, use `self` directly
- [x] 1.5: Delete the 6 functions from `auth.py` (lines 26-169): `_cleanup_trade`, `_cleanup_combat`, `_cleanup_party`, `_save_player_state`, `_remove_from_room`, `_cleanup_player`

### Task 2: Update app.py callers (AC: #2)

- [x] 2.1: In `Game.shutdown()` (line 112-142): Remove `from server.net.handlers.auth import _cleanup_player` (line 114), replace `await _cleanup_player(entity_id, self)` (line 130) with `await self.player_manager.cleanup_session(entity_id, self)`
- [x] 2.2: In `Game.handle_disconnect()` (line 357-365): Remove `from server.net.handlers.auth import _cleanup_player` (line 359), replace `await _cleanup_player(entity_id, self)` (line 365) with `await self.player_manager.cleanup_session(entity_id, self)`

### Task 3: Update auth.py callers (AC: #3)

- [x] 3.1: In `handle_logout` (line 181): Replace `await _cleanup_player(entity_id, game)` with `await game.player_manager.cleanup_session(entity_id, game)`
- [x] 3.2: In `_kick_old_session` (line 245): Replace `await _cleanup_player(entity_id, game)` with `await game.player_manager.cleanup_session(entity_id, game)`
- [x] 3.3: In `handle_login` (line 287): Replace `await _cleanup_player(entity_id, game)` with `await game.player_manager.cleanup_session(entity_id, game)`

### Task 4: Clean up unused imports in auth.py (AC: #1)

- [x] 4.1: After removing the 6 cleanup functions, remove imports that are no longer used by remaining auth.py code:
  - Check if `player_repo` is still used — YES, `handle_login` and `handle_register` use it (lines 207, 272, etc.) — KEEP
  - Check if `settings` is still used — YES, `handle_register` and `handle_login` use it — KEEP
  - Check if `PlayerSession` is still used — YES, `handle_login` constructs PlayerSession (line ~370+) — KEEP
  - Check if `room_repo` is still used — YES, `handle_login` uses it — KEEP
  - **No imports need removal** — all are used by the remaining login/register functions

### Task 5: Update test files that directly import `_cleanup_player` (AC: #5)

5 test files reference `_cleanup_player` and/or patch `server.net.handlers.auth.player_repo` for cleanup:

- [x] 5.1: **`tests/test_party.py`** (lines 387, 409, 429) — 3 tests directly `from server.net.handlers.auth import _cleanup_player` and call it. Replace with `await game.player_manager.cleanup_session(entity_id, game)` — no import needed since `game` is already available. These tests use `MagicMock` for `game.transaction` so `player_repo` calls silently succeed without explicit patching.
- [x] 5.2: **`tests/test_combat_multiplayer.py`** (line 389) — 1 test directly imports `_cleanup_player`. Replace with `await game.player_manager.cleanup_session("player_1", game)`. This test patches `player_repo` via `patch.object(player_repo, ...)` on the module directly (line 440-442) — this approach still works after relocation since both auth.py and manager.py import from `server.player.repo`.
- [x] 5.3: **`tests/test_exploration_xp.py`** (line 130) — 1 test directly imports `_cleanup_player` and calls it (line 157). Replace with `await game.player_manager.cleanup_session(entity.id, game)`. This file also patches `server.net.handlers.auth.player_repo` at line 151 for the cleanup path — must change to `server.player.manager.player_repo`. Note: line 192 patches the same path but for `handle_login` tests, NOT cleanup — that patch stays as-is since `handle_login` still uses `player_repo` from auth.py.
- [x] 5.4: **`tests/test_logout.py`** — Tests patch `server.net.handlers.auth.player_repo` in two categories:
  - **Cleanup-only tests** (lines 82, 122, 155, 197, 232, 383, 412): These test `handle_logout` which calls cleanup. Change patch path from `server.net.handlers.auth.player_repo` to `server.player.manager.player_repo`.
  - **Dual cleanup+login tests** (lines 299, 346): `test_relogin_same_socket_after_logout` calls both `handle_logout` (cleanup) and `handle_login` (auth.py `player_repo`). `test_relogin_same_socket_without_logout` calls `handle_login` which internally triggers `_cleanup_player` for same-socket re-login. These tests need TWO patches: `server.player.manager.player_repo` for the cleanup path AND `server.net.handlers.auth.player_repo` for the login path (which still uses auth.py's `player_repo` for `get_by_username`, `update_stats`, `update_position`).
- [x] 5.5: **`tests/test_game.py`** — 2 tests (`test_game_shutdown_saves_player_state` line 185, `test_handle_disconnect_saves_position` line 274) patch `server.net.handlers.auth.player_repo`. Must change cleanup-related patches to `server.player.manager.player_repo`.
- [x] 5.6: Run `make test` and fix any failing tests

### Task 6: Verify and finalize (AC: #5)

- [x] 6.1: Run `make test` — all 807+ tests must pass
- [x] 6.2: Verify no remaining references to `_cleanup_player` in codebase: `grep -r "_cleanup_player" server/ tests/` should return zero hits
- [x] 6.3: Verify no deferred `_cleanup_player` imports in app.py

## Dev Notes

### Architecture & Patterns

- **Pure refactor** — zero gameplay behavior changes
- **ADR-15-2:** `cleanup_session(entity_id, game)` takes the full `Game` object because cleanup touches trade, combat, party, room, and DB managers. This is the same "pass the orchestrator" pattern used by handlers — acceptable since the alternative (injecting 5 managers individually) adds complexity without reducing coupling
- The sub-cleanup functions become private methods on `PlayerManager` — they are implementation details of session cleanup
- `Game` type uses `TYPE_CHECKING` guard to avoid circular import (same pattern as auth.py)

### Critical Implementation Details

- **Deferred import of `cleanup_pending_invites`**: `_cleanup_party` does `from server.net.handlers.party import cleanup_pending_invites` (auth.py line 102). This deferred import MUST be preserved in the moved method. Story 15.4 will eliminate it by moving invite state to `PartyManager`.
- **`self` vs `game.player_manager`**: Inside `cleanup_session()` and its sub-methods, use `self.get_session()` and `self.remove_session()` instead of `game.player_manager.get_session()` — the method is now on `PlayerManager` itself.
- **Import chain**: `server/player/manager.py` will gain imports for `player_repo`, `settings`, and `logging`. The `Game` import uses `TYPE_CHECKING` guard. No circular import risk.
- **Test patching**: The `player_repo` used in `_save_player_state` will now be imported in `server.player.manager`. Tests that mock DB calls during cleanup must patch `server.player.manager.player_repo` instead of (or in addition to) `server.net.handlers.auth.player_repo`.

### Cleanup Function Signature Reference

Current code in auth.py that will move to PlayerManager:

```python
# Becomes self._cleanup_trade(entity_id, game)
async def _cleanup_trade(entity_id: str, game: Game) -> None:
    # Cancels active trade, notifies other party

# Becomes self._cleanup_combat(entity_id, entity, game)
async def _cleanup_combat(entity_id: str, entity, game: Game) -> None:
    # Syncs combat stats, removes participant, notifies remaining

# Becomes self._cleanup_party(entity_id, game)
async def _cleanup_party(entity_id: str, game: Game) -> None:
    # Handles party disconnect, cleans pending invites (deferred import)

# Becomes self._save_player_state(entity_id, player_info, game)
async def _save_player_state(entity_id: str, player_info: PlayerSession, game: Game) -> None:
    # Persists position, stats, inventory, visited rooms

# Becomes self._remove_from_room(entity_id, room_key, game)
async def _remove_from_room(entity_id: str, room_key: str, game: Game) -> None:
    # Removes entity from room, broadcasts departure
```

### Files to Modify

| File | Changes |
|------|---------|
| `server/player/manager.py` | Add `cleanup_session()` + 5 private sub-methods, add imports for `player_repo`, `settings`, `logging`, `TYPE_CHECKING` guard for `Game` |
| `server/app.py` | Remove 2 deferred `_cleanup_player` imports (lines 114, 359), call `self.player_manager.cleanup_session()` instead |
| `server/net/handlers/auth.py` | Delete 6 functions (lines 26-169), update 3 call sites in `handle_logout`, `_kick_old_session`, `handle_login` |
| `tests/test_party.py` | Replace 3 direct `_cleanup_player` imports (lines 387, 409, 429) with `game.player_manager.cleanup_session()` |
| `tests/test_combat_multiplayer.py` | Replace 1 direct `_cleanup_player` import (line 389) with `game.player_manager.cleanup_session()` |
| `tests/test_exploration_xp.py` | Replace 1 direct `_cleanup_player` import (line 130) with `game.player_manager.cleanup_session()`, update `player_repo` patch path at line 151 to `server.player.manager.player_repo` |
| `tests/test_logout.py` | Add `server.player.manager.player_repo` patches for cleanup-path mocking |
| `tests/test_game.py` | Change cleanup-path `player_repo` patches to `server.player.manager.player_repo` |

### Anti-Patterns to Avoid

- Do NOT create a separate `cleanup.py` module — the cleanup logic belongs on `PlayerManager` per ADR-15-2
- Do NOT inject individual managers (trade, combat, party, room) into `PlayerManager.__init__()` — the `game` parameter at call time is the established pattern
- Do NOT remove the deferred import of `cleanup_pending_invites` — that's Story 15.4's scope
- Do NOT change assertion values in any test — pure refactor
- Do NOT change gameplay behavior — this is purely structural

### Previous Story Intelligence

From Story 15.1:
- `PlayerManager` in `server/player/manager.py` is a plain class with 7 methods, owns `_sessions: dict[str, PlayerSession]`
- Pattern: `from __future__ import annotations` as first import
- Test files heavily patch `server.net.handlers.auth.player_repo` — critical to verify mock paths after relocation
- All 807 tests pass with 0 failures, 0 warnings

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Story 15.2 (lines 3652-3689)]
- [Source: server/net/handlers/auth.py — _cleanup_player and sub-functions (lines 26-169)]
- [Source: server/player/manager.py — PlayerManager class (lines 1-42)]
- [Source: server/app.py — shutdown() deferred import (line 114), handle_disconnect() deferred import (line 359)]
- [Source: _bmad-output/planning-artifacts/epics.md — ADR-15-2 (line 3914)]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- All 807 tests pass (0 failures, 0 warnings, ~3.9s)
- `grep -r "_cleanup_player" server/ tests/ --include="*.py"` returns zero hits

### Completion Notes List

- Moved `_cleanup_player` and 5 sub-functions from `server/net/handlers/auth.py` to `PlayerManager.cleanup_session()` in `server/player/manager.py`
- Removed 2 deferred `_cleanup_player` imports from `server/app.py` (shutdown + handle_disconnect)
- Updated 3 call sites in auth.py (handle_logout, _kick_old_session, handle_login)
- Updated 5 test files: test_party.py (3 imports), test_combat_multiplayer.py (1 import), test_exploration_xp.py (1 import + patch path), test_logout.py (9 patch paths including 2 dual-patch), test_game.py (2 patch paths)
- Updated comments/docstrings referencing `_cleanup_player` in party.py and test files
- Preserved deferred import of `cleanup_pending_invites` from party.py (Story 15.4 will clean up)
- Pure refactor — zero gameplay behavior changes

### File List

**Modified:**
- `server/player/manager.py` — added `cleanup_session()` + 5 private sub-methods, new imports for `player_repo`, `settings`, `logging`, `TYPE_CHECKING`
- `server/app.py` — removed 2 deferred `_cleanup_player` imports, calls `self.player_manager.cleanup_session()` instead
- `server/net/handlers/auth.py` — deleted 6 cleanup functions (lines 26-169), updated 3 call sites
- `server/net/handlers/party.py` — updated docstring reference
- `tests/test_party.py` — replaced 3 `_cleanup_player` imports with `game.player_manager.cleanup_session()`
- `tests/test_combat_multiplayer.py` — replaced 1 `_cleanup_player` import with `game.player_manager.cleanup_session()`
- `tests/test_exploration_xp.py` — replaced 1 `_cleanup_player` import, changed `player_repo` patch path
- `tests/test_logout.py` — changed 9 `player_repo` patch paths from `server.net.handlers.auth.player_repo` to `server.player.manager.player_repo`, added dual patches for 2 relogin tests
- `tests/test_game.py` — changed 2 `player_repo` patch paths
