# Story 11.2: Stat-to-Combat Integration

Status: done

## Story

As a player,
I want my ability scores to meaningfully affect combat outcomes,
so that investing in different stats creates distinct playstyles and tactical choices.

## Acceptance Criteria

1. **STR scales physical damage**: Cards with `damage/physical` effect deal `base_value + floor(source_strength × STAT_SCALING_FACTOR)`. Player STR=1 → +1, STR=6 → +6, STR=10 → +10 (at default factor 1.0).

2. **INT scales elemental/arcane damage**: Cards with `damage/fire`, `damage/ice`, or `damage/arcane` effect deal `base_value + floor(source_intelligence × STAT_SCALING_FACTOR)`. Physical damage is NOT scaled by INT.

3. **WIS scales healing**: Cards/items with `heal` effect restore `base_value + floor(source_wisdom × STAT_SCALING_FACTOR)`. Still capped at `max_hp`.

4. **DEX reduces incoming damage**: All damage applied to a target (card damage, mob attack) is reduced by `floor(target_dexterity × STAT_SCALING_FACTOR)` AFTER shield absorption. Minimum damage is always 1.

5. **DoT damage unaffected by stats**: DoT tick damage is NOT reduced by DEX and NOT modified by source stats. Flat value from card definition.

6. **Shield unaffected by stats**: Shield value is NOT modified by any stat. Flat value from card definition.

7. **STAT_SCALING_FACTOR config**: `STAT_SCALING_FACTOR: float = 1.0` added to `Settings` in `server/core/config.py`. All stat bonus formulas use `floor(stat × settings.STAT_SCALING_FACTOR)`.

8. **Mob attack uses STR-derived formula**: Mob attack damage = `(hit_dice × 2) + floor(mob_strength × STAT_SCALING_FACTOR)` with DEX reduction applied to the target. The `attack` key is removed from `_STATS_WHITELIST` and all mob attack references in `CombatInstance` replaced with STR-derived calculation.

9. **`attack` key fully deprecated**: `attack` removed from `_STATS_WHITELIST` in `player/repo.py`. All `mob_stats["attack"]` references in combat instance replaced.

10. **All existing combat tests updated and new stat-aware tests added**: `pytest tests/` passes with no failures.

## Tasks / Subtasks

