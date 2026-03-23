# Story 3.4: NPC Entity & Hostile Behavior

Status: done

## Story

As a player,
I want to encounter hostile NPCs placed in rooms,
So that the world has threats to fight.

## Acceptance Criteria

1. Room's configuration references NPC templates from `data/npcs/` → NPC entities created with stats, behavior_type, and loot_table from the template and appear in `room_state` broadcast
2. NPC with `behavior_type: "hostile"` and alive → player moves onto NPC's tile → movement result includes `mob_encounter` with NPC entity ID
3. NPC killed (`is_alive = false`) → player moves onto its tile → no `mob_encounter` triggered
4. NPC entities appear in room_state with position and type info

## Tasks / Subtasks

- [ ] Task 1: Create `server/room/objects/npc.py` with `NpcEntity` dataclass (AC: #1, #4)
  - [ ] Define `NpcEntity` with `id`, `npc_key`, `name`, `x`, `y`, `behavior_type`, `stats` (dict with hp, max_hp, attack, defense), `loot_table`, `is_alive`, `spawn_config`
  - [ ] NpcEntity should be distinct from PlayerEntity — it's a mob/NPC, not a player
- [ ] Task 2: Create NPC template loading from JSON (AC: #1)
  - [ ] Create `data/npcs/base_npcs.json` with 1-2 NPC templates (e.g., "forest_goblin" hostile mob)
  - [ ] Create loader function to read NPC templates from JSON into a dict keyed by `npc_key`
- [ ] Task 3: Update `RoomInstance` to hold NPC entities (AC: #1, #4)
  - [ ] Add `self._npcs: dict[str, NpcEntity]` to RoomInstance
  - [ ] Add `add_npc(npc)`, `remove_npc(npc_id)`, `get_npc(npc_id)` methods
  - [ ] Update `get_state()` to include NPCs in the response
- [ ] Task 4: Spawn NPCs when room loads (AC: #1)
  - [ ] Room JSON `spawn_points` can include `{"type": "npc", "npc_key": "forest_goblin", "x": 3, "y": 3}`
  - [ ] During room load, for each NPC spawn point, look up template and create NpcEntity
  - [ ] Add to test room JSON with an NPC spawn point
- [ ] Task 5: Update movement to detect NPC encounters (AC: #2, #3)
  - [ ] In `RoomInstance.move_entity()`, after move succeeds check for NPCs at target tile
  - [ ] If hostile NPC is alive at target → add `mob_encounter` to result
  - [ ] If NPC is dead → no encounter (existing mob check uses `mob_` prefix — update to use NPC system)
- [ ] Task 6: Write tests `tests/test_npc.py` (AC: #1-4)
  - [ ] Test NPC entity creation from template
  - [ ] Test NPC appears in room_state
  - [ ] Test moving onto hostile alive NPC triggers mob_encounter
  - [ ] Test moving onto dead NPC does not trigger encounter
  - [ ] Test NPC template loading from JSON
- [ ] Task 7: Verify all tests pass
  - [ ] Run `pytest tests/test_npc.py -v`
  - [ ] Run `pytest tests/ -v` to verify no regressions (141 existing tests)

## Dev Notes

### Architecture Compliance

| Component | File Location |
|-----------|--------------|
| NpcEntity | `server/room/objects/npc.py` |
| NPC templates | `data/npcs/base_npcs.json` |
| Room NPC support | `server/room/room.py` |
| Movement NPC detection | `server/room/room.py` → `move_entity()` |

### NPC Template JSON Format (from architecture.md §4.3)

```json
{
  "npc_key": "forest_goblin",
  "name": "Forest Goblin",
  "behavior_type": "hostile",
  "spawn_type": "persistent",
  "spawn_config": {
    "respawn_seconds": 60
  },
  "stats": {"hp": 50, "max_hp": 50, "attack": 10, "defense": 5},
  "loot_table": "goblin_loot"
}
```

### Room Spawn Point for NPCs

```json
{"type": "npc", "npc_key": "forest_goblin", "x": 3, "y": 3}
```

### NPC in room_state

NPCs should appear alongside player entities in the room state:
```python
{
  "npcs": [
    {"id": "npc_forest_goblin_0", "name": "Forest Goblin", "x": 3, "y": 3, "npc_key": "forest_goblin", "is_alive": true}
  ]
}
```

### Existing Movement Mob Detection

`RoomInstance.move_entity()` at line 107-112 currently checks for entities with `id.startswith("mob_")`. This needs to be replaced with proper NPC detection using `self._npcs`.

### Anti-Patterns to Avoid

- **DO NOT** implement combat logic — Story 3.4 just detects encounters; Epic 4 handles combat
- **DO NOT** implement NPC respawning — Story 3.5 handles that
- **DO NOT** implement NPC dialogue, shops, or quests — deferred features
- **DO NOT** implement NPC AI/pathfinding — NPCs are stationary
- **DO** keep NPC entity separate from PlayerEntity — they have different fields and behavior

### Previous Story Intelligence

From Story 3.3:
- Object registration pattern in `server/room/objects/__init__.py`
- `RoomInstance` stores objects in `self.objects` and indexes interactive ones in `self._interactive_objects`
- Handler pattern and login check well-established
- 141 existing tests must not regress

### Project Structure Notes

- New files: `server/room/objects/npc.py`, `data/npcs/base_npcs.json`, `tests/test_npc.py`
- Modified files: `server/room/room.py` (NPC storage, get_state, move_entity)

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#4.1 Object Categories]
- [Source: _bmad-output/planning-artifacts/architecture.md#4.3 NPC Spawn System]
- [Source: _bmad-output/planning-artifacts/architecture.md#2.3 Entities]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.4]

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
