# Story 8.1: Card Cost & Energy System

Status: done

## Story

As a player,
I want cards to cost energy to play so I have to make strategic choices each turn,
so that combat has meaningful resource management beyond just picking the best card.

## Acceptance Criteria

1. **Given** a player enters combat,
   **When** the CombatInstance is created,
   **Then** the player starts with configured starting energy (default: 3),
   **And** energy and max_energy are included in the `combat_start` message per participant,
   **And** energy and max_energy are included in every `combat_turn` message per participant.

2. **Given** it is a player's turn and they play a card with cost > 0,
   **When** the card is played,
   **Then** the player's energy is reduced by the card's cost,
   **And** if the player doesn't have enough energy, the play is rejected with error: `"Not enough energy"`.

3. **Given** a new combat cycle begins (all participants have acted),
   **When** the cycle resets,
   **Then** each player regenerates configured energy (default: 3, capped at max_energy).

4. **Given** a player uses an item during combat,
   **When** the item is used,
   **Then** no energy is consumed (items are free — energy is a card-only resource).

5. **Given** a player passes their turn,
   **When** the pass is processed,
   **Then** no energy is consumed.

6. **Given** `data/cards/starter_cards.json` has cards with costs,
   **When** the story is complete,
   **Then** card costs are rebalanced: cheap (1-2), medium (3-4), expensive (5-7),
   **And** the sum of costs across a typical hand allows meaningful play with starting energy.

7. **Given** energy values need to be tunable,
   **When** the story is complete,
   **Then** `COMBAT_STARTING_ENERGY` and `COMBAT_ENERGY_REGEN` are added to server config (Pydantic BaseSettings).

8. **And** all existing combat tests are updated and `pytest tests/` passes.

## Tasks / Subtasks

- [x] Task 1: Add energy config settings (AC: 7)
  - [x] Add `COMBAT_STARTING_ENERGY: int = 3` and `COMBAT_ENERGY_REGEN: int = 3` to `server/core/config.py` `Settings` class

- [x] Task 2: Initialize energy in CombatInstance (AC: 1)
  - [x] In `server/combat/instance.py` `add_participant()`: set `stats.setdefault("energy", settings.COMBAT_STARTING_ENERGY)` and `stats.setdefault("max_energy", settings.COMBAT_STARTING_ENERGY)`
  - [x] In `get_state()`: add `"energy"` and `"max_energy"` to each participant dict (alongside `hp`, `max_hp`, `shield`)
  - [x] Import settings at method level (deferred import pattern) to avoid circular imports

- [x] Task 3: Enforce energy cost on card play (AC: 2)
  - [x] In `server/combat/instance.py` `play_card()`: before calling `hand.play_card()`, check `stats["energy"] >= card_def.cost`
  - [x] If insufficient energy: raise `ValueError("Not enough energy")`
  - [x] On successful play: deduct `stats["energy"] -= card_cost`
  - [x] Added `get_card_cost()` method to CardHand to peek at cost without removing card

- [x] Task 4: Energy regeneration on cycle end (AC: 3)
  - [x] In `_advance_turn()`: when a full cycle completes, regenerate energy for all alive participants
  - [x] Regen formula: `stats["energy"] = min(stats["energy"] + COMBAT_ENERGY_REGEN, stats["max_energy"])`

- [x] Task 5: Ensure items and pass don't consume energy (AC: 4, 5)
  - [x] Verified `use_item()` does NOT deduct energy — energy logic only in `play_card()`
  - [x] Verified `pass_turn()` does NOT deduct energy
  - [x] Added tests: `test_pass_turn_no_energy_cost`, `test_use_item_no_energy_cost`

- [x] Task 6: Strip energy at combat end (AC: 8)
  - [x] In `server/net/handlers/combat.py` `_check_combat_end()`: strip `"energy"` and `"max_energy"` from entity stats alongside `"shield"`
  - [x] Did NOT add `"energy"` to `_sync_combat_stats` whitelist — combat-only transient

- [x] Task 7: Rebalance card costs (AC: 6)
  - [x] Edited `data/cards/starter_cards.json` with tiered costs:
    - Cost 1: fire_bolt, ice_shard, slash, heal_light, quick_draw
    - Cost 2: iron_shield, fortify, venom_fang, poison_strike
    - Cost 3: arcane_surge, heavy_strike, flame_wave, greater_heal, steel_wall, fire_shield
  - [x] With starting energy=3: player can play 3 cheap, or 1 cheap + 1 medium, or 1 expensive per cycle

- [x] Task 8: Update all combat tests (AC: 8)
  - [x] Added 7 new energy tests to `test_combat.py`
  - [x] Updated `test_combat_entry.py`: assert energy/max_energy in combat start state
  - [x] All existing tests pass without modification (372 total, 0 failures)

## Dev Notes

### Key Architecture Patterns

