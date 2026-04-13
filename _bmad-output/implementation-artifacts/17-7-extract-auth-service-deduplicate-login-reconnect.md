# Story 17.7: Extract Auth Service + Deduplicate Login/Reconnect

Status: done

## Story

As a developer,
I want auth session setup logic extracted into a `player/service.py` module with shared helpers,
So that login and reconnect use the same code path, and the auth handler is thin routing only.

## Acceptance Criteria

1. **AC1 — Move 6 helper functions to `player/service.py`:**
   - Given: `_default_stats`, `_resolve_stats`, `_resolve_room_and_place`, `_hydrate_inventory`, `_build_login_response` currently in `server/net/handlers/auth.py`; `_find_spawn_point` in `server/app.py`
   - Then: All 6 functions moved to `server/player/service.py`
   - And: `_find_spawn_point` from `app.py` is consolidated with `_resolve_room_and_place` (which already contains the same spawn-with-fallback logic)
   - And: `_find_spawn_point` is also exported as a public `find_spawn_point()` for `Game.respawn_player()` to call

2. **AC2 — Shared `build_stats_payload()`:**
   - Given: Stats payload construction duplicated in `_build_login_response()` (auth.py lines 116-125), `handle_register()` (auth.py lines 200-209 — the stats dict portion), and `handle_stats()` (query.py lines 95-105)
   - Then: A shared `build_stats_payload(stats: dict) -> dict` function exists in `player/service.py`
   - And: All 3 locations call it instead of inline construction
   - Note: `handle_register` has no pre-existing `stats` dict — caller must use `_default_stats()` from `service.py` to build one, then override `hp`/`max_hp` with constitution-adjusted values before calling `build_stats_payload` (see Dev Notes for code pattern)

3. **AC3 — Shared `setup_full_session()`:**
   - Given: Login (auth.py lines 257-297) and reconnect Case 2 (auth.py lines 412-468, inside the `async with game.transaction()` block starting at line 396) share ~40 lines of session setup logic
   - Then: A shared `setup_full_session()` in `player/service.py` handles: `_resolve_stats`, entity construction, room resolution via `_resolve_room_and_place`, `room.add_entity`, `connection_manager.connect`, `_hydrate_inventory`, visited_rooms population (`player.visited_rooms or []`, append room_key if not present), `player_manager.set_session` (with `visited_rooms=set(visited_rooms)`, `pending_level_ups=0`), `_build_login_response`, send login response, send room_state, broadcast entity_entered, pending level-up check, `_start_heartbeat`
   - And: Both `handle_login` and `handle_reconnect` Case 2 call `setup_full_session()`
   - Note: The callers (`handle_login`, `handle_reconnect`) still own the transaction (`async with game.transaction()`) and the DB lookups (`player_repo.get_by_username`, `player_repo.get_by_id`). `setup_full_session` receives the `player` DB row and `session` as parameters.

4. **AC4 — Test patch targets updated:**
   - Given: Tests patch `server.net.handlers.auth.player_repo`, `server.net.handlers.auth.verify_password`, `server.net.handlers.auth.item_repo`, `server.net.handlers.auth.room_repo`
   - Then: Patch targets for functions that moved to `player/service.py` are updated to `server.player.service.*`
   - And: Patches for `verify_password` and handler-level refs (`player_repo` used directly in handlers) remain targeting their actual import location
   - And: All 1066+ tests pass

## Tasks / Subtasks

