# Story 7.6: NPC Death State Broadcast

Status: ready-for-dev

## Story

As a player,
I want to see NPCs disappear from the room when someone defeats them,
so that the world state is consistent for all players.

## Acceptance Criteria

1. **Given** `NpcEntity` dataclass exists,
   **When** the story is complete,
   **Then** an `in_combat: bool = False` field is added to `NpcEntity`,
   **And** `to_dict()` does NOT include `in_combat` (server-internal state).

2. **Given** a player walks onto a hostile NPC's tile,
   **When** the encounter is detected in `room.py:move_entity`,
   **Then** the encounter check verifies both `is_alive` and `not in_combat`,
   **And** `npc.in_combat` is set to `True` (NOT `is_alive = False`),
   **And** `is_alive` remains `True` until combat victory.

3. **Given** combat ends with victory (mob HP <= 0),
   **When** combat resolution runs,
   **Then** `npc.is_alive` is set to `False`,
   **And** `npc.in_combat` is set to `False`,
   **And** a `room_state` rebroadcast is sent to all players in the room.

4. **Given** combat ends with defeat or all players flee,
   **When** combat resolution runs,
   **Then** `npc.in_combat` is set to `False` (NPC returns to available),
   **And** `npc.is_alive` remains `True`.

5. **Given** the server restarts,
   **When** NPCs are reloaded,
   **Then** `in_combat` defaults to `False` (purely in-memory, not persisted to DB),
   **And** all NPCs are available for encounters.

6. **Given** `movement.py` currently sets `npc.is_alive = False` at encounter,
   **When** the story is complete,
   **Then** this line is changed to set `npc.in_combat = True` instead,
   **And** all affected tests are updated and `pytest tests/` passes.

## Tasks / Subtasks

- [ ] Task 1: Add `in_combat` field to NpcEntity (AC: 1, 5)
  - [ ] In `server/room/objects/npc.py`, add `in_combat: bool = False` to the NpcEntity dataclass
  - [ ] In `to_dict()`, exclude `in_combat` — it's server-internal state
  - [ ] Default is False — safe on server restart

- [ ] Task 2: Fix encounter to set in_combat, not is_alive (AC: 2) — Fixes ISS-008
  - [ ] In `server/net/handlers/movement.py` `_handle_mob_encounter()` (~line 107):
    - Remove: `npc.is_alive = False` (and any `game.kill_npc()` call)
    - Add: `npc.in_combat = True`
  - [ ] This prevents the flee exploit — NPC stays alive during combat

- [ ] Task 3: Update encounter detection (AC: 2)
  - [ ] In `server/room/room.py` (~line 138-141), update NPC encounter check:
    - From: `npc.is_alive and npc.behavior_type == "hostile"`
    - To: `npc.is_alive and not npc.in_combat and npc.behavior_type == "hostile"`
  - [ ] This prevents two players from fighting the same NPC simultaneously

- [ ] Task 4: Set NPC death on combat victory (AC: 3)
  - [ ] In `server/net/handlers/combat.py` `_check_combat_end()`, when `victory=True`:
    - Set `npc.is_alive = False`
    - Set `npc.in_combat = False`
    - Call `game.kill_npc(room_key, npc_id)` for respawn timer (if applicable)
    - Broadcast updated `room_state` to all players in the room
  - [ ] Need to track which NPC is in the combat instance — store `npc_id` and `room_key` in CombatInstance

- [ ] Task 5: Restore NPC on defeat/flee (AC: 4)
  - [ ] In `_check_combat_end()`, when `victory=False` (defeat):
    - Set `npc.in_combat = False`
    - NPC returns to normal — can be fought again
  - [ ] On flee (all players flee): same as defeat — `npc.in_combat = False`
  - [ ] Check flee handler in combat.py for last-player-flee case

- [ ] Task 6: Store NPC reference in CombatInstance (AC: 3, 4)
  - [ ] CombatInstance needs to know which NPC is the mob: store `npc_id` and `room_key`
  - [ ] Currently mob data is passed as a dict to `create_instance()` — add `npc_id` and `room_key` fields
  - [ ] This allows combat end to look up the actual NpcEntity for state changes

- [ ] Task 7: Tests (AC: 6)
  - [ ] Test: encounter sets `in_combat=True`, NOT `is_alive=False`
  - [ ] Test: victory sets `is_alive=False` and `in_combat=False`
  - [ ] Test: defeat/flee sets `in_combat=False`, `is_alive` stays True
  - [ ] Test: NPC with `in_combat=True` is not targetable by other players
  - [ ] Update any existing tests that assert `is_alive=False` at encounter
  - [ ] Run `pytest tests/`

## Dev Notes

### Current Implementation (The Bug — ISS-008)

In `movement.py` `_handle_mob_encounter()` (~line 107): `npc.is_alive = False` is set **immediately at encounter**, before combat even starts. Then `game.kill_npc()` is called, which starts the respawn timer. This means:
- NPC appears dead on the map during combat
- If player flees, NPC is already dead → free kill exploit
- Respawn timer starts at encounter, not at actual death
- Other players see NPC die before combat resolves

### NpcEntity Dataclass (npc.py lines 10-22)

```python
@dataclass
class NpcEntity:
    id: str
    npc_key: str
    name: str
    x: int
    y: int
    behavior_type: str = "hostile"
    stats: dict = field(default_factory=dict)
    loot_table: str = ""
    is_alive: bool = True
    spawn_config: dict = field(default_factory=dict)
```

Add `in_combat: bool = False` after `is_alive`.

### CombatInstance Mob Tracking

`CombatInstance` currently stores mob as a dict in `self.mob` with stats. It does NOT store `npc_id` or `room_key`. These need to be added so combat end can look up the NpcEntity to update its state. Pass them through `CombatManager.create_instance()`.

### game.kill_npc()

Currently called at encounter time. Move this call to combat victory. This method sets `is_alive=False` and schedules respawn via the scheduler. It's in `server/app.py`.

### ISS-008 Fix

This story fully resolves ISS-008. The core fix is Tasks 2 and 4: move NPC death from encounter to victory. Mark ISS-008 as done when this story completes.

### Project Structure Notes

- Modified files: `server/room/objects/npc.py` (add field), `server/net/handlers/movement.py` (fix encounter), `server/room/room.py` (update check), `server/net/handlers/combat.py` (add death on victory), `server/combat/instance.py` or `manager.py` (store npc reference)
- No new files needed

### References

- [Source: server/room/objects/npc.py — lines 10-22, NpcEntity dataclass]
- [Source: server/net/handlers/movement.py — ~line 107, _handle_mob_encounter]
- [Source: server/room/room.py — lines 138-141, encounter detection]
- [Source: server/net/handlers/combat.py — _check_combat_end]
- [Source: server/app.py — game.kill_npc]
- [Source: ISS-008 — NPC marked dead at encounter]
- [Source: architecture.md#Section 4.3 — NPC Spawn System]

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
