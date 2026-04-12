# Story 14.4b: Room Accessors & Interact Signature

Status: done

## Story

As a developer,
I want clean public APIs on `RoomInstance` and room objects knowing their own room,
So that no module accesses another module's private attributes, and interactive objects don't scan all rooms to find themselves.

## Acceptance Criteria

1. **Given** `RoomInstance` with private attributes `_entities`, `_npcs`, `_interactive_objects`, **When** public read-only properties `entities`, `npcs`, `interactive_objects` are added, **Then** they return `MappingProxyType` views of the underlying dicts, **And** mutation through these views raises `TypeError`.

2. **Given** handler code in `movement.py`, `interact.py`, and `query.py` that accessed `room._entities`, `room._npcs`, `room._interactive_objects`, **When** the refactor is complete, **Then** all external access uses `room.entities`, `room.npcs`, `room.interactive_objects` (public read-only accessors).

3. **Given** `InteractiveObject` base class and its subclasses (`ChestObject`, `LeverObject`), **When** the refactor is complete, **Then** each object stores `self.room_key` set at creation time (passed via `create_object()` and set by `RoomInstance.__init__`), **And** `_get_room_key()` methods are deleted from `ChestObject` and `LeverObject`, **And** code that called `_get_room_key()` uses `self.room_key` instead.

4. **Given** all existing tests, **When** Story 14.4b is implemented, **Then** all tests pass without assertion value changes (pure refactor).

## Tasks / Subtasks

