# Story 4.5: Combat Resolution & Rewards

Status: done

## Story

As a player,
I want to win combat by defeating the mob and receive XP rewards, or lose and face consequences,
So that combat has meaningful stakes.

## Acceptance Criteria

1. Card play reduces mob HP to 0 → combat marked finished, victory=true → all participants receive {"type": "combat_end", "victory": true, "rewards": {"xp": 25}} → all participants marked in_combat=false → mob respawn scheduled
2. All players' HP reaches 0 → combat marked finished, victory=false → all participants receive {"type": "combat_end", "victory": false, "rewards": {}} → all participants marked in_combat=false
3. Combat ends (victory or defeat) → CombatInstance removed from CombatManager → all player-to-instance mappings cleaned up

## Tasks / Subtasks

- [ ] Task 1: Add combat resolution check to CombatInstance (AC: #1-2)
  - [ ] Add `check_combat_end() -> dict | None` method — checks is_finished after each action, returns combat_end result or None
  - [ ] Victory result: {"victory": True, "rewards": {"xp": 25}}
  - [ ] Defeat result: {"victory": False, "rewards": {}}
- [ ] Task 2: Wire resolution into play_card and pass_turn handlers (AC: #1-3)
  - [ ] After broadcasting combat_turn, check instance.is_finished
  - [ ] If finished: broadcast combat_end to all participants, clean up instance from CombatManager
  - [ ] Remove all player-to-instance mappings
- [ ] Task 3: Write tests (AC: #1-3)
- [ ] Task 4: Verify all tests pass

## Dev Notes

### Architecture Compliance

| Component | File Location |
|-----------|--------------|
| CombatInstance (MODIFY) | `server/combat/instance.py` |
| Combat handlers (MODIFY) | `server/net/handlers/combat.py` |
| Tests | `tests/test_combat_resolution.py` (NEW) |

### Previous Story Intelligence

From Story 4-4:
- play_card and pass_turn are now async
- play_card returns effect_results in result dict
- EffectRegistry wired into CombatInstance
- 238 tests must not regress

### Anti-Patterns to Avoid

- **DO NOT** implement in_combat flag on PlayerEntity yet — that integration happens in Story 4.7
- **DO NOT** implement mob respawn scheduling — Story 3.5 already handles that, wiring happens in 4.7
- **DO** focus on combat end detection, result broadcasting, and CombatManager cleanup

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
