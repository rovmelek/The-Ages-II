# Story 10.7: Mob Loot Drops

Status: done

## Story

As a player,
I want defeated mobs to drop items based on their loot table,
so that combat has tangible rewards beyond XP.

## Acceptance Criteria

1. **Given** an NPC template defines `"loot_table": "slime_loot"`, **When** combat ends with victory (mob HP <= 0), **Then** loot is generated from the NPC's loot table, items are added to each victorious player's inventory, inventory is persisted to DB, and the `combat_end` message includes `"loot": [{"item_key": "...", "quantity": N}, ...]`.

2. **Given** `LOOT_TABLES` in `chest.py` currently only has `common_chest` and `rare_chest`, **When** the story is complete, **Then** the following mob loot tables are added: `goblin_loot`, `slime_loot`, `bat_loot`, `troll_loot`, `dragon_loot` with thematically appropriate drops (e.g., slime -> healing_potion, goblin -> iron_shard).

3. **Given** the `generate_loot()` function exists in `chest.py`, **When** the story is complete, **Then** `generate_loot()` and `LOOT_TABLES` are moved to a shared location (`server/items/loot.py`) accessible by both chest and combat systems. `chest.py` imports from the shared location. Existing tests that import from `chest.py` are updated.

4. **Given** multiple players are in combat when the mob is defeated, **When** loot is generated, **Then** each player receives the same loot (prototype — no loot splitting).

5. **Given** an NPC has an empty `loot_table` string or a key not found in `LOOT_TABLES`, **When** combat ends with victory, **Then** no loot is generated, no inventory changes occur, and the `combat_end` message omits the `loot` field or includes an empty list. No errors are raised.

6. **Given** the web client receives a `combat_end` with loot, **When** the UI updates, **Then** the loot items are displayed in the combat result message (item_key and quantity — human-readable names are a future enhancement).

7. **And** tests verify loot generation, inventory integration, and combat_end payload. `pytest tests/` passes.

## Tasks / Subtasks

