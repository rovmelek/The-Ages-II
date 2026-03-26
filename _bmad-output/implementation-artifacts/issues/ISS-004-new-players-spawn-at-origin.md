# Issue: New players spawn at (0,0) instead of room's designated spawn point

**ID:** ISS-004
**Severity:** High
**Status:** Fixed
**Delivery:** Epic 1 (Player Login and Room Entry)
**Test:** Manual — register new account, observe spawn coordinates
**Created:** 2026-03-25
**Assigned:** BMad Developer

## Description

New player accounts have `position_x=0, position_y=0` as the database default. When logging in, the server used these coordinates directly without checking if they represent a valid spawn point. In rooms like `town_square` (spawn point at 50,50), new players appeared at the top-left corner (0,0) instead of the designated player spawn location.

## Expected

New players should appear at the room's defined `player` spawn point (e.g., (50,50) for town_square). The DB default of (0,0) is a storage placeholder, not a valid gameplay position.

## Actual

New players spawned at (0,0), which could be:
- A wall tile (stuck/unable to move)
- Far from the intended starting area
- Disorienting with nothing visible in the viewport

## Impact

**Significant UX issue.** New players could spawn stuck in walls or in empty corners of large rooms, creating a confusing first experience. In `town_square`, spawning at (0,0) puts the player 70+ tiles away from the center where objects and exits are located.

## Design Reference

- Epic 1 Story 1.7: Player Login and Room Entry
- Auth handler: `server/net/handlers/auth.py`
- Room spawn points: defined in `data/rooms/*.json` under `spawn_points[type=player]`

## Steps to Reproduce

1. Register a new account
2. Login for the first time
3. Observe player position in `room_state` is (0,0)
4. In `town_square`, this places the player at the top-left corner, far from spawn point (50,50)

## Screenshot/Video

N/A — verified via WebSocket JSON responses.

## Fix Applied

Added spawn position override in `server/net/handlers/auth.py` after entity creation:

```python
# Override position for new players spawning at DB default (0,0)
if entity.x == 0 and entity.y == 0:
    sx, sy = room.get_player_spawn()
    if sx != 0 or sy != 0:
        entity.x = sx
        entity.y = sy
    else:
        # Fallback to room center if no spawn point
        entity.x = room.width // 2
        entity.y = room.height // 2
```

## Verification

New player login now places entity at room's designated spawn point (50,50 for town_square).

## Related Issues

- ISS-003 (default room fix is a prerequisite — must spawn in correct room before position matters)

---

**Priority for fix:** This release (High — affects every new player)
