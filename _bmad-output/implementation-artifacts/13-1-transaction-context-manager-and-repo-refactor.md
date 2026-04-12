# Story 13.1: Transaction Context Manager and Repo Refactor

Status: done

## Story

As a developer,
I want all database writes within a single logical operation to be atomic (all-or-nothing),
so that the server never persists partial state on crash or concurrent access, and the codebase is ready for PostgreSQL.

## Acceptance Criteria

1. **Given** the `Game` class owns the session factory, **When** Story 13.1 is implemented, **Then** `Game` gains a `transaction()` async context manager method that yields an `AsyncSession`, auto-commits on clean exit, and auto-rolls back on exception.

2. **Given** any repo write function (`create`, `save`, `update_position`, `update_stats`, `update_inventory`, `update_visited_rooms`, `upsert_room`, `save_state`, `load_cards_from_json`, `load_items_from_json`, `set_player_object_state`, `set_room_object_state`), **When** called inside a `transaction()` block, **Then** the repo function executes the query but does NOT call `session.commit()` — the transaction context manager commits at block exit.

3. **Given** a handler that performs multiple DB writes in one logical operation (e.g., `_save_player_state` with position + stats + inventory + visited_rooms), **When** all writes are inside one `async with game.transaction() as session:` block, **Then** all writes commit atomically.

4. **Given** the trade swap in `_execute_trade` (`server/net/handlers/trade.py:447`) currently bypasses repos with raw `session.execute(sa_update(Player))` + direct `session.commit()`, **When** Story 13.1 is implemented, **Then** the trade swap uses `player_repo.update_inventory()` for both players inside one `transaction()` block.

5. **Given** the loot distribution in `_check_combat_end` (`server/net/handlers/combat.py:121-129`) currently bypasses repos with direct `player.inventory` mutation + `session.commit()`, **When** Story 13.1 is implemented, **Then** loot distribution uses `player_repo.update_inventory()` inside a `transaction()` block.

6. **Given** the chest interaction in `ChestObject.interact()` (`server/room/objects/chest.py:38-45`) currently uses direct `player.inventory` mutation + `session.commit()`, **When** Story 13.1 is implemented, **Then** chest interaction uses `player_repo.update_inventory()` inside a `transaction()` block.

7. **Given** the scheduler spawn checkpoint code in `_run_rare_spawn_checks` (`server/core/scheduler.py:127-196`) currently uses direct `session.execute()`, `session.add()`, `session.flush()`, `session.commit()`, **When** Story 13.1 is implemented, **Then** scheduler uses a `transaction()` block (inline SpawnCheckpoint operations are acceptable since no repo exists for this model).

8. **Given** all 26 `session_factory()` call sites in server code, **When** Story 13.1 is implemented, **Then** all are replaced with `game.transaction()` (or `self.transaction()` in `Game` methods).

9. **Given** all existing tests (804 tests), **When** Story 13.1 is implemented, **Then** all tests pass with updated mock patterns — mock `transaction()` replaces mock `session_factory()`.

10. **Given** a solo player triggers combat (not in a party), **When** combat runs through to victory with loot and XP, **Then** behavior is identical to pre-13.1 — no gameplay changes. This is a pure refactor.

## Tasks / Subtasks