- [x] Task 1: Extract loot system to shared module (AC: #3)
  - [x] 1.1: Create `server/items/loot.py` — move `LOOT_TABLES` dict and `generate_loot()` from `server/room/objects/chest.py`
  - [x] 1.2: Update `server/room/objects/chest.py` to import `generate_loot` from `server.items.loot` (chest.py only uses `generate_loot()`, not `LOOT_TABLES` directly)
  - [x] 1.3: Update any test files that import `generate_loot` or `LOOT_TABLES` from `chest` to use `server.items.loot`

- [x] Task 2: Add mob loot tables (AC: #2)
  - [x] 2.1: In `server/items/loot.py`, add 5 new loot tables to `LOOT_TABLES`:
    - `slime_loot`: `[{"item_key": "healing_potion", "quantity": 1}]`
    - `goblin_loot`: `[{"item_key": "iron_shard", "quantity": 1}]`
    - `bat_loot`: `[{"item_key": "antidote", "quantity": 1}]`
    - `troll_loot`: `[{"item_key": "healing_potion", "quantity": 1}, {"item_key": "iron_shard", "quantity": 2}]`
    - `dragon_loot`: `[{"item_key": "fire_essence", "quantity": 2}, {"item_key": "healing_potion", "quantity": 2}]`

- [x] Task 3: Add loot distribution to combat victory handler (AC: #1, #4, #5)
  - [x] 3.1: In `server/net/handlers/combat.py` `_check_combat_end()`, on victory (BEFORE `game.kill_npc()`): look up the NPC entity via `room = game.room_manager.get_room(instance.room_key)` then `npc = room.get_npc(instance.npc_id)`. Extract `loot_table` string early.
  - [x] 3.2: If `loot_table` is empty or `generate_loot()` returns empty list, skip loot — no error, no `loot` key in message (or empty list).
  - [x] 3.3: Call `generate_loot(loot_table)` to get items list.
  - [x] 3.4: Batch-load all needed `ItemDef` objects ONCE via `item_repo.get_all(session)` or individual `item_repo.get_by_key(session, key)` calls — build a local `{item_key: ItemDef}` dict OUTSIDE the per-participant loop. Do NOT query per item per player.
  - [x] 3.5: For each participant where `game.player_entities.get(eid)` is not None: (a) update DB inventory via direct model mutation in an `async_session()` scope (load player, merge loot into `player.inventory` dict, commit) — see Dual-Write code sample below, (b) update runtime `Inventory` via `inventory.add_item(item_def, quantity)`. Both DB and runtime must be updated (dual-write).
  - [x] 3.6: Add `"loot": loot_items` as a **top-level key** in the `end_result` dict (same level as `"victory"` and `"rewards"`) in the handler code (`_check_combat_end`), NOT inside `CombatInstance.get_combat_end_result()`.
  - [x] 3.7: If a participant disconnected (player_info is None), silently skip them — no error. This matches the existing XP guard pattern.

- [x] Task 4: Update web client combat end display (AC: #6)
  - [x] 4.1: In `web-demo/js/game.js` `handleCombatEnd()`, after displaying XP, check for `data.loot` array
  - [x] 4.2: If loot exists and is non-empty, display each item: "Loot: item_key x quantity, ..." in the chat log

- [x] Task 5: Add tests (AC: #7)
  - [x] 5.1: Create `tests/test_loot.py` — test `generate_loot()` with mob loot table keys, unknown keys, and empty string
  - [x] 5.2: Test combat victory with loot — verify `combat_end` result includes loot
  - [x] 5.3: Test that loot is added to player inventory after combat victory
  - [x] 5.4: Test multi-player combat — each player gets the same loot
  - [x] 5.5: Test NPC with empty `loot_table` — no loot generated, no errors
  - [x] 5.6: Run `pytest tests/` — all tests pass

## Dev Notes

### Critical Implementation Details

**Loot Lookup Timing:** In `_check_combat_end()`, the NPC data (including `loot_table`) must be read BEFORE `game.kill_npc()` is called. Currently `kill_npc()` sets `npc.is_alive = False` but doesn't remove the NPC from the room, so the data should still be accessible. However, to be safe, extract the `loot_table` value early in the victory branch.

**NPC Access Pattern:** The `CombatInstance` stores `npc_id` and `room_key` (set at creation in `_handle_mob_encounter()`). To get the NPC's `loot_table`:
```python
room = game.room_manager.get_room(instance.room_key)
npc = room.get_npc(instance.npc_id) if room else None
loot_table_key = npc.loot_table if npc else ""
```

**Item Lookup — NO `game.item_defs` attribute exists.** The `Game` class does NOT have an `item_defs` dict. Items are loaded into the DB at startup via `item_repo.load_items_from_json()`. To look up item definitions at runtime, use `item_repo.get_by_key(session, item_key)` inside an `async_session()` scope — this returns a DB model, convert with `ItemDef.from_db(db_item)`. For batch loading (preferred for loot), use `item_repo.get_all(session)` to build a local dict once, then reuse it. See `auth.py:266-267` for the pattern:
```python
from server.items import item_repo as items_repo
from server.items.item_def import ItemDef

async with async_session() as session:
    all_items = await items_repo.get_all(session)
    item_defs = {i.item_key: ItemDef.from_db(i) for i in all_items}
```

**Dual-Write Pattern (DB + Runtime):** Both the DB inventory row AND the runtime `Inventory` object must be updated, or they desync. Follow chest.py's pattern: update DB first, then sync runtime. For each participant:
```python
# 1. Update DB inventory
db_id = player_info["db_id"]  # NOT player_info["entity"].player_db_id
async with async_session() as session:
    player = await player_repo.get_by_id(session, db_id)
    db_inv = dict(player.inventory or {})
    for item in loot_items:
        db_inv[item["item_key"]] = db_inv.get(item["item_key"], 0) + item["quantity"]
    player.inventory = db_inv
    await session.commit()

# 2. Sync runtime inventory
runtime_inv = player_info["inventory"]
for item in loot_items:
    idef = item_defs.get(item["item_key"])
    if idef:
        runtime_inv.add_item(idef, item["quantity"])
```

**DB Persistence:** Stats and inventory use separate `async_session()` scopes — each repo function opens/commits its own session. Do NOT try to share a session between `update_stats()` and `update_inventory()`. Call them sequentially in separate scopes. This matches `handle_use_item_combat` (combat.py:248-251).

**`combat_end` Message Format:** Currently sends `{"type": "combat_end", "victory": true, "rewards": {"xp": 25}}`. Add loot as a **top-level key** (same level as `victory` and `rewards`): `{"type": "combat_end", "victory": true, "rewards": {"xp": 25}, "loot": [{"item_key": "healing_potion", "quantity": 1}]}`. Add the `"loot"` key to `end_result` dict in `_check_combat_end()` handler code — do NOT modify `CombatInstance.get_combat_end_result()`.

**`generate_loot()` returns shallow copies.** `list(LOOT_TABLES.get(...))` copies the list but inner dicts share references with `LOOT_TABLES`. Do NOT mutate the returned dicts (e.g., don't add a `"name"` field). If mutation is needed, use `copy.deepcopy()` or create new dicts.

### Files to Create

- `server/items/loot.py` — shared loot table definitions and `generate_loot()` function
- `tests/test_loot.py` — unit tests for the extracted loot module

### Files to Modify

- `server/room/objects/chest.py` — remove `LOOT_TABLES` and `generate_loot()`, replace with imports from `server.items.loot`
- `server/net/handlers/combat.py` — add loot generation and distribution in `_check_combat_end()` victory branch
- `web-demo/js/game.js` — update `handleCombatEnd()` to display loot items
- `tests/test_chest.py` — update import of `generate_loot` from `server.room.objects.chest` to `server.items.loot`

### Existing Code Patterns to Follow

- **Item lookup:** NO `game.item_defs` attribute exists. Use `item_repo.get_by_key(session, key)` or batch via `item_repo.get_all(session)` inside `async_session()`. See "Item Lookup" section above.
- **Inventory.add_item():** `add_item(item_def: ItemDef, quantity: int = 1)` — stacks if already present.
- **Inventory.to_dict():** Returns `{item_key: quantity}` for DB serialization.
- **Player entities dict:** `game.player_entities[entity_id]` -> `{"entity": PlayerEntity, "room_key": str, "inventory": Inventory, "db_id": int}`. Use `player_info["db_id"]` for DB operations (NOT `entity.player_db_id` — both work but `"db_id"` is the established pattern in combat handlers).
- **Handler function signature:** `async def handle_X(ws, data, game)` — `game` is the `Game` instance.
- **NPC access:** `room.get_npc(npc_id)` returns `NpcEntity | None` — used throughout codebase (combat.py:103, movement.py:124, auth.py:59).

### What NOT to Do

- Do NOT add randomization to `generate_loot()` — the current implementation returns all items from the table deterministically. Keep this consistent with chest behavior. Randomized drops are a future enhancement.
- Do NOT add new item definitions — use existing items (healing_potion, antidote, fire_essence, iron_shard) for mob loot tables.
- Do NOT modify `CombatInstance` class or `get_combat_end_result()` — loot generation and `"loot"` key injection belong in the handler layer (`_check_combat_end()`), not in the combat instance.
- Do NOT persist `loot_table` on `CombatInstance` — read it from the NPC entity at combat end time.
- Do NOT add loot on defeat — loot is victory-only.
- Do NOT mutate dicts returned by `generate_loot()` — they share references with `LOOT_TABLES` (shallow copy). Create new dicts if additional fields are needed.
- Do NOT try to share a DB session between `update_stats()` and `update_inventory()` — each repo function manages its own session/commit. Call them sequentially.
- Do NOT use `game.item_defs` — this attribute does not exist on the `Game` class.

### Testing Patterns

- **Unit test for loot module (`tests/test_loot.py`):** Test `generate_loot()` with known mob table keys (`slime_loot`, `goblin_loot`, etc.), unknown keys (returns empty list), and empty string (returns empty list). Also test that `generate_loot` returns copies, not references to `LOOT_TABLES` entries.
- **Combat handler test:** Mock `game.room_manager.get_room()` to return a room with an NPC that has a `loot_table`. Verify loot appears as top-level `"loot"` key in `combat_end` message. Follow patterns in `tests/test_combat.py` and `tests/test_combat_resolution.py`.
- **Integration:** Verify both DB inventory and runtime `Inventory` are updated after combat victory.
- **Edge case — disconnected participant:** If `game.player_entities.get(eid)` returns None during loot distribution, that participant is silently skipped (no loot, no error). This matches the existing XP guard pattern at combat.py:57-58. A test should verify no crash when a participant is missing from `player_entities`.
- **Import path test:** Verify `tests/test_chest.py` still works after `generate_loot` is moved — update its import from `server.room.objects.chest` to `server.items.loot`.

### Previous Story Learnings

- **From 10.6:** 518 tests pass, 2 pre-existing failures (TestChestInteraction DB issues), 2 deselected (known hangers). Zero new failures.
- **From 10.2:** Interactive objects are non-walkable — NPC interaction requires adjacency.
- **From 10.1:** `_cleanup_player()` refactor centralizes player removal logic. Use it as reference for save-before-remove patterns.
- **Git pattern:** Recent commits show one commit per story. Keep loot table extraction and combat integration in the same commit.

### Project Structure Notes

- New file `server/items/loot.py` fits the items domain — loot tables are item-related, not room-object-related.
- Moving `generate_loot()` out of `chest.py` follows the architecture principle: chest.py is a room object handler, loot generation is a shared item system concern.
- The `server/items/` package already has `__init__.py`, `item_def.py`, `item_repo.py`, `inventory.py`.

### References

- [Source: server/room/objects/chest.py#LOOT_TABLES] — current loot table definitions (lines 21-30)
- [Source: server/room/objects/chest.py#generate_loot] — current loot generation function (lines 33-35)
- [Source: server/net/handlers/combat.py#_check_combat_end] — combat victory handler (lines 46-117)
- [Source: server/combat/instance.py#get_combat_end_result] — combat end result builder (lines 398-404)
- [Source: server/items/inventory.py#add_item] — inventory item addition (lines 42-50)
- [Source: server/room/objects/npc.py#NpcEntity] — NPC dataclass with loot_table field (line 20)
- [Source: data/npcs/base_npcs.json] — NPC templates with loot_table strings
- [Source: data/items/base_items.json] — available item definitions
- [Source: web-demo/js/game.js#handleCombatEnd] — client combat end display (lines 992-1024)
- [Source: _bmad-output/planning-artifacts/epics.md#Story 10.7] — acceptance criteria
- [Source: _bmad-output/planning-artifacts/architecture.md] — architecture spec

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- CombatManager uses `_player_to_instance` (not `_player_instances`) — fixed in tests
- Pre-existing test failures: 2 TestChestInteraction DB issues (unchanged from Story 10.6 baseline)
- Pre-existing deselected: 2 known hanging tests

### Completion Notes List

- Extracted `LOOT_TABLES` and `generate_loot()` from `server/room/objects/chest.py` to new shared module `server/items/loot.py`
- Added 5 mob loot tables: `slime_loot`, `goblin_loot`, `bat_loot`, `troll_loot`, `dragon_loot`
- Added loot distribution in `_check_combat_end()` victory branch — NPC lookup before kill, batch item_def loading, dual-write to DB + runtime inventory
- Loot added as top-level `"loot"` key in `combat_end` message, not inside `CombatInstance`
- Disconnected participants silently skipped (matching existing XP guard pattern)
- Web client `handleCombatEnd()` displays loot as "Loot: item_key xN" after XP
- 16 new tests in `tests/test_loot.py` covering: all 5 mob tables, unknown/empty tables, list copy behavior, combat victory with loot, no-loot-table edge case, multi-player same loot, disconnected participant, defeat no loot
- Updated `tests/test_chest.py` import path for `generate_loot`
- 534 passed, 2 pre-existing failures, 2 deselected — zero new failures

### Change Log

- 2026-04-10: Story 10.7 implemented — mob loot drops on combat victory

### File List

- server/items/loot.py (created — shared loot tables and generate_loot)
- server/room/objects/chest.py (modified — removed LOOT_TABLES/generate_loot, imports from server.items.loot)
- server/net/handlers/combat.py (modified — loot distribution in _check_combat_end victory branch)
- web-demo/js/game.js (modified — loot display in handleCombatEnd)
- tests/test_loot.py (created — 16 tests for loot system)
- tests/test_chest.py (modified — updated generate_loot import path)
