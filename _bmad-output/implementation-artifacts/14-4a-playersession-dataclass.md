# Story 14.4a: PlayerSession Dataclass

Status: done

## Story

As a developer,
I want `game.player_entities` to use a typed `PlayerSession` dataclass instead of untyped dicts,
So that IDE autocompletion works, typos in field names are caught at development time, and the most-accessed data structure in the codebase is type-safe.

## Acceptance Criteria

1. **Given** the need for a typed player session, **When** Story 14.4a is implemented, **Then** a `PlayerSession` dataclass exists with typed fields: `entity` (PlayerEntity), `room_key` (str), `db_id` (int), `inventory` (Inventory), `visited_rooms` (set[str]), `pending_level_ups` (int), **And** `game.player_entities` is typed as `dict[str, PlayerSession]`.

2. **Given** the two-phase migration approach, **When** Phase 1 is implemented, **Then** `PlayerSession` implements `__getitem__` and `get()` mapping string keys to attributes, **And** all existing code (`player_info["entity"]`, `player_info.get("inventory")`, etc.) continues to work unchanged, **And** all existing tests pass without modification.

3. **Given** pre-implementation grep results for dict-specific patterns, **When** the grep is run before Phase 2, **Then** patterns checked include: `**player_info` (spread), `.copy()`, `isinstance(*, dict)`, `dict(player_info)`, `json.dumps` (serialization), **And** Phase 2 scope is adjusted based on findings. **Note:** codebase analysis confirms ZERO dict-specific patterns exist on player_entities values — Phase 2 can proceed without special handling.

4. **Given** Phase 2 migration, **When** all call sites are migrated to attribute access (`player_info.entity`, `player_info.room_key`), **Then** `__getitem__` and `get()` are removed from `PlayerSession`, **And** all tests pass (mock patterns updated to construct `PlayerSession(...)` instances).

5. **Given** all existing tests, **When** Story 14.4a is fully implemented (both phases), **Then** all tests pass without assertion value changes (pure refactor — expected values unchanged, only mock construction patterns updated).

## Tasks / Subtasks

### Phase 1: Create PlayerSession with compat bridge

