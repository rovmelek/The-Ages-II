---
id: ISS-033
title: "handle_flee_outcome never syncs stats back to entity before remove_participant"
severity: Medium
status: open
found_during: "Epic 18 investigation"
---

# ISS-033: Flee Combat — No Stat Sync Before Participant Removal

## Summary

`handle_flee_outcome()` in `server/combat/service.py` calls `instance.remove_participant(entity_id)` which pops the participant's combat stats dict. No stats (HP, energy, shield damage, heals) are synced back to `entity.stats` before the pop. Fled players lose ALL combat stat changes.

## Root Cause

`remove_participant()` in `CombatInstance` pops `participant_stats[entity_id]`. The flee handler never copies combat stat values back to the entity before calling it.

## Impact

- Players who flee combat lose all HP changes from combat (damage taken, heals received)
- On reconnect/save, their HP is whatever it was at combat entry, not current
- With Epic 18, energy changes during combat would also be lost

## Proposed Fix

In `handle_flee_outcome()`, before calling `instance.remove_participant()`, sync `hp`, `max_hp`, `energy`, `max_energy` from `instance.participant_stats[entity_id]` back to `entity.stats`.

## Files

- `server/combat/service.py` — `handle_flee_outcome()`

## Fixed In

Epic 18, Task 12.
