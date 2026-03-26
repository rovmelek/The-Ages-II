# Issue: Insufficient mob spawn density across all rooms

**ID:** ISS-002
**Severity:** Medium
**Status:** Fixed
**Delivery:** Epic 6 (Sample Data)
**Test:** Manual — visual inspection of map in web client
**Created:** 2026-03-25
**Assigned:** BMad Developer

## Description

Room data files had very few NPC spawn points. `town_square` (100x100, the default spawn room) had zero mobs — it was a completely safe zone with nothing to fight. `dark_cave` had only 2 slimes in a 100x100 grid, making them nearly impossible to find. `test_room` had 1 goblin and `other_room` had none.

## Expected

Players should encounter mobs relatively easily when exploring rooms. The 25x25 viewport means players can only see ~6% of a 100x100 room at once, so mobs need to be distributed densely enough that players encounter them within reasonable exploration.

## Actual

- `town_square`: 0 mobs (100x100 map)
- `dark_cave`: 2 slimes (100x100 map) — at (30,30) and (60,60) only
- `test_room`: 1 goblin (5x5 map)
- `other_room`: 0 mobs (5x5 map)

Players could walk around for extended periods without ever encountering a mob.

## Impact

Poor gameplay experience. New players logging in for the first time land in `town_square` with no mobs at all, giving them no way to test or experience the combat system without first navigating to another room and finding sparse mob locations.

## Design Reference

- Epic 6 Story 6.1: Sample Room Data
- Room data: `data/rooms/*.json`
- NPC templates: `data/npcs/npcs.json`

## Steps to Reproduce

1. Start server and login via web client
2. Spawn in `town_square` — no `!` icons visible anywhere
3. Walk around entire map — never encounter a mob
4. Travel to `dark_cave` — must navigate to exact coordinates (30,30) or (60,60) to find a slime

## Screenshot/Video

N/A — verified via web client visual inspection.

## Fix Applied

Added NPC spawn points to all room JSON files:

| Room | Before | After | Mob Types |
|------|--------|-------|-----------|
| `town_square` | 0 | 8 | Forest Goblin (6), Slime (2) |
| `dark_cave` | 2 | 20 | Slime (10), Cave Bat (8), original Slimes (2) |
| `test_room` | 1 | 3 | Forest Goblin (1), Cave Bat (1), Slime (1) |
| `other_room` | 0 | 2 | Forest Goblin (1), Cave Bat (1) |

Mobs are spread across the map to ensure players encounter them within reasonable exploration distance.

## Verification

After fix and server restart, `room_state` returns populated NPC lists. Red `!` icons visible on the map in the web client.

## Related Issues

- ISS-001 (this issue was masked by ISS-001 — even these sparse mobs weren't spawning)

---

**Priority for fix:** This release
