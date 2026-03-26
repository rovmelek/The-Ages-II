# Story ISS-005: DoT Effects Tick Resolution

Status: done

## Story

As a player,
I want damage-over-time effects (poison, bleed) to deal damage each turn after being applied,
so that DoT cards like `venom_fang` and `poison_strike` function as designed and provide meaningful combat value.

## Acceptance Criteria

1. **Given** a DoT effect has been applied to the mob (via card or item),
   **When** any player's turn begins,
   **Then** all active DoT effects on the mob tick — each deals its `value` as damage to the mob's HP.

2. **Given** a DoT effect has been applied to a player (e.g., if mobs ever apply DoTs),
   **When** that player's turn begins,
   **Then** all active DoT effects on that player tick — each deals its `value` as damage to the player's HP (respecting shield).

3. **Given** a DoT effect ticks,
   **When** its `remaining` counter reaches 0 after decrementing,
   **Then** the effect is removed from the target's `active_effects` list.

4. **Given** DoT effects tick at the start of a turn,
   **When** the combat_turn response is sent to clients,
   **Then** the response includes a `dot_ticks` array with each tick result: `{subtype, value, target, remaining}`.

5. **Given** a DoT effect kills the mob (HP reaches 0),
   **When** the tick completes,
   **Then** combat ends with a victory result (same as normal combat end flow).

6. **Given** a DoT effect kills a player (HP reaches 0),
   **When** the tick completes,
   **Then** that player's turn is skipped (dead player skip logic already exists), and combat end is checked.

7. **Given** multiple DoT effects are active simultaneously,
   **When** a turn begins,
   **Then** all active DoTs tick in order (oldest first), and all results are collected.

8. **Given** the `venom_fang` card is played (6 poison, 3 turns),
   **When** 3 subsequent turns pass,
   **Then** the mob takes 6 damage on each of those 3 turns (18 total), and the effect is removed after the 3rd tick.

## Tasks / Subtasks

- [x] Task 1: Add `_process_dot_effects()` to CombatInstance (AC: 1, 2, 3, 7)
  - [x] Create method `_process_dot_effects(target_stats: dict) -> list[dict]`
  - [x] Iterate `target_stats.get("active_effects", [])`
  - [x] For each DoT entry: apply `value` damage to target HP (respect shield if player target)
  - [x] Decrement `remaining` by 1
  - [x] Remove entries where `remaining <= 0`
  - [x] Return list of tick result dicts: `{type: "dot_tick", subtype, value, target_hp, remaining}`

- [x] Task 2: Call DoT processing at start of each action (AC: 1, 2, 4, 5, 6)
  - [x] In `play_card()`: call `_process_dot_effects()` on mob BEFORE resolving card effects
  - [x] In `play_card()`: call `_process_dot_effects()` on current player BEFORE resolving card effects
  - [x] In `pass_turn()`: same — process DoTs on mob and current player before the pass action
  - [x] In `use_item()`: same — process DoTs before item resolution
  - [x] Include dot_ticks in the returned result dict

- [x] Task 3: Integrate with combat end check (AC: 5, 6)
  - [x] After DoT processing, if mob HP <= 0 or player HP <= 0, combat end should be detected by existing `is_finished` property — no new code needed, just verify it works
  - [x] Verify dead player skip logic in `_advance_turn()` handles DoT-killed players

- [x] Task 4: Update client to display DoT ticks (AC: 4)
  - [x] In `web-demo/js/game.js` `handleCombatTurn`: render `dot_ticks` from result data
  - [x] Show in combat result text: "Poison dealt 6 damage to Slime (2 turns remaining)"

- [x] Task 5: Write tests (AC: 1, 3, 5, 7, 8)
  - [x] Test: DoT ticks each turn and decrements remaining
  - [x] Test: DoT removed when remaining reaches 0
  - [x] Test: Multiple DoTs tick independently
  - [x] Test: DoT can kill mob (HP reaches 0)
  - [x] Test: DoT damage respects shield on player targets

## Dev Notes

### Root Cause

`server/core/effects/dot.py` correctly appends DoT entries to `target["active_effects"]` (line 16-21), but `server/combat/instance.py` never reads `active_effects` back. There is zero code in the entire `CombatInstance` class that references `active_effects`. The data is written and then completely ignored.

### Architecture Patterns