- [x] Task 1: Add `Game.transaction()` context manager (AC: #1)
  - [x] 1.1: In `server/app.py`, add method to `Game` class:
    ```python
    @asynccontextmanager
    async def transaction(self):
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    ```
  - [x] 1.2: `asynccontextmanager` is already imported in `server/app.py` (line 6). No new imports needed.
  - [x] 1.3: Keep `self.session_factory` attribute on `Game.__init__` (line 46) — `transaction()` wraps it, does not replace the attribute.

- [x] Task 2: Remove `session.commit()` from all repo/state files (AC: #2)
  - [x] 2.1: `server/player/repo.py` — Remove `await session.commit()` from 5 functions:
    - `save()` (line 43): Remove `await session.commit()`
    - `update_position()` (line 60): Remove `await session.commit()`
    - `update_inventory()` (line 74): Remove `await session.commit()`
    - `update_visited_rooms()` (line 85): Remove `await session.commit()`
    - `update_stats()` (line 107): Remove `await session.commit()`
  - [x] 2.2: `server/player/repo.py` `create()` (line 35): Replace `await session.commit()` with `await session.flush()`. Flush sends the INSERT to the DB generating the auto-increment `player.id` without ending the transaction. The `session.refresh(player)` on line 36 needs this ID.
  - [x] 2.3: `server/room/repo.py` — 3 locations:
    - `save_state()` (line 23): Remove `await session.commit()`
    - `upsert_room()` update branch (line 39): Remove `await session.commit()`
    - `upsert_room()` insert branch (line 42): Replace `await session.commit()` with `await session.flush()`. Same reason as `player_repo.create()` — `session.refresh(room)` on line 43 needs the auto-increment ID.
  - [x] 2.4: `server/items/item_repo.py` `load_items_from_json()` (line 58): Remove `await session.commit()`
  - [x] 2.5: `server/combat/cards/card_repo.py` `load_cards_from_json()` (line 48): Remove `await session.commit()`
  - [x] 2.6: `server/room/objects/state.py` — 2 functions:
    - `set_player_object_state()` (line 54): Remove `await session.commit()`
    - `set_room_object_state()` (line 90): Remove `await session.commit()`

- [x] Task 3: Replace all 26 `session_factory()` call sites with `transaction()` (AC: #8)
  - [x] 3.1: `server/app.py` — 4 sites:
    - `startup()` line 61: `self.session_factory()` → `self.transaction()`
    - `startup()` line 72: `self.session_factory()` → `self.transaction()`
    - `startup()` line 81: `self.session_factory()` → `self.transaction()`
    - `respawn_player()` line 281: `self.session_factory()` → `self.transaction()`
  - [x] 3.2: `server/net/handlers/auth.py` — 3 sites:
    - `_save_player_state()` line 113: → `game.transaction()`
    - `handle_register()` line 205: → `game.transaction()`
    - `handle_login()` line 267: → `game.transaction()`
  - [x] 3.3: `server/net/handlers/movement.py` — 4 sites:
    - `_handle_mob_encounter()` line 180: → `game.transaction()`
    - `_handle_exit_transition()` lines 248, 309, 326: → `game.transaction()`
  - [x] 3.4: `server/net/handlers/combat.py` — 5 sites:
    - `_sync_combat_stats()` line 35: → `game.transaction()`
    - `_check_combat_end()` lines 78, 121, 138: → `game.transaction()`
    - `handle_use_item_combat()` line 318: → `game.transaction()`
  - [x] 3.5: `server/net/handlers/inventory.py` — 1 site:
    - `handle_use_item()` line 94: → `game.transaction()`
  - [x] 3.6: `server/net/handlers/interact.py` — 2 sites:
    - `handle_interact()` lines 106, 124: → `game.transaction()`
  - [x] 3.7: `server/net/handlers/levelup.py` — 1 site:
    - `handle_level_up()` line 91: → `game.transaction()`
  - [x] 3.8: `server/core/xp.py` — 1 site:
    - `grant_xp()` line 50: → `game.transaction()`
  - [x] 3.9: `server/room/objects/chest.py` — 1 site:
    - `ChestObject.interact()` line 27: → `game.transaction()`
  - [x] 3.10: `server/room/objects/lever.py` — 1 site:
    - `LeverObject.interact()` line 29: → `game.transaction()`
  - [x] 3.11: `server/core/scheduler.py` — 2 sites:
    - `_run_rare_spawn_checks()` line 127: `self._game.session_factory()` → `self._game.transaction()`
    - `_recover_checkpoints()` line 205: `self._game.session_factory()` → `self._game.transaction()`
  - [x] 3.12: `server/net/handlers/trade.py` — 1 site:
    - `_execute_trade()` line 447: → `game.transaction()`

- [x] Task 4: Eliminate 4 repo bypass patterns (AC: #4, #5, #6, #7)
  - [x] 4.1: **Trade bypass** (`server/net/handlers/trade.py:447-454`): Replace raw `sa_update(Player)` calls with two `player_repo.update_inventory(session, db_id, new_inv)` calls inside one `game.transaction()` block. Remove the `from sqlalchemy import update as sa_update` and `from server.player.models import Player` imports if no longer needed. Atomicity preserved — both calls share the same session.
  - [x] 4.2: **Combat loot bypass** (`server/net/handlers/combat.py:121-129`): Replace `player_repo.get_by_id()` + direct `player.inventory` mutation + `session.commit()` with: read current DB inventory via `player_repo.get_by_id()`, merge loot items into a new dict, then call `player_repo.update_inventory(session, db_id, merged_dict)`. Do NOT call `session.commit()` — the transaction CM handles it.
  - [x] 4.3: **Chest bypass** (`server/room/objects/chest.py:38-45`): Same pattern — read player via `player_repo.get_by_id()`, build merged inventory dict, call `player_repo.update_inventory(session, player_id, db_inventory)`. Remove the mid-block `await session.commit()` on line 45 — the transaction CM commits at block exit.
  - [x] 4.4: **Scheduler bypass** (`server/core/scheduler.py:127-196`): No repo exists for `SpawnCheckpoint`, so inline `session.execute()`, `session.add()`, `session.flush()` are acceptable. Remove the 2 explicit `session.commit()` calls (lines 164 and 196). Keep `session.flush()` on line 151 (needed to persist the new checkpoint row so subsequent operations in the same loop iteration can reference it). The transaction CM commits all checkpoint updates together at block exit.

- [x] Task 5: Update all test files (AC: #9)
  - [x] 5.1: **Mock pattern change**: Replace `game.session_factory = <mock>` with `game.transaction = <mock>` in all test files. Mock shape is identical: `MagicMock(return_value=mock_ctx)` where `mock_ctx.__aenter__` returns a mock session and `mock_ctx.__aexit__` returns False.
  - [x] 5.2: **Helper function rename** — 10 files have `_mock_session_factory()` helpers. Rename to `_mock_transaction()` and update all references:
    - `tests/test_logout.py` (line 14, assigned line 31)
    - `tests/test_room_transition.py` (line 19, assigned lines 32, 174, 267, 303)
    - `tests/test_loot.py` (line 89, assigned line 103)
    - `tests/test_chest.py` (line 22, assigned line 35)
    - `tests/test_lever.py` (line 22, assigned line 31)
    - `tests/test_blocking_objects.py` (line 137, assigned line 147)
    - `tests/test_xp.py` (line 14, assigned line 202)
    - `tests/test_level_up.py` (line 85, assigned lines 103, 294)
    - `tests/test_exploration_xp.py` (line 39, assigned lines 51, 131, 167)
    - `tests/test_interaction_xp.py` (line 28, assigned line 40)
  - [x] 5.3: **Integration tests with real DB** — Files that assign `game.session_factory = test_session_factory` for integration-style tests should keep the `session_factory` assignment. The real `Game.transaction()` method wraps `session_factory`, so these tests exercise the real transaction path. No mock of `transaction` needed.
    - `tests/test_auth.py` (lines 50-54): Keep `game.session_factory = test_session_factory` — transaction() uses it
    - `tests/test_game.py` (lines 61, 84, 117): Same
    - `tests/test_login.py` (lines 66-77): Same
    - `tests/test_startup_wiring.py` (lines 49, 104, 124): Same
    - `tests/test_stats_persistence.py` (lines 69-78): Same
    - `tests/test_integration.py` (lines 100-123): Same
  - [x] 5.4: **Inline `MagicMock` session_factory** — Replace `game.session_factory = MagicMock(...)` with `game.transaction = MagicMock(...)`:
    - `tests/test_game.py` (lines 167, 220, 256, 292)
    - `tests/test_spawn.py` (lines 190, 229, 265, 298, 375)
    - `tests/test_events.py` (line 209)
    - `tests/test_trade.py` (lines 773, 824, 915, 969)
    - `tests/test_party.py` (line 335)
    - `tests/test_combat_multiplayer.py` (line 377)
    - `tests/test_party_combat.py` (line 105)
  - [x] 5.5: **Save/restore pattern** — `tests/test_stats_persistence.py` line 286 (`game.session_factory = mock_factory`) → `game.transaction = mock_factory`
  - [x] 5.6: **Repo direct tests** (`tests/test_repos.py`, `tests/test_database.py`, `tests/test_sample_data.py`): These use local `async_sessionmaker` variables — no `game.session_factory` changes needed. But since repos no longer call `session.commit()`, any test that calls a repo write function must commit manually afterwards, or the test's transaction-scoped session auto-rollback will discard the data. Verify these tests still pass.

- [x] Task 6: Final validation (AC: #9, #10)
  - [x] 6.1: Run `make test` — all 804 tests must pass, 0 warnings.
  - [x] 6.2: Grep validation: `grep -r 'session\.commit()' server/` should only match `server/app.py` (inside `Game.transaction()`).
  - [x] 6.3: Grep validation: `grep -r 'session_factory()' server/` should return zero matches.

## Dev Notes

### Architecture Pattern

`Game.transaction()` is a thin wrapper around `self.session_factory()`. It adds commit-on-success and rollback-on-error semantics. The `session_factory` attribute remains on `Game` — `transaction()` delegates to it. This means:
- Integration tests can still assign `game.session_factory = test_session_factory` and `transaction()` will use it naturally.
- Unit tests that mock `game.transaction` directly bypass the real session factory entirely.

### Critical: flush vs commit in repos

Two repo functions use `session.refresh()` after insert to get auto-increment IDs:
- `player_repo.create()` — needs `player.id` for entity_id generation (`f"player_{db_id}"`)
- `room_repo.upsert_room()` insert branch — needs `room.id` for return value

Replace `commit()` with `flush()` in these two locations. `flush()` sends the INSERT to the DB (generating the ID) without ending the transaction.

### Bypass pattern details

| Bypass | File | Current Pattern | New Pattern |
|--------|------|-----------------|-------------|
| Trade | `trade.py:447-454` | Raw `sa_update(Player)` × 2 + `commit()` | `player_repo.update_inventory()` × 2 in `transaction()` |
| Combat loot | `combat.py:121-129` | `get_by_id()` + `player.inventory = ...` + `commit()` | `get_by_id()` + build dict + `update_inventory()` in `transaction()` |
| Chest | `chest.py:38-45` | `get_by_id()` + `player.inventory = ...` + `commit()` | `get_by_id()` + build dict + `update_inventory()` in `transaction()` |
| Scheduler | `scheduler.py:127-196` | Raw `execute/add/flush/commit` | Keep inline ops, wrap in `transaction()`, remove 2 `commit()` calls |

### Scheduler atomicity change

Currently each rare spawn iteration commits independently (lines 164, 196). After refactor, the entire `_run_rare_spawn_checks` call is one transaction — all checkpoint updates commit together. In normal operation: identical behavior. On crash mid-loop: previously partial commits, now full rollback. This is better (consistent state).

### Test file summary

| Category | Files | Action |
|----------|-------|--------|
| `_mock_session_factory()` helpers | 10 | Rename to `_mock_transaction()`, assign to `game.transaction` |
| Real DB fixtures (`test_session_factory`) | 6 | Keep `game.session_factory = test_session_factory` (transaction wraps it) |
| Inline `MagicMock` | 7 | `game.session_factory = MagicMock(...)` → `game.transaction = MagicMock(...)` |
| Save/restore | 1 | Update mock line only |
| Local fixture vars | 3 | No changes needed |
| No references | 23+ | No changes needed |

### Files modified (production)

| File | Changes |
|------|---------|
| `server/app.py` | Add `transaction()` method; replace 4 `session_factory()` calls |
| `server/player/repo.py` | Remove 5 `commit()`, replace 1 with `flush()` |
| `server/room/repo.py` | Remove 2 `commit()`, replace 1 with `flush()` |
| `server/items/item_repo.py` | Remove 1 `commit()` |
| `server/combat/cards/card_repo.py` | Remove 1 `commit()` |
| `server/room/objects/state.py` | Remove 2 `commit()` |
| `server/net/handlers/auth.py` | Replace 3 `session_factory()` calls |
| `server/net/handlers/movement.py` | Replace 4 `session_factory()` calls |
| `server/net/handlers/combat.py` | Replace 5 `session_factory()` calls; refactor loot bypass |
| `server/net/handlers/inventory.py` | Replace 1 `session_factory()` call |
| `server/net/handlers/interact.py` | Replace 2 `session_factory()` calls |
| `server/net/handlers/levelup.py` | Replace 1 `session_factory()` call |
| `server/net/handlers/trade.py` | Replace 1 `session_factory()` call; replace raw SQL with repo |
| `server/core/xp.py` | Replace 1 `session_factory()` call |
| `server/core/scheduler.py` | Replace 2 `session_factory()` calls; remove 2 `commit()` calls |
| `server/room/objects/chest.py` | Replace 1 `session_factory()` call; replace direct mutation with repo |
| `server/room/objects/lever.py` | Replace 1 `session_factory()` call |

### What NOT to change

- `session_factory` attribute on `Game.__init__` — `transaction()` wraps it
- Repo function signatures — no parameter changes
- Handler function signatures — no parameter changes
- Web client, database schema, game logic — no changes
- No new files, no new dependencies, no config changes

### Project Structure Notes

- All changes are edits to existing files
- No new directories or files created
- Pure refactor — zero gameplay behavior changes

### References

- [Source: _bmad-output/planning-artifacts/epics.md, line 2906 — Epic 13, Story 13.1]
- [Source: _bmad-output/project-context.md, lines 107-110 — Repo pattern: "Repos call session.commit() internally"]
- [Source: _bmad-output/project-context.md, line 165 — Anti-pattern: "NEVER call session.commit() outside repos"]
- [Source: server/app.py:46 — self.session_factory = _database.async_session]
- [Source: server/app.py:6 — asynccontextmanager already imported]
- [Source: server/player/repo.py:22-37 — create() with commit+refresh pattern]
- [Source: server/room/repo.py:27-44 — upsert_room() with commit+refresh pattern]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Completion Notes List

- Added `Game.transaction()` async context manager wrapping `session_factory` with auto-commit/rollback
- Removed 13 `session.commit()` calls from 6 repo/state files (replaced 2 with `session.flush()` for auto-increment ID generation)
- Added `session.flush()` to `room_repo.save_state()` for new object ID population
- Replaced all 26 `session_factory()` call sites with `transaction()` across 12 server files
- Eliminated 4 repo bypass patterns: trade (raw SQL → repo), combat loot (direct mutation → repo), chest (direct mutation → repo), scheduler (removed 2 explicit commits)
- Updated 18 test files: renamed 10 `_mock_session_factory` helpers, updated 7 inline mock files, 1 mixed file
- Fixed test assertions for refactored chest/loot code (update_inventory via repo instead of direct mutation)
- Fixed test_stats_persistence repo tests (added manual commits since repos no longer auto-commit)
- Fixed test_trade DB failure simulation (execute raises instead of commit)
- 804 tests pass, 0 failures

### File List

**Production code (17 files):**
- server/app.py
- server/player/repo.py
- server/room/repo.py
- server/items/item_repo.py
- server/combat/cards/card_repo.py
- server/room/objects/state.py
- server/net/handlers/auth.py
- server/net/handlers/movement.py
- server/net/handlers/combat.py
- server/net/handlers/inventory.py
- server/net/handlers/interact.py
- server/net/handlers/levelup.py
- server/net/handlers/trade.py
- server/core/xp.py
- server/core/scheduler.py
- server/room/objects/chest.py
- server/room/objects/lever.py

**Test code (18 files):**
- tests/test_logout.py
- tests/test_room_transition.py
- tests/test_loot.py
- tests/test_chest.py
- tests/test_lever.py
- tests/test_blocking_objects.py
- tests/test_xp.py
- tests/test_level_up.py
- tests/test_exploration_xp.py
- tests/test_interaction_xp.py
- tests/test_game.py
- tests/test_spawn.py
- tests/test_events.py
- tests/test_trade.py
- tests/test_party.py
- tests/test_combat_multiplayer.py
- tests/test_party_combat.py
- tests/test_stats_persistence.py
