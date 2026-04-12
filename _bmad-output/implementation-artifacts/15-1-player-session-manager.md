# Story 15.1: Player Session Manager

Status: done

## Story

As a developer,
I want player session lifecycle (create, lookup, remove, iterate) managed by a dedicated `PlayerManager` class,
So that session operations are centralized instead of scattered across handlers and the `Game` class.

## Acceptance Criteria

1. **Given** `game.player_entities` is a raw `dict[str, PlayerSession]` accessed directly from 13+ server files with 7 distinct access patterns (`.get()`, `[id] = session`, `.pop()`, `[id].attr = value`, `[id]` direct index, `not in`, `.clear()`), **When** Story 15.1 is implemented, **Then** a `PlayerManager` class exists in `server/player/manager.py` with methods:
   - `get_session(entity_id: str) -> PlayerSession | None` — replaces `.get()` and direct `[id]` lookups
   - `set_session(entity_id: str, session: PlayerSession) -> None` — replaces `[id] = session`
   - `remove_session(entity_id: str) -> PlayerSession | None` — replaces `.pop()`
   - `has_session(entity_id: str) -> bool` — replaces `in` / `not in` checks
   - `all_entity_ids() -> list[str]` — returns snapshot list (not view) for safe iterate-during-mutation
   - `all_sessions() -> Iterator[tuple[str, PlayerSession]]` — replaces `.items()` iteration
   - `clear() -> None` — replaces `.clear()`

2. **Given** `PlayerSession` is constructed in `server/net/handlers/auth.py` at line ~370 with 6 keyword arguments, **When** Story 15.1 is implemented, **Then** `set_session(entity_id, session)` takes a pre-constructed `PlayerSession` — construction remains at the call site in `auth.py`.

3. **Given** all server files that access `player_entities` (~39 occurrences across 13 files), **When** Story 15.1 is implemented, **Then** they use the appropriate `PlayerManager` method instead, **And** the internal `_sessions` dict is not publicly accessible.

4. **Given** all existing tests (807+, ~146 `player_entities` references across 26 test files), **When** Story 15.1 is implemented, **Then** all tests pass with no assertion value changes, **And** test fixtures use `game.player_manager` methods.

## Tasks / Subtasks

### Task 1: Create PlayerManager class (AC: #1)

- [x] 1.1: Create `server/player/manager.py` with `PlayerManager` class
  - Class owns a private `_sessions: dict[str, PlayerSession]` dict
  - Implement all 7 methods per AC #1
  - `all_entity_ids()` returns `list(self._sessions.keys())` — snapshot, not view
  - `all_sessions()` returns `iter(self._sessions.items())`
  - `remove_session()` returns the removed `PlayerSession | None` (mirrors `dict.pop(key, None)`)
  - Import: `from server.player.session import PlayerSession`
  - Use `from __future__ import annotations` as first import

### Task 2: Wire PlayerManager into Game (AC: #1, #3)

- [x] 2.1: In `server/app.py` `Game.__init__()`:
  - Add `from server.player.manager import PlayerManager` import
  - Replace `self.player_entities: dict[str, PlayerSession] = {}` with `self.player_manager = PlayerManager()`
  - Remove the `PlayerSession` import from `server/app.py` (only `PlayerManager` needed at `app.py` level)

### Task 3: Update server/app.py internal usages (AC: #3)

- [x] 3.1: `Game.shutdown()` (line 119): Replace `list(self.player_entities.keys())` with `self.player_manager.all_entity_ids()`
- [x] 3.2: `Game.shutdown()` (line 141): Replace `self.player_entities.clear()` with `self.player_manager.clear()`
- [x] 3.3: `Game.respawn_player()` (line 290): Replace `self.player_entities.get(entity_id)` with `self.player_manager.get_session(entity_id)`

### Task 4: Update server/net/handlers/auth.py (AC: #2, #3)

- [x] 4.1: Line ~154: Replace `game.player_entities.get(entity_id)` with `game.player_manager.get_session(entity_id)`
- [x] 4.2: Line ~169: Replace `game.player_entities.pop(entity_id, None)` with `game.player_manager.remove_session(entity_id)`
- [x] 4.3: Line ~370: Replace `game.player_entities[entity_id] = PlayerSession(...)` with `game.player_manager.set_session(entity_id, PlayerSession(...))`
- [x] 4.4: Line ~422: Replace `game.player_entities[entity_id].pending_level_ups = pending` — first do `session = game.player_manager.get_session(entity_id)` then `session.pending_level_ups = pending`

### Task 5: Update all handler files (AC: #3)

All are `.get()` → `game.player_manager.get_session()` replacements:

