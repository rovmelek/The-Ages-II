# Issue: NPC templates loaded after rooms — all NPCs fail to spawn

**ID:** ISS-001
**Severity:** Critical
**Status:** Fixed
**Delivery:** Epics 3/6 (NPC Spawning, Integration)
**Test:** Manual WebSocket test — login and check room_state NPCs
**Created:** 2026-03-25
**Assigned:** BMad Developer

## Description

`Game.startup()` loaded NPC templates from `data/npcs/` *after* loading rooms and spawning NPCs. Since `create_npc_from_template()` relies on the `_NPC_TEMPLATES` dictionary being populated, every call returned `None` and no NPCs were ever placed in any room.

## Expected

After server startup, rooms should contain hostile NPCs at their defined spawn points (e.g., Forest Goblin at (4,0) in test_room, Slimes at (30,30) and (60,60) in dark_cave). Players should see `!` icons on the map and trigger combat by walking into them.

## Actual

All rooms had 0 NPCs. `room_state` messages returned empty `npcs: []` arrays. Combat was impossible because there were no mobs to encounter.

## Impact

**Game-breaking.** The entire combat system (Epic 4) was unreachable because no hostile NPCs existed in any room. Players could explore, chat, and interact with objects, but the core gameplay loop (combat) was completely non-functional.

## Design Reference

- Architecture: `_bmad-output/planning-artifacts/architecture.md` (Section 3.2 System Relationships)
- Epic 3 Story 3.4: NPC Entity and Hostile Behavior
- Epic 6 Story 6.3: End-to-End Startup and Gameplay Wiring
- Server spec: `THE_AGES_SERVER_PLAN.md`

## Steps to Reproduce

1. Start the server with `python run.py`
2. Connect via WebSocket and send `{"action": "login", "username": "...", "password": "..."}`
3. Receive `room_state` message
4. Observe `npcs` array is empty `[]`
5. Walk to any NPC spawn point (e.g., (4,0) in test_room) — no combat triggers

## Screenshot/Video

N/A — verified via WebSocket JSON responses.

## Root Cause

In `server/app.py`, the `startup()` method had this order:
1. Load rooms from JSON → DB → memory (calls `create_npc_from_template()`)
2. Load cards
3. Load items
4. **Load NPC templates** ← too late, rooms already tried to spawn NPCs

## Fix Applied

Moved NPC template loading to **before** room loading in `server/app.py`:
1. **Load NPC templates** ← moved here
2. Load rooms from JSON → DB → memory (now finds templates successfully)
3. Load cards
4. Load items

**Commit scope:** Single line-group move in `server/app.py` (~8 lines relocated).

## Verification

After fix, WebSocket login returns `room_state` with populated NPCs:
```
Room: town_square — 8 NPCs
  Forest Goblin at (15,15) alive=True
  ...
```

## Related Issues

- ISS-002 (low mob density made testing difficult even after this fix)

---

**Priority for fix:** Immediate (Critical — core gameplay blocked)
