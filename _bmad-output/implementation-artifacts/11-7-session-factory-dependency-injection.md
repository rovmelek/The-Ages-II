# Story 11.7: Session Factory Dependency Injection

Status: done

## Story

As a developer,
I want the database session factory to be owned by the Game orchestrator and injected into all consumers,
so that tests cannot accidentally connect to the production database and future database migration (e.g., PostgreSQL) requires changing only one line.

## Acceptance Criteria

1. **Game owns session_factory**: `Game.__init__()` sets `self.session_factory = async_session` (imported from `server.core.database`). All 11 consumer modules stop importing `async_session` directly and instead use the `game` reference they already receive.

2. **All 26 usage sites migrated**: Every `async with async_session() as session:` becomes `async with game.session_factory() as session:` (or `self.session_factory()` for Game methods, `self._game.session_factory()` for Scheduler).

3. **Integration test simplified**: `tests/test_integration.py` fixture replaces 6 per-module `async_session` patches with `game.session_factory = test_session_factory` — one assignment. `player_repo` patches remain as-is.

4. **All test files updated**: 67 `async_session` patches across 14 test files are replaced with `game.session_factory` assignment or mock attribute. Tests using `MagicMock()` for game work automatically since `game.session_factory` is just a mock attribute.

5. **No test touches real DB**: After the refactor, no test can accidentally write to `data/game.db`. The `game.session_factory` attribute controls all DB access, and tests set it to in-memory or mock session factories.

6. **Dead code cleanup**: Remove unused `get_session()` generator from `server/core/database.py` (lines 26-29) — never imported or called anywhere.

7. **All existing tests pass**: `pytest tests/` passes (excluding known hanging tests `test_disconnect_notifies_others`, `test_register_returns_player_id`). No regressions.

## Tasks / Subtasks

