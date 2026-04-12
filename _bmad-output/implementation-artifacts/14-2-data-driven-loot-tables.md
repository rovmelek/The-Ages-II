# Story 14.2: Data-Driven Loot Tables

Status: done

## Story

As a developer,
I want loot tables defined in JSON data files instead of hardcoded Python dicts,
So that game content follows the architecture's JSON-driven configuration principle and loot can be modified without code changes.

## Acceptance Criteria

1. **Given** the hardcoded `LOOT_TABLES` dict in `server/items/loot.py`, **When** Story 14.2 is implemented, **Then** a `data/loot/loot_tables.json` file contains the same data in direct 1:1 JSON translation (dict of table_key -> list of `{item_key, quantity}`).

2. **Given** the `item_repo.py` module (`server/items/item_repo.py`), **When** Story 14.2 is implemented, **Then** a `load_loot_tables(data_dir: Path) -> dict` function loads and returns the JSON loot tables (ADR-14-2: loader lives in `item_repo.py` alongside `load_items_from_json()`).

3. **Given** `Game.startup()` in `server/app.py` (line ~60), **When** Story 14.2 is implemented, **Then** loot tables are loaded **after** items (loot references item keys) and stored as `game.loot_tables` attribute. The loader is called in the startup method between item loading (line ~94) and handler registration (line ~96).

4. **Given** all call sites that import or reference `LOOT_TABLES` or `generate_loot` from `server/items/loot.py`:
   - `server/net/handlers/combat.py` line 13: `from server.items.loot import generate_loot` (used at line 117)
   - `server/room/objects/chest.py` line 8: `from server.items.loot import generate_loot` (used at line 35)
   **When** Story 14.2 is implemented, **Then** they reference `game.loot_tables` instead of the module-level constant, and the `generate_loot` function is replaced with a simple inline lookup: `list(game.loot_tables.get(key, []))`.
   **And** the `server/items/loot.py` module is deleted entirely.

5. **Given** all existing tests, **When** Story 14.2 is implemented, **Then** all tests pass. Test files that reference loot tables are updated:
   - `tests/test_loot.py`: Update imports, replace `LOOT_TABLES` references with loaded JSON data, update `generate_loot` tests to use new lookup pattern.
   - `tests/test_party_combat.py` lines 485 and 653: Update `from server.items.loot import generate_loot` imports.
   - `tests/test_chest.py` line 10: Update `from server.items.loot import generate_loot` import.

## Tasks / Subtasks

