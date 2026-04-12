# Story 12.7: Party Combat Integration

Status: done

## Story

As a party member,
I want my nearby party members to join me in combat when I encounter a mob,
so that we can fight together as a team with scaled challenge and shared rewards.

## Acceptance Criteria

1. **Given** a player in a party moves onto a tile with an alive, non-`in_combat` hostile mob, **When** combat is triggered, **Then** all party members in the same room who are NOT already `in_combat` are pulled into the combat instance, **And** the triggering player and all joining members are set `in_combat = True`, **And** only the triggering player's party joins — other players/parties on the same tile are unaffected, **And** the mob is marked `in_combat` to prevent duplicate encounters.

2. **Given** a party combat encounter starts with N party members, **When** the `CombatInstance` is created, **Then** mob HP is scaled: `base_hp * N` (party_size at encounter time), **And** `mob.stats["max_hp"]` is also scaled to match, **And** mob HP does not rescale if members leave mid-combat (flee/death).

3. **Given** party members are pulled into combat, **When** the combat instance is created, **Then** ALL participating players (triggering player AND pulled-in party members) receive a `combat_start` message, **And** each player's `combat_start` includes their hand, the mob info, and combat state.

4. **Given** a party member sends `/flee` during party combat, **When** the flee is processed, **Then** remaining members are notified via `combat_update` (existing behavior from Story 12.6).

5. **Given** a party member dies during party combat, **When** their HP reaches 0, **Then** they respawn in `town_square` with full HP per existing death/respawn mechanic, **And** they do NOT receive combat XP, **And** party membership persists across respawn.

6. **Given** the mob is defeated in party combat, **When** combat ends in victory, **Then** combat XP is calculated per existing formula (`calculate_combat_xp(hit_dice, charisma)` in `server/core/xp.py:11`), **And** `XP_PARTY_BONUS_PERCENT` (default 10) is applied ONLY if 2+ players are in the combat instance at victory, **And** XP (with bonus if applicable) is awarded to each surviving combat participant via `grant_xp()`.

7. **Given** a mob is defeated in party combat, **When** loot is generated, **Then** each surviving combat participant receives an independent loot roll from the mob's loot table via `generate_loot()` (`server/items/loot.py:42`), **And** each participant's loot is added to their inventory independently, **And** each participant's `combat_end` message includes their own loot.

8. **Given** a player `/party leave`s during active party combat, **When** the leave is processed, **Then** the player remains in the combat instance — party leave does not affect current combat, **And** XP is calculated based on combat participants at victory, not current party state.

9. **Given** a non-party player in the same room, **When** a party member triggers combat, **Then** the non-party player is NOT pulled into combat.

10. **Given** a party member in the same room is already `in_combat` (different combat instance), **When** another party member triggers a new encounter, **Then** the already-in-combat member is NOT pulled into the new encounter.

11. **Given** a solo player (not in a party) triggers combat, **When** the encounter is processed, **Then** existing solo combat behavior is preserved exactly (no HP scaling, no party bonus XP).

## Tasks / Subtasks