- [x] Task 1: Add `room_key` field to `InteractiveObject` base class (AC: #3)
  - [x] 1.1: In `server/room/objects/base.py`, add `room_key: str = ""` field to the `RoomObject` dataclass (line 12-21). This makes it available to all subclasses including `InteractiveObject`. Place it after `config`.

- [x] Task 2: Pass `room_key` through `create_object()` (AC: #3)
  - [x] 2.1: In `server/room/objects/registry.py`, modify `create_object()` (line 18) to accept an optional `room_key: str = ""` parameter. Pass `room_key=room_key` to both the `handler_cls(...)` call (line 24) and the `RoomObject(...)` fallback (line 35).
  - [x] 2.2: In `server/room/room.py`, the `_interactive_objects` dict (line 46) currently stores raw dicts. Objects are created via `create_object()` at interact-time in `server/net/handlers/interact.py` (line 93). Instead, create objects at `RoomInstance.__init__` time. Replace the `_interactive_objects` indexing loop (lines 47-49) to:
    1. Import `create_object` from `server.room.objects.registry`
    2. Build `_interactive_objects` as `dict[str, InteractiveObject | RoomObject]` instead of `dict[str, dict]`
    3. For each interactive object dict, call `create_object(obj, room_key=self.room_key)` and store the result
    4. Keep the same key (object id)

    **WAIT** — This changes the type of `_interactive_objects` from `dict[str, dict]` to `dict[str, RoomObject]`. This affects:
    - `get_object()` return type (line 97-99): currently returns `dict | None`, would return `RoomObject | None`
    - Handler code in `movement.py` (line 29-31) and `interact.py` (line 78-79) and `query.py` (line 50-52) iterates `.values()` and accesses `obj["x"]`, `obj["y"]`, `obj["id"]`, `obj["type"]` — these would need to change to `obj.x`, `obj.y`, `obj.id`, `obj.type`
    - `interact.py` (line 93) currently calls `create_object(obj_dict)` on the raw dict — this would no longer be needed since objects are pre-created
    - `get_state()` (line 161-179) returns `self.objects` (the raw list), not `_interactive_objects`, so it's unaffected
    - Test `test_interaction_xp.py` line 69 sets `room._interactive_objects = {"chest_1": chest_dict}` with a raw dict — must update to use an object instance

    This is the right design per ADR-14-13 (room_key stored at creation time), but it changes the type of the dict values. Proceed with this approach.

- [x] Task 3: Update `interact.py` handler to use pre-created objects (AC: #2, #3)
  - [x] 3.1: In `server/net/handlers/interact.py`, at line 78, change `room._interactive_objects.values()` to `room.interactive_objects.values()`. Change `obj["x"]` to `obj.x`, `obj["y"]` to `obj.y` (line 79). Change `obj_dict = obj` to keep consistent naming. Change `target_id = obj_dict["id"]` (line 89) to `target_id = obj_dict.id`.
  - [x] 3.2: In the `target_id` path (lines 46-57), `obj_dict = room.get_object(target_id)` (line 48) now returns a `RoomObject`. Change `obj_dict["x"], obj_dict["y"]` at line 54 to `obj_dict.x, obj_dict.y`.
  - [x] 3.3: At line 99, currently `obj = create_object(obj_dict)` creates a fresh object from the raw dict. Since objects are now pre-created in `RoomInstance.__init__`, use `obj_dict` directly (it IS the pre-created `InteractiveObject`). Replace `obj = create_object(obj_dict)` with `obj = obj_dict` (or rename to avoid confusion). Keep the `isinstance(obj, InteractiveObject)` check at line 100 as a safety guard.
  - [x] 3.4: At lines 120 and 123, `obj_dict.get('type', 'object')` and `obj_dict.get("type")` use dict `.get()` — change to `obj_dict.type` (attribute access on `RoomObject`). Also at line 123, `obj_dict.get("type") == "lever"` becomes `obj_dict.type == "lever"`.
  - [x] 3.5: Remove the `from server.room.objects.registry import create_object` import (line 12) since `create_object` is no longer called in this module. Keep the `import server.room.objects` (line 10) for type registration.

- [x] Task 4: Add `MappingProxyType` read-only properties to `RoomInstance` (AC: #1)
  - [x] 4.1: In `server/room/room.py`, add `from types import MappingProxyType` at the top (after line 2).
  - [x] 4.2: Add three `@property` methods after `get_object()` (after line 99):
    ```python
    @property
    def entities(self) -> MappingProxyType:
        """Read-only view of player entities in the room."""
        return MappingProxyType(self._entities)

    @property
    def npcs(self) -> MappingProxyType:
        """Read-only view of NPCs in the room."""
        return MappingProxyType(self._npcs)

    @property
    def interactive_objects(self) -> MappingProxyType:
        """Read-only view of interactive objects in the room."""
        return MappingProxyType(self._interactive_objects)
    ```

- [x] Task 5: Update handler code to use public accessors (AC: #2)
  - [x] 5.1: In `server/net/handlers/movement.py` line 29: change `room._interactive_objects.values()` to `room.interactive_objects.values()`. Also change `obj["x"]` to `obj.x`, `obj["y"]` to `obj.y` (line 30), `obj["id"]` to `obj.id`, `obj["type"]` to `obj.type` (line 31).
  - [x] 5.2: In `server/net/handlers/query.py` line 50: change `room._interactive_objects.values()` to `room.interactive_objects.values()`. Change `obj["x"]` to `obj.x`, `obj["y"]` to `obj.y`, `obj["id"]` to `obj.id`, `obj["type"]` to `obj.type` (lines 51-52).
  - [x] 5.3: In `server/net/handlers/query.py` line 53: change `room._npcs.values()` to `room.npcs.values()`.
  - [x] 5.4: In `server/net/handlers/query.py` line 56: change `room._entities.values()` to `room.entities.values()`.
  - [x] 5.5: In `server/net/handlers/query.py` line 90: change `room._entities.values()` to `room.entities.values()`.

- [x] Task 6: Delete `_get_room_key()` from `ChestObject` and `LeverObject` (AC: #3)
  - [x] 6.1: In `server/room/objects/chest.py`, delete `_get_room_key()` method (lines 62-67). At line 24, change `room_key = self._get_room_key(game)` to `room_key = self.room_key`.
  - [x] 6.2: In `server/room/objects/lever.py`, delete `_get_room_key()` method (lines 54-59). At line 18, change `room_key = self._get_room_key(game)` to `room_key = self.room_key`.

- [x] Task 7: Update `get_object()` return type (AC: #4)
  - [x] 7.1: In `server/room/room.py`, update `get_object()` (line 97-99) return type from `dict | None` to match the new dict value type. Since `_interactive_objects` now stores `RoomObject | InteractiveObject`, return type becomes `RoomObject | None`. Import `RoomObject` from `server.room.objects.base`.

- [x] Task 8: Update test files that directly access private attributes (AC: #4)
  - [x] 8.1: In `tests/test_game.py` line 225: change `room._entities` to `room.entities`.
  - [x] 8.2: In `tests/test_logout.py` line 74: change `room._entities` to `room.entities`.
  - [ ] 8.3: In `tests/test_interaction_xp.py`:
    - Line 69: `room._interactive_objects = {"chest_1": chest_dict}` — this sets up directional search data. Since `_interactive_objects` now stores `RoomObject` instances, this test only uses this for the directional path. However, all 4 tests in this class use `target_id` path (not directional), so this line is only in `test_first_chest_interact_grants_xp`. It needs to create a proper object instance or can be removed if not exercised by the test (the test uses `target_id`, not `direction`). Check if this line is actually needed — if the test only uses `target_id` path, the line sets up `_interactive_objects` but the `target_id` path uses `room.get_object()` (mocked separately at line 68).
    - Lines 68, 96, 119, 145: `room.get_object.return_value = chest_dict`/`lever_dict` — after refactor, `get_object()` returns `RoomObject`. Update mock return values to `RoomObject` or `InteractiveObject` instances, or keep as-is since `room` is a `MagicMock` and `get_object` is already mocked.
    - Lines 73, 100, 123, 149: All 4 tests patch `create_object` — after refactor, `create_object` is no longer called at interact-time. The mock pattern changes: instead of patching `create_object`, the pre-created object is looked up from `room.interactive_objects.get(target_id)` or the `obj_dict` from `get_object()` IS the object. Update mocks: make `room.get_object.return_value` a mock `InteractiveObject` with the `.interact()` method, so the handler uses it directly. Remove `create_object` patches.
    - Lines 120, 123 in interact handler reference `obj_dict.type` — since tests mock `room.get_object` to return an object, ensure mock has `.type` attribute set.
  - [x] 8.4: In `tests/test_startup_wiring.py` line 246: change `room_instance._npcs` to `room_instance.npcs`.
  - [x] 8.5: In `tests/test_interact.py` line 140: `room.get_object("chest_01")["type"]` uses dict subscript — after refactor, `get_object()` returns `RoomObject`. Change to `room.get_object("chest_01").type`.

- [x] Task 9: Run `make test` and verify all tests pass (AC: #4)

## Dev Notes

### Architecture Compliance
- **ADR-14-3**: Use `MappingProxyType` for zero-copy read-only enforcement. External code iterates views but cannot mutate underlying dicts.
- **ADR-14-13**: `room_key` stored on object at creation time. No `interact()` signature change.
- **Pure refactor**: All existing tests must pass without assertion value changes. Only mock construction patterns and private→public accessor changes allowed in tests.
- **Cross-cutting rule**: Refactoring stories (14.4a, 14.4b, 14.5): all existing tests pass, no assertion changes, no new behavior.

### Key Implementation Details

**`_interactive_objects` type change:**
The dict value type changes from `dict` to `RoomObject | InteractiveObject`. This means all code that accessed `obj["x"]`, `obj["y"]`, `obj["id"]`, `obj["type"]` must change to `obj.x`, `obj.y`, `obj.id`, `obj.type`. The affected locations are:
- `movement.py:29-31` (`_find_nearby_objects`)
- `interact.py:78-80` (`handle_interact` directional search)
- `query.py:50-52` (`handle_look`)

**`create_object()` is currently called at interact-time:**
In `interact.py:99`, `obj = create_object(obj_dict)` creates a fresh object each time. After this refactor, objects are pre-created in `RoomInstance.__init__`, so the handler uses the pre-created object directly. The `create_object` import can be removed from `interact.py`.

**`interact.py` has two lookup paths that both need updating:**
1. `target_id` path (line 48): `obj_dict = room.get_object(target_id)` — `get_object()` now returns `RoomObject`. Lines 54, 89, 120, 123 all use dict access patterns (`obj_dict["x"]`, `obj_dict.get("type")`) that must change to attribute access.
2. Directional path (line 78): iterates `room._interactive_objects.values()` — same dict→attribute access changes needed.

**`RoomInstance.__init__` changes:**
The current indexing loop (lines 47-49) stores raw dicts. Replace with object creation:
```python
from server.room.objects.registry import create_object
# In __init__:
self._interactive_objects: dict[str, RoomObject] = {}
for obj in self.objects:
    if obj.get("id") and obj.get("category") == "interactive":
        self._interactive_objects[obj["id"]] = create_object(obj, room_key=self.room_key)
```

**`lever.py` still writes `room._grid` (line 41):**
This is a write operation on a private attribute. It is OUT OF SCOPE for this story (FR109/FR110 target `_entities`, `_npcs`, `_interactive_objects` accessors and `_get_room_key` elimination). A `_grid` accessor/mutator would be a separate concern.

**`game.room_manager._rooms` access in tests:**
Many tests set `game.room_manager._rooms["key"] = room` for setup. This is out of scope — it's `RoomManager`'s private attribute, not `RoomInstance`'s.

### What NOT to Change
- `interact()` method signature — stays `async def interact(self, player_id: int, game: Game)`
- `RoomInstance.get_state()` — returns `self.objects` (raw list), unaffected
- `room._grid` access (lever.py line 41, tests) — out of scope
- `game.room_manager._rooms` access in tests — out of scope (RoomManager concern)
- Internal `RoomInstance` usage of `self._entities`, `self._npcs`, `self._interactive_objects` — class methods continue to use private attributes internally
- Assertion values in any existing test

### Files to Modify

**Production files (8):**
| File | Changes |
|------|---------|
| `server/room/objects/base.py` | Add `room_key: str = ""` to `RoomObject` dataclass |
| `server/room/objects/registry.py` | Add `room_key` param to `create_object()`, pass to constructors |
| `server/room/room.py` | Import `MappingProxyType`, `create_object`, `RoomObject`; change `_interactive_objects` to store objects; add 3 `@property` accessors; update `get_object()` return type |
| `server/room/objects/chest.py` | Delete `_get_room_key()`, use `self.room_key` |
| `server/room/objects/lever.py` | Delete `_get_room_key()`, use `self.room_key` |
| `server/net/handlers/movement.py` | `room._interactive_objects` → `room.interactive_objects`; dict access → attribute access |
| `server/net/handlers/interact.py` | `room._interactive_objects` → `room.interactive_objects`; use pre-created objects; remove `create_object` import; dict access → attribute access throughout (both `target_id` and directional paths, plus post-interact references at lines 120, 123) |
| `server/net/handlers/query.py` | `room._interactive_objects` → `room.interactive_objects`; `room._npcs` → `room.npcs`; `room._entities` → `room.entities`; dict access → attribute access for interactive objects |

**Test files (5):**
| File | Changes |
|------|---------|
| `tests/test_game.py` line 225 | `room._entities` → `room.entities` |
| `tests/test_logout.py` line 74 | `room._entities` → `room.entities` |
| `tests/test_interaction_xp.py` | `_interactive_objects` setup → object instances; remove `create_object` patches; update `get_object` mock returns to objects with `.type` attribute; 4 tests affected (lines 62-160) |
| `tests/test_interact.py` line 140 | `get_object(...)["type"]` → `.type` (attribute access) |
| `tests/test_startup_wiring.py` line 246 | `room_instance._npcs` → `room_instance.npcs` |

### Previous Story Intelligence (14.3b)
- Additive-only pattern used in 14.3a/14.3b — this story is different: pure refactor, no additive fields
- Test assertion values must NOT change (pure refactor rule)
- All 805 tests pass before this story

### References
- [Source: _bmad-output/planning-artifacts/epics.md#Story 14.4b] — AC and FRs (FR109, FR110)
- [Source: _bmad-output/planning-artifacts/epics.md#ADR-14-3] — MappingProxyType for read-only accessors
- [Source: _bmad-output/planning-artifacts/epics.md#ADR-14-13] — room_key stored on object at creation
- [Source: server/room/room.py:42-49] — current `_entities`, `_npcs`, `_interactive_objects` definitions
- [Source: server/room/room.py:97-99] — `get_object()` currently returns `dict | None`
- [Source: server/room/objects/base.py:12-32] — `RoomObject` and `InteractiveObject` base classes
- [Source: server/room/objects/registry.py:18-43] — `create_object()` factory function
- [Source: server/room/objects/chest.py:62-67] — `ChestObject._get_room_key()`
- [Source: server/room/objects/lever.py:54-59] — `LeverObject._get_room_key()`
- [Source: server/net/handlers/movement.py:29] — `room._interactive_objects` access
- [Source: server/net/handlers/interact.py:48,54,78,89,99,100,120,123] — `get_object()`, `_interactive_objects` access, `create_object()` call, dict access patterns
- [Source: server/net/handlers/query.py:50,53,56,90] — private attribute access
- [Source: _bmad-output/project-context.md] — project rules and patterns

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List
- Added `room_key: str = ""` field to `RoomObject` dataclass in `base.py`
- Added `room_key` parameter to `create_object()` in `registry.py`, passed to both `handler_cls` and `RoomObject` constructors
- Changed `RoomInstance.__init__` to create objects at init time via `create_object(obj, room_key=self.room_key)` instead of storing raw dicts in `_interactive_objects`
- Added 3 `@property` accessors on `RoomInstance` returning `MappingProxyType` views: `entities`, `npcs`, `interactive_objects`
- Updated `get_object()` return type from `dict | None` to `RoomObject | None`
- Removed `create_object` import from `interact.py`; handler now uses pre-created object directly via `isinstance(obj_dict, InteractiveObject)` check
- Changed all dict access patterns (`obj["x"]`, `obj.get("type")`) to attribute access (`obj.x`, `obj.type`) in `interact.py`, `movement.py`, `query.py`
- Deleted `_get_room_key()` from both `ChestObject` and `LeverObject`; replaced with `self.room_key`
- Updated 5 test files: private→public accessor changes (`_entities`→`entities`, `_npcs`→`npcs`), dict→attribute access, removed `create_object` mock patterns in `test_interaction_xp.py`
- All 805 tests pass, zero assertion value changes (pure refactor)

### File List
- server/room/objects/base.py (modified — added `room_key: str = ""` field to `RoomObject`)
- server/room/objects/registry.py (modified — added `room_key` parameter to `create_object()`)
- server/room/room.py (modified — import `MappingProxyType`, `RoomObject`, `create_object`; create objects at init; add 3 property accessors; update `get_object()` return type)
- server/room/objects/chest.py (modified — deleted `_get_room_key()`, use `self.room_key`)
- server/room/objects/lever.py (modified — deleted `_get_room_key()`, use `self.room_key`)
- server/net/handlers/movement.py (modified — `room._interactive_objects` → `room.interactive_objects`, dict→attribute access)
- server/net/handlers/interact.py (modified — removed `create_object` import; use pre-created objects; dict→attribute access throughout)
- server/net/handlers/query.py (modified — `room._interactive_objects`/`_npcs`/`_entities` → public accessors; dict→attribute access)
- tests/test_game.py (modified — `room._entities` → `room.entities`)
- tests/test_logout.py (modified — `room._entities` → `room.entities`)
- tests/test_interaction_xp.py (modified — rewrote mock pattern: `AsyncMock(spec=InteractiveObject)` replaces `create_object` patches)
- tests/test_interact.py (modified — `get_object(...)["type"]` → `.type`)
- tests/test_startup_wiring.py (modified — `room_instance._npcs` → `room_instance.npcs`)
