# ISS-020: 10 Broken Tests From Epic 14 Refactors

**Severity:** High (test suite has 8 failures + 2 collection errors, masking regressions)
**Found during:** Epic 14 retrospective analysis
**Status:** Done

## Problem

10 tests broke across Epic 14 stories and were carried forward as "pre-existing failures" without being fixed. They fall into 4 root causes:

### Root Cause A: `server/items/loot.py` deleted in Story 14.2 (6 tests)

Story 14.2 replaced the hardcoded `generate_loot()` / `LOOT_TABLES` module with data-driven `game.loot_tables` loaded from `data/loot/loot_tables.json`. The module was deleted. 6 tests still reference it.

| Test | File | Type | Action |
|------|------|------|--------|
| `test_loot.py` (entire file) | Collection error | Module-level import of deleted `generate_loot` | Remove import; replace 10 `generate_loot` unit tests with `load_loot_tables()` tests; add `game.loot_tables` to `_make_game()` for integration tests |
| `test_chest.py` (entire file) | Collection error | Module-level import of deleted `generate_loot` | Remove import; delete 2 `generate_loot` tests (coverage in test_loot.py); add `game.loot_tables` to `_make_game()` |
| `test_party_combat.py::test_per_player_loot_independence` | Runtime import | Tests deleted `generate_loot()` function | Delete — function doesn't exist |
| `test_party_combat.py::test_check_combat_end_per_player_loot` | Runtime import + patches deleted `combat.generate_loot` | Tests loot via deleted code path | Delete — duplicated by `test_loot.py::test_combat_victory_multi_player_same_loot` |

### Root Cause B: `create_object` removed from `interact.py` in Story 14.4b (4 tests)

Story 14.4b changed `handle_interact` to use pre-created `InteractiveObject` instances from `room._interactive_objects` instead of calling `create_object()` on-the-fly. 4 tests patch the deleted import.

| Test | Issue | Action |
|------|-------|--------|
| `test_first_chest_interact_grants_xp` | Patches `interact.create_object` | Rewrite: real `ChestObject` with mocked `interact()` |
| `test_repeat_chest_interact_no_xp` | Same | Same |
| `test_first_lever_interact_grants_xp` | Same | Same |
| `test_repeat_lever_interact_no_xp` | Same | Same |

### Root Cause C: Stats response enriched in Story 14.3b (1 test)

Story 14.3b added `xp_for_next_level` and `xp_for_current_level` to the stats response. Test not updated.

| Test | Issue | Action |
|------|-------|--------|
| `test_stats_excludes_transient` | Missing 2 keys in `expected_keys` | Add the 2 keys |

### Root Cause D: `get_object()` returns dataclass not dict (1 test, from Story 14.4b)

| Test | Issue | Action |
|------|-------|--------|
| `test_room_get_object_found` | `room.get_object("chest_01")["type"]` — subscript on dataclass | Change to `.type` |

## Impact

- Zero behavioral change — all fixes are test-only
- Restores test suite to 0 failures, 0 collection errors
- Replaces data validation coverage lost when `generate_loot` unit tests are removed
