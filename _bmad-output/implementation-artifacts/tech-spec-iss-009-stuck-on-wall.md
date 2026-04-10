---
title: 'ISS-009: Returning players stuck on non-walkable tile'
type: 'bugfix'
created: '2026-04-09'
status: 'done'
context:
  - '_bmad-output/planning-artifacts/architecture.md'
---

# ISS-009: Returning players stuck on non-walkable tile

<frozen-after-approval reason="human-owned intent -- do not modify unless human renegotiates">

## Intent

**Problem:** Returning players whose saved position lands on a non-walkable tile (e.g., wall at 0,0 from DB defaults) spawn stuck and cannot move. The login handler only validates spawn position for first-time logins.

**Approach:** Add a walkability check for returning players in the login handler. If their saved position is non-walkable, relocate them to the room's player spawn point and persist the corrected position.

## Boundaries & Constraints

**Always:** Preserve existing first-login spawn logic. Persist corrected position to DB so subsequent logins don't repeat the fix.

**Ask First:** N/A

**Never:** Do not change DB column defaults or player model. Do not alter registration flow.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Returning player on walkable tile | saved pos (50,50) floor | Spawn at (50,50) as before | N/A |
| Returning player on wall | saved pos (0,0) wall | Relocate to room spawn point (50,50) | N/A |
| Returning player, spawn also unwalkable | saved pos (0,0), spawn broken | Fallback to find_first_walkable() | N/A |

</frozen-after-approval>

## Code Map

- `server/net/handlers/auth.py` -- login handler, entity placement logic
- `server/room/room.py` -- get_player_spawn(), is_walkable(), find_first_walkable()

## Tasks & Acceptance

**Execution:**
- [x] `server/net/handlers/auth.py` -- Add walkability validation for returning players after entity creation
- [x] `tests/` -- Add test for returning player on non-walkable tile being relocated

**Acceptance Criteria:**
- Given a returning player with saved position on a wall tile, when they log in, then they are relocated to the room's player spawn point
- Given a returning player with saved position on a floor tile, when they log in, then they spawn at their saved position (no change)

## Verification

**Commands:**
- `pytest tests/ -x -q` -- expected: all tests pass including new test
