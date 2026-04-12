# ISS-019: Lever Directly Writes room._grid

**Severity:** Low (code style — single private attribute access from neighbor class)
**Found during:** Epic 14 retrospective
**Status:** Done

## Problem

`lever.py:41` writes `room._grid[target_y][target_x] = new_tile` — the only external production code accessing `RoomInstance._grid` directly. Violates the underscore-private convention that the rest of the codebase follows.

## Root Cause

No `set_tile()` method existed on `RoomInstance` when the lever was implemented. The direct access was the simplest path.

## Fix

Add `set_tile(x, y, tile_type)` to `RoomInstance`. Update `lever.py` to use it.

## Impact

1 production file, 1 line changed. Zero behavioral change.