- [x] Task 1: Modify `_handle_mob_encounter` to gather eligible party members (AC: #1, #2, #3, #9, #10, #11)
  - [x] 1.1: After trade cancellation and NPC validation, check if triggering player is in a party via `game.party_manager.get_party(entity_id)`.
  - [x] 1.2: If in a party, gather eligible members: iterate `party.members`, include members where (a) `game.connection_manager.get_room(mid) == room_key` (same room), (b) `game.player_entities[mid]["entity"].in_combat is False` (not already in combat), and (c) `mid != entity_id` (not the triggering player, already included).
  - [x] 1.3: Build `all_player_ids = [entity_id] + eligible_members` and `player_stats_map` with defaulted combat keys for each.
  - [x] 1.4: Scale mob HP before calling `start_combat()`: `mob_stats["hp"] *= len(all_player_ids)`, `mob_stats["max_hp"] *= len(all_player_ids)`.
  - [x] 1.5: Cancel active trades for all eligible members (same pattern as triggering player).
  - [x] 1.6: Call `game.combat_manager.start_combat(mob_name, mob_stats, all_player_ids, player_stats_map, card_defs, ...)` — this handles adding all participants.
  - [x] 1.7: Mark all participating players `in_combat = True`.
  - [x] 1.8: Send `combat_start` message to ALL participants (not just triggering player).
  - [x] 1.9: Solo player path: if not in a party or no eligible members, pass `[entity_id]` as single-element list — no HP scaling. Existing behavior preserved.

- [x] Task 2: Modify `_check_combat_end` for party XP bonus and per-player loot (AC: #5, #6, #7)
  - [x] 2.1: On victory, after getting `rewards_per_player` from `instance.get_combat_end_result()` (which calls `calculate_combat_xp(hit_dice, cha)` per player inside `CombatInstance.get_combat_end_result()` at instance.py:419), apply the party bonus in the handler: if `len(participant_ids) >= 2`, multiply each player's XP in `rewards_per_player[eid]["xp"]` by `(1 + settings.XP_PARTY_BONUS_PERCENT / 100)` using `math.floor()`. Import `math` and `settings` in combat.py.
  - [x] 2.2: Dead players (`hp <= 0`) should NOT receive XP — this is a BEHAVIOR CHANGE from current code. Currently `_check_combat_end` (combat.py:114-119) grants XP to ALL participants without checking HP. Add an HP > 0 check: skip the `grant_xp()` call for participants where `entity.stats.get("hp", 0) <= 0`. Dead players still get `in_combat = False` and respawn — only XP is skipped.
  - [x] 2.3: On victory with loot, each surviving participant gets an independent `generate_loot()` call (not shared loot). Currently (combat.py:66) `generate_loot()` is called once and the same items are given to all. Restructure: move `generate_loot()` inside the per-player loop (combat.py:74), call it per surviving player (HP > 0), so each gets their own roll. Dead players get no loot.
  - [x] 2.4: Each player's `combat_end` message includes their individual loot — the existing `player_end_result` dict is already per-player (combat.py:130), so attach each player's loot to their own result dict.

- [x] Task 3: Verify party leave does not affect combat (AC: #8)
  - [x] 3.1: Review `_handle_leave` (line 389) in `server/net/handlers/party.py` — confirm it does NOT remove the player from combat or call `combat_manager.remove_player()`. Verified: it only calls `party_manager.remove_member()` and sends `party_update`. No combat interaction — safe.

- [x] Task 4: Write tests (AC: #1-11)
  - [x] 4.1: Create `tests/test_party_combat.py` with tests covering:
    - Party member triggers mob → all same-room non-combat party members join
    - Mob HP scaled by party size at encounter
    - All participants receive `combat_start`
    - Solo player (no party) → no scaling, existing behavior
    - Party member in different room → not pulled in
    - Party member already in combat → not pulled in
    - Non-party player in same room → not pulled in
    - Party XP bonus applied when 2+ survivors at victory
    - Solo combat → no party XP bonus
    - Dead player does NOT receive XP
    - Per-player independent loot rolls on victory
    - Party leave during combat → player stays in combat
    - Flee during party combat → remaining notified (existing behavior)
    - Trade cancelled for all pulled-in members

## Dev Notes

### Architecture Compliance

- **Handler pattern**: Modify existing `_handle_mob_encounter()` in `server/net/handlers/movement.py` (line 115). Do NOT create a new handler.
- **Combat handler**: Modify `_check_combat_end()` in `server/net/handlers/combat.py` (line 49) for XP bonus and per-player loot.
- **`start_combat()` API**: Already accepts `str | list[str]` for `player_ids` and `dict[str, dict]` for `player_stats_map` (added in Story 12.6, `server/combat/manager.py:44`).
- **Error format**: `{"type": "error", "detail": "..."}` — matches all existing handler error responses.
- **Import guard**: `TYPE_CHECKING` for `Game` already in movement.py (line 16) and combat.py (line 14).
- **`from __future__ import annotations`** already present in both files.

### Key Implementation Details

**Mob encounter flow (modified `_handle_mob_encounter`, movement.py:115):**
1. Validate NPC (existing: alive, not in_combat) — keep as-is
2. Cancel triggering player's trade (existing) — keep as-is
3. NEW: Check party membership → gather eligible same-room, non-combat members
4. NEW: Cancel trades for eligible members
5. Mark NPC `in_combat = True` (existing) — keep as-is
6. Load card defs (existing) — keep as-is
7. Build mob_stats (existing) — then NEW: scale HP by len(all_player_ids) if > 1
8. Build player_stats_map for ALL participants (NEW: loop over all_player_ids)
9. Call `start_combat()` with all_player_ids (existing call, just pass list)
10. Mark ALL participants `in_combat = True` (NEW: loop)
11. Send `combat_start` to ALL participants (NEW: loop, get each player's WS)

**XP bonus logic (modified `_check_combat_end`, combat.py:49):**
- `get_combat_end_result()` (instance.py:419) already computes per-player base XP via `calculate_combat_xp(hit_dice, cha)` and returns `rewards_per_player[eid] = {"xp": ...}`
- In the handler, AFTER getting `rewards_per_player`, apply party bonus: if `len(participant_ids) >= 2`, `rewards_per_player[eid]["xp"] = math.floor(xp * (1 + settings.XP_PARTY_BONUS_PERCENT / 100))` for each player
- Dead players (hp <= 0): skip `grant_xp()` call entirely — this is a NEW behavior (currently all participants get XP regardless of HP)
- Dead players still get `in_combat = False`, combat-only stat cleanup, and respawn
- `grant_xp()` called with `apply_cha_bonus=False` — CHA is already applied in `calculate_combat_xp()`

**Per-player loot (modified `_check_combat_end`, combat.py:59):**
- Current: `generate_loot()` called once → same items given to all participants
- New: `generate_loot()` called per surviving participant → each gets independent roll
- Each player's `combat_end` includes their individual loot in `player_end_result`

### Existing Code to Reuse

- **`game.party_manager.get_party(entity_id)`** (`server/party/manager.py:104`): Returns `Party` or `None`. Use to check party membership.
- **`party.members`** (`server/party/manager.py:17`): Ordered list of entity_ids.
- **`game.connection_manager.get_room(entity_id)`** (`server/net/connection_manager.py:46`): Returns room_key for player.
- **`game.combat_manager.start_combat()`** (`server/combat/manager.py:44`): Accepts `str | list[str]` for player_ids. Already handles multi-player setup.
- **`game.trade_manager.cancel_trades_for(entity_id)`** (`server/trade/manager.py`): Cancel trade for a player, returns cancelled session or None.
- **`generate_loot(loot_table_key)`** (`server/items/loot.py:42`): Returns list of loot item dicts.
- **`calculate_combat_xp(hit_dice, charisma)`** (`server/core/xp.py:11`): Returns base XP with CHA bonus.
- **`grant_xp()`** (`server/core/xp.py:29`): Apply XP, persist, send message, level-up detection.
- **`settings.XP_PARTY_BONUS_PERCENT`** (`server/core/config.py:29`): Default 10.

### What NOT to Change

- **`CombatInstance`** (`server/combat/instance.py`): No changes needed — already supports N players (Story 12.6).
- **`CombatManager`** (`server/combat/manager.py`): No changes needed — `start_combat()` already accepts lists.
- **`PartyManager`** (`server/party/manager.py`): No changes needed — query-only usage.
- **`handle_flee()`** (`server/net/handlers/combat.py:202`): Already handles multi-player flee with `combat_update` broadcast.
- **`_broadcast_combat_state()`** (`server/net/handlers/combat.py:37`): Already broadcasts to all participants.
- **Web client** (`web-demo/`): No changes needed — combat UI already handles multi-player combat_start, combat_update, combat_end messages (verified in Story 12.6).

### Testing Patterns

- **Unit tests**: Create `Game()`, `PartyManager`, register 2-3 player entities in same room, create party, trigger mob encounter, verify all participants join combat with scaled mob HP.
- **Mock pattern**: `AsyncMock` for WebSockets, `MagicMock(return_value=mock_ctx)` for session_factory (sync callable returning async context manager).
- **Flat test file**: `tests/test_party_combat.py` — no nested directories.
- **Existing test preservation**: All existing combat test files must pass unchanged.

### Project Structure Notes

- New files: `tests/test_party_combat.py`
- Modified files:
  - `server/net/handlers/movement.py` (modify `_handle_mob_encounter` for party member gathering and HP scaling)
  - `server/net/handlers/combat.py` (modify `_check_combat_end` for party XP bonus and per-player loot)
- No new modules, packages, dependencies, or config values.

### References

- [Source: `_bmad-output/planning-artifacts/epics.md` — Story 12.7, lines 2772-2838]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — Epic 12 Party Combat, lines 645-649]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — ADR-5, line 665]
- [Source: `_bmad-output/project-context.md` — Epic 12 patterns, lines 197-220]
- [Source: `server/net/handlers/movement.py` — `_handle_mob_encounter`, lines 115-188]
- [Source: `server/net/handlers/combat.py` — `_check_combat_end`, lines 49-166]
- [Source: `server/combat/manager.py` — `start_combat()`, lines 44-68]
- [Source: `server/party/manager.py` — `get_party()`, line 104]
- [Source: `server/core/xp.py` — `calculate_combat_xp()`, line 11; `grant_xp()`, line 29]
- [Source: `server/items/loot.py` — `generate_loot()`, line 42]
- [Source: `server/core/config.py` — `XP_PARTY_BONUS_PERCENT`, line 29]
- [Source: `_bmad-output/implementation-artifacts/12-6-combatinstance-multi-player-extension.md` — Previous story context]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Modified `_handle_mob_encounter` (movement.py) to gather eligible party members from same room, scale mob HP by party size, cancel trades for all, send `combat_start` to all participants
- Extracted `_cancel_trade_for()` helper to reduce code duplication in trade cancellation
- Modified `_check_combat_end` (combat.py) to apply `XP_PARTY_BONUS_PERCENT` when 2+ participants at victory
- Dead players (hp <= 0) now skip XP grant and loot — behavior change from previous code
- Loot generation changed from single shared roll to independent per-player rolls for surviving participants
- Each player's `combat_end` message includes their individual loot (not shared)
- Verified `_handle_leave` in party handler does not affect combat state — party leave during combat is safe
- Fixed existing `test_combat_entry_cancels_trade` in test_trade.py to work with new party-aware encounter flow
- 18 new tests in `tests/test_party_combat.py` covering all 11 ACs
- 805 tests pass total (787 original + 18 new), zero regressions, zero warnings
- Code review: 1 LOW finding fixed (dead player combat_end message showed non-zero XP rewards — now zeroed)

### File List

New files:
- tests/test_party_combat.py

Modified files:
- server/net/handlers/movement.py (party member gathering, HP scaling, trade cancel for all, combat_start to all)
- server/net/handlers/combat.py (party XP bonus, dead player XP skip, per-player loot)
- tests/test_trade.py (fixed test_combat_entry_cancels_trade for party-aware encounter)
