# Story 4.3: Combat Instance & Turn Structure

Status: done

## Story

As a player,
I want turn-based combat where I choose one action per turn — play a card, or pass,
So that combat is strategic and I make meaningful decisions each turn.

## Acceptance Criteria

1. CombatInstance created with mob and card definitions → player added as participant → player marked in_combat → CardHand created → player added to turn order
2. Player's turn → plays a card → turn advances to next participant → after all participants acted (full cycle) → mob attacks a random player
3. Player's turn → passes → mob attacks the passing player → turn advances to next participant
4. NOT player's turn → tries to play card or pass → error: "Not your turn"
5. Two players in combat → turns alternate: Player 1 → Player 2 → mob attacks random → Player 1 → ...

## Tasks / Subtasks

- [x] Task 1: Create `server/combat/instance.py` with `CombatInstance` class (AC: #1-5)
  - [x] `__init__(instance_id, mob_npc, card_defs)` — stores mob stats, initializes participants list and turn order
  - [x] `add_participant(entity_id, player_stats, card_defs) -> CardHand` — creates CardHand, tracks participant, sets turn order
  - [x] `remove_participant(entity_id)` — removes from combat (for flee)
  - [x] `get_current_turn() -> str` — returns entity_id of current turn holder
  - [x] `advance_turn() -> dict | None` — advances to next participant; if cycle complete, triggers mob attack and returns mob_attack result
  - [x] `play_card(entity_id, card_key) -> dict` — validates turn, calls CardHand.play_card, advances turn; returns card_played result
  - [x] `pass_turn(entity_id) -> dict` — validates turn, mob attacks this player, advances turn; returns pass result with mob_attack
  - [x] `get_state() -> dict` — returns current combat state for client (current_turn, participants, mob_hp, hands)
  - [x] `is_finished` property — True if mob HP <= 0 or all players HP <= 0
- [x] Task 2: Create `server/combat/manager.py` with `CombatManager` class (AC: #1)
  - [x] `_instances: dict[str, CombatInstance]` — active combat instances
  - [x] `_player_to_instance: dict[entity_id, instance_id]` — reverse lookup
  - [x] `create_instance(mob_npc, card_defs) -> CombatInstance` — creates and registers instance
  - [x] `get_instance(instance_id) -> CombatInstance | None`
  - [x] `get_player_instance(entity_id) -> CombatInstance | None` — lookup by player
  - [x] `remove_instance(instance_id)` — cleanup
- [x] Task 3: Create `server/net/handlers/combat.py` with combat action handlers (AC: #2-4)
  - [x] `handle_play_card(ws, data, *, game)` — validates player in combat and turn, calls instance.play_card, broadcasts turn state
  - [x] `handle_pass_turn(ws, data, *, game)` — validates, calls instance.pass_turn, broadcasts
  - [x] Both handlers send combat_turn state to all participants after action
- [x] Task 4: Integrate CombatManager into Game (AC: #1)
  - [x] Add `self.combat_manager = CombatManager()` to Game.__init__
  - [x] Register `play_card` and `pass_turn` handlers in `_register_handlers()`
- [x] Task 5: Write tests `tests/test_combat.py` (AC: #1-5)
  - [x] Test CombatInstance creation and participant addition
  - [x] Test turn order with single player
  - [x] Test turn order with multiple players (alternating + mob attack after cycle)
  - [x] Test play_card advances turn
  - [x] Test pass_turn triggers mob attack on passer
  - [x] Test wrong turn rejected with error
  - [x] Test CombatManager create/get/remove
  - [x] Test get_state returns correct structure
- [x] Task 6: Verify all tests pass
  - [x] Run `pytest tests/test_combat.py -v`
  - [x] Run `pytest tests/ -v` to verify no regressions

## Dev Notes

### Architecture Compliance

| Component | File Location |
|-----------|--------------|
| CombatInstance | `server/combat/instance.py` (NEW) |
| CombatManager | `server/combat/manager.py` (NEW) |
| Combat handlers | `server/net/handlers/combat.py` (NEW) |
| Game integration | `server/app.py` (MODIFY) |
| Tests | `tests/test_combat.py` (NEW) |

### Existing Infrastructure to Reuse

- **CardDef/CardHand** from `server/combat/cards/` — create CardHand per participant
- **PlayerEntity.in_combat** — already exists, set to True when entering combat
- **NpcEntity.stats** — dict with hp, max_hp, attack, defense
- **ConnectionManager** — broadcast combat state to participants
- **MessageRouter** — register play_card, pass_turn actions

### Combat Turn Flow

```
Player1 plays card → advance → Player2's turn
Player2 passes → mob attacks Player2 → advance → cycle complete
Mob attacks random player (end of cycle)
Player1's turn again
```

### Mob Attack Pattern

Mob attacks deal damage equal to `mob_stats["attack"]`, targeting:
- On pass: the player who passed
- On cycle end: a random participant

### CombatInstance State Format

```python
{
    "instance_id": "combat_123",
    "current_turn": "player_1",
    "participants": [
        {"entity_id": "player_1", "hp": 80, "max_hp": 100, "shield": 0},
        {"entity_id": "player_2", "hp": 100, "max_hp": 100, "shield": 0},
    ],
    "mob": {"name": "Forest Goblin", "hp": 50, "max_hp": 50},
    "hands": {"player_1": [...], "player_2": [...]},
}
```

### Anti-Patterns to Avoid

- **DO NOT** implement effect resolution through EffectRegistry — Story 4.4 handles that
- **DO NOT** implement combat end/rewards — Story 4.5 handles that
- **DO NOT** implement flee action — Story 4.6 handles that
- **DO NOT** implement combat entry from mob encounter — Story 4.7 handles that
- **DO** use simple damage calculation for mob attacks (mob.attack value directly)
- **DO** keep card play as "remove from hand, advance turn" — effect resolution deferred

### Previous Story Intelligence

From Story 4-2:
- CardHand(card_defs, hand_size=5) creates deck and draws initial hand
- CardHand.play_card(card_key) moves to discard and draws replacement
- CardDef.to_dict() serializes for client
- 200 existing tests must not regress

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#5 Combat System]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 4.3]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Created `server/combat/instance.py` with `CombatInstance` class: participants, turn order, play_card, pass_turn, mob attacks, cycle-end attacks, state serialization
- Created `server/combat/manager.py` with `CombatManager` class: instance tracking, player-to-instance mappings, create/get/remove
- Created `server/net/handlers/combat.py` with `handle_play_card` and `handle_pass_turn` handlers
- Integrated `CombatManager` into `Game.__init__()` and registered combat handlers
- 24 new tests covering instance creation, participant management, turn order, play/pass mechanics, cycle mob attacks, state format, is_finished conditions, CombatManager CRUD
- All 224 tests pass (200 existing + 24 new)

### File List

- `server/combat/instance.py` (NEW)
- `server/combat/manager.py` (NEW)
- `server/net/handlers/combat.py` (NEW)
- `server/app.py` (MODIFIED — CombatManager integration, combat handler registration)
- `tests/test_combat.py` (NEW — 24 tests)
