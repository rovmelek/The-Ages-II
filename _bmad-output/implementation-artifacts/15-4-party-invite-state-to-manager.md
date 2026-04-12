# Story 15.4: Party Invite State → PartyManager

Status: done

## Story

As a developer,
I want party invite tracking state managed by `PartyManager` instead of module-level globals in the party handler,
So that the handler is stateless and the unique `set_game_ref()` wiring pattern is eliminated.

## Acceptance Criteria

1. **Given** 4 module-level mutable dicts in `server/net/handlers/party.py`:
   - `_pending_invites: dict[str, str]` (line 21)
   - `_outgoing_invites: dict[str, str]` (line 22)
   - `_invite_timeouts: dict[str, asyncio.TimerHandle]` (line 23)
   - `_invite_cooldowns: dict[str, dict[str, float]]` (line 24)
   **And** `_game_ref: Game | None` global (line 27) with `set_game_ref()` setter (line 30),
   **When** Story 15.4 is implemented,
   **Then** these dicts and the game ref are attributes on `PartyManager` (in `server/party/manager.py`),
   **And** the module-level globals and `set_game_ref()` function are removed from `party.py`.

2. **Given** `_invite_timeouts` stores `asyncio.TimerHandle` objects whose sync callback (`_handle_invite_timeout`, line 272) needs `connection_manager` to send timeout notifications and `_get_entity_name()` to look up display names,
   **When** Story 15.4 is implemented,
   **Then** `PartyManager.__init__` accepts `connection_manager` via constructor injection (consistent with `CombatManager(effect_registry=...)` pattern),
   **And** timer callbacks reference `self._connection_manager` instead of `_game_ref.connection_manager`,
   **And** display names are stored at invite creation time so the timeout callback does not need player session lookup at fire time.

3. **Given** `app.py` line 45: `self.party_manager = PartyManager()` and line 155/233: `set_party_game_ref(self)` import+call,
   **When** Story 15.4 is implemented,
   **Then** the `set_party_game_ref` call and its import are removed,
   **And** `PartyManager` construction passes `connection_manager`: `self.party_manager = PartyManager(connection_manager=self.connection_manager)`.

4. **Given** handler functions in `party.py` that access the module-level invite dicts (`_pending_invites`, `_outgoing_invites`, `_invite_timeouts`, `_invite_cooldowns`),
   **When** Story 15.4 is implemented,
   **Then** they access `game.party_manager` attributes/methods instead.

5. **Given** `cleanup_pending_invites(entity_id)` in `party.py` (line 86) is called from `PlayerManager.cleanup_session()` (manager.py line 154) via deferred import,
   **When** Story 15.4 is implemented,
   **Then** this becomes `game.party_manager.cleanup_invites(entity_id)` on `PartyManager`,
   **And** the deferred import in `PlayerManager._cleanup_party()` (line 154) is removed.

6. **Given** helper functions `_cancel_invite`, `_set_cooldown`, `_check_cooldown` in `party.py` operate on module-level dicts,
   **When** Story 15.4 is implemented,
   **Then** they become methods on `PartyManager` (or are inlined into the methods that use them).

7. **Given** all existing tests (807+),
   **When** Story 15.4 is implemented,
   **Then** all tests pass with no assertion value changes.

## Tasks / Subtasks

### Task 1: Add invite state and methods to PartyManager (AC: #1, #2, #6)

- [x] 1.1: Add new attributes to `PartyManager.__init__`:
  - `self._pending_invites: dict[str, str] = {}`
  - `self._outgoing_invites: dict[str, str] = {}`
  - `self._invite_timeouts: dict[str, asyncio.TimerHandle] = {}`
  - `self._invite_cooldowns: dict[str, dict[str, float]] = {}`
  - Accept `connection_manager` parameter: `def __init__(self, *, connection_manager: ConnectionManager | None = None)`
  - Store as `self._connection_manager = connection_manager`
  - Add `import asyncio` and `from server.net.connection_manager import ConnectionManager`

- [x] 1.2: Move helper functions to PartyManager methods:
  - `cancel_invite(self, target_id: str) -> str | None` — same logic as `_cancel_invite`, operates on `self._pending_invites` etc.
  - `set_cooldown(self, inviter_id: str, target_id: str) -> None` — same logic as `_set_cooldown`
  - `check_cooldown(self, inviter_id: str, target_id: str) -> bool` — same logic as `_check_cooldown`
  - `cleanup_invites(self, entity_id: str) -> None` — same logic as `cleanup_pending_invites`

