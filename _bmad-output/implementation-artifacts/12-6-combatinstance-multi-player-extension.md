# Story 12.6: CombatInstance Multi-Player Extension

Status: done

## Story

As a developer,
I want the CombatInstance to support multiple players in a single combat,
so that party combat can be built on a proven multi-player combat engine.

## Acceptance Criteria

1. **Given** the existing `CombatInstance` class, **When** Story 12.6 implementation begins, **Then** the developer audits `CombatInstance` internals: verify `participants` supports a list, turn cycling handles N players, victory/defeat conditions work with N players.

2. **Given** the existing `CombatManager.create_instance()` creates a combat instance, **When** Story 12.6 extends the flow for multi-player, **Then** `CombatManager` gains a `start_combat()` method that accepts either a single `entity_id` or a list of `entity_ids`, creates the instance, adds all participants, registers player-to-instance mappings, and returns the instance, **And** solo combat (single player) continues to work identically to pre-12.6 behavior, **And** all existing combat tests pass without modification.

3. **Given** a combat instance is created with N players, **When** turns are processed, **Then** turn order is round-robin through the player list (first player in list goes first), **And** each player gets one action per turn (play card, use item, pass, or flee).

4. **Given** a combat instance has multiple players, **When** end of cycle is reached (all players have acted), **Then** mob attacks one random player from the active player list, **And** only players still in combat are eligible targets.

5. **Given** a player flees from multi-player combat, **When** the flee is processed, **Then** the player is removed from the combat instance's active player list, **And** their `in_combat` flag is cleared, **And** turn cycling continues with remaining players.

6. **Given** a player dies in multi-player combat, **When** their HP reaches 0, **Then** their turns are skipped by `_advance_turn()`, **And** death/respawn mechanic applies per existing behavior.

7. **Given** all players in a combat instance have fled or died, **When** no active players remain, **Then** combat ends in defeat, **And** mob HP resets (existing behavior via NPC `in_combat = False` release).

8. **Given** the mob's HP reaches 0 in multi-player combat, **When** combat ends in victory, **Then** victory is detected correctly regardless of which player dealt the killing blow, **And** all surviving players in the instance are eligible for rewards.

## Tasks / Subtasks

- [x] Task 1: Audit CombatInstance for N-player readiness (AC: #1)
  - [x] 1.1: Verify `self.participants` is already `list[str]` (line 34 of `server/combat/instance.py`) — it is, no change needed.
  - [x] 1.2: Verify `add_participant()` (line 41) supports multiple calls — it does (appends to list).
  - [x] 1.3: Verify `remove_participant()` (line 56) handles turn index adjustment correctly for N players — it does (adjusts `_turn_index` and `_actions_this_cycle`).
  - [x] 1.4: Verify `_advance_turn()` (line 308) cycles round-robin through N participants — it does (`_turn_index + 1 % len`).
  - [x] 1.5: Verify `_advance_turn()` skips dead players (line 333) — it does (loop up to `len(participants)` checking HP).
  - [x] 1.6: Verify `is_finished` (line 407) handles N players — `not self.participants` catches all-fled, `all(hp <= 0)` catches all-dead.
  - [x] 1.7: Verify `get_combat_end_result()` (line 418) computes per-player rewards for all participants — it does (loops `self.participants`).
  - [x] 1.8: Verify cycle-end mob attack (line 317) uses `random.choice(self.participants)` — **BUG**: this includes dead players. In solo combat, dead player = `is_finished`, so this never fires on a dead target. In multi-player, one player can be dead while others are alive, so the mob could attack a dead player. Fix needed: filter for alive participants before `random.choice`.
  - [x] 1.9: Verify DoT processing ticks only the current player's DoTs (not all players') — it does (called with `self.participant_stats[entity_id]` per action).

