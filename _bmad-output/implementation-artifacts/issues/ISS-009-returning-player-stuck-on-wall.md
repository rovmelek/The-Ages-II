# Issue: Returning players stuck on non-walkable tile after login

**ID:** ISS-009
**Severity:** High
**Status:** Fixed
**Delivery:** Post-Epic 9 (Server Hardening follow-up)
**Test:** `pytest tests/test_login.py` — 4 new test cases
**Created:** 2026-04-09
**Assigned:** BMad Developer

## Description

Returning players whose saved position lands on a non-walkable tile (e.g., wall at 0,0 from database defaults) spawned stuck and could not move. The login handler only validated spawn position for first-time logins; returning players used their saved `position_x`/`position_y` without any walkability check.

Investigation revealed the same vulnerability existed in two additional player-placement paths: room transitions and death/respawn.

## Expected

All player-placement paths should validate that the target tile is walkable. If not, relocate the player to the room's designated spawn point, with fallback to the first walkable tile found by row scan.

## Actual

- **Login (returning player):** Entity placed at saved DB position without walkability check. If position was a wall tile, player was stuck.
- **Room transition:** Entry position from exit definition used directly without walkability or bounds validation. A misconfigured exit could place players on walls.
- **Death/respawn:** Spawn point validated, but no warning logged for degenerate rooms with no walkable tiles.

## Impact

**Significant UX issue.** Any returning player with a saved wall-tile position was permanently stuck until the database was manually reset. This could affect players whose rooms were redesigned between sessions, or players created before ISS-004's fix was applied (ISS-004 only fixed first-login; returning players retained the old (0,0) position).

## Design Reference

- ISS-004: New players spawn at origin (original incomplete fix)
- Epic 7 Story 7.1: Spawn Point Resolution
- Auth handler: `server/net/handlers/auth.py`
- Movement handler: `server/net/handlers/movement.py`
- Game orchestrator: `server/app.py` (respawn_player)
- Room spawn logic: `server/room/room.py` (get_player_spawn, is_walkable, find_first_walkable)

## Steps to Reproduce

1. Register and login (player saved at spawn point 50,50)
2. Stop the server
3. Manually edit `data/game.db` to set `position_x=0, position_y=0` for the player (or use a player created before ISS-004 fix)
4. Start the server and login
5. Player is at (0,0) — a wall tile in town_square — and cannot move in any direction

## Screenshot/Video

N/A — verified via WebSocket JSON responses and pytest.

## Root Cause

ISS-004 added spawn point resolution for **first-time logins only** (`is_first_login = player.current_room_id is None`). Returning players (`current_room_id` is set) bypassed this check entirely and were placed at their saved DB coordinates, even if those coordinates pointed to a wall tile.

The same oversight existed in:
- `_handle_exit_transition()` in `movement.py` — entry position from exit definitions was never validated
- `respawn_player()` in `app.py` — spawn point was validated but the final fallback had no warning for degenerate rooms

## Fix Applied

Unified walkability validation across all three player-placement paths:

**1. Login handler** (`server/net/handlers/auth.py`):
```python
is_first_login = player.current_room_id is None
needs_relocation = is_first_login or not room.is_walkable(entity.x, entity.y)
if needs_relocation:
    sx, sy = room.get_player_spawn()
    if not room.is_walkable(sx, sy):
        sx, sy = room.find_first_walkable()
    if not room.is_walkable(sx, sy):
        logger.warning(...)
    entity.x = sx
    entity.y = sy
    await player_repo.update_position(session, player.id, room_key, sx, sy)
```

**2. Room transition** (`server/net/handlers/movement.py`):
Added walkability check on `entry_x`/`entry_y` with same cascade: spawn point → first walkable → warning.

**3. Death/respawn** (`server/app.py`):
Added warning log when `find_first_walkable()` returns a non-walkable tile (degenerate room).

## Verification

- 484 tests pass (4 new tests added)
- `test_returning_player_on_wall_relocated_to_spawn` — wall position relocated to spawn
- `test_returning_player_spawn_also_unwalkable_uses_first_walkable` — double fallback
- `test_returning_player_on_walkable_tile_stays_put` — happy path, no false relocation
- 3 rounds of adversarial code review (blind hunter, edge case hunter, acceptance auditor)

## Lesson Learned

**Every code path that places a player in a room must validate tile walkability.** This bug existed because ISS-004's fix was applied to only one of three placement paths. When adding new placement paths in the future (e.g., teleportation, party summon, admin move), always include the walkability cascade: check position → try spawn point → try first walkable → log warning.

## Related Issues

- ISS-004 (original incomplete fix — only handled first-login, not returning players)
- ISS-003 (default room fix — prerequisite for correct spawn behavior)

---

**Priority for fix:** This release (High — affects any returning player with stale position data)
