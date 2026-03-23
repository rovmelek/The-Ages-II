# Story 4.4: Card Effect Resolution

Status: done

## Story

As a player,
I want my cards to deal damage, heal me, raise shields, and apply effects to the mob,
So that different cards create different tactical outcomes.

## Acceptance Criteria

1. Player plays a card with effects: [{"type": "damage", "value": 20}] → each effect resolved sequentially through EffectRegistry → mob HP reduced by 20
2. Player plays a card with effects: [{"type": "heal", "value": 15}] → player HP restored by 15 (capped at max_hp)
3. Player has 12 shield, mob attacks for 8 → 8 shield consumed, 0 HP damage, 4 shield remaining
4. Player has 5 shield, mob attacks for 12 → 5 shield consumed, 7 HP damage
5. Card with multiple effects: [{"type": "damage", "value": 10}, {"type": "heal", "value": 5}] → mob takes 10 damage AND player heals 5 HP
6. Card with "draw" effect → additional cards drawn into hand after effect resolution

## Tasks / Subtasks

- [ ] Task 1: Wire EffectRegistry into CombatInstance (AC: #1-6)
  - [ ] Add `effect_registry` parameter to `CombatInstance.__init__()` — accept an EffectRegistry instance
  - [ ] Create `async def resolve_card_effects(entity_id, card_def) -> list[dict]` method on CombatInstance
  - [ ] Iterate card's effects list sequentially, calling `registry.resolve()` for each
  - [ ] For damage/dot effects: source=player_stats, target=mob_stats
  - [ ] For heal/shield effects: source=player_stats, target=player_stats (self-targeting)
  - [ ] For draw effects: after resolution, call `CardHand.draw_card()` for the value count
  - [ ] Collect all effect results into a list and return
- [ ] Task 2: Integrate effect resolution into `play_card()` (AC: #1-5)
  - [ ] After CardHand.play_card() returns the played CardDef, call resolve_card_effects()
  - [ ] Since EffectRegistry handlers are async, `play_card()` must become `async def play_card()`
  - [ ] Add effect_results to the play_card return dict
  - [ ] Check mob HP after resolution — if <= 0, combat may be finished (is_finished property handles this)
- [ ] Task 3: Update combat handlers for async play_card (AC: #1-5)
  - [ ] Update `handle_play_card` in `server/net/handlers/combat.py` — play_card is now awaited
  - [ ] Update `handle_pass_turn` if pass_turn also becomes async
- [ ] Task 4: Update CombatManager.create_instance to accept EffectRegistry (AC: #1)
  - [ ] Pass EffectRegistry to CombatInstance constructor
  - [ ] Game class should create the registry and pass it to CombatManager
- [ ] Task 5: Write tests `tests/test_combat_effects.py` (AC: #1-6)
  - [ ] Test damage card reduces mob HP
  - [ ] Test heal card restores player HP (capped at max)
  - [ ] Test shield card adds shield to player
  - [ ] Test multi-effect card (damage + heal) applies both
  - [ ] Test draw effect draws additional cards
  - [ ] Test dot effect adds to mob's active_effects
  - [ ] Test shield absorption on mob attack (already tested but verify with new flow)
- [ ] Task 6: Verify all tests pass
  - [ ] Run `pytest tests/test_combat_effects.py -v`
  - [ ] Run `pytest tests/ -v` to verify no regressions

## Dev Notes

### Architecture Compliance

| Component | File Location |
|-----------|--------------|
| CombatInstance (MODIFY) | `server/combat/instance.py` |
| CombatManager (MODIFY) | `server/combat/manager.py` |
| Combat handlers (MODIFY) | `server/net/handlers/combat.py` |
| Game integration (MODIFY) | `server/app.py` |
| Tests | `tests/test_combat_effects.py` (NEW) |

### Existing Infrastructure to Reuse

- **EffectRegistry** from `server/core/effects/registry.py` — `create_default_registry()` returns a ready registry with damage, heal, shield, dot, draw handlers
- **Effect handlers** in `server/core/effects/` — all async, signature: `(effect: dict, source: dict, target: dict, context: dict) -> dict`
- **CombatInstance** from `server/combat/instance.py` — already has play_card, pass_turn, participant_stats, mob_stats
- **CardDef.effects** — list of effect dicts, already populated from card definitions
- **CardHand.draw_card()** — draws from deck, reshuffles discard if needed

### Effect Targeting Rules

- **damage**: source=player_stats, target=mob_stats (player attacks mob)
- **heal**: source=player_stats, target=player_stats (self-heal)
- **shield**: source=player_stats, target=player_stats (self-shield)
- **dot**: source=player_stats, target=mob_stats (applies to mob)
- **draw**: no target mutation, returns instruction; combat system calls CardHand.draw_card()

### Critical: Async Transition

`play_card()` must become async because EffectRegistry.resolve() is async. This is a breaking change for existing tests in `tests/test_combat.py`. Options:
1. **Recommended**: Make play_card async, update all callers and tests to await it
2. Existing tests use synchronous calls — they need `pytest-asyncio` and `await`

### Anti-Patterns to Avoid

- **DO NOT** change the EffectRegistry interface — it's shared with future item system
- **DO NOT** implement combat end/rewards logic — Story 4.5 handles that
- **DO NOT** handle DoT tick resolution (applying damage each turn) — future story
- **DO** keep mob attacks using direct damage (mob_stats["attack"]) not through EffectRegistry
- **DO** preserve all existing test behavior — play_card still advances turns, pass_turn still triggers mob attack

### Previous Story Intelligence

From Story 4-3:
- CombatInstance tracks participants, participant_stats, mob_stats, hands
- play_card validates turn, calls CardHand.play_card, advances turn via _advance_turn
- _advance_turn triggers mob attack at cycle end
- _mob_attack_target uses shield absorption pattern
- Code review found: dead player check needed, turn index fix on remove, action results in broadcast
- 227 total tests must not regress

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#5 Combat System]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 4.4]

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