- [x] 1.3: Add invite management methods:
  - `has_pending_invite(self, target_id: str) -> bool` — replaces `target_id in _pending_invites`
  - `get_pending_invite(self, target_id: str) -> str | None` — replaces `_pending_invites.get(target_id)`
  - `get_outgoing_invite(self, entity_id: str) -> str | None` — replaces `_outgoing_invites.get(entity_id)`
  - `create_invite(self, inviter_id: str, target_id: str, target_name: str) -> None` — stores invite, schedules timeout, stores target display name for timeout callback
  - `handle_invite_timeout(self, target_id: str) -> None` — same logic as `_handle_invite_timeout`, uses `self._connection_manager` and stored `target_name` instead of `_game_ref`

### Task 2: Update `Game.__init__` in `app.py` (AC: #3)

- [x] 2.1: Change `PartyManager()` construction to `PartyManager(connection_manager=self.connection_manager)`
- [x] 2.2: Remove the import of `set_game_ref as set_party_game_ref` from line 155
- [x] 2.3: Remove the `set_party_game_ref(self)` call at line 233

### Task 3: Update party handler to use PartyManager (AC: #4)

- [x] 3.1: Remove module-level globals: `_pending_invites`, `_outgoing_invites`, `_invite_timeouts`, `_invite_cooldowns`, `_game_ref`
- [x] 3.2: Remove functions: `set_game_ref()`, `_cancel_invite()`, `_set_cooldown()`, `_check_cooldown()`, `cleanup_pending_invites()`, `_handle_invite_timeout()`
- [x] 3.3: Update `_handle_invite()` — replace direct dict access with `game.party_manager` method calls:
  - `target_id in _pending_invites` → `game.party_manager.has_pending_invite(target_id)`
  - `_check_cooldown(...)` → `game.party_manager.check_cooldown(...)`
  - `_cancel_invite(old_target)` → `game.party_manager.cancel_invite(old_target)`
  - Dict stores + timeout scheduling → `game.party_manager.create_invite(entity_id, target_id, target_name)`
- [x] 3.4: Update `_handle_accept()` — replace `_pending_invites.get(entity_id)` → `game.party_manager.get_pending_invite(entity_id)`, `_cancel_invite(entity_id)` → `game.party_manager.cancel_invite(entity_id)`
- [x] 3.5: Update `_handle_reject()` — same pattern: use `game.party_manager.get_pending_invite()`, `cancel_invite()`, `set_cooldown()`
- [x] 3.6: Update `_handle_kick()` — replace `_set_cooldown(entity_id, target_id)` (line 473) → `game.party_manager.set_cooldown(entity_id, target_id)`
- [x] 3.7: Update `_handle_status()` — replace `_pending_invites.get(entity_id)` → `game.party_manager.get_pending_invite(entity_id)`
- [x] 3.8: Remove `import time` from `party.py` (only used by `_set_cooldown` and `_check_cooldown` which are now on PartyManager)

### Task 4: Update PlayerManager cleanup (AC: #5)

- [x] 4.1: In `server/player/manager.py` `_cleanup_party()` (line 154):
  - Replace `from server.net.handlers.party import cleanup_pending_invites` + `cleanup_pending_invites(entity_id)` with `game.party_manager.cleanup_invites(entity_id)`
  - The `game` parameter is already available (passed to `cleanup_session`)

### Task 5: Update tests (AC: #7)

- [x] 5.1: Update `tests/test_party_commands.py` imports:
  - Remove: `_cancel_invite`, `_check_cooldown`, `_invite_cooldowns`, `_invite_timeouts`, `_outgoing_invites`, `_pending_invites`, `_set_cooldown`, `cleanup_pending_invites`, `set_game_ref`
  - These are now accessed via `game.party_manager` in tests
- [x] 5.2: Update `_make_game()` helper — `PartyManager()` is now constructed without `connection_manager` in unit tests (pass `connection_manager=game.connection_manager` or `None`)
- [x] 5.3: Update `_clear_invite_state()` fixture — clear `game.party_manager._pending_invites` etc. (or create a `clear_invites()` method on PartyManager for test use)
  - Since the fixture runs before each test and creates fresh `PartyManager` instances via `_make_game()`, the `autouse` fixture may just need to clear the manager's state — but since each test creates its own `game`, the fixture may become a no-op