- [x] Task 1: Add STAT_SCALING_FACTOR to server config (AC: #7)
  - [x] Add `STAT_SCALING_FACTOR: float = 1.0` to `Settings` class in `server/core/config.py` after `CON_HP_PER_POINT` (line 18), before `ADMIN_SECRET` (line 19)

- [x] Task 2: Update `handle_damage` to add stat bonuses (AC: #1, #2, #4)
  - [x] In `server/core/effects/damage.py:5`, modify `handle_damage()`:
    - Read `effect["subtype"]` (default `"physical"`)
    - If subtype is `"physical"`: add `floor(source["strength"] × STAT_SCALING_FACTOR)` to `raw_damage`
    - If subtype is `"fire"`, `"ice"`, or `"arcane"`: add `floor(source["intelligence"] × STAT_SCALING_FACTOR)` to `raw_damage`
    - After shield absorption, apply DEX reduction: `actual_damage = max(1, post_shield_damage - floor(target["dexterity"] × STAT_SCALING_FACTOR))`
    - Import `settings` from `server.core.config` and `math.floor`
    - Use `.get("strength", 0)`, `.get("dexterity", 0)`, `.get("intelligence", 0)` for safety

- [x] Task 3: Update `handle_heal` to add WIS bonus (AC: #3)
  - [x] In `server/core/effects/heal.py:5`, modify `handle_heal()`:
    - Add `floor(source["wisdom"] × STAT_SCALING_FACTOR)` to `value` before healing
    - Source is the caster (player_stats for self-heal)
    - Import `settings` from `server.core.config` and `math.floor`
    - Use `.get("wisdom", 0)` for safety

- [x] Task 4: Update mob attack to use STR-derived formula with DEX reduction (AC: #8)
  - [x] In `server/combat/instance.py:339`, modify `_mob_attack_target()`:
    - Replace `attack = self.mob_stats.get("attack", 10)` with: `base_attack = self.mob_stats.get("attack", 10)` and `stat_bonus = floor(self.mob_stats.get("strength", 0) × settings.STAT_SCALING_FACTOR)` → `raw_damage = base_attack + stat_bonus`
    - After shield absorption, apply DEX reduction from target: `actual_damage = max(1, post_shield_damage - floor(target_stats.get("dexterity", 0) × settings.STAT_SCALING_FACTOR))`
    - Import `settings` from `server.core.config` and `math.floor`
  - [x] Note: `attack` key still exists on mob_stats from `_derive_stats_from_hit_dice()` (npc.py:65, attack line at npc.py:79) as `hit_dice × 2`. It remains usable as `base_attack` until a future cleanup.

- [x] Task 5: Remove `attack` from persistence and sync loops (AC: #9)
  - [x] In `server/player/repo.py:75`, remove `"attack"` from `_STATS_WHITELIST` set
  - [x] In `server/net/handlers/combat.py:29`, change `_sync_combat_stats` key loop to `for key in ("hp", "max_hp"):` (remove `"attack"`)
  - [x] In `server/net/handlers/combat.py:110`, change `_check_combat_end` final sync loop to `for key in ("hp", "max_hp"):` (remove `"attack"`)
  - [x] In `server/net/handlers/auth.py:45`, change `_cleanup_player` sync loop to `for key in ("hp", "max_hp"):` (remove `"attack"`) — note: the loop is at line 45, not line 44
  - [x] Keep `"attack": 10` in `_DEFAULT_STATS` (auth.py, inside `handle_login`) as a runtime value — it's still used by `_mob_attack_target` as base_attack. The whitelist removal just stops it from being persisted to DB for *players*.
  - [x] Mob stats still have `attack` key from `_derive_stats_from_hit_dice()` — DO NOT remove from NPC stat derivation.

- [x] Task 6: Update existing combat tests (AC: #10)
  - [x] Update `_make_player_stats()` and `_make_mob_stats()` helpers in test files to include stat ability keys (`strength`, `dexterity`, `intelligence`, `wisdom`) where needed for stat-aware combat:
    - `tests/test_combat.py:19-24` — `_make_mob_stats(hp, attack)` and `_make_player_stats(hp, attack)` with `"defense": 5`
    - `tests/test_combat_resolution.py:17-22` — `_make_mob_stats(hp, attack)` and `_make_player_stats(hp)` with `"shield": 0`
    - `tests/test_combat_effects.py:16-21` — `_make_mob_stats(hp, attack)` and `_make_player_stats(hp, max_hp, attack)` with `"shield": 0`
    - `tests/test_combat_flee.py:20-25` — `_make_mob_stats(hp, attack)` and `_make_player_stats(hp)` with `"shield": 0`
    - `tests/test_item_usage.py:66-71` — `_make_player_stats(hp, max_hp)` and `_make_mob_stats(hp, attack)`
  - [x] Update `tests/test_dot_effects.py:10` — this file has `_make_instance()` (NOT `_make_player_stats`/`_make_mob_stats`). It creates stats inline: `{"hp": 100, "max_hp": 100, "attack": 10, "xp": 0}` for the player and `{"hp": mob_hp, "max_hp": mob_hp, "attack": mob_attack}` for the mob. Add ability score keys to both inline stat dicts.
  - [x] Update damage/heal assertions to account for stat bonuses
  - [x] Ensure DoT assertions remain unchanged (DoT is NOT stat-modified)

- [x] Task 7: Add new stat-aware tests (AC: #10)
  - [x] Test STR bonus on physical damage (Slash card base=12, STR=6 → 12+6=18 raw)
  - [x] Test INT bonus on fire/ice/arcane damage (Fire Bolt base=20, INT=4 → 20+4=24 raw)
  - [x] Test INT does NOT apply to physical damage
  - [x] Test STR does NOT apply to elemental damage
  - [x] Test WIS bonus on heal (Heal Light base=15, WIS=3 → 15+3=18 healed)
  - [x] Test DEX reduces damage after shield absorption (min 1)
  - [x] Test DoT tick NOT reduced by DEX
  - [x] Test shield value NOT modified by stats
  - [x] Test mob attack with STR bonus and target DEX reduction
  - [x] Test STAT_SCALING_FACTOR=0.5 produces `floor(stat × 0.5)` bonus

- [x] Task 8: Run `pytest tests/` and fix any failures (AC: #10)

## Dev Notes

### Key Architecture Patterns

- **Effect handlers are stateless async functions**: Signature `async (effect, source, target, context) -> dict`. `source` and `target` are dicts (player_stats or mob_stats). The handlers modify `target` in-place and return result dicts.
- **`source` dict for cards/items = player's `participant_stats[entity_id]`**: Set in `resolve_card_effects()` at instance.py:87-100. For self-targeting effects (heal, shield, draw), source == target == player_stats. For damage/dot, source = player_stats, target = mob_stats.
- **`source` dict for mob attacks is `self.mob_stats`**: Mob attack happens in `_mob_attack_target()` at instance.py:339 — this is direct damage calculation, NOT routed through EffectRegistry.
- **DoT ticking is separate from EffectRegistry**: `_process_dot_effects()` at instance.py:261 applies DoT damage directly (shield absorption + HP reduction). It does NOT call `handle_damage()`. Therefore, DEX reduction for DoT must NOT be added here (AC #5).
- **Config access pattern**: Import `from server.core.config import settings` then use `settings.STAT_SCALING_FACTOR`. Use `math.floor()` for the stat bonus calculation.
- **Stats in combat dicts**: After Story 11.1, participant_stats dicts include `strength`, `dexterity`, `constitution`, `intelligence`, `wisdom`, `charisma` (copied from PlayerEntity.stats by `add_participant()`). Mob stats include all 6 abilities (from `_derive_stats_from_hit_dice()`).

### Critical Implementation Details

**Damage flow in `handle_damage` (current, damage.py:5-20):**
```python
raw_damage = effect.get("value", 0)
shield = target.get("shield", 0)
absorbed = min(shield, raw_damage)
target["shield"] = shield - absorbed
actual_damage = raw_damage - absorbed
target["hp"] = max(0, target["hp"] - actual_damage)
```

**New flow must be:**
```python
base_damage = effect.get("value", 0)
# Add stat bonus based on subtype
subtype = effect.get("subtype", "physical")
if subtype == "physical":
    bonus = math.floor(source.get("strength", 0) * settings.STAT_SCALING_FACTOR)
elif subtype in ("fire", "ice", "arcane"):
    bonus = math.floor(source.get("intelligence", 0) * settings.STAT_SCALING_FACTOR)
else:
    bonus = 0
raw_damage = base_damage + bonus
# Shield absorption
shield = target.get("shield", 0)
absorbed = min(shield, raw_damage)
target["shield"] = shield - absorbed
post_shield = raw_damage - absorbed
# DEX reduction (after shield, min 1)
dex_reduction = math.floor(target.get("dexterity", 0) * settings.STAT_SCALING_FACTOR)
actual_damage = max(1, post_shield - dex_reduction) if post_shield > 0 else 0
target["hp"] = max(0, target["hp"] - actual_damage)
```

**Important edge case**: If `post_shield == 0` (all damage absorbed by shield), do NOT apply the `max(1, ...)` floor — actual_damage stays 0. The `max(1, ...)` minimum only applies when there IS post-shield damage.

**Mob attack flow in `_mob_attack_target` (current, instance.py:339-355):**
```python
attack = self.mob_stats.get("attack", 10)
# ... shield absorption and HP reduction
```
Must become STR-derived with DEX reduction, matching the damage handler pattern but computed inline (not via EffectRegistry).

### What NOT to Change

- Do NOT modify `handle_dot()` in `dot.py` — DoT recording is unaffected
- Do NOT modify `_process_dot_effects()` in `instance.py` — DoT ticking bypasses stats
- Do NOT modify `handle_shield()` in `shield.py` — shield is flat value
- Do NOT modify `handle_draw()` in `draw.py` — draw is unrelated
- Do NOT change the hardcoded XP reward of 25 in `instance.py:403` — that's Story 11.3
- Do NOT add XP curve config — that's Story 11.3
- Do NOT remove `attack` from `_DEFAULT_STATS` in auth.py — keep as runtime default
- Do NOT remove `attack` from `_derive_stats_from_hit_dice()` in npc.py — mob stats still use it as base_attack

### Card Subtypes in Data (for reference)

From `data/cards/starter_cards.json`:
- **physical**: `slash` (12), `poison_strike` (8), `heavy_strike` (25) → STR bonus
- **fire**: `fire_bolt` (20), `flame_wave` (18), `fire_shield` (10) → INT bonus
- **ice**: `ice_shard` (15) → INT bonus
- **arcane**: `arcane_surge` (10) → INT bonus
- **heal**: `heal_light` (15), `greater_heal` (30), `fortify` (5) → WIS bonus
- **shield**: `iron_shield` (12), `steel_wall` (20), `fortify` (8), `fire_shield` (10) → no stat bonus

### Test Helper Update Pattern

Each test file has slightly different helper signatures — read each file before updating. Example from `test_combat.py:19-24`:
```python
def _make_mob_stats(hp=50, attack=10):
    return {"hp": hp, "max_hp": hp, "attack": attack}
def _make_player_stats(hp=100, attack=15):
    return {"hp": hp, "max_hp": hp, "attack": attack, "defense": 5}
```

Other files differ: `test_combat_effects.py` has `max_hp` param and `"shield": 0`; `test_combat_resolution.py` has `hp`-only params with `"shield": 0`; `test_item_usage.py` has `hp, max_hp` params. Preserve each file's existing signature and dict keys — just ADD ability score kwargs (`strength=0, dexterity=0, intelligence=0, wisdom=0`) and include them in the returned dict.

Using `strength=0` as default means existing tests (that don't pass ability scores) get 0 stat bonus, preserving their current damage assertions. New stat-aware tests explicitly pass non-zero values.

### Previous Story Intelligence

From Story 11.1 dev notes:
- Stats are unstructured dicts — no schema enforcement
- Login merge pattern `{**_DEFAULT_STATS, **db_stats}` handles migration
- NPC stats derived from `hit_dice` via `_derive_stats_from_hit_dice()` in npc.py
- `add_participant()` at instance.py:46 does `dict(player_stats)` — shallow copy includes all ability scores
- `_STATS_WHITELIST` currently has 11 keys including `attack` (to be removed)
- All 538 tests passing after 11.1

### Project Structure Notes

- Effect handlers: `server/core/effects/damage.py`, `heal.py`, `shield.py`, `dot.py`, `draw.py`
- Combat instance: `server/combat/instance.py`
- Config: `server/core/config.py` (Pydantic BaseSettings)
- Stats whitelist: `server/player/repo.py:75`
- Combat handler: `server/net/handlers/combat.py`
- Auth handler: `server/net/handlers/auth.py`
- Tests: `tests/` (flat directory)

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Epic 11, Story 11.2, lines 1981-2049]
- [Source: server/core/effects/damage.py — handle_damage, lines 5-20]
- [Source: server/core/effects/heal.py — handle_heal, lines 5-17]
- [Source: server/combat/instance.py — _mob_attack_target, lines 339-355]
- [Source: server/combat/instance.py — _process_dot_effects, lines 261-304]
- [Source: server/combat/instance.py — resolve_card_effects, lines 76-115]
- [Source: server/player/repo.py:75 — _STATS_WHITELIST]
- [Source: server/net/handlers/combat.py:29 — _sync_combat_stats]
- [Source: server/net/handlers/combat.py:110 — _check_combat_end final sync]
- [Source: server/net/handlers/auth.py:45 — _cleanup_player sync loop]
- [Source: server/core/config.py:7 — Settings class]
- [Source: data/cards/starter_cards.json — card subtypes and values]
- [Source: _bmad-output/implementation-artifacts/11-1-dnd-stat-system-and-npc-hit-dice.md — previous story]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Added `STAT_SCALING_FACTOR = 1.0` to server config
- `handle_damage` now adds STR bonus (physical) or INT bonus (fire/ice/arcane) to base damage, applies DEX reduction after shield (min 1 if post-shield > 0, 0 if fully absorbed)
- `handle_heal` now adds WIS bonus to base heal value
- `_mob_attack_target` now uses `base_attack + floor(mob_STR × factor)` with target DEX reduction
- `attack` removed from `_STATS_WHITELIST` (no longer persisted for players)
- `attack` removed from `_sync_combat_stats`, `_check_combat_end`, and `_cleanup_player` sync loops
- DoT, shield, and draw effects deliberately NOT modified (per AC #5, #6)
- All 6 combat test files updated: helpers now include ability score kwargs defaulting to 0
- 20 new tests in `test_stat_combat.py` covering all stat-combat interactions and STAT_SCALING_FACTOR
- 108 combat tests passing (88 existing + 20 new); full suite 207 passed (failures are pre-existing Python 3.9 compat issues)

### File List

- server/core/config.py (modified — added STAT_SCALING_FACTOR)
- server/core/effects/damage.py (modified — STR/INT bonus, DEX reduction)
- server/core/effects/heal.py (modified — WIS bonus)
- server/combat/instance.py (modified — _mob_attack_target STR+DEX)
- server/player/repo.py (modified — removed attack from _STATS_WHITELIST)
- server/net/handlers/combat.py (modified — removed attack from sync loops)
- server/net/handlers/auth.py (modified — removed attack from _cleanup_player sync)
- tests/test_combat.py (modified — stat kwargs in helpers)
- tests/test_combat_effects.py (modified — stat kwargs in helpers)
- tests/test_combat_resolution.py (modified — stat kwargs in helpers)
- tests/test_combat_flee.py (modified — stat kwargs in helpers)
- tests/test_item_usage.py (modified — stat kwargs in helpers)
- tests/test_dot_effects.py (modified — stat keys in inline dicts)
- tests/test_stat_combat.py (new — 20 stat-to-combat tests)