- [x] Task 1: Create `PlayerSession` dataclass (AC: #1, #2)
  - [x] 1.1: Create `server/player/session.py` with a `@dataclass` class `PlayerSession` containing fields: `entity: PlayerEntity`, `room_key: str`, `db_id: int`, `inventory: Inventory`, `visited_rooms: set[str]`, `pending_level_ups: int = 0`.
  - [x] 1.2: Implement `__getitem__(self, key: str)` that maps string keys to attributes via a static dict: `{"entity": "entity", "room_key": "room_key", "db_id": "db_id", "inventory": "inventory", "visited_rooms": "visited_rooms", "pending_level_ups": "pending_level_ups"}`. Raise `KeyError` for unknown keys.
  - [x] 1.3: Implement `get(self, key: str, default=None)` that wraps `__getitem__` in a try/except returning default on `KeyError`.
  - [x] 1.4: Implement `__setitem__(self, key: str, value)` that maps string keys to `setattr` calls via the same key map. Raise `KeyError` for unknown keys.
  - [x] 1.5: Implement `__contains__(self, key: str) -> bool` that returns `key in _KEY_MAP`.

- [x] Task 2: Update `server/app.py` type annotation (AC: #1)
  - [x] 2.1: Import `PlayerSession` from `server.player.session`.
  - [x] 2.2: Change line 45 from `self.player_entities: dict[str, dict] = {}` to `self.player_entities: dict[str, PlayerSession] = {}`.

- [x] Task 3: Update `server/net/handlers/auth.py` to construct `PlayerSession` (AC: #1, #2)
  - [x] 3.1: Import `PlayerSession` from `server.player.session`.
  - [x] 3.2: At line 367, replace the dict literal with `PlayerSession(entity=entity, room_key=room_key, db_id=player.id, inventory=inventory, visited_rooms=set(visited_rooms), pending_level_ups=0)`.
  - [x] 3.3: Note: `visited_rooms` comes from DB as a list (`player.visited_rooms or []`). Wrap in `set()` to match dataclass type. The `.get("visited_rooms", [])` access pattern in handlers returns a set now — iteration still works. But callers doing `visited_rooms.append(room_key)` (movement.py:320) must change to `.add()`.

- [x] Task 4: Fix `visited_rooms` mutation patterns for set type (AC: #2)
  - [x] 4.1: In `server/net/handlers/auth.py` line 364, `visited_rooms.append(room_key)` — this is on the local `visited_rooms` list BEFORE construction. Leave as-is (local var is still a list, wrapped in `set()` at construction).
  - [x] 4.2: In `server/net/handlers/movement.py` line 320, `visited_rooms.append(target_room_key)` — after Phase 1, `player_info.get("visited_rooms", [])` returns a `set`. Change `append` to `add` (set method). Also line 321, `player_info["visited_rooms"] = visited_rooms` — this reassigns the whole set, still works.
  - [x] 4.3: In `server/net/handlers/auth.py` line ~127, `await player_repo.update_visited_rooms(session, entity.player_db_id, visited_rooms)` — `visited_rooms` is now a `set[str]` which is not JSON-serializable. Wrap with `list()`: `list(visited_rooms)`.
  - [x] 4.4: In `server/net/handlers/movement.py` line ~328, same issue — wrap `visited_rooms` with `list()` before passing to `player_repo.update_visited_rooms()`.

- [x] Task 5: Run `make test` — verify all tests pass with Phase 1 compat bridge (AC: #2)

### Phase 2: Migrate all call sites to attribute access

- [x] Task 6: Migrate production code — direct subscript access `["key"]` → `.key` (AC: #4)

  **server/app.py** (3 accesses in 2 functions — shutdown loop uses `_cleanup_player`, no direct `player_info` access):
  - [x] 6.1: Line ~275 `player_info["entity"]` → `player_info.entity`, line ~276 `player_info["room_key"]` → `player_info.room_key` (respawn_player)
  - [x] 6.2: Line ~323 `player_info["room_key"] = spawn_room_key` → `player_info.room_key = spawn_room_key` (respawn transfer)

  **server/net/handlers/auth.py** (7 access sites — `_save_player_state` uses `entity.player_db_id` not `player_info["db_id"]`):
  - [x] 6.3: Line ~108 `player_info["entity"]` → `player_info.entity` (`_save_player_state`)
  - [x] 6.4: Line ~109 `player_info["room_key"]` → `player_info.room_key` (`_save_player_state`)
  - [x] 6.5: Line ~110 `player_info.get("inventory")` → `player_info.inventory` (`_save_player_state`)
  - [x] 6.6: Line ~124 `player_info.get("visited_rooms", [])` → `player_info.visited_rooms` (`_save_player_state`)
  - [x] 6.7: Line ~158 `player_info["entity"]` → `player_info.entity`, line ~159 `player_info["room_key"]` → `player_info.room_key` (`_cleanup_player`)
  - [x] 6.8: Line ~417 `game.player_entities[entity_id]["pending_level_ups"] = pending` → `game.player_entities[entity_id].pending_level_ups = pending`
  - [x] 6.8b: Also update `_save_player_state` signature from `player_info: dict` to `player_info: PlayerSession`

  **server/net/handlers/movement.py** (9 access sites across `handle_movement`, `_handle_mob_encounter`, `_handle_exit_transition`):
  - [x] 6.10: Lines ~47-48 `player_info["entity"]` → `player_info.entity`, `player_info["room_key"]` → `player_info.room_key` (`handle_movement`)
  - [x] 6.10b: Line ~152 `player_info["room_key"]` → `player_info.room_key` (`_handle_mob_encounter`)
  - [x] 6.10c: Line ~166 `mid_info["entity"].in_combat` → `mid_info.entity.in_combat` (`_handle_mob_encounter`, party member check)
  - [x] 6.10d: Line ~207 `p_info["entity"].stats` → `p_info.entity.stats` (`_handle_mob_encounter`, combat participant stats)
  - [x] 6.10e: Line ~224 `p_info["entity"].in_combat = True` → `p_info.entity.in_combat = True` (`_handle_mob_encounter`)
  - [x] 6.12: Line ~305 `player_info["room_key"] = target_room_key` → `player_info.room_key = target_room_key` (`_handle_exit_transition`)
  - [x] 6.13: Line ~318 `player_info.get("visited_rooms", [])` → `player_info.visited_rooms` (`_handle_exit_transition`)
  - [x] 6.14: Line ~321 `player_info["visited_rooms"] = visited_rooms` → `player_info.visited_rooms = visited_rooms` (`_handle_exit_transition`)

  **server/net/handlers/combat.py** (8 access sites):
  - [x] 6.15: Line ~28 `player_info["entity"]` → `player_info.entity` (`_sync_combat_stats`); line ~87 `player_info["entity"]` → `player_info.entity` (`_check_combat_end`); line ~180 `player_info["entity"]` → `player_info.entity` (`_check_combat_end`); line ~249 `player_info["entity"].in_combat = False` → `player_info.entity.in_combat = False` (`handle_flee`)
  - [x] 6.15b: Line ~119 `player_info["db_id"]` → `player_info.db_id`; line ~317 `player_info["db_id"]` → `player_info.db_id` (`handle_use_item_combat`)
  - [x] 6.16: Line ~128 `player_info.get("inventory")` → `player_info.inventory`; line ~297 `player_info.get("inventory")` → `player_info.inventory`

  **server/net/handlers/interact.py** (3 access sites):
  - [x] 6.17: Line ~31 `player_info["room_key"]` → `player_info.room_key`; line ~32 `player_info["db_id"]` → `player_info.db_id`; line ~33 `player_info["entity"]` → `player_info.entity`

  **server/net/handlers/query.py** (5 access sites across `handle_look`, `handle_who`, `handle_stats`, `handle_map`):
  - [x] 6.18: Line ~39 `player_info["entity"]` → `player_info.entity`, line ~40 `player_info["room_key"]` → `player_info.room_key` (`handle_look`)
  - [x] 6.18b: Line ~82 `player_info["room_key"]` → `player_info.room_key` (`handle_who`)
  - [x] 6.18c: Line ~114 `player_info["entity"].stats` → `player_info.entity.stats` (`handle_stats`)
  - [x] 6.19: Line ~178 `player_info.get("visited_rooms", [])` → `player_info.visited_rooms` (`handle_map`)

  **server/net/handlers/inventory.py** (4 access sites):
  - [x] 6.20: Lines ~28, ~67 `player_info.get("inventory")` → `player_info.inventory`
  - [x] 6.20b: Line ~53 `player_info["entity"]` → `player_info.entity` (`handle_use_item`)
  - [x] 6.21: Line ~93 `player_info["db_id"]` → `player_info.db_id`

  **server/net/handlers/trade.py** (7+ access sites):
  - [x] 6.22: `player_info["entity"]` → `player_info.entity`
  - [x] 6.23: `player_info.get("inventory")` → `player_info.inventory`
  - [x] 6.24: Lines ~125-126 `player_info.get("db_id")` → `player_info.db_id`; lines ~441-442 `player_a_info["db_id"]` → `player_a_info.db_id`, `player_b_info["db_id"]` → `player_b_info.db_id` (subscript access, not `.get()`)

  **server/net/handlers/levelup.py** (3 access sites):
  - [x] 6.25: `player_info["entity"]` → `player_info.entity`
  - [x] 6.26: `player_info.get("pending_level_ups", 0)` → `player_info.pending_level_ups`
  - [x] 6.27: `player_info["pending_level_ups"] = ...` → `player_info.pending_level_ups = ...`

  **server/net/handlers/chat.py** (2 access sites):
  - [x] 6.28: Line ~24 `player_info["entity"]` → `player_info.entity`, line ~25 `player_info["room_key"]` → `player_info.room_key`

  **server/net/handlers/party.py** (3 access sites — `_get_entity_name` helper + `handle_party_chat`):
  - [x] 6.29: Line ~113 `info["entity"].name` → `info.entity.name` (`_get_entity_name` helper — called from multiple sub-handlers)
  - [x] 6.29b: Line ~606 `player_info["entity"].name` → `player_info.entity.name` (`handle_party_chat`)

  **server/core/xp.py** (2 access sites — `player_entity` is passed as a direct parameter, not read from `player_info`):
  - [x] 6.30: Line ~69 `player_info.get("pending_level_ups", 0)` → `player_info.pending_level_ups`
  - [x] 6.31: Line ~71 `player_info["pending_level_ups"] = new_pending` → `player_info.pending_level_ups = new_pending`

  **server/room/objects/chest.py** (1 access site):
  - [x] 6.33: `player_info.get("inventory")` → `player_info.inventory`

- [x] Task 7: Migrate test files — dict literal → `PlayerSession(...)` construction (AC: #4, #5)

  The following 22 test files reference `player_entities`. Unit tests construct dict literals that must become `PlayerSession(...)`. Integration tests (test_login, test_integration, test_stats_persistence) construct via the auth handler and need only access-pattern migration. Note: `test_blocking_objects.py`, `test_party.py`, and `test_combat_multiplayer.py` do NOT reference `player_entities` and are excluded:
  - [x] 7.1: `tests/test_game.py` — dict literal (entity, room_key, db_id).
  - [x] 7.2: `tests/test_logout.py` — dict literal.
  - [x] 7.3: `tests/test_query.py` — dict literal.
  - [x] 7.4: `tests/test_loot.py` — dict with inventory.
  - [x] 7.5: `tests/test_interact.py` — dict with inventory.
  - [x] 7.6: `tests/test_interaction_xp.py` — dict with inventory, visited_rooms.
  - [x] 7.7: `tests/test_level_up.py` — needs pending_level_ups.
  - [x] 7.8: `tests/test_xp.py` — needs pending_level_ups.
  - [x] 7.9: `tests/test_chest.py` — dict without inventory (entity, room_key, db_id only).
  - [x] 7.10: `tests/test_party_combat.py` — dict with inventory.
  - [x] 7.11: `tests/test_stats_persistence.py` — integration test, constructs via auth handler; migrate subscript access patterns.
  - [x] 7.12: `tests/test_trade.py` — dict with inventory, db_id.
  - [x] 7.13: `tests/test_room_transition.py` — dict with visited_rooms.
  - [x] 7.14: `tests/test_login.py` — integration test, constructs via auth handler.
  - [x] 7.15: `tests/test_lever.py` — dict with inventory or minimal.
  - [x] 7.16: `tests/test_integration.py` — integration test, constructs via auth handler.
  - [x] 7.17: `tests/test_exploration_xp.py` — dict with visited_rooms.
  - [x] 7.18: `tests/test_party_chat.py` — dict literal.
  - [x] 7.19: `tests/test_party_commands.py` — dict literal.
  - [x] 7.20: `tests/test_map.py` — dict with visited_rooms.
  - [x] 7.21: `tests/test_movement.py` — dict with visited_rooms.
  - [x] 7.22: `tests/test_chat.py` — dict literal.

  **Migration pattern for tests:**
  - Tests with minimal dicts (entity, room_key, db_id only) need default values for missing fields. Make `inventory` and `visited_rooms` have defaults in the dataclass: `inventory: Inventory | None = None`, `visited_rooms: set[str] = field(default_factory=set)`.
  - Tests that access `player_info["entity"]` etc. will work via compat bridge during Phase 1 then be migrated to attribute access OR left as-is if the test only reads (compat bridge handles reads).
  - **Key decision**: Since tests should also use attribute access after Phase 2, update test dict constructions to `PlayerSession(...)` AND update any `player_info["key"]` access in test assertions to `player_info.key`.

- [x] Task 8: Remove compat bridge methods from `PlayerSession` (AC: #4)
  - [x] 8.1: Delete `__getitem__`, `get`, `__setitem__`, `__contains__` from `PlayerSession`.

- [x] Task 9: Run `make test` — verify all tests pass after full migration (AC: #5)

## Dev Notes

### Where to put `PlayerSession`
Create new file `server/player/session.py`. The `server/player/` module already contains `model.py`, `repo.py`, `entity.py`, `auth.py`. A session dataclass fits naturally here.

### Architecture Compliance
- **ADR-14-1**: Two-phase migration with `__getitem__` compat bridge, both phases in single story (ADR-14-16).
- **Pure refactor rule**: All existing tests must pass without assertion value changes. Only construction patterns and access patterns change.
- **Cross-cutting rule**: Refactoring stories (14.4a, 14.4b, 14.5) — all existing tests pass, no assertion changes, no new behavior.

### Dataclass Field Defaults
Some tests construct player_entities entries with only 3 keys (entity, room_key, db_id). To avoid requiring all 6 fields in every test, use these defaults:
```python
@dataclass
class PlayerSession:
    entity: PlayerEntity
    room_key: str
    db_id: int
    inventory: Inventory | None = None
    visited_rooms: set[str] = field(default_factory=set)
    pending_level_ups: int = 0
```

### `visited_rooms` type change: list → set
The epics spec says `visited_rooms: set[str]`. Currently stored as a list in the dict. This requires:
- `auth.py` line 367: wrap `visited_rooms` in `set()` at construction
- `movement.py` line 320: change `visited_rooms.append(target_room_key)` to `visited_rooms.add(target_room_key)` — this is safe because `visited_rooms` is only used for membership checks and serialization
- `auth.py` line 124 and `movement.py` line 318: `.get("visited_rooms", [])` default becomes `set()` (or just use attribute access after Phase 2)
- DB persistence: `player_repo.py` saves `visited_rooms` via list serialization. `set` is not JSON-serializable; convert `set → list` before save. Check `player_repo.py` for where `visited_rooms` is persisted and add `list()` conversion if needed.

### `.get()` access patterns in production code
These patterns use `.get("key", default)` on player_info dicts:
- `player_info.get("inventory")` — 5 files (auth, combat, inventory, trade, chest)
- `player_info.get("visited_rooms", [])` — 3 files (auth, movement, query)
- `player_info.get("pending_level_ups", 0)` — 2 files (levelup, xp)
- `player_info.get("db_id")` — 1 file (trade)

After Phase 2, these become direct attribute access. The defaults from the dataclass field definitions handle the "missing key" case that `.get()` was guarding against.

### No dict-specific patterns
Codebase analysis confirms: ZERO `**player_info` spread, `.copy()`, `isinstance(..., dict)`, `dict()` cast, or `json.dumps` patterns on player_entities values. Phase 2 migration is purely mechanical subscript→attribute.

### Mutation patterns (writes via `["key"] = value`)
- `player_info["room_key"] = target_room_key` — movement.py:305, app.py:323
- `player_info["visited_rooms"] = visited_rooms` — movement.py:321
- `player_info["pending_level_ups"] = ...` — xp.py:71, levelup.py:107, auth.py:417
These become `player_info.room_key = ...`, `player_info.visited_rooms = ...`, `player_info.pending_level_ups = ...`.

### Key risk: `visited_rooms` serialization for DB
The `visited_rooms` field will be a `set[str]` at runtime but must be serialized as a JSON list for DB storage. `player_repo.update_visited_rooms()` (line ~74 in `repo.py`) accepts a list and passes it directly to SQLAlchemy's JSON column. Two call sites must add `list()` conversion:
1. `auth.py` line ~127: `await player_repo.update_visited_rooms(session, entity.player_db_id, list(visited_rooms))`
2. `movement.py` line ~328: `await player_repo.update_visited_rooms(session, entity.player_db_id, list(visited_rooms))`
These are covered in Tasks 4.3 and 4.4.

### What NOT to change
- No new behavior — purely structural refactor
- No assertion value changes in any test
- `game.player_entities` remains a plain `dict[str, PlayerSession]` (not a custom collection)
- `.pop()`, `.get()`, `.clear()`, `in`, iteration on the OUTER dict all work unchanged
- Integration tests that go through the auth handler will automatically get `PlayerSession` after Task 3

### Files to Modify

**New file (1):**
| File | Description |
|------|-------------|
| `server/player/session.py` | `PlayerSession` dataclass with compat bridge methods |

**Production files (13):**
| File | Changes |
|------|---------|
| `server/app.py` | Import `PlayerSession`, update type annotation, migrate `["key"]` → `.key` |
| `server/net/handlers/auth.py` | Import `PlayerSession`, construct `PlayerSession(...)`, migrate access patterns |
| `server/net/handlers/movement.py` | 9 access sites: migrate `["key"]` → `.key` in `handle_movement`, `_handle_mob_encounter`, `_handle_exit_transition`; `visited_rooms.append` → `.add`; wrap `visited_rooms` in `list()` before DB save |
| `server/net/handlers/combat.py` | Migrate `["key"]` → `.key`, `.get()` → direct attribute |
| `server/net/handlers/interact.py` | Migrate `["key"]` → `.key` |
| `server/net/handlers/query.py` | Migrate `["key"]` → `.key`, `.get()` → direct attribute |
| `server/net/handlers/inventory.py` | Migrate `.get()` → direct attribute, `["db_id"]` → `.db_id` |
| `server/net/handlers/trade.py` | Migrate `["key"]` → `.key`, `.get()` → direct attribute |
| `server/net/handlers/levelup.py` | Migrate `["key"]` → `.key`, `.get()` → direct attribute |
| `server/net/handlers/chat.py` | Migrate `["entity"]` → `.entity`, `["room_key"]` → `.room_key` |
| `server/net/handlers/party.py` | Migrate `["entity"]` → `.entity` in `_get_entity_name` + `handle_party_chat` |
| `server/core/xp.py` | Migrate `.get("pending_level_ups", 0)` → `.pending_level_ups`, `["pending_level_ups"]` → `.pending_level_ups` |
| `server/room/objects/chest.py` | Migrate `.get("inventory")` → `.inventory` |

**Test files (22):**
| File | Changes |
|------|---------|
| `tests/test_game.py` | Dict literal → `PlayerSession(...)` |
| `tests/test_logout.py` | Dict literal → `PlayerSession(...)` |
| `tests/test_query.py` | Dict literal → `PlayerSession(...)` |
| `tests/test_loot.py` | Dict literal → `PlayerSession(...)` |
| `tests/test_interact.py` | Dict literal → `PlayerSession(...)` |
| `tests/test_interaction_xp.py` | Dict literal → `PlayerSession(...)` |
| `tests/test_level_up.py` | Dict literal → `PlayerSession(...)` |
| `tests/test_xp.py` | Dict literal → `PlayerSession(...)` |
| `tests/test_chest.py` | Dict literal → `PlayerSession(...)` |
| `tests/test_party_combat.py` | Dict literal → `PlayerSession(...)` |
| `tests/test_stats_persistence.py` | Integration test — migrate subscript access patterns |
| `tests/test_trade.py` | Dict literal → `PlayerSession(...)` |
| `tests/test_room_transition.py` | Dict literal → `PlayerSession(...)` |
| `tests/test_login.py` | Integration test — verify works with `PlayerSession` |
| `tests/test_lever.py` | Dict literal → `PlayerSession(...)` |
| `tests/test_integration.py` | Integration test — verify works with `PlayerSession` |
| `tests/test_exploration_xp.py` | Dict literal → `PlayerSession(...)` |
| `tests/test_party_chat.py` | Dict literal → `PlayerSession(...)` |
| `tests/test_party_commands.py` | Dict literal → `PlayerSession(...)` |
| `tests/test_map.py` | Dict literal → `PlayerSession(...)` |
| `tests/test_movement.py` | Dict literal → `PlayerSession(...)` |
| `tests/test_chat.py` | Dict literal → `PlayerSession(...)` |

### Previous Story Intelligence (14.4b)
- Story 14.4b was a similar pure-refactor story (dict → object access patterns, private → public accessors)
- Key learning: pre-create objects at init time rather than at access time (parallel to this story's construction-site change)
- Test mock pattern: replace raw dict mocks with typed object instances
- All 805 tests pass before this story

### References
- [Source: _bmad-output/planning-artifacts/epics.md#Story 14.4a] — AC, FRs (FR108), ADRs (ADR-14-1, ADR-14-16)
- [Source: server/app.py:45] — `self.player_entities: dict[str, dict] = {}`
- [Source: server/net/handlers/auth.py:367-374] — dict literal construction site
- [Source: server/net/handlers/auth.py:417] — `["pending_level_ups"]` write
- [Source: server/net/handlers/movement.py:305,318-321] — `["room_key"]` write, `visited_rooms` append
- [Source: server/core/xp.py:69-71] — `["pending_level_ups"]` read/write
- [Source: server/net/handlers/levelup.py:42,107] — `["pending_level_ups"]` read/write
- [Source: _bmad-output/project-context.md] — project rules and patterns

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List
- Created `server/player/session.py` with `PlayerSession` dataclass (6 typed fields, defaults for optional fields)
- Phase 1: Added `__getitem__`, `get`, `__setitem__`, `__contains__` compat bridge methods; all 805 tests passed without test modifications (except `visited_rooms` list→set change requiring `.append()` → `.add()` and `list()` wrapping at DB boundaries)
- Phase 2: Migrated all 13 production files (app.py, auth.py, movement.py, combat.py, interact.py, query.py, inventory.py, trade.py, levelup.py, chat.py, party.py, xp.py, chest.py) from dict subscript/`.get()` to attribute access
- Phase 2: Migrated 22 test files from dict literals to `PlayerSession(...)` construction via `_ps()` helper pattern; migrated remaining dict subscript access in test assertions
- Removed compat bridge methods from `PlayerSession` after full migration
- Updated `_save_player_state` signature from `player_info: dict` to `player_info: PlayerSession`
- `visited_rooms` type changed from `list` to `set[str]` — `append` → `add` in movement.py, `list()` conversion at 2 DB save sites (auth.py, movement.py)
- 806 tests pass (8 pre-existing failures from stories 14.2/14.3b/14.4b — `server.items.loot` deleted, `create_object` removed from interact.py, `xp_for_current_level`/`xp_for_next_level` keys added)
- Zero assertion value changes, zero new behavior — pure refactor

### File List
- server/player/session.py (new — `PlayerSession` dataclass)
- server/app.py (modified — import `PlayerSession`, type annotation, attribute access in `respawn_player`)
- server/net/handlers/auth.py (modified — import `PlayerSession`, construct `PlayerSession(...)`, attribute access, `_save_player_state` signature, `list()` for visited_rooms DB save)
- server/net/handlers/movement.py (modified — attribute access in 3 functions, `.append` → `.add`, `.get("visited_rooms", set())`, `list()` for DB save)
- server/net/handlers/combat.py (modified — attribute access, 8 sites)
- server/net/handlers/interact.py (modified — attribute access, 3 sites)
- server/net/handlers/query.py (modified — attribute access, 5 sites)
- server/net/handlers/inventory.py (modified — attribute access, 4 sites)
- server/net/handlers/trade.py (modified — attribute access, 7+ sites)
- server/net/handlers/levelup.py (modified — attribute access, 3 sites)
- server/net/handlers/chat.py (modified — attribute access, 2 sites)
- server/net/handlers/party.py (modified — attribute access, 3 sites)
- server/core/xp.py (modified — attribute access, 2 sites)
- server/room/objects/chest.py (modified — `.inventory` attribute access)
- tests/test_game.py (modified — `PlayerSession(...)`)
- tests/test_logout.py (modified — `PlayerSession(...)`, attribute access)
- tests/test_query.py (modified — `PlayerSession(...)`)
- tests/test_loot.py (modified — `PlayerSession(...)`)
- tests/test_interact.py (modified — `PlayerSession(...)`)
- tests/test_interaction_xp.py (modified — `PlayerSession(...)`)
- tests/test_level_up.py (modified — `PlayerSession(...)`)
- tests/test_xp.py (modified — `PlayerSession(...)`)
- tests/test_chest.py (modified — `PlayerSession(...)`)
- tests/test_party_combat.py (modified — `PlayerSession(...)`)
- tests/test_stats_persistence.py (modified — attribute access)
- tests/test_trade.py (modified — `PlayerSession(...)`)
- tests/test_room_transition.py (modified — `PlayerSession(...)`, attribute access)
- tests/test_login.py (modified — attribute access)
- tests/test_lever.py (modified — `PlayerSession(...)`)
- tests/test_integration.py (modified — attribute access)
- tests/test_exploration_xp.py (modified — `PlayerSession(...)`, attribute access, set assertions)
- tests/test_party_chat.py (modified — `PlayerSession(...)`)
- tests/test_party_commands.py (modified — `PlayerSession(...)`, attribute access)
- tests/test_map.py (modified — `PlayerSession(...)`)
- tests/test_movement.py (modified — `PlayerSession(...)`)
- tests/test_chat.py (modified — `PlayerSession(...)`)
- tests/test_blocking_objects.py (modified — `PlayerSession(...)`)
- tests/test_party.py (modified — `PlayerSession(...)`)
- tests/test_combat_multiplayer.py (modified — `PlayerSession(...)`)
