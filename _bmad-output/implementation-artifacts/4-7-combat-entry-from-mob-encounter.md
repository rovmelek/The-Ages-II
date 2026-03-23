# Story 4.7: Combat Entry from Mob Encounter

Status: done

## Story

As a player,
I want combat to start automatically when I walk into a hostile mob,
So that exploration seamlessly leads to encounters.

## Acceptance Criteria

1. Player moves onto tile with alive hostile NPC → CombatInstance created via CombatManager → player added as participant → mob marked not alive → player receives combat_start message with instance state
2. Combat handlers (play_card, pass_turn, flee) find CombatInstance for player and process actions
3. Mob already in combat (is_alive=false) → another player moves onto tile → no additional combat triggered
4. Player.in_combat set to true on combat entry, false on combat end/flee

## Tasks / Subtasks

- [ ] Task 1: Add combat entry logic to movement handler (AC: #1, #3)
  - [ ] After detecting mob_encounter in move result, initiate combat
  - [ ] Load card definitions from DB for the player's deck
  - [ ] Create CombatInstance, add player, mark NPC not alive, set player.in_combat=true
  - [ ] Send combat_start message to player
- [ ] Task 2: Set in_combat=false on combat end and flee (AC: #4)
  - [ ] In _check_combat_end handler helper, set in_combat=false for all participants
  - [ ] In handle_flee, set in_combat=false for the fleeing player
- [ ] Task 3: Write tests (AC: #1-4)
- [ ] Task 4: Verify all tests pass

## Dev Notes

### Architecture Compliance

| Component | File Location |
|-----------|--------------|
| Movement handler (MODIFY) | `server/net/handlers/movement.py` |
| Combat handlers (MODIFY) | `server/net/handlers/combat.py` |
| Tests | `tests/test_combat_entry.py` (NEW) |

### Existing Infrastructure

- `room.move_entity()` already detects mob_encounter and returns `{"mob_encounter": {"entity_id": npc.id, "name": npc.name}}`
- `NpcEntity.is_alive` — already checked in room.move_entity (only alive hostile NPCs trigger)
- `PlayerEntity.in_combat` — already exists on dataclass
- `card_repo.get_all(session)` — loads all Card DB models
- `CardDef.from_db(card)` — converts Card model to CardDef

### Previous Story Intelligence

From Story 4-6:
- handle_flee removes participant and player mapping, but doesn't set in_combat=false
- _check_combat_end broadcasts combat_end but doesn't set in_combat=false
- 251 tests must not regress

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
