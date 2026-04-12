# Story 16.5: Decompose handle_login

Status: done

## Story

As a **server developer**,
I want `handle_login` (160 lines, 12 concerns) broken into focused helper functions,
So that the login flow is readable, testable, and reusable by `handle_reconnect` (Story 16.9).

## Acceptance Criteria

1. **Given** `handle_login` at `server/net/handlers/auth.py:112-271` mixes 12 concerns,
   **When** Story 16.5 is implemented,
   **Then** the following helper functions exist in the same file:
   - `_default_stats()` — module-level FUNCTION (not constant) that reads `settings.*` on each call
   - `_resolve_stats(player, session)` — first-time vs returning player stats
   - `_resolve_room_and_place(entity, player, room_key, game, session)` — loads room + finds spawn (raises `ValueError` if room not found)
   - `_hydrate_inventory(player, session)` — rebuilds `Inventory` from DB
   - `_build_login_response(db_id, entity_id, username, stats, session_token=None)` — takes field parameters (not `Player` model)

2. **Given** the refactored `handle_login`,
   **When** measured,
   **Then** it is ≤60 lines.

3. **Given** line 268 currently shadows `session` variable (DB `AsyncSession` → `PlayerSession`),
   **When** Story 16.5 is implemented,
   **Then** the shadowing is eliminated (use `player_session` for the `PlayerManager.get_session` lookup).

4. **Given** all 959+ existing tests,
   **When** Story 16.5 is implemented,
   **Then** all tests pass unchanged.

## Tasks / Subtasks

- [x] Task 1: Create `_default_stats()` function (AC: #1)
  - [x] 1.1: Extract the inline `_DEFAULT_STATS` dict (lines 139-145) to a module-level function
  - [x] 1.2: Function reads `settings.DEFAULT_BASE_HP`, `settings.DEFAULT_ATTACK`, `settings.DEFAULT_STAT_VALUE` on each call

- [x] Task 2: Create `_resolve_stats()` function (AC: #1)
  - [x] 2.1: Extract stats resolution logic (lines 146-156) into `_resolve_stats(player, session)`
  - [x] 2.2: First-time: build defaults, compute max_hp from CON, persist via `player_repo.update_stats`
  - [x] 2.3: Returning: merge `_default_stats()` with saved `db_stats`

- [x] Task 3: Create `_resolve_room_and_place()` function (AC: #1)
  - [x] 3.1: Extract room loading + spawn placement (lines 168-195) into `_resolve_room_and_place`
  - [x] 3.2: Raises `ValueError` if room not found (caller catches and sends error JSON)
  - [x] 3.3: Preserve the extra walkability check with `find_first_walkable()` fallback (line 186-192)

- [x] Task 4: Create `_hydrate_inventory()` function (AC: #1)
  - [x] 4.1: Extract inventory hydration (lines 202-208) into `_hydrate_inventory(player, session)`
  - [x] 4.2: Returns `Inventory` (empty if no DB inventory)

- [x] Task 5: Create `_build_login_response()` function (AC: #1)
  - [x] 5.1: Extract login_success JSON construction (lines 226-248) into `_build_login_response`
  - [x] 5.2: Takes `db_id, entity_id, username, stats, session_token=None` (field params, not Player model)
  - [x] 5.3: Include `xp_for_next_level` and `xp_for_current_level` calculations
  - [x] 5.4: Add `session_token` to response only if not None

- [x] Task 6: Refactor `handle_login` to use helpers (AC: #1, #2, #3)
  - [x] 6.1: Replace inline code with calls to `_default_stats`, `_resolve_stats`, `_resolve_room_and_place`, `_hydrate_inventory`, `_build_login_response`
  - [x] 6.2: Rename `session` → `player_session` at line 268 to eliminate variable shadowing
  - [x] 6.3: Wrap `_resolve_room_and_place` in try/except ValueError (send error JSON on catch)
  - [x] 6.4: Verify `handle_login` is ≤60 lines

- [x] Task 7: Run full test suite (AC: #4)
  - [x] 7.1: Run `make test` — all 959+ tests pass, 0 failures

## Dev Notes

### Current `handle_login` Structure (server/net/handlers/auth.py:112-271, 160 lines)

| Lines | Operation | Concern |
|-------|-----------|---------|
| 114-115 | Input extraction | Validation |
| 117-123 | DB lookup + password verify | Authentication |
| 126-136 | Duplicate session check/kick | Session management |
| 139-156 | Stats resolution with defaults | Business logic |
| 158-165 | Entity creation | Object construction |
| 168-195 | Room load + spawn placement | Business logic |
| 198-199 | Room/connection registration | Side effects |
| 202-208 | Inventory hydration from DB | Business logic |
| 211-213 | Visited rooms restoration | Business logic |
| 216-223 | Session creation | Side effects |
| 226-263 | Response + broadcast | Messaging |
| 266-271 | Pending level-up check | Business logic |

### Variable Shadowing (line 268)

Current code at line 268:
```python
session = game.player_manager.get_session(entity_id)
```
This shadows the DB `session` from line 117's `async with game.transaction() as session`. Fix: rename to `player_session`.

### Key Design Decision: _default_stats() as Function

`_default_stats()` MUST be a function (not a module-level constant) because `settings.*` values are read at import time. Tests that monkeypatch `settings.DEFAULT_BASE_HP` etc. would see stale values if it were a constant. This is documented in ADR-16-7.

### Test Impact

No test patches need updating — all tests patch `player_repo`, `verify_password`, `room_repo`, and `item_repo` at the module level. The helper functions use these same module-level imports, so patches continue to intercept correctly.

Test files that import from auth.py:
- `tests/test_logout.py` — imports `handle_login`, `handle_logout`; patches `server.net.handlers.auth.player_repo`, `verify_password`, `room_repo`
- `tests/test_exploration_xp.py` — imports `handle_login`; patches same
- Various integration tests use login through the WebSocket handler pipeline

### Architecture Compliance

- **File**: Only `server/net/handlers/auth.py` modified — all helpers in same file
- **Pattern**: Internal helpers prefixed with `_` — not part of public API
- **No new dependencies** — all imports already exist in the file
- **Testing**: Use `make test` (never bare `pytest`)
- **Pure refactor**: Zero behavior changes

### Previous Story Intelligence (16.4)

- `grant_xp` was split in 16.4a; combat service extracted in 16.4
- This story follows the same business/messaging separation philosophy
- `PlayerSession` constructor: `PlayerSession(entity=..., room_key=..., db_id=..., inventory=..., visited_rooms=..., pending_level_ups=...)`

### References

- [Source: _bmad-output/planning-artifacts/epic-16-tech-spec.md#Story-16.5] — Full implementation spec with code samples
- [Source: _bmad-output/planning-artifacts/epics.md#Story-16.5] — Acceptance criteria
- [Source: server/net/handlers/auth.py] — Current implementation (271 lines)
- [Source: CLAUDE.md] — Project conventions

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Completion Notes List

- Extracted 5 helper functions: `_default_stats`, `_resolve_stats`, `_resolve_room_and_place`, `_hydrate_inventory`, `_build_login_response`
- `handle_login` reduced from 160 lines to 55 lines
- Variable shadowing eliminated (line 268 `session` → `player_session`)
- `_default_stats()` is a function (not constant) per ADR-16-7
- `_build_login_response` takes field params for future `handle_reconnect` reuse
- 959 tests pass, 0 failures

### File List

- `server/net/handlers/auth.py` — Modified: extracted 5 helpers, refactored `handle_login`