- [x] 5.1: `server/net/handlers/movement.py` — lines ~41, ~168, ~225 use `.get()`; line ~209 uses direct `[pid]` index — replace with `get_session()` + None guard
- [x] 5.2: `server/net/handlers/combat.py` — lines ~23, ~167, ~208, ~310, ~355 — all `.get()`
- [x] 5.3: `server/net/handlers/chat.py` — line ~21 — `.get()`
- [x] 5.4: `server/net/handlers/interact.py` — line ~26 — `.get()`
- [x] 5.5: `server/net/handlers/inventory.py` — lines ~24, ~49 — `.get()`
- [x] 5.6: `server/net/handlers/query.py` — lines ~34, ~78, ~109, ~147, ~173 — `.get()`
- [x] 5.7: `server/net/handlers/trade.py` — lines ~34, ~35, ~62, ~117, ~386, ~387 — `.get()`
- [x] 5.8: `server/net/handlers/party.py` — lines ~111, ~127, ~581 use `.get()`; line ~190 uses `not in` — replace with `not game.player_manager.has_session(target_id)`
- [x] 5.9: `server/net/handlers/levelup.py` — line ~30 — `.get()`

### Task 6: Update non-handler server files (AC: #3)

- [x] 6.1: `server/core/xp.py` — line ~74 — `.get()` → `game.player_manager.get_session()`
- [x] 6.2: `server/room/objects/chest.py` — line ~47 — `.get()` → `game.player_manager.get_session()`

### Task 7: Update documentation (AC: #3)

- [x] 7.0: Update `_bmad-output/project-context.md` — replace `game.player_entities[entity_id]` reference in the "Player State — Dual Storage" section with `game.player_manager.get_session(entity_id)` and update the description accordingly
- [x] 7.0b: Update `server/player/session.py` docstring — change "typed replacement for player_entities dict values" to reference `PlayerManager`

### Task 8: Update test files (AC: #4)

- [x] 8.1: Across all ~26 test files, replace `game.player_entities[id] = ...` with `game.player_manager.set_session(id, ...)`
- [x] 8.2: Replace `game.player_entities.get(id)` with `game.player_manager.get_session(id)`
- [x] 8.3: Replace `id not in game.player_entities` / `id in game.player_entities` with `not game.player_manager.has_session(id)` / `game.player_manager.has_session(id)`
- [x] 8.4: Replace `len(game.player_entities)` with checking via `all_entity_ids()` length
- [x] 8.5: Replace `game.player_entities.clear()` with `game.player_manager.clear()`
- [x] 8.6: Replace `game.player_entities = players or {}` patterns in mock setups (e.g., `test_trade.py`) with `game.player_manager = PlayerManager()` and use `set_session()`
- [x] 8.7: Run `make test` to verify all 807+ tests pass

## Dev Notes

### Architecture & Patterns

- **Pure refactor** — zero gameplay behavior changes
- `PlayerManager` is a plain Python class (no inheritance), owns the dict internally
- Follows existing manager pattern: `CombatManager`, `TradeManager`, `PartyManager`, `RoomManager`
- `Game.__init__` creates `self.player_manager = PlayerManager()` — same pattern as other managers
- The `_sessions` dict is private (no public accessor) — all access through methods

### Critical Implementation Details