- [x] Task 1: Add `session_factory` attribute to `Game.__init__()` (AC: #1)
  - [x] In `server/app.py`, add `self.session_factory = async_session` to `Game.__init__()` (after line 40)
  - [x] Keep the `from server.core.database import async_session, init_db` import — `async_session` is still used to set the default, and `init_db` is used in `startup()`

- [x] Task 2: Migrate `server/app.py` usage sites to `self.session_factory` (AC: #2)
  - [x] Line 54: `async with async_session()` → `async with self.session_factory()` (room loading in startup)
  - [x] Line 65: same (card loading in startup)
  - [x] Line 74: same (item loading in startup)
  - [x] Line 257: same (respawn_player stats persistence)

- [x] Task 3: Migrate handler modules to `game.session_factory()` (AC: #1, #2)
  - [x] `server/net/handlers/auth.py` (line 9 import, lines 78, 146, 208): Remove `async_session` import. Use `game.session_factory()` at all 3 sites. `game` is available as `game: Game` parameter in `_cleanup_player`, `handle_register`, `handle_login`.
  - [x] `server/net/handlers/movement.py` (line 10 import, lines 139, 195, 239, 256): Remove `async_session` import. Use `game.session_factory()` at all 4 sites. `game` available via handler params and helper function params.
  - [x] `server/net/handlers/combat.py` (line 8 import, lines 34, 71, 81, 123, 299): Remove `async_session` import. Use `game.session_factory()` at all 5 sites. `game` available via function params.
  - [x] `server/net/handlers/inventory.py` (line 8 import, line 95): Remove `async_session` import. Use `game.session_factory()`. `game` available via handler param.
  - [x] `server/net/handlers/interact.py` (line 9 import, lines 107, 125): Remove `async_session` import. Use `game.session_factory()` at both sites. `game` available via handler param.
  - [x] `server/net/handlers/levelup.py` (line 9 import, line 92): Remove `async_session` import. Use `game.session_factory()`. `game` available via handler param.

- [x] Task 4: Migrate non-handler modules to `game.session_factory()` (AC: #1, #2)
  - [x] `server/core/xp.py` (line 8 import, line 51): Remove `async_session` import. Use `game.session_factory()`. `game` available as parameter (type `Any`).
  - [x] `server/core/scheduler.py` (line 12 import, lines 128, 206): Remove `async_session` import. Use `self._game.session_factory()`. `self._game` is set via `start(game)`.
  - [x] `server/room/objects/chest.py` (line 6 import, line 28): Remove `async_session` import. Use `game.session_factory()`. `game` available as `interact()` parameter.
  - [x] `server/room/objects/lever.py` (line 6 import, line 30): Remove `async_session` import. Use `game.session_factory()`. `game` available as `interact()` parameter.

- [x] Task 5: Remove dead `get_session()` from `server/core/database.py` (AC: #6)
  - [x] Remove lines 26-29 (`async def get_session()` and its body) — never imported or called anywhere in the codebase. Originally intended for FastAPI `Depends()` injection but never adopted.

- [x] Task 6: Update `tests/test_integration.py` fixture (AC: #3, #5)
  - [x] In the `client` fixture (lines 94-127), replace 6 `async_session` patches (lines 101-109):
    ```python
    # REMOVE these 6 patches:
    patch("server.net.handlers.auth.async_session", test_session_factory)
    patch("server.net.handlers.movement.async_session", test_session_factory)
    patch("server.net.handlers.combat.async_session", test_session_factory)
    patch("server.net.handlers.inventory.async_session", test_session_factory)
    patch("server.room.objects.chest.async_session", test_session_factory)
    patch("server.app.async_session", test_session_factory)
    
    # REPLACE with (after game manager swap):
    game.session_factory = test_session_factory
    ```
  - [x] Keep `player_repo` patches — those mock specific repo methods and are a separate concern
  - [x] Add teardown: restore `game.session_factory` to original after test (same pattern as `game.room_manager` restore)

- [x] Task 7: Update remaining test files (AC: #4, #5)
  - [x] `tests/test_login.py`: Replace `patch("server.net.handlers.auth.async_session", test_session_factory)` with `game.session_factory = test_session_factory` (line 67). Already imports `game`.
  - [x] `tests/test_auth.py`: Replace `patch("server.net.handlers.auth.async_session", test_session_factory)` with `game.session_factory = test_session_factory` (line 48-50). Need to add `game` import.
  - [x] `tests/test_stats_persistence.py`: Replace `patch("server.net.handlers.auth.async_session", test_session_factory)` with `game.session_factory = test_session_factory` (line 69). For combat mock at line 278, change to `game.session_factory = mock_session_factory`.
  - [x] `tests/test_game.py`: Replace 8 `async_session` patches (lines 62, 85, 118, 124, 163, 215, 250, 285) with `game.session_factory = ...` on each created `Game()` instance.
  - [x] `tests/test_startup_wiring.py`: Replace 3 `async_session` patches (lines 50, 105, 124) with `game.session_factory = test_session_factory` on each `Game()` instance.
  - [x] `tests/test_room_transition.py`: Replace 10 `async_session` patches with `game.session_factory = AsyncMock()` on `_make_game()` result.
  - [x] `tests/test_logout.py`: Replace 8 `async_session` patches with `game.session_factory = mock_factory` on `_make_game()` result.
  - [x] `tests/test_chest.py`: Replace 4 `async_session` patches with `game.session_factory = mock_factory` on `_make_game()` result.
  - [x] `tests/test_loot.py`: Replace 6 `async_session` patches with `game.session_factory = mock_factory` on `_make_game()` result.
  - [x] `tests/test_exploration_xp.py`: Replace 4 `async_session` patches. `game` is `MagicMock()` — set `game.session_factory = mock_factory` attribute.
  - [x] `tests/test_interaction_xp.py`: Replace 4 `async_session` patches. `game` is `MagicMock()` — set `game.session_factory = mock_factory` attribute.
  - [x] `tests/test_level_up.py`: Replace 6 `async_session` patches. `game` is `MagicMock()` — set `game.session_factory = mock_factory` attribute.
  - [x] `tests/test_xp.py`: Replace 4 `async_session` patches. `game` is `MagicMock()` — set `game.session_factory = mock_factory` attribute.
  - [x] Note: `tests/test_interact.py` uses `from server.core.database import async_session` for direct DB setup in test helpers — NOT for patching handlers. These are unaffected. Leave them as-is.

- [x] Task 8: Run full test suite and verify no test touches real DB (AC: #7, #5)
  - [x] Run `.venv/bin/python -m pytest tests/ -x -q --tb=short -k "not test_disconnect_notifies_others and not test_register_returns_player_id"`
  - [x] Verify `data/game.db` mtime is unchanged after test run

## Dev Notes

### Key Architecture Pattern

The refactor makes `Game` the single owner of the database session factory, consistent with how it already owns `RoomManager`, `CombatManager`, `ConnectionManager`, etc. The pattern:

```python
# Game.__init__():
self.session_factory = async_session  # default from server.core.database

# In handlers (already receive game):
async with game.session_factory() as session:
    await player_repo.update_stats(session, db_id, stats)

# In tests:
game.session_factory = test_session_factory  # one line, done
```

### Why This Fix is Correct

The root cause: `server/core/xp.py`, `server/net/handlers/interact.py`, and `server/net/handlers/levelup.py` imported `async_session` directly but were NOT patched in the integration test fixture. This caused `grant_xp()` to write to the real `data/game.db` during tests. With SQLite's single-writer constraint, zombie test processes holding DB locks caused subsequent test runs to hang indefinitely.

By routing all DB access through `game.session_factory`, a single attribute assignment controls all consumers. It's structurally impossible to miss a module.

### How `game` is Already Available Everywhere

| Consumer | `game` reference |
|----------|-----------------|
| `Game` methods (startup, respawn) | `self` |
| Handler functions (auth, movement, etc.) | `game: Game` keyword param via lambda closures |
| `grant_xp()` | `game: Any` positional param |
| `Scheduler` | `self._game` (set in `start()`) |
| `ChestObject.interact()` / `LeverObject.interact()` | `game: Game` parameter |

No signatures need to change. Every call site already has access.

### Test Migration Patterns

**Pattern A: WebSocket integration tests** (test_integration, test_login, test_auth, test_stats_persistence)
- These create `TestClient(app)` and access the module-level `game` singleton
- Replace per-module `async_session` patches with `game.session_factory = test_session_factory`
- Add teardown to restore original `game.session_factory`

**Pattern B: Unit tests creating Game()** (test_game, test_startup_wiring, test_room_transition, test_logout, test_chest, test_loot)
- These create fresh `Game()` instances
- Set `game.session_factory` to mock/test factory before calling methods
- No teardown needed — game instance is discarded

**Pattern C: Unit tests with MagicMock game** (test_exploration_xp, test_interaction_xp, test_level_up, test_xp)
- `game = MagicMock()` — setting `game.session_factory` is trivial (just a mock attribute)
- The `session_factory()` call returns a mock context manager automatically

### Mock Session Factory for Unit Tests

Tests that currently use `patch("module.async_session")` as a pure mock (not providing real test DB) need a mock session factory that works as a context manager:

```python
mock_session = AsyncMock()
mock_factory = AsyncMock()
mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
game.session_factory = mock_factory
```

However, most of these tests already build this pattern via `patch()`. The key change is assigning to `game.session_factory` instead of patching the module attribute.

### What NOT to Change

- Do NOT change `player_repo` patches — repos accept `AsyncSession` as a parameter, they don't import `async_session`. The repo mocking is a separate concern.
- Do NOT change `tests/test_interact.py` — it uses `async_session` directly for test DB setup, not for handler patching.
- Do NOT change `server/core/database.py` beyond removing dead `get_session()` — the module-level `async_session` factory is still created there and used as the default in `Game.__init__()`.
- Do NOT change handler function signatures — `game` is already available everywhere.

### Previous Story Intelligence

From Story 11.6 code review:
- Root cause analysis confirmed `server.core.xp.async_session` was unpatched in integration tests
- 5 zombie Python processes held `data/game.db` locks, causing `grant_xp()` to block indefinitely
- The problem was deterministic once zombie processes existed, but appeared "intermittent" because the first test run (no zombies) always succeeded
- 599 tests passed on clean first run, confirming no actual test logic issues

### Project Structure Notes

- Modified production files (11): `server/app.py`, `server/core/xp.py`, `server/core/scheduler.py`, `server/core/database.py`, `server/net/handlers/auth.py`, `server/net/handlers/movement.py`, `server/net/handlers/combat.py`, `server/net/handlers/inventory.py`, `server/net/handlers/interact.py`, `server/net/handlers/levelup.py`, `server/room/objects/chest.py`, `server/room/objects/lever.py`
- Modified test files (14): `test_integration.py`, `test_login.py`, `test_auth.py`, `test_stats_persistence.py`, `test_game.py`, `test_startup_wiring.py`, `test_room_transition.py`, `test_logout.py`, `test_chest.py`, `test_loot.py`, `test_exploration_xp.py`, `test_interaction_xp.py`, `test_level_up.py`, `test_xp.py`
- No new files created

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Epic 11, Story 11.7]
- [Source: server/core/database.py:1-29 — async_session definition and dead get_session()]
- [Source: server/app.py:31-41 — Game.__init__()]
- [Source: server/app.py:54,65,74,257 — async_session usage sites in Game]
- [Source: server/core/xp.py:8,51 — unpatched async_session import and usage]
- [Source: server/core/scheduler.py:12,128,206 — async_session import and usage]
- [Source: tests/test_integration.py:94-127 — client fixture with 6 async_session patches at lines 101-109]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Added `self.session_factory = async_session` to `Game.__init__()` — single point of DB session factory ownership
- Migrated all 11 production modules (26 usage sites) from `async_session` import to `game.session_factory()` / `self.session_factory()` / `self._game.session_factory()`
- Removed dead `get_session()` from `server/core/database.py`
- Updated 16 test files to replace 67+ `patch("*.async_session")` calls with `game.session_factory = ...` assignments
- Key fix: mock session factory must use `MagicMock(return_value=mock_ctx)` (sync callable), NOT `AsyncMock()` (which returns a coroutine instead of a context manager)
- Also fixed `test_blocking_objects.py`, `test_lever.py`, `test_events.py`, `test_spawn.py` — additional test files that patched the now-removed `async_session` module attributes
- 599 tests pass, 0 failures, 2 deselected (known hanging tests)

### File List

- server/app.py (modified — added `self.session_factory`, migrated 4 usage sites to `self.session_factory()`)
- server/core/database.py (modified — removed dead `get_session()`)
- server/core/xp.py (modified — removed `async_session` import, uses `game.session_factory()`)
- server/core/scheduler.py (modified — removed `async_session` import, uses `self._game.session_factory()`)
- server/net/handlers/auth.py (modified — removed `async_session` import, uses `game.session_factory()`)
- server/net/handlers/movement.py (modified — removed `async_session` import, uses `game.session_factory()`)
- server/net/handlers/combat.py (modified — removed `async_session` import, uses `game.session_factory()`)
- server/net/handlers/inventory.py (modified — removed `async_session` import, uses `game.session_factory()`)
- server/net/handlers/interact.py (modified — removed `async_session` import, uses `game.session_factory()`)
- server/net/handlers/levelup.py (modified — removed `async_session` import, uses `game.session_factory()`)
- server/room/objects/chest.py (modified — removed `async_session` import, uses `game.session_factory()`)
- server/room/objects/lever.py (modified — removed `async_session` import, uses `game.session_factory()`)
- tests/test_integration.py (modified — replaced 6 async_session patches with `game.session_factory = test_session_factory`)
- tests/test_login.py (modified — replaced patch with `game.session_factory` assignment)
- tests/test_auth.py (modified — replaced patch with `game.session_factory` assignment)
- tests/test_stats_persistence.py (modified — replaced patches with `game.session_factory` assignments)
- tests/test_game.py (modified — replaced 8 patches with `game.session_factory` assignments)
- tests/test_startup_wiring.py (modified — replaced 3 patches with `game.session_factory` assignments)
- tests/test_room_transition.py (modified — replaced 10 patches with `game.session_factory` in `_make_game()`)
- tests/test_logout.py (modified — replaced 8 patches with `game.session_factory` in `_make_game()`)
- tests/test_chest.py (modified — replaced 4 patches with `game.session_factory` in `_make_game()`)
- tests/test_loot.py (modified — replaced 6 patches with `game.session_factory` in `_make_game()`)
- tests/test_exploration_xp.py (modified — replaced 4 patches with `game.session_factory` setup)
- tests/test_interaction_xp.py (modified — replaced 4 patches with `game.session_factory` setup)
- tests/test_level_up.py (modified — replaced 6 patches with `game.session_factory` setup)
- tests/test_xp.py (modified — replaced 4 patches with `game.session_factory` setup)
- tests/test_blocking_objects.py (modified — removed chest async_session patch, added `game.session_factory` in `_make_game()`)
- tests/test_lever.py (modified — removed lever async_session patches, added `game.session_factory` in `_make_game()`)
- tests/test_events.py (modified — replaced scheduler async_session patch with `game.session_factory` setup)
- tests/test_spawn.py (modified — replaced 5 scheduler async_session patches with `game.session_factory` setup)