- [x] Task 1: Create `server/player/service.py` (AC: #1, #2, #3)
  - [x] 1.1 Create new file with `from __future__ import annotations` and TYPE_CHECKING guard for `Game`
  - [x] 1.2 Move `_default_stats()` from auth.py — must remain a function (ADR-16-7)
  - [x] 1.3 Move `_resolve_stats()` from auth.py
  - [x] 1.4 Move `_resolve_room_and_place()` from auth.py; the spawn-point fallback logic is already in this function — `_find_spawn_point` from `app.py` duplicates it
  - [x] 1.5 Extract the shared spawn logic into `find_spawn_point(room, room_key, entity_name)` — a public function used by both `_resolve_room_and_place` and `Game.respawn_player`
  - [x] 1.6 Move `_hydrate_inventory()` from auth.py
  - [x] 1.7 Move `_build_login_response()` from auth.py
  - [x] 1.8 Create `build_stats_payload(stats: dict) -> dict` extracting the shared stats dict construction
  - [x] 1.9 Refactor `_build_login_response` to call `build_stats_payload`
  - [x] 1.10 Create `setup_full_session()` extracting the shared login/reconnect-Case2 block

- [x] Task 2: Refactor `server/net/handlers/auth.py` (AC: #1, #3)
  - [x] 2.1 Import helpers from `server.player.service` instead of defining them locally
  - [x] 2.2 Refactor `handle_login` to call `setup_full_session()`
  - [x] 2.3 Refactor `handle_reconnect` Case 2 to call `setup_full_session()`
  - [x] 2.4 Refactor `handle_register` to use `build_stats_payload()`
  - [x] 2.5 Remove moved function definitions and their now-unused imports (`room_repo`, `item_repo`, `Inventory`, `ItemDef`); auth.py shrunk from 469 to 229 lines

- [x] Task 3: Refactor `server/net/handlers/query.py` (AC: #2)
  - [x] 3.1 Import `build_stats_payload` from `server.player.service`
  - [x] 3.2 Refactor `handle_stats` to call `build_stats_payload()` — preserve `xp_next` legacy key

- [x] Task 4: Refactor `server/app.py` (AC: #1)
  - [x] 4.1 Remove `_find_spawn_point` static method from Game class
  - [x] 4.2 Import `find_spawn_point` from `server.player.service`
  - [x] 4.3 Update `respawn_player` to call `find_spawn_point()` instead of `self._find_spawn_point()`

- [x] Task 5: Update test patch targets (AC: #4)
  - [x] 5.1 Analyzed each test file for patch target migration
  - [x] 5.2 `tests/test_logout.py`: dual-patched 2 relogin tests
  - [x] 5.3 `tests/test_exploration_xp.py`: dual-patched 1 test
  - [x] 5.4 `tests/test_msg_seq.py`: dual-patched reconnect test
  - [x] 5.5 `tests/test_grace_period.py`: dual-patched login test
  - [x] 5.6 `tests/test_session_tokens.py`: dual-patched 4 tests (login + 3 reconnect Case 2)
  - [x] 5.7 Verified `make_bare_game()` covers all attributes; `_start_heartbeat` not added to avoid breaking heartbeat tests (tests that need it mock explicitly)

- [x] Task 6: Run `make test` and verify all 1066+ tests pass (AC: #4)

## Dev Notes

### Architecture Constraints

- `from __future__ import annotations` must be first import in every new module
- Never import `Game` at module level — use `if TYPE_CHECKING: from server.app import Game`
- `_default_stats()` MUST remain a function (not constant) per ADR-16-7 — test monkeypatching depends on it
- `STAT_NAMES` is in `server.core.constants` (Story 17.1), `PROTOCOL_VERSION` also in `server.core.constants` (Story 17.13)
- DB access via `async with game.transaction() as session:` — but `setup_full_session` receives `session` as a parameter (the caller owns the transaction)
- Sprint 2 AC: no handler files should contain extracted business logic (verifiable by grep)

### Key Differences Between Login and Reconnect Case 2

Both paths share: `_resolve_stats` → `PlayerEntity` construction → `_resolve_room_and_place` → `room.add_entity` → `connection_manager.connect` → `_hydrate_inventory` → `set_session` → `_build_login_response` → send room_state → broadcast entity_entered → pending level-up check → `_start_heartbeat`

Differences that `setup_full_session` must handle:
- **Token**: Login calls `game.token_store.issue(player.id)` to create token; reconnect Case 2 already has `new_token` from earlier (issued at line 319 before Case 1/Case 2 branching). Solution: `setup_full_session` takes `session_token` as a parameter.
- **request_id**: Both wrap response with `with_request_id(..., data)`. Solution: pass `data` dict.
- **No `last_seq` check**: Neither login nor Case 2 checks `last_seq` — only Case 1 does. No special handling needed.

Blocks that stay in the handler (NOT moved into `setup_full_session`):
- **Login pre-block (lines 241-256)**: entity_id assignment (line 241), then grace-period stale-session cleanup (lines 243-249: cancel deferred cleanup handle, cancel heartbeat, cleanup session if grace-period WS-gone session exists), then active session kick (lines 251-256: `_kick_old_session`).
- **Reconnect Case 2 pre-block (lines 396-411)**: `async with game.transaction()` + `player_repo.get_by_id` lookup + error return if None + active session kick.

### `_find_spawn_point` Consolidation

`Game._find_spawn_point()` (app.py lines 257-268, including `@staticmethod` decorator at line 257) duplicates the spawn logic in `_resolve_room_and_place()` (auth.py lines 77-84, the spawn-finding portion; lines 85-88 are position assignment/DB update, which stay in `_resolve_room_and_place`). Both do: `get_player_spawn()` → fallback `find_first_walkable()` → warning log.

Consolidation plan:
- Extract as `find_spawn_point(room, room_key: str, entity_name: str) -> tuple[int, int]` in `player/service.py`
- `_resolve_room_and_place` calls `find_spawn_point` internally
- `Game.respawn_player` imports and calls `find_spawn_point` instead of `self._find_spawn_point`

### `build_stats_payload` Design

The 3 duplication sites have slight differences:
- `_build_login_response`: uses `stats.get("hp", ...)` with settings defaults as fallbacks
- `handle_register`: has NO pre-existing stats dict — computes `default_max_hp` inline, then constructs the entire stats payload from scratch
- `handle_stats`: identical keys plus legacy `xp_next`

The shared function signature: `build_stats_payload(stats: dict) -> dict`
- Takes a stats dict with all expected keys populated
- Returns: hp, max_hp, attack, xp, level, xp_for_next_level, xp_for_current_level, plus all STAT_NAMES
- `handle_stats` adds `xp_next` on top (legacy key)

For `handle_register`, the caller must first construct a synthetic stats dict from defaults:
```python
default_max_hp = settings.DEFAULT_BASE_HP + settings.DEFAULT_STAT_VALUE * settings.CON_HP_PER_POINT
stats = _default_stats()
stats["hp"] = default_max_hp
stats["max_hp"] = default_max_hp
payload = build_stats_payload(stats)
```
This uses `_default_stats()` from `service.py` (which already populates STAT_NAMES defaults).

### `setup_full_session` Signature

```python
async def setup_full_session(
    *,
    websocket: WebSocket,
    player,        # DB player row
    session,       # DB session (caller owns transaction)
    game: Game,
    session_token: str,
    data: dict,    # original message (for with_request_id)
) -> bool:
```

Returns `True` on success, `False` if room not found (error already sent to client). Internally catches `ValueError` from `_resolve_room_and_place`, sends the error response via `websocket`, and returns `False`. Callers check the return value and `return` early on `False`. This eliminates the duplicated `try/except ValueError` blocks from both `handle_login` (lines 264-268) and `handle_reconnect` Case 2 (lines 419-427).

Internally it does everything from `_resolve_stats` through `_start_heartbeat`, including `room_key` computation (`player.current_room_id or settings.DEFAULT_SPAWN_ROOM`).

### Patch Target Migration

**Critical principle**: Patch targets must match the module where the name is *looked up at runtime*. After refactor:
- `server/player/service.py` imports: `player_repo`, `room_repo`, `item_repo` (used by moved helpers: `_resolve_stats`, `_resolve_room_and_place`, `_hydrate_inventory`)
- `server/net/handlers/auth.py` keeps: `player_repo` (for `get_by_username` in login, `get_by_id` in reconnect, `create` in register), `verify_password`

**Which `player_repo` calls stay in `auth.py`:** `player_repo.get_by_username` (handle_login), `player_repo.get_by_id` (handle_reconnect), `player_repo.create` (handle_register). These are credential/lookup calls that remain in the thin handler.

**Which `player_repo` calls move to `service.py`:** `player_repo.update_stats` (inside `_resolve_stats`), `player_repo.update_position` (inside `_resolve_room_and_place`).

**Dual-patch situation**: Tests that exercise `handle_login` or `handle_reconnect` Case 2 call BOTH handler-level `player_repo` (for lookup) AND service-level `player_repo` (for stat/position updates via `setup_full_session`). If both modules import `player_repo` separately, both must be patched with the SAME mock, or alternatively `auth.py` can re-export from `service` (not recommended). The simplest approach: patch `server.player.service.player_repo` for the moved functions, and keep `server.net.handlers.auth.player_repo` for handler-level lookups. If a single test exercises both, it needs both patches pointing to the same mock.

Test files affected (only specific tests within each file):
| Test File | Tests Affected | Patches to Migrate |
|-----------|---------------|-------------------|
| `test_logout.py` | `test_relogin_same_socket_after_logout` (~L299), `test_relogin_same_socket_without_logout` (~L347) | `auth.player_repo` → dual-patch `auth.player_repo` + `service.player_repo`; `auth.room_repo` → `service.room_repo`; `auth.verify_password` stays |
| `test_exploration_xp.py` | `test_visited_rooms_restored_on_login` (~L190) | Same pattern as above |
| `test_msg_seq.py` | ~L248 | `auth.player_repo` → dual-patch; `auth.item_repo` → `service.item_repo` |
| `test_grace_period.py` | ~L266 | `auth.player_repo` → dual-patch; `auth.item_repo` → `service.item_repo`; `auth.verify_password` stays |
| `test_session_tokens.py` | Multiple (~L183, L271, L316, L381) | Dual-patch `auth.player_repo` + `service.player_repo`; L183 is login (also has `auth.verify_password` — stays, `auth.item_repo` → `service.item_repo`); L271/L316/L381 are reconnect Case 2 (`auth.item_repo` → `service.item_repo` where present) |
| `test_session_tokens.py` | `test_reconnect_player_not_found` (~L346) | Only `auth.player_repo` — returns None before service code runs; NO dual-patch needed |

**Dual-patch code pattern** — when a test exercises both handler-level and service-level `player_repo` calls:
```python
mock_repo = AsyncMock()
with patch("server.net.handlers.auth.player_repo", mock_repo), \
     patch("server.player.service.player_repo", mock_repo):
    # Both get_by_username (auth) and update_stats (service) hit the same mock
```

### Project Structure Notes

- New file: `server/player/service.py` — sits alongside `manager.py`, `auth.py`, `entity.py`, `session.py` in the player domain module
- No new test file needed — existing tests cover all paths
- `make_bare_game()` in `tests/conftest.py` already covers all Game attributes needed. Note: `_start_heartbeat` is a class method on `Game`, so `make_bare_game()` (which returns a real `Game.__new__` instance) inherits it. Tests that call `setup_full_session` through `make_bare_game()` may need to override `_start_heartbeat` with a `MagicMock()` to avoid asyncio task creation in test context.

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Story 17.7]
- [Source: server/net/handlers/auth.py — current auth handler with helpers and duplication]
- [Source: server/net/handlers/query.py:86-106 — handle_stats with duplicated stats payload]
- [Source: server/app.py:257-268 — Game._find_spawn_point static method]
- [Source: tests/conftest.py — make_bare_game() helper]
- [Source: ADR-16-7 — _default_stats must be function not constant]
- [Source: ADR-17-3 — Game retains thin delegation wrappers]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Completion Notes List
- Created `server/player/service.py` (~175 lines) with 9 functions: `_default_stats`, `_resolve_stats`, `find_spawn_point`, `_resolve_room_and_place`, `_hydrate_inventory`, `build_stats_payload`, `_build_login_response`, `setup_full_session`
- `auth.py` shrunk from 469 to 229 lines — handlers are thin routing only
- `_find_spawn_point` consolidated from `app.py` and `auth.py` into `find_spawn_point()` in `service.py`
- `build_stats_payload()` eliminates stats dict duplication across 3 sites
- `setup_full_session()` deduplicates ~40 lines shared between login and reconnect Case 2
- Dual-patch pattern used in tests to mock both `auth.player_repo` and `service.player_repo` with same mock
- All 1066 tests pass

### File List
- `server/player/service.py` (created)
- `server/net/handlers/auth.py` (modified — shrunk from 469 to 229 lines)
- `server/net/handlers/query.py` (modified — uses `build_stats_payload`)
- `server/app.py` (modified — removed `_find_spawn_point`, imports from service)
- `tests/test_logout.py` (modified — dual-patch 2 relogin tests)
- `tests/test_exploration_xp.py` (modified — dual-patch 1 test)
- `tests/test_msg_seq.py` (modified — dual-patch 1 test)
- `tests/test_grace_period.py` (modified — dual-patch 1 test)
- `tests/test_session_tokens.py` (modified — dual-patch 4 tests)
