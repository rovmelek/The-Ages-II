---
id: ISS-034
title: "_reset_player_stats does not clear active_effects on respawn"
severity: Low
status: open
found_during: "Epic 18 investigation"
---

# ISS-034: Respawn Does Not Clear DoT Active Effects

## Summary

`_reset_player_stats()` in `server/player/service.py` clears `shield` but not `active_effects`. If a player dies with active DoTs (poison, bleed), the `active_effects` list could persist through respawn.

## Root Cause

`active_effects` was never added to the pop list in `_reset_player_stats()`. In practice, `clean_player_combat_stats()` runs first and doesn't clean `active_effects` from the entity stats either — it only pops `shield`.

## Impact

Theoretical: DoT effects could carry through death/respawn into the next combat. Low severity because `active_effects` is not in `_STATS_WHITELIST` so it won't survive a disconnect/reconnect cycle, but within a single session the stale effects could cause phantom damage.

## Proposed Fix

Add `entity.stats.pop("active_effects", None)` to `_reset_player_stats()`.

## Files

- `server/player/service.py` — `_reset_player_stats()`

## Fixed In

Epic 18, Task 4.