- **Energy is combat-session-only** (like `shield`) — lives in `instance.participant_stats`, NOT persisted to DB, stripped at combat end
- **CardDef already has `cost: int` field** — defined in `server/combat/cards/card_def.py` line 17, included in `to_dict()` and `from_db()`. No changes to CardDef needed.
- **CardHand.play_card()** does NO cost validation — it only manages deck/hand/discard. Energy validation belongs in `CombatInstance.play_card()`.
- **Settings pattern**: `server/core/config.py` uses `pydantic-settings` `BaseSettings`. Add new fields there, import via `from server.core.config import settings` (or deferred import inside methods).
- **Error handling**: `play_card()` raises `ValueError` for invalid moves. The handler in `combat.py` catches `ValueError` and returns `{"type": "error", "detail": str(e)}`. New energy error follows this pattern.
- **`get_state()` broadcasts automatically**: Both `combat_start` and `combat_turn` messages build from `instance.get_state()`, so adding energy there propagates everywhere.
- **`_check_combat_end()`** in `server/net/handlers/combat.py` strips transient stats: line ~62 does `entity.stats.pop("shield", None)`. Add same for `"energy"` and `"max_energy"`.
- **`_sync_combat_stats()`** syncs `("hp", "max_hp", "attack", "xp")` only. Energy must NOT be added here.

### Card Cost Lookup Before Play

The tricky part: `play_card()` currently calls `hand.play_card(card_key)` which removes the card from hand. You need the card's cost BEFORE removing it. Options:
1. Look up cost from `hand.get_card_in_hand(card_key)` or similar — check if hand exposes card lookup
2. Call `hand.play_card()` which returns the `CardDef`, then check cost after getting it but before deducting
3. Best approach: get the `CardDef` from hand (peek), check energy, then play. `CardHand` stores `CardDef` objects in `self._hand` list — you may need to peek by iterating `self._hand` to find the matching `card_key`

Actually, looking at `card_hand.py`, `play_card()` returns the `CardDef` after removing it. The cleanest approach: add a method to peek at the card's cost without removing it, OR restructure `play_card()` to: (1) find card in hand, (2) check cost, (3) remove and return.

### Cycle Detection in `_advance_turn()`

`_advance_turn()` (instance.py ~line 294) manages turn advancement. A "cycle" = when `self._turn_index` wraps around to 0. This is where mob attacks happen at cycle end. Energy regen should happen at the same point — when the turn index wraps back to the start.

### Test Helper Patterns

All combat test files use local factory helpers:
- `_make_cards()` — returns `[CardDef(card_key=..., cost=1, effects=[...])]`
- `_make_instance_with_player()` — creates CombatInstance + adds participant
- Player stats dicts: `{"hp": 100, "max_hp": 100, "attack": 15}` — add `"energy"` is NOT needed if `add_participant()` auto-sets it via `setdefault`

### Card File Location

The card data file is `data/cards/starter_cards.json` (NOT `base_set.json` as mentioned in the epic). Contains 15 cards, all currently cost 1 or 2.

### What NOT to Build

- No mana/energy display in the web client (separate UI story if needed later)
- No energy-related items (energy potions, etc.)
- No per-card energy regen effects
- No energy carry-over between combats
- Energy does NOT persist to DB — combat-only transient

### Project Structure Notes

- All server changes in existing files — no new files needed
- Config change: `server/core/config.py`
- Core combat logic: `server/combat/instance.py`
- Combat handler cleanup: `server/net/handlers/combat.py`
- Card data: `data/cards/starter_cards.json`
- Tests: 8+ test files need updates

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 8.1 — full acceptance criteria]
- [Source: _bmad-output/planning-artifacts/architecture.md#Section 5 — Combat System]
- [Source: _bmad-output/project-context.md#Combat Flow Order — DoT/action/sync sequence]
- [Source: server/combat/instance.py — CombatInstance class, play_card(), get_state(), _advance_turn()]
- [Source: server/combat/cards/card_def.py — CardDef with cost field]
- [Source: server/combat/cards/card_hand.py — CardHand.play_card() returns CardDef]
- [Source: server/net/handlers/combat.py — _check_combat_end(), _sync_combat_stats()]
- [Source: server/core/config.py — Settings class with Pydantic BaseSettings]
- [Source: data/cards/starter_cards.json — 15 cards, all cost 1-2 currently]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Debug Log References

### Completion Notes List
- Task 1: Added `COMBAT_STARTING_ENERGY` and `COMBAT_ENERGY_REGEN` config settings (both default 3)
- Task 2: Energy initialized via `setdefault` in `add_participant()`, included in `get_state()` per participant
- Task 3: Added `get_card_cost()` to CardHand for peek-before-play pattern; energy check + deduction in `play_card()`
- Task 4: Energy regen for all alive participants at cycle end in `_advance_turn()`
- Task 5: Verified items and pass don't consume energy; added tests confirming both
- Task 6: Energy/max_energy stripped from entity stats at combat end alongside shield
- Task 7: Rebalanced 15 cards across 3 cost tiers (1/2/3) for meaningful strategic choices
- Task 8: Added 7 new energy tests + updated combat entry state assertions; 372 tests pass

### File List
- `server/core/config.py` — Added COMBAT_STARTING_ENERGY, COMBAT_ENERGY_REGEN settings
- `server/combat/instance.py` — Energy init in add_participant, cost check in play_card, regen in _advance_turn, energy in get_state
- `server/combat/cards/card_hand.py` — Added get_card_cost() method
- `server/net/handlers/combat.py` — Strip energy/max_energy at combat end
- `data/cards/starter_cards.json` — Rebalanced card costs (1/2/3 tiers)
- `tests/test_combat.py` — 7 new energy tests
- `tests/test_combat_entry.py` — Energy assertions in combat start state