- [x] Task 1b: Fix mob cycle-end targeting to exclude dead players (AC: #4)
  - [x] 1b.1: In `server/combat/instance.py` `_advance_turn()` (line 317), change `random.choice(self.participants)` to filter for alive players: `alive = [eid for eid in self.participants if self.participant_stats[eid]["hp"] > 0]`, then `target = random.choice(alive) if alive else None`. Only call `_mob_attack_target(target)` if `target` is not None.
  - [x] 1b.2: Add test in Task 6: mob cycle-end attack never targets dead player when alive players exist.

- [x] Task 2: Add `start_combat()` to CombatManager (AC: #2)
  - [x] 2.1: In `server/combat/manager.py`, add a `start_combat()` method that:
    - Accepts `mob_name`, `mob_stats`, `player_ids: str | list[str]`, `player_stats_map: dict[str, dict]`, `card_defs: list[CardDef]`, `npc_id=None`, `room_key=None`, `mob_hit_dice=0`
    - Normalizes `player_ids` to a list (`[player_ids] if isinstance(player_ids, str) else list(player_ids)`)
    - Calls `self.create_instance(...)` to create the instance
    - For each player in `player_ids`: calls `instance.add_participant(eid, player_stats_map[eid], card_defs)` and `self.add_player_to_instance(eid, instance.instance_id)`
    - Returns the `CombatInstance`
  - [x] 2.2: Import `CardDef` under `TYPE_CHECKING` guard in `server/combat/manager.py`

- [x] Task 3: Refactor `_handle_mob_encounter` to use `start_combat()` (AC: #2)
  - [x] 3.1: In `server/net/handlers/movement.py`, update `_handle_mob_encounter()` (lines 172-183) to call `game.combat_manager.start_combat()` instead of manually calling `create_instance()`, `add_participant()`, and `add_player_to_instance()` separately.
  - [x] 3.2: Build `player_stats_map = {entity_id: player_stats}` and pass to `start_combat()`.
  - [x] 3.3: This is a refactor — the solo combat path should behave identically.

- [x] Task 4: Update disconnect cleanup for multi-player awareness (AC: #5, #7)
  - [x] 4.1: Review `_cleanup_player()` in `server/net/handlers/auth.py` (lines 57-90) — it already handles multi-player: removes participant, checks if last, notifies remaining. No changes expected; confirmed with tests.

- [x] Task 5: Update combat handler for multi-player broadcasting (AC: #3, #4, #5, #6, #8)
  - [x] 5.1: Review `_broadcast_combat_state()` in `server/net/handlers/combat.py` (line 37) — already broadcasts to all `instance.participants`. No changes needed.
  - [x] 5.2: Review `_check_combat_end()` (line 49) — already iterates all `participant_ids`, applies per-player rewards, handles respawn. No changes needed.
  - [x] 5.3: Review `handle_flee()` (line 202) — already removes participant, notifies remaining, handles last-player case. No changes needed.

- [x] Task 6: Write multi-player combat tests (AC: #1-8)
  - [x] 6.1: Create `tests/test_combat_multiplayer.py` with tests for:
    - `start_combat()` with single player (backward compat — same as existing solo flow)
    - `start_combat()` with multiple players (2-3 players)
    - Turn order is round-robin through participant list
    - Each player gets one action per turn cycle
    - Cycle-end mob attack targets random player from active list
    - Player flee removes from participants, turn cycling continues
    - Dead player turns are skipped
    - All players fled → combat ends in defeat (`is_finished` is True, `not participants`)
    - All players dead → combat ends in defeat (`all hp <= 0`)
    - Mob killed → victory, all surviving players get rewards
    - Turn index adjustment when player before current index is removed
    - Turn index adjustment when player at current index is removed
    - Mob cycle-end attack only targets alive players (not dead ones)
    - `_cleanup_player` handles multi-player combat disconnect (remaining participants notified)
    - Solo combat via `start_combat()` produces identical behavior to direct `create_instance`+`add_participant`

## Dev Notes

### Architecture Compliance

- **Handler pattern**: No new handlers needed — existing `handle_play_card`, `handle_flee`, `handle_pass_turn`, `handle_use_item_combat` all work with multi-player already (they look up the calling player's instance and operate on it).
- **Import guard**: `TYPE_CHECKING` already used in `server/combat/manager.py` (line 5). Add `CardDef` import under it for the `start_combat()` type hint.
- **`from __future__ import annotations`** already present in `server/combat/manager.py` (line 2).
- **Error format**: `{"type": "error", "detail": "..."}` — matches all existing handler error responses.
- **ADR-5**: Extend `CombatInstance`, don't rewrite. Preserve all 762 existing tests.

### Key Finding: CombatInstance Already Supports N Players

The audit reveals that `CombatInstance` is **already designed for N players**:
- `self.participants: list[str]` (line 34) — a list, not a single reference
- `add_participant()` appends to the list (line 47)
- `remove_participant()` handles turn index adjustment (lines 56-70)
- `_advance_turn()` cycles round-robin with dead-player skipping (lines 308-339)
- `is_finished` checks `not self.participants` (all fled) and `all(hp <= 0)` (all dead) (lines 407-416)
- `get_combat_end_result()` computes per-player rewards for all participants (lines 418-433)
- Cycle-end mob attack uses `random.choice(self.participants)` (line 317)

**The primary work is:**
1. Adding a convenience `start_combat()` method to `CombatManager` that accepts a list of player IDs (Task 2)
2. Refactoring `_handle_mob_encounter` to use it (Task 3)
3. Writing comprehensive multi-player tests to prove correctness (Task 6)

### Existing Code to Reuse

- **`CombatInstance.add_participant(entity_id, player_stats, card_defs)`** (`server/combat/instance.py:41`): Already supports sequential calls for N players.
- **`CombatInstance.remove_participant(entity_id)`** (`server/combat/instance.py:56`): Handles turn index adjustment when removing from N-player list.
- **`CombatManager.create_instance()`** (`server/combat/manager.py:21`): Creates and registers a combat instance. `start_combat()` will wrap this.
- **`CombatManager.add_player_to_instance(entity_id, instance_id)`** (`server/combat/manager.py:43`): Registers player-to-instance mapping.
- **`_cleanup_player()`** (`server/net/handlers/auth.py:25`): Already handles multi-player combat disconnect (syncs stats, removes participant, notifies remaining, cleans up if last).
- **`_check_combat_end()`** (`server/net/handlers/combat.py:49`): Already handles per-player rewards, respawn for all defeated players.
- **`_broadcast_combat_state()`** (`server/net/handlers/combat.py:37`): Already syncs and broadcasts to all participants.
- **`handle_flee()`** (`server/net/handlers/combat.py:202`): Already handles flee with remaining-participant notification.

### What NOT to Change

- **`CombatInstance` class**: No structural changes needed — it already supports N players. One targeted fix required: `_advance_turn()` must filter dead players from mob cycle-end targeting (Task 1b). Do not refactor other internals.
- **Combat handlers** (`server/net/handlers/combat.py`): Already multi-player aware. Do not modify.
- **`_cleanup_player`** (`server/net/handlers/auth.py`): Already handles multi-player cleanup. Do not modify.
- **Web client** (`web-demo/`): No changes needed — combat UI already shows participants list and handles combat_update messages.

### Testing Patterns

- **Unit tests**: Create `CombatInstance` directly, add multiple participants via `add_participant()`, test turn cycling, flee, death, victory/defeat.
- **Manager tests**: Create `CombatManager`, call `start_combat()` with 1 player and multiple players, verify all mappings.
- **Integration tests**: Use `_handle_mob_encounter` pattern — create `Game`, register entities, verify `combat_start` sent to triggering player (solo path unchanged).
- **Flat test file**: `tests/test_combat_multiplayer.py` — no nested directories.
- **Existing test preservation**: All 5 existing combat test files (`test_combat.py`, `test_combat_effects.py`, `test_combat_flee.py`, `test_combat_resolution.py`, `test_combat_entry.py`) must pass unchanged.

### Project Structure Notes

- New files: `tests/test_combat_multiplayer.py`
- Modified files:
  - `server/combat/instance.py` (fix `_advance_turn()` mob targeting to exclude dead players)
  - `server/combat/manager.py` (add `start_combat()` method)
  - `server/net/handlers/movement.py` (refactor `_handle_mob_encounter` to use `start_combat()`)
- No new modules, packages, or dependencies.

### References

- [Source: `_bmad-output/planning-artifacts/epics.md` — Story 12.6, lines 2713-2770]
- [Source: `_bmad-output/planning-artifacts/epics.md` — Story 12.7, lines 2772-2838 (downstream consumer)]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — Epic 12 Party Combat, lines 645-649]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — ADR-5, line 665]
- [Source: `_bmad-output/project-context.md` — Epic 12 patterns, lines 197-220]
- [Source: `server/combat/instance.py` — CombatInstance class, full file]
- [Source: `server/combat/manager.py` — CombatManager class, full file]
- [Source: `server/net/handlers/combat.py` — Combat handlers, full file]
- [Source: `server/net/handlers/movement.py` — `_handle_mob_encounter`, lines 115-191]
- [Source: `server/net/handlers/auth.py` — `_cleanup_player` combat section, lines 57-90]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Audit confirmed CombatInstance already supports N players (list-based participants, round-robin turns, dead-player skipping, per-player rewards)
- Fixed bug in `_advance_turn()`: cycle-end mob attack could target dead players in multi-player — now filters for alive players only
- Added `start_combat()` convenience method to `CombatManager` accepting single string or list of entity_ids
- Refactored `_handle_mob_encounter` in movement handler to use `start_combat()` — solo combat path unchanged
- Verified `_cleanup_player`, `_broadcast_combat_state`, `_check_combat_end`, and `handle_flee` already handle multi-player correctly — no changes needed
- 25 new tests in `tests/test_combat_multiplayer.py` covering all ACs
- 787 tests pass total (762 original + 25 new), zero regressions, zero warnings
- Code review: 1 LOW finding fixed (conditional test assertion → explicit assertion)

### File List

New files:
- tests/test_combat_multiplayer.py

Modified files:
- server/combat/instance.py (fixed `_advance_turn()` mob targeting to exclude dead players)
- server/combat/manager.py (added `start_combat()` method, `CardDef` TYPE_CHECKING import)
- server/net/handlers/movement.py (refactored `_handle_mob_encounter` to use `start_combat()`)