- `all_entity_ids()` MUST return a snapshot `list` (not a view/iterator) — `app.py:119` iterates while calling `_cleanup_player` which removes sessions during the loop
- `remove_session()` returns the removed session (like `dict.pop(key, None)`) — callers may need the value
- `movement.py:209` currently uses direct `[pid]` index (assumes key exists) — replace with `get_session(pid)` + appropriate None guard to be safe
- `auth.py:422` mutates session attribute through index — get session via `get_session()` first, then mutate the returned object directly (it's a reference, not a copy)
- `PlayerSession` construction stays in `auth.py` — no factory method needed on `PlayerManager`

### Files to Create

| File | Purpose |
|------|---------|
| `server/player/manager.py` | `PlayerManager` class |

### Files to Modify (Server — 13 files)

| File | Changes |
|------|---------|
| `server/app.py` | Replace `player_entities` dict with `player_manager = PlayerManager()`, update `shutdown()` and `respawn_player()` |
| `server/net/handlers/auth.py` | `.get()`, `.pop()`, `[id] = session`, `[id].attr` → PlayerManager methods |
| `server/net/handlers/movement.py` | 4 sites: `.get()` and `[id]` → `get_session()` |
| `server/net/handlers/combat.py` | 5 sites: `.get()` → `get_session()` |
| `server/net/handlers/chat.py` | 1 site: `.get()` → `get_session()` |
| `server/net/handlers/interact.py` | 1 site: `.get()` → `get_session()` |
| `server/net/handlers/inventory.py` | 2 sites: `.get()` → `get_session()` |
| `server/net/handlers/query.py` | 5 sites: `.get()` → `get_session()` |
| `server/net/handlers/trade.py` | 6 sites: `.get()` → `get_session()` |
| `server/net/handlers/party.py` | 3 `.get()` + 1 `not in` → `get_session()` / `has_session()` |
| `server/net/handlers/levelup.py` | 1 site: `.get()` → `get_session()` |
| `server/core/xp.py` | 1 site: `.get()` → `get_session()` |
| `server/room/objects/chest.py` | 1 site: `.get()` → `get_session()` |

### Files to Modify (Tests — ~26 files)

Mechanical replacement of `game.player_entities` → `game.player_manager` method calls. Key test files with highest reference counts:

- `tests/test_game.py` — 5+ refs (set, containment, len checks)
- `tests/test_logout.py` — 5+ refs (set, containment, mutation)
- `tests/test_movement.py` — setup via set
- `tests/test_chat.py` — setup via set
- `tests/test_chest.py` — setup via set
- `tests/test_interact.py` — setup via set
- `tests/test_party.py` — setup via set
- `tests/test_trade.py` — mock setup (MagicMock game)
- `tests/test_login.py` — `.clear()` in teardown
- All other test files that reference `player_entities`

### Anti-Patterns to Avoid

- Do NOT add a `player_entities` property that returns the dict — the point is to hide it
- Do NOT create a factory method for PlayerSession on PlayerManager — construction stays at call site
- Do NOT change any assertion values in tests — pure mechanical refactor
- Do NOT change any gameplay behavior — this is purely structural
- Do NOT add logging, metrics, or events to PlayerManager — keep it minimal

### Project Structure Notes

- `server/player/manager.py` follows existing convention: `server/combat/manager.py`, `server/trade/manager.py`, `server/party/manager.py`
- `server/player/__init__.py` already exists — no new package creation needed
- Existing `server/player/session.py` contains `PlayerSession` — `PlayerManager` imports from there

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Story 15.1 (lines 3603-3651)]
- [Source: server/app.py — Game class, player_entities dict (line 46)]
- [Source: server/player/session.py — PlayerSession dataclass]
- [Source: _bmad-output/project-context.md — Player State Dual Storage section]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- All 807 tests pass (0 failures, 0 warnings, ~3.8s)

### Completion Notes List

- Created `PlayerManager` class in `server/player/manager.py` with 7 methods covering all access patterns
- Replaced `game.player_entities` dict with `game.player_manager = PlayerManager()` in `Game.__init__()`
- Updated all 13 server files (40 code references) to use `PlayerManager` methods
- Updated all 26 test files (146 references) — mechanical replacement with zero assertion value changes
- Updated `project-context.md` to reference new `player_manager.get_session()` API
- Updated `session.py` docstring to reference `PlayerManager`
- Pure refactor — zero gameplay behavior changes

### File List

**Created:**
- `server/player/manager.py`

**Modified (Server — 14 files):**
- `server/app.py`
- `server/net/handlers/auth.py`
- `server/net/handlers/movement.py`
- `server/net/handlers/combat.py`
- `server/net/handlers/chat.py`
- `server/net/handlers/interact.py`
- `server/net/handlers/inventory.py`
- `server/net/handlers/query.py`
- `server/net/handlers/trade.py`
- `server/net/handlers/party.py`
- `server/net/handlers/levelup.py`
- `server/core/xp.py`
- `server/room/objects/chest.py`
- `server/player/session.py`

**Modified (Docs):**
- `_bmad-output/project-context.md`

**Modified (Tests — 26 files):**
- `tests/test_blocking_objects.py`
- `tests/test_chat.py`
- `tests/test_chest.py`
- `tests/test_combat_multiplayer.py`
- `tests/test_concurrency.py`
- `tests/test_exploration_xp.py`
- `tests/test_game.py`
- `tests/test_interact.py`
- `tests/test_interaction_xp.py`
- `tests/test_lever.py`
- `tests/test_level_up.py`
- `tests/test_login.py`
- `tests/test_logout.py`
- `tests/test_loot.py`
- `tests/test_map.py`
- `tests/test_movement.py`
- `tests/test_party.py`
- `tests/test_party_chat.py`
- `tests/test_party_combat.py`
- `tests/test_party_commands.py`
- `tests/test_query.py`
- `tests/test_room_transition.py`
- `tests/test_stats_persistence.py`
- `tests/test_trade.py`
- `tests/test_xp.py`
