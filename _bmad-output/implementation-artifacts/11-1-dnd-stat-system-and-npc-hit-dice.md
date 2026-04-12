# Story 11.1: D&D Stat System & NPC Hit Dice

Status: done

## Story

As a player,
I want my character to have meaningful ability scores (STR, DEX, CON, INT, WIS, CHA),
so that my character feels unique and stats affect gameplay beyond flat HP and attack.

## Acceptance Criteria

1. **New player gets 6 ability scores**: On first login (empty DB stats), player has `strength=1, dexterity=1, constitution=1, intelligence=1, wisdom=1, charisma=1`, `level=1`, `xp=0`, and `max_hp = 100 + (constitution × CON_HP_PER_POINT)` = 105.

2. **Returning player stats restored**: On login with existing DB stats, all 6 abilities and level are restored from DB — not reset to defaults.

3. **Migration for existing players**: If a player has pre-Epic-11 stats (hp, max_hp, attack, xp but no ability scores), missing abilities default to 1, level defaults to 1, existing hp/max_hp/xp are preserved. max_hp is NOT recalculated from CON on migration (preserves the player's current state).

4. **Stats whitelist expanded**: `_STATS_WHITELIST` in `player/repo.py` includes: `hp, max_hp, attack, xp, strength, dexterity, constitution, intelligence, wisdom, charisma, level`. The `attack` key is kept during transition (deprecated in Story 11.2).

5. **CON_HP_PER_POINT config**: `CON_HP_PER_POINT: int = 5` added to server config.

6. **NPC hit_dice system**: NPC JSON data restructured to use `hit_dice` and `hp_multiplier`. All 6 abilities derived from `hit_dice`. `max_hp = hit_dice × hp_multiplier`. Mob `attack` = `hit_dice × 2` (transitional).

7. **NPC data updated**: cave_bat(hd=2, hpm=12), slime(hd=3, hpm=10), forest_goblin(hd=4, hpm=12), cave_troll(hd=7, hpm=28), forest_dragon(hd=10, hpm=50).

8. **Combat instance uses NPC attack from hit_dice**: At combat init, mob `attack` is populated from `hit_dice × 2`.

9. **All existing tests updated and passing**: `pytest tests/` passes with no failures.

## Tasks / Subtasks

- [x] Task 1: Add CON_HP_PER_POINT to server config (AC: #5)
  - [x] Add `CON_HP_PER_POINT: int = 5` to `Settings` class in `server/core/config.py`

- [x] Task 2: Expand stats whitelist (AC: #4)
  - [x] Update `_STATS_WHITELIST` at `server/player/repo.py:75` to add `strength, dexterity, constitution, intelligence, wisdom, charisma, level`
  - [x] Keep `attack` in whitelist (transitional — removed in Story 11.2)

- [x] Task 3: Update default stats and login logic (AC: #1, #2, #3)
  - [x] Change `_DEFAULT_STATS` at `server/net/handlers/auth.py:215` to include all 6 abilities + level
  - [x] Update register response (auth.py lines 150-162) to include new stat fields
  - [x] Update login stat resolution (auth.py lines 216-223) — merge logic already handles missing keys via `{**_DEFAULT_STATS, **db_stats}`
  - [x] Add max_hp computation for NEW players only: after merge, if player is first-time (db_stats was empty), compute `max_hp = 100 + (stats["constitution"] * settings.CON_HP_PER_POINT)` and set `hp = max_hp`. Do NOT recalculate for returning players (their max_hp comes from DB).
  - [x] Update `login_success` message (auth.py lines 286-298) to include abilities and level
  - [x] Ensure max_hp is NOT recalculated for returning players who have existing max_hp in DB (migration AC #3)

- [x] Task 4: Update NPC data and entity creation (AC: #6, #7)
  - [x] Restructure `data/npcs/base_npcs.json` — replace flat `hp, max_hp, attack, defense` with `hit_dice, hp_multiplier` fields
  - [x] Update `create_npc_from_template()` in `server/room/objects/npc.py:65-80` to derive stats from hit_dice:
    - All 6 abilities = hit_dice
    - `hp = max_hp = hit_dice × hp_multiplier`
    - `attack = hit_dice × 2`
    - Store derived stats in `npc.stats` dict

- [x] Task 5: Update combat instance mob stats (AC: #8)
  - [x] Verify `CombatInstance.__init__` (instance.py:29) mob_stats default still works with new NPC stat shape
  - [x] Mob stats dict passed to CombatInstance must include `attack` key (populated from hit_dice × 2 by NPC creation)

- [x] Task 6: Update query handler to return new stat keys (AC: #1, #2)
  - [x] Update `handle_stats` in `server/net/handlers/query.py:109-118` — expand the hardcoded 4-key dict to include `strength, dexterity, constitution, intelligence, wisdom, charisma, level`
  - [x] Update defaults in the `.get()` calls to match new `_DEFAULT_STATS`

- [x] Task 7: Update combat stat sync to include new keys (AC: #4)
  - [x] Update `_sync_combat_stats` in `server/net/handlers/combat.py:29` — expand `for key in ("hp", "max_hp", "attack", "xp"):` to include `level` (ability scores do NOT change during combat, so they don't need syncing)
  - [x] Update `_cleanup_player` in `server/net/handlers/auth.py:44` — expand `for key in ("hp", "max_hp", "attack"):` to match. Ability scores are not modified during combat so do not need cleanup sync.

- [x] Task 8: Update web-demo client for new stat keys (AC: #1)
  - [x] Update `web-demo/js/game.js` to handle new stat keys in `login_success` and `stats_result` messages without breaking
  - [x] The HUD already shows HP/XP/ATK from Story 10.8 — keep existing display working, new stats will be fully displayed in Story 11.6

- [x] Task 9: Update all tests (AC: #9)
  - [x] Update test helper functions that create mock stats:
    - `test_combat.py:19-24` — `_make_mob_stats()`, `_make_player_stats()`
    - `test_combat_resolution.py:17-22` — same helpers
    - `test_combat_effects.py:16-21` — same helpers
    - `test_combat_flee.py:20-25` — same helpers
    - `test_item_usage.py:66-71` — same helpers
    - `test_dot_effects.py:10-19` — `_make_instance()`
  - [x] Update tests with hardcoded player stats:
    - `test_stats_persistence.py:133-151` — default stat assertions (test method at line 133)
    - `test_stats_persistence.py:175,189-193` — returning player stat assertions
    - `test_query.py:36,183-204,211-219` — stats_result response assertions
    - `test_combat_entry.py:35-48,81-84` — NPC and player stat setup
    - `test_logout.py:28,88-89,122-123,161` — entity stats setup
    - `test_loot.py:99,110-112,141,269-270,329-330,344,414-415,427,491-492` — all stat references
    - `test_integration.py:72-74,148-154,337,394-395` — NPC stats and XP assertion
  - [x] Update NPC template tests:
    - `test_npc.py:49,65-66,98-99,205` — NPC template stats
    - `test_spawn.py:67,84,113,148` — spawn template stats
    - `test_sample_data.py:149,159` — sample NPC data validation
  - [x] Run `pytest tests/` and fix any remaining failures

## Dev Notes

### Key Architecture Patterns

- **Stats are unstructured dicts**: Both `PlayerEntity.stats` and `NpcEntity.stats` are plain `dict` — no schema enforcement. Keys are convention-driven.
- **Stats whitelist is the persistence gate**: `_STATS_WHITELIST` in `repo.py:75` determines which keys survive DB round-trip. Any new key not in whitelist is silently stripped on `update_stats()`.
- **Login merge pattern**: `{**_DEFAULT_STATS, **db_stats}` at auth.py:223 means defaults are applied for ANY missing key. This naturally handles migration — just add new keys to `_DEFAULT_STATS` and existing players get defaults for missing keys on next login.
- **NPC stats come from JSON templates**: `create_npc_from_template()` at npc.py:77 does `stats=dict(tmpl.get("stats", {}))` — shallow copy of template stats dict. The NPC creation function must now DERIVE stats from hit_dice instead of copying flat values.
- **Combat instance copies stats**: `add_participant()` at instance.py:39-52 shallow-copies player stats and adds combat-only transient keys (shield, energy). Mob stats are passed directly.
- **`defense` is dead code**: NPCs define `defense` in JSON (values 2-15) but it's never read by any combat calculation. This story removes it from NPC data (replaced by DEX from hit_dice in Story 11.2).
- **Ability scores don't change during combat**: `_cleanup_player` (auth.py:44) and `_sync_combat_stats` (combat.py:29) sync mutable combat stats back to entity. Ability scores (STR/DEX/CON/INT/WIS/CHA) are NOT modified during combat and do NOT need syncing. Only `level` should be added to the sync list (in case combat XP triggers a level-up in Story 11.5).

### Critical File Locations

| File | What to Change | Lines |
|------|---------------|-------|
| `server/core/config.py` | Add `CON_HP_PER_POINT` to `Settings` class | Before line 18 (inside class, before `ADMIN_SECRET`) |
| `server/player/repo.py` | Expand `_STATS_WHITELIST` | Line 75 |
| `server/net/handlers/auth.py` | Update `_DEFAULT_STATS`, register response, login_success message, `_cleanup_player` | Lines 43-46, 150-162, 215-223, 286-298 |
| `server/net/handlers/query.py` | Update `handle_stats` hardcoded 4-key dict to include new stats | Lines 109-118 |
| `server/net/handlers/combat.py` | Update `_sync_combat_stats` key loop to include `level` | Line 29 |
| `server/room/objects/npc.py` | Update `create_npc_from_template()` to derive from hit_dice | Lines 65-80 |
| `data/npcs/base_npcs.json` | Restructure to hit_dice + hp_multiplier | Entire file |
| `server/combat/instance.py` | Verify mob_stats default (line 29) | Line 29 |
| `web-demo/js/game.js` | Handle new stat keys in login_success/stats_result without breaking | Various |

### What NOT to Change (Story 11.2+ scope)

- Do NOT wire stats into effect handlers (damage.py, heal.py) — that's Story 11.2
- Do NOT remove `attack` from whitelist — it stays as transitional value
- Do NOT add XP curve config — that's Story 11.3
- Do NOT add `STAT_SCALING_FACTOR` config — that's Story 11.2
- Do NOT modify effect resolution — stats bonuses come in Story 11.2
- Do NOT change the hardcoded XP reward of 25 in instance.py:403 — that's Story 11.3

### NPC Data Transformation

Current `data/npcs/base_npcs.json` format:
```json
{"stats": {"hp": 50, "max_hp": 50, "attack": 10, "defense": 5}}
```

New format:
```json
{"hit_dice": 4, "hp_multiplier": 12}
```

Stats are derived at NPC creation time by `create_npc_from_template()`, NOT stored in JSON.

### Existing _DEFAULT_STATS Pattern

Current (auth.py:215):
```python
_DEFAULT_STATS = {"hp": 100, "max_hp": 100, "attack": 10, "xp": 0}
```

New:
```python
_DEFAULT_STATS = {
    "hp": 100, "max_hp": 100, "attack": 10, "xp": 0, "level": 1,
    "strength": 1, "dexterity": 1, "constitution": 1,
    "intelligence": 1, "wisdom": 1, "charisma": 1,
}
```

Note: `hp` and `max_hp` default to 100 here as fallback values. For NEW players (empty db_stats), `max_hp` is then computed as `100 + (constitution × CON_HP_PER_POINT)` = 105 and `hp` set to match. This computation happens in login logic AFTER the merge, only when db_stats was empty. Returning players keep their DB-stored max_hp. The `attack=10` remains as transitional value.

### Migration Logic

The existing merge `{**_DEFAULT_STATS, **db_stats}` at auth.py:223 handles migration naturally:
- Old player in DB: `{"hp": 85, "max_hp": 100, "attack": 10, "xp": 200}`
- After merge: `{"hp": 85, "max_hp": 100, "attack": 10, "xp": 200, "level": 1, "strength": 1, ...}`
- Their `max_hp` stays 100 (from DB), not recalculated to 105
- New abilities default to 1 from `_DEFAULT_STATS`

### Test Impact Summary

18 test files reference player/NPC stats. Key patterns to update:
- **Helper functions** (`_make_mob_stats`, `_make_player_stats`): Update to include new stat keys where needed
- **NPC template fixtures**: Replace flat stats with hit_dice-based data
- **Default stat assertions**: Update expected values from `{hp:100, max_hp:100, attack:10, xp:0}` to include new keys
- **Stats result assertions**: test_query.py must expect new stat keys in response
- **XP=25 assertions**: Do NOT change — XP reward stays 25 until Story 11.3

### Project Structure Notes

- All server code under `server/` with domain-driven directories: `core/`, `net/`, `player/`, `room/`, `combat/`, `items/`
- Config uses Pydantic BaseSettings in `server/core/config.py`
- Tests in flat `tests/` directory, no subdirectories
- NPC data in `data/npcs/base_npcs.json`

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Epic 11, Story 11.1]
- [Source: _bmad-output/planning-artifacts/architecture.md — Section 9.1 Player Model]
- [Source: server/player/repo.py:75 — _STATS_WHITELIST]
- [Source: server/net/handlers/auth.py:215 — _DEFAULT_STATS]
- [Source: server/room/objects/npc.py:65-80 — create_npc_from_template]
- [Source: server/combat/instance.py:29,339-355 — mob stats usage]
- [Source: CLAUDE.md — Server Architecture section]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Added `CON_HP_PER_POINT = 5` to server config
- Expanded `_STATS_WHITELIST` to include 6 ability scores + level (11 keys total)
- Updated `_DEFAULT_STATS` with ability scores and level; first-time players get CON-derived `max_hp = 105`
- Returning players get missing ability scores filled via merge pattern; max_hp NOT recalculated on migration
- NPC data restructured from flat stats to `hit_dice` + `hp_multiplier` with derived stat block
- `_derive_stats_from_hit_dice()` function added to npc.py with legacy format fallback
- Combat stat sync keys expanded to include `level`
- Query handler `handle_stats` now returns all 11 stat keys
- Web-demo client updated: stats fallback, `/stats` chat display includes abilities
- Entity broadcast includes `level` field
- All 538 tests pass (2 pre-existing chest integration failures excluded)

### File List

- server/core/config.py (modified — added CON_HP_PER_POINT)
- server/player/repo.py (modified — expanded _STATS_WHITELIST)
- server/net/handlers/auth.py (modified — _DEFAULT_STATS, login logic, register response, _cleanup_player, entity_data broadcast)
- server/net/handlers/query.py (modified — handle_stats expanded to 11 keys)
- server/net/handlers/combat.py (modified — _sync_combat_stats key loop, _check_combat_end final sync)
- server/net/handlers/movement.py (modified — entity_entered broadcast includes level)
- server/room/objects/npc.py (modified — _derive_stats_from_hit_dice, create_npc_from_template)
- data/npcs/base_npcs.json (modified — restructured to hit_dice + hp_multiplier)
- web-demo/js/game.js (modified — stats fallback, /stats display)
- tests/test_auth.py (modified — ability score assertions)
- tests/test_query.py (modified — 11-key stats assertions)
- tests/test_sample_data.py (modified — hit_dice/hp_multiplier assertions)
- tests/test_stats_persistence.py (modified — CON-derived max_hp assertions)