- [x] 5.4: Update test assertions that check `_pending_invites["player_2"]` → `game.party_manager._pending_invites["player_2"]` (or use accessor methods)
- [x] 5.5: Update `TestInviteTimeout.test_invite_timeout_cleans_up` — remove `set_game_ref(game)`, use `game.party_manager.handle_invite_timeout("player_2")` instead of importing `_handle_invite_timeout`
- [x] 5.6: Update `TestDisconnectCleanup` — call `game.party_manager.cleanup_invites(...)` instead of `cleanup_pending_invites(...)`
- [x] 5.7: Run `make test` — all 807+ tests must pass

## Dev Notes

### Architecture & Patterns

- **Pure refactor** — zero gameplay behavior changes
- **ADR-15-4:** Party invite dicts become `PartyManager` attributes — `connection_manager` injected via constructor (matches `CombatManager(effect_registry=...)` pattern)
- This is the last module with `set_*_ref()` wiring — after this, all state lives in managers owned by `Game`

### Invite State — Current Location vs Target

| Item | Current location (`party.py`) | Target location (`PartyManager`) |
|------|------------------------------|----------------------------------|
| `_pending_invites` | Module global (line 21) | `self._pending_invites` attribute |
| `_outgoing_invites` | Module global (line 22) | `self._outgoing_invites` attribute |
| `_invite_timeouts` | Module global (line 23) | `self._invite_timeouts` attribute |
| `_invite_cooldowns` | Module global (line 24) | `self._invite_cooldowns` attribute |
| `_game_ref` | Module global (line 27) | Eliminated — `connection_manager` injected via constructor |
| `set_game_ref()` | Free function (line 30) | Eliminated |
| `_cancel_invite()` | Free function (line 36) | `self.cancel_invite()` method |
| `_set_cooldown()` | Free function (line 47) | `self.set_cooldown()` method |
| `_check_cooldown()` | Free function (line 54) | `self.check_cooldown()` method |
| `cleanup_pending_invites()` | Free function (line 86) | `self.cleanup_invites()` method |
| `_handle_invite_timeout()` | Free function (line 272) | `self.handle_invite_timeout()` method |

### Timeout Callback Design

The current `_handle_invite_timeout` is a sync callback from `asyncio.call_later`. It accesses `_game_ref.connection_manager` to send async notifications via `loop.create_task()`. After refactoring:

- `PartyManager.handle_invite_timeout(target_id)` uses `self._connection_manager` directly
- Target display name is stored at invite creation time in a dict (e.g., `self._invite_names: dict[str, str]` mapping `target_id -> target_name`) so the timeout callback does not need to look up `game.player_manager` (player may have disconnected by timeout fire time). Only `target_name` is needed — it's sent to the inviter in the `"expired"` message; `inviter_id` is already known from `_pending_invites`
- The `call_later` callback references `self.handle_invite_timeout` — since `PartyManager` outlives individual invites, this is safe

### Constructor Injection

```python
class PartyManager:
    def __init__(self, *, connection_manager: ConnectionManager | None = None) -> None:
        self._parties: dict[str, Party] = {}
        self._player_party: dict[str, str] = {}
        # Invite tracking (moved from party.py handler)
        self._pending_invites: dict[str, str] = {}
        self._outgoing_invites: dict[str, str] = {}
        self._invite_timeouts: dict[str, asyncio.TimerHandle] = {}
        self._invite_cooldowns: dict[str, dict[str, float]] = {}
        self._invite_names: dict[str, str] = {}  # target_id -> target_name
        self._connection_manager = connection_manager
```

`connection_manager` is `None`-optional so existing test helpers like `_make_game()` that construct `PartyManager()` without arguments continue to work. Tests that exercise timeout notification can pass a mock `connection_manager`.

### Test Impact

- `tests/test_party_commands.py` — main impact file:
  - Imports of module-level dicts (`_pending_invites` etc.) change to accessing `game.party_manager._pending_invites` (or via methods)
  - `_clear_invite_state()` no longer needed as a separate function — each test creates a fresh `_make_game()` which creates a fresh `PartyManager`
  - The `autouse` fixture `_clean_state` can be simplified or removed since module-level state no longer exists
  - `set_game_ref(game)` call in `TestInviteTimeout` is removed
  - `cleanup_pending_invites("player_2")` → `game.party_manager.cleanup_invites("player_2")`
- Tests that directly set `_pending_invites["player_2"] = "player_1"` to set up test state → set `game.party_manager._pending_invites["player_2"] = "player_1"` (direct attribute access for test setup is acceptable)
- No assertion value changes — all party behavior is identical

### Files to Modify

