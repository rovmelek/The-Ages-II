# Story 4.6: Flee Combat

Status: done

## Story

As a player,
I want to flee from combat if it's too dangerous,
So that I can avoid death and try again later.

## Acceptance Criteria

1. Player in combat sends {"action": "flee"} → player removed from CombatInstance → player's in_combat=false → player receives {"type": "combat_fled"}
2. Player flees, other participants remain → combat continues for remaining participants → remaining participants receive updated combat state
3. Last participant flees → combat ends (no victory, no defeat) → CombatInstance cleaned up
4. Player not in combat sends flee → error: "Not in combat"

## Tasks / Subtasks

- [ ] Task 1: Add flee support to CombatInstance (AC: #1-3)
  - [ ] Already has `remove_participant()` — reuse it
- [ ] Task 2: Create `handle_flee` in combat handlers (AC: #1-4)
  - [ ] Validate player is in combat
  - [ ] Remove participant from instance
  - [ ] Remove player-to-instance mapping from CombatManager
  - [ ] Send combat_fled to the fleeing player
  - [ ] If participants remain, broadcast updated state
  - [ ] If no participants remain, clean up instance
- [ ] Task 3: Register flee handler in Game (AC: #1)
- [ ] Task 4: Write tests (AC: #1-4)
- [ ] Task 5: Verify all tests pass

## Dev Notes

### Architecture Compliance

| Component | File Location |
|-----------|--------------|
| Combat handlers (MODIFY) | `server/net/handlers/combat.py` |
| Game (MODIFY) | `server/app.py` — register flee handler |
| Tests | `tests/test_combat_flee.py` (NEW) |

### Previous Story Intelligence

From Story 4-5:
- CombatInstance.remove_participant() already exists and handles turn index adjustment
- CombatManager.remove_player() removes player-to-instance mapping
- CombatManager.remove_instance() cleans up instance and all mappings
- _check_combat_end() in handlers detects and broadcasts combat end
- 245 tests must not regress

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