- **Effect Registry** (`server/core/effects/`) — handles one-time effect application. DoT ticking is NOT an effect registry concern — it's a combat instance turn-management concern.
- **CombatInstance** (`server/combat/instance.py`) — owns turn order, action resolution, and mob attacks. DoT ticking belongs here as part of turn resolution.
- **DoT data format** in `active_effects`: `{type: "dot", subtype: "poison", value: 6, remaining: 3}`

### Existing Code to Reuse

- `_mob_attack_target()` (instance.py:230-246) — reference for shield-respecting damage application
- `_advance_turn()` (instance.py:207-228) — dead player skip logic (line 222-226) already handles players killed by any source
- `is_finished` property (instance.py:277-285) — checks mob HP and all player HP, will auto-detect DoT kills
- `handle_dot()` (dot.py:5-28) — the recording side is correct, do NOT modify

### Critical Constraints

- **DO NOT** modify `dot.py` — the recording side is correct
- **DO NOT** change the `active_effects` data format — it's already stored correctly
- **DO** process DoTs at the START of each action (before card/item effects), so DoT kills happen before the player wastes an action
- **DO** process DoTs on BOTH mob and current player — the system should be symmetric even if mobs can't currently apply DoTs
- **DO** include tick results in the action result dict so the client can display them
- **Shield handling**: When ticking DoTs on players, respect shield (absorb damage from shield first, then HP). Use same logic as `_mob_attack_target()`.

### Affected Cards

Two cards in `data/cards/starter_cards.json` are currently broken:
- `venom_fang`: DoT poison 6 damage for 3 turns (currently does 0 DoT damage)
- `poison_strike`: 8 physical + DoT poison 4 damage for 3 turns (only the 8 physical works)

### What NOT to Build

- No new effect types — just make existing DoT ticking work
- No mob DoT abilities — just ensure player DoTs on mobs tick (mob-on-player DoTs will work automatically if ever added)
- No DoT stacking rules (combine/refresh) — multiple DoTs tick independently
- No DoT resistance/immunity system

### Project Structure Notes

- `server/combat/instance.py` — Primary change: add `_process_dot_effects()`, call from `play_card()`, `use_item()`, `pass_turn()`
- `web-demo/js/game.js` — Minor change: render DoT tick results in combat turn display
- `tests/` — New test file or add to existing combat tests

### References

- [Source: server/core/effects/dot.py — lines 5-28 — DoT recording handler]
- [Source: server/combat/instance.py — lines 72-141 — action resolution methods]
- [Source: server/combat/instance.py — lines 207-228 — turn advance and dead player skip]
- [Source: server/combat/instance.py — lines 230-246 — mob attack with shield logic]
- [Source: server/combat/instance.py — lines 277-293 — combat end detection]
- [Source: data/cards/starter_cards.json — venom_fang and poison_strike definitions]
- [Source: _bmad-output/implementation-artifacts/issues/ISS-005-dot-effects-never-tick.md — original bug report]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Completion Notes List
- Task 1: Added `_process_dot_effects()` method to CombatInstance — iterates active_effects, applies damage (with shield absorption), decrements remaining, removes expired, returns tick results. Non-dot effects are preserved.
- Task 2: Integrated DoT processing into `play_card()`, `pass_turn()`, and `use_item()` — DoTs tick on both mob and current player at the start of each action, before card/item effects. Results included as `dot_ticks` in the action result dict.
- Task 3: Verified combat end detection works — `is_finished` property checks mob HP and all player HP, auto-detecting DoT kills. Dead player skip in `_advance_turn()` handles DoT-killed players.
- Task 4: Updated web client `handleCombatTurn` to render DoT tick results with formatted messages showing subtype, damage, target, shield absorbed, and remaining turns.
- Task 5: Added 13 tests covering: single/multi DoT ticking, expiration/removal, mob kill via DoT, shield absorption on player targets, full venom_fang lifecycle (18 total damage over 3 turns), integration with play_card/pass_turn.

### File List
- `server/combat/instance.py` — Added `_process_dot_effects()`, integrated into `play_card()`, `use_item()`, `pass_turn()`
- `web-demo/js/game.js` — Added DoT tick rendering in `handleCombatTurn`
- `tests/test_dot_effects.py` — NEW: 13 tests for DoT ticking