| File | Changes |
|------|---------|
| `server/party/manager.py` | Add invite state attributes, invite methods, `connection_manager` param |
| `server/net/handlers/party.py` | Remove all module-level globals and helper functions; update handlers to use `game.party_manager` |
| `server/app.py` | Change `PartyManager()` constructor, remove `set_party_game_ref` import and call |
| `server/player/manager.py` | Replace deferred `cleanup_pending_invites` import with `game.party_manager.cleanup_invites()` |
| `tests/test_party_commands.py` | Update imports, state access, fixture, and test helpers |

### Anti-Patterns to Avoid

- Do NOT change party gameplay behavior — pure refactor
- Do NOT change assertion values in any test
- Do NOT leave any module-level mutable state in `party.py`
- Do NOT import `PartyManager` methods back into `party.py` as module-level names — always access via `game.party_manager`
- Do NOT change the `@requires_auth` decorator or handler registration
- Do NOT forget to store display names at invite creation time — the timeout callback must not depend on player sessions still existing

### Previous Story Intelligence

From Story 15.3:
- `@requires_auth` decorator injects `entity_id` and `player_info` kwargs — all party handlers are already decorated
- `handle_party` and `handle_party_chat` already use `game=game` keyword; inner helpers receive `game` as a positional arg

From Story 15.2:
- `PlayerManager.cleanup_session()` in `server/player/manager.py` calls `cleanup_pending_invites(entity_id)` via deferred import at line 154 — this is the deferred import to eliminate

From Story 15.1:
- `game.player_manager` is the standard session access pattern — `_get_entity_name()` already uses it

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Story 15.4 (lines 3739-3782)]
- [Source: _bmad-output/planning-artifacts/epics.md — ADR-15-4 (line 3916)]
- [Source: server/net/handlers/party.py — module-level globals (lines 20-33)]
- [Source: server/party/manager.py — PartyManager class (lines 21-131)]
- [Source: server/app.py — PartyManager construction (line 45), set_game_ref import (line 155), call (line 233)]
- [Source: server/player/manager.py — cleanup_pending_invites deferred import (line 154)]
- [Source: tests/test_party_commands.py — test imports and state access (lines 11-22, 99-112)]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- All 807 tests pass (0 failures, 0 warnings, ~4.1s)
- `grep -r "_pending_invites\|_outgoing_invites\|_invite_timeouts\|_invite_cooldowns\|_game_ref\|set_game_ref\|cleanup_pending_invites" server/net/handlers/party.py` returns zero hits
- `grep -r "cleanup_pending_invites\|from server.net.handlers.party" server/` only returns legitimate handler imports in app.py

### Completion Notes List

- Moved 4 module-level mutable dicts + `_game_ref` global from `party.py` handler to `PartyManager` attributes
- Added 10 invite management methods to `PartyManager`: `cancel_invite`, `set_cooldown`, `check_cooldown`, `has_pending_invite`, `get_pending_invite`, `get_outgoing_invite`, `create_invite`, `handle_invite_timeout`, `cleanup_invites`
- `PartyManager.__init__` now accepts `connection_manager` via keyword-only constructor injection (matches `CombatManager(effect_registry=...)` pattern)
- Eliminated `set_game_ref()` / `set_party_game_ref()` wiring pattern — the last `set_*_ref()` in the codebase
- `handle_invite_timeout` stores `target_name` at invite creation time via `_invite_names` dict — no player session lookup at fire time
- Eliminated deferred import of `cleanup_pending_invites` in `PlayerManager._cleanup_party()` — now calls `game.party_manager.cleanup_invites(entity_id)` directly
- Removed `autouse` fixture and `_clear_invite_state()` from tests — each test creates fresh `_make_game()` with fresh `PartyManager`
- Removed `import asyncio`, `import time` from `party.py` (no longer needed)
- Pure refactor — zero gameplay behavior changes

### File List

**Modified:**
- `server/party/manager.py` — Added invite state attributes, 10 invite methods, `connection_manager` constructor param
- `server/net/handlers/party.py` — Removed all module-level globals, helper functions, and `set_game_ref()`; updated all handlers to use `game.party_manager` methods
- `server/app.py` — Changed `PartyManager()` to `PartyManager(connection_manager=self.connection_manager)`; removed `set_party_game_ref` import and call
- `server/player/manager.py` — Replaced deferred `cleanup_pending_invites` import with `game.party_manager.cleanup_invites(entity_id)`
- `tests/test_party_commands.py` — Updated all imports, state access, fixtures, and test helpers to use `game.party_manager`