- [x] Task 1: Create `data/loot/loot_tables.json` (AC: #1)
  - [x] 1.1: Create `data/loot/` directory
  - [x] 1.2: Create `loot_tables.json` — direct 1:1 translation of `LOOT_TABLES` dict from `server/items/loot.py` (lines 11-39):
    ```json
    {
      "common_chest": [
        {"item_key": "healing_potion", "quantity": 1},
        {"item_key": "iron_shard", "quantity": 2}
      ],
      "rare_chest": [
        {"item_key": "healing_potion", "quantity": 3},
        {"item_key": "fire_essence", "quantity": 1}
      ],
      "slime_loot": [
        {"item_key": "healing_potion", "quantity": 1}
      ],
      "goblin_loot": [
        {"item_key": "iron_shard", "quantity": 1}
      ],
      "bat_loot": [
        {"item_key": "antidote", "quantity": 1}
      ],
      "troll_loot": [
        {"item_key": "healing_potion", "quantity": 1},
        {"item_key": "iron_shard", "quantity": 2}
      ],
      "dragon_loot": [
        {"item_key": "fire_essence", "quantity": 2},
        {"item_key": "healing_potion", "quantity": 2}
      ]
    }
    ```

- [x] Task 2: Add `load_loot_tables()` to `server/items/item_repo.py` (AC: #2)
  - [x] 2.1: Add a standalone function at module level (NOT async — it's pure file I/O like `load_npc_templates`):
    ```python
    def load_loot_tables(data_dir: Path) -> dict[str, list[dict[str, Any]]]:
        """Load loot table definitions from JSON file."""
        loot_file = data_dir / "loot_tables.json"
        if not loot_file.exists():
            return {}
        with open(loot_file) as f:
            return json.load(f)
    ```
  - [x] 2.2: Add `from typing import Any` import if not already present (it is NOT currently imported in `item_repo.py`)

- [x] Task 3: Add `game.loot_tables` attribute and load in startup (AC: #3)
  - [x] 3.1: In `Game.__init__()` (line ~34), after `self._shutting_down` (line ~47), add: `self.loot_tables: dict = {}`
    No `from typing import Any` import needed — use plain `dict` annotation (consistent with `self.player_entities: dict[str, dict] = {}` on line ~45).
  - [x] 3.2: In `Game.startup()`, after item loading (line ~94) and before handler registration (line ~96), add:
    ```python
    # Load loot tables from JSON (after items, since loot references item keys)
    loot_dir = settings.DATA_DIR / "loot"
    if loot_dir.exists():
        from server.items import item_repo as loot_repo
        self.loot_tables = loot_repo.load_loot_tables(loot_dir)
    ```
    Note: Reuse the existing `item_repo` import pattern. Since `item_repo` is already imported inside the items block (line ~90), either reuse that reference or import fresh — the existing pattern uses block-scoped imports.

- [x] Task 4: Update `server/net/handlers/combat.py` to use `game.loot_tables` (AC: #4)
  - [x] 4.1: Remove line 13: `from server.items.loot import generate_loot`
  - [x] 4.2: At line 117, replace `loot_items = generate_loot(loot_table_key)` with:
    `loot_items = list(game.loot_tables.get(loot_table_key, []))`

- [x] Task 5: Update `server/room/objects/chest.py` to use `game.loot_tables` (AC: #4)
  - [x] 5.1: Remove line 8: `from server.items.loot import generate_loot`
  - [x] 5.2: At line 35, replace `items = generate_loot(loot_table)` with:
    `items = list(game.loot_tables.get(loot_table, []))`

- [x] Task 6: Delete `server/items/loot.py` (AC: #4)
  - [x] 6.1: Delete the file entirely — all its functionality is replaced

- [x] Task 7: Update `tests/test_loot.py` (AC: #5)
  - [x] 7.1: Remove imports of `LOOT_TABLES` and `generate_loot` from `server.items.loot`
  - [x] 7.2: Load loot tables from JSON at module level or in tests:
    ```python
    from server.items.item_repo import load_loot_tables
    from pathlib import Path
    LOOT_TABLES = load_loot_tables(Path("data/loot"))
    ```
  - [x] 7.3: Replace `generate_loot(key)` calls with `list(LOOT_TABLES.get(key, []))` or a local helper
  - [x] 7.4: Update `test_all_npc_loot_tables_present` to use the loaded dict
  - [x] 7.5: Update `test_generate_loot_returns_list_copy` — now `list()` call guarantees new list each time, test still passes
  - [x] 7.6: Update combat integration tests in `test_loot.py` — the `_check_combat_end` calls now need `game.loot_tables` set on the mock game:
    - In `_make_game()`: add `game.loot_tables = load_loot_tables(Path("data/loot"))`
    - Remove `patch("server.net.handlers.combat.generate_loot")` if present — no longer needed since combat uses `game.loot_tables` directly

- [x] Task 8: Update `tests/test_party_combat.py` (AC: #5)
  - [x] 8.1: Line 485: Remove `from server.items.loot import generate_loot` — replace with loading from JSON or using `game.loot_tables`
  - [x] 8.2: Line 653: Remove `from server.items.loot import generate_loot as gl` — replace with loot table lookup or load from JSON
  - [x] 8.3: Line 659: Remove `patch("server.net.handlers.combat.generate_loot", ...)` — combat now uses `game.loot_tables` directly. Set `game.loot_tables` on mock game instead.
  - [x] 8.4: Ensure all mock game objects in party combat tests have `loot_tables` attribute set

- [x] Task 9: Update `tests/test_chest.py` (AC: #5)
  - [x] 9.1: Line 10: Remove `from server.items.loot import generate_loot`
  - [x] 9.2: Lines 84-94: `test_generate_loot_common` and `test_generate_loot_unknown_table` directly call `generate_loot()`. Rewrite to use `load_loot_tables` + `list(tables.get(...))` pattern, or remove if redundant with `test_loot.py` coverage.
  - [x] 9.3: `_make_game()` (line ~31) creates a real `Game()` — after adding `loot_tables` to `__init__`, it will default to `{}`. Chest interaction tests (`test_open_chest_first_time`, `test_chest_loot_added_to_inventory`, etc.) need `game.loot_tables` populated with data from JSON. Add `game.loot_tables = load_loot_tables(Path("data/loot"))` to `_make_game()`.
  - [x] 9.4: Add `from server.items.item_repo import load_loot_tables` and `from pathlib import Path` imports

- [x] Task 10: Run `make test` and verify all tests pass (AC: #5)

## Dev Notes

### Architecture Compliance
- **ADR-14-2**: Loader function in `item_repo.py` alongside `load_items_from_json()` — NOT a new file
- **ADR-14-15**: Direct 1:1 JSON translation — no weighted drops, no probability, no rarity tiers. Each table key maps to a flat list of `{item_key, quantity}` entries.
- JSON data files live under `data/` (consistent with `data/rooms/`, `data/cards/`, `data/items/`, `data/npcs/`)

### Key Implementation Details

**Loader is synchronous (not async):** Unlike `load_items_from_json` which writes to DB, loot table loading is pure file I/O with no DB interaction — similar to `load_npc_templates()` in `server/room/objects/npc.py`. No `session` parameter needed.

**Shallow copy safety:** The old `generate_loot()` returned `list(LOOT_TABLES.get(...))` — a shallow copy of the list but shared inner dicts. The new `list(game.loot_tables.get(key, []))` preserves this exact behavior. Call sites must NOT mutate returned dicts (documented in Story 10.7 notes).

**`game` access in `chest.py`:** The `interact()` method already receives `game: Game` as a parameter (line 24), so accessing `game.loot_tables` is straightforward.

**`game` access in `combat.py`:** The `_check_combat_end` function already receives `game` as a parameter. `generate_loot` at line 117 can be replaced directly with `game.loot_tables.get(...)`.

**Startup ordering:** Loot tables must load after items because loot entries reference item keys. The JSON is loaded without validation against item keys (matching current behavior — `generate_loot` never validated item keys either). Load after item loading block (line ~94) and before `_register_handlers()` (line ~96).

### What NOT to Change
- **Test assertion values**: Keep all literal assertions (`assert items[0]["item_key"] == "healing_potion"`, etc.)
- **Loot table content**: The JSON must be byte-for-byte equivalent to the Python dict. Do not add, remove, or reorder entries.
- **Combat loot distribution logic**: Only change the loot lookup; do not touch DB writes, inventory updates, or per-player distribution.
- **Chest interaction logic**: Only change the loot lookup; do not touch state management, DB writes, or item hydration.

### Previous Story Intelligence (14.1)
Story 14.1 established the pattern for infrastructure changes:
- Pure mechanical replacement across files
- Zero test assertion changes
- `make test` as verification gate
- All 804 tests must pass
- Import pattern: `from server.core.config import settings` — follow similar patterns for any new imports

### Project Structure Notes
- New JSON file: `data/loot/loot_tables.json` (new subdirectory under `data/`)
- Deleted file: `server/items/loot.py`
- Modified files: `server/items/item_repo.py`, `server/app.py`, `server/net/handlers/combat.py`, `server/room/objects/chest.py`
- Modified test files: `tests/test_loot.py`, `tests/test_party_combat.py`, `tests/test_chest.py`

### References
- [Source: _bmad-output/planning-artifacts/epics.md#Story 14.2]
- [Source: _bmad-output/planning-artifacts/epics.md#ADR-14-2, ADR-14-15]
- [Source: server/items/loot.py] — current hardcoded loot tables (to be deleted)
- [Source: server/items/item_repo.py] — loader function target
- [Source: server/app.py#startup] — initialization sequence
- [Source: server/net/handlers/combat.py#line 117] — combat loot call site
- [Source: server/room/objects/chest.py#line 35] — chest loot call site
- [Source: _bmad-output/implementation-artifacts/14-1-centralize-game-parameters-in-config.md] — previous story patterns

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List
- Created `data/loot/loot_tables.json` with 1:1 translation of hardcoded `LOOT_TABLES` dict (7 table keys, matching content exactly)
- Added `load_loot_tables(data_dir)` sync function to `server/items/item_repo.py` (ADR-14-2)
- Added `self.loot_tables: dict = {}` to `Game.__init__()` and loading in `Game.startup()` after items
- Replaced `generate_loot(key)` with `list(game.loot_tables.get(key, []))` in combat.py and chest.py
- Deleted `server/items/loot.py` entirely
- Updated `tests/test_loot.py`: replaced module import with `load_loot_tables` + local `_get_loot` helper; set `game.loot_tables` on mock games
- Updated `tests/test_party_combat.py`: replaced `generate_loot` imports and `patch()` with `game.loot_tables` setup
- Updated `tests/test_chest.py`: replaced `generate_loot` import with `load_loot_tables`; set `game.loot_tables` on mock game; rewrote loot unit tests
- All 804 tests pass, zero assertion value changes

### File List
- data/loot/loot_tables.json (new)
- server/items/item_repo.py (modified — added `load_loot_tables()`, `from typing import Any`)
- server/app.py (modified — added `self.loot_tables`, loot loading in startup)
- server/net/handlers/combat.py (modified — removed `generate_loot` import, use `game.loot_tables`)
- server/room/objects/chest.py (modified — removed `generate_loot` import, use `game.loot_tables`)
- server/items/loot.py (deleted)
- tests/test_loot.py (modified — replaced imports, use JSON-loaded tables)
- tests/test_party_combat.py (modified — replaced `generate_loot` usage with `game.loot_tables`)
- tests/test_chest.py (modified — replaced `generate_loot` usage with `load_loot_tables`)
