# ISS-032: Movement Handler Duplicates Spawn Point Resolution Logic

**Severity:** Low
**Status:** Done
**Found during:** Codebase Architecture Review (2026-04-12)

## Problem

The exit transition handler `_handle_exit_transition()` in `server/net/handlers/movement.py:214-222` contains spawn-point resolution logic that duplicates `find_spawn_point()` in `server/player/service.py:61-74`.

**Movement handler (lines 214-222):**
```python
if entry_x is None or entry_y is None or not target_room.is_walkable(entry_x, entry_y):
    entry_x, entry_y = target_room.get_player_spawn()
if not target_room.is_walkable(entry_x, entry_y):
    entry_x, entry_y = target_room.find_first_walkable()
if not target_room.is_walkable(entry_x, entry_y):
    logger.warning(
        "Room %s has no walkable tile; placing %s at (%d, %d)",
        target_room_key, entity.name, entry_x, entry_y,
    )
```

**player/service.py `find_spawn_point()` (lines 61-74):**
```python
def find_spawn_point(room, room_key: str, entity_name: str) -> tuple[int, int]:
    sx, sy = room.get_player_spawn()
    if not room.is_walkable(sx, sy):
        sx, sy = room.find_first_walkable()
    if not room.is_walkable(sx, sy):
        logger.warning(
            "Room %s has no walkable tile; placing %s at (%d, %d)",
            room_key, entity_name, sx, sy,
        )
    return sx, sy
```

Steps 2 and 3 (spawn point fallback → first walkable → warning) are identical. The movement handler adds a step 1 (try exit-defined `entry_x/entry_y` first) that `find_spawn_point` doesn't have.

## History

Story 17.7 consolidated the spawn-point logic from `Game._find_spawn_point()` (app.py) and `_resolve_room_and_place()` (auth.py) into the shared `find_spawn_point()` function. The movement handler's duplicate was missed during that consolidation because it has the extra entry-coordinate step.

## Affected Files

| File | Change |
|------|--------|
| `server/net/handlers/movement.py:211-222` | Replace inline spawn logic with call to `find_spawn_point()` |

## Proposed Fix

In `_handle_exit_transition()`, replace lines 211-222:

```python
# Determine entry position in target room (validate walkability)
entry_x = exit_info.get("entry_x")
entry_y = exit_info.get("entry_y")
if entry_x is None or entry_y is None or not target_room.is_walkable(entry_x, entry_y):
    entry_x, entry_y = target_room.get_player_spawn()
if not target_room.is_walkable(entry_x, entry_y):
    entry_x, entry_y = target_room.find_first_walkable()
if not target_room.is_walkable(entry_x, entry_y):
    logger.warning(
        "Room %s has no walkable tile; placing %s at (%d, %d)",
        target_room_key, entity.name, entry_x, entry_y,
    )
```

with:

```python
# Determine entry position in target room (validate walkability)
entry_x = exit_info.get("entry_x")
entry_y = exit_info.get("entry_y")
if entry_x is None or entry_y is None or not target_room.is_walkable(entry_x, entry_y):
    entry_x, entry_y = find_spawn_point(target_room, target_room_key, entity.name)
```

Add import at top of file:
```python
from server.player.service import find_spawn_point
```

This preserves the exit-coordinate-first behavior (step 1) while delegating the fallback chain to the shared function.

## Impact

- 1 file changed (`movement.py`) — net reduction of ~6 lines
- Add 1 import
- No behavioral change — same fallback logic, same log message
- No test changes needed — `test_exit_uses_spawn_when_no_entry_coords` in `tests/test_room_transition.py` already exercises the fallback path (exit without `entry_x`/`entry_y`) and serves as an implicit regression test, since `find_spawn_point()` produces identical behavior
- Eliminates the last known duplicate of the spawn-point resolution pattern
