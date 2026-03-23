# Story 3.2: Chests with One-Time Loot

Status: done

## Story

As a player,
I want to open chests and receive loot that's unique to me,
So that I'm rewarded for exploring the world.

## Acceptance Criteria

1. Player interacts with a chest they haven't opened → loot generated from the chest's `loot_table` config, added to player's inventory, `PlayerObjectState` created marking opened, client receives `interact_result` with loot
2. Player interacts with a chest they already opened → client receives `interact_result` with `"Already looted"`, no items added
3. Player A opens a chest → Player B can open the same chest independently and receive their own loot (per-player state via `state_scope: "player"`)
4. Chest object must be registered in the object registry as type `"chest"` so `handle_interact` delegates correctly

## Tasks / Subtasks

- [ ] Task 1: Create `server/room/objects/chest.py` with `ChestObject` class (AC: #1, #2, #4)
  - [ ] Subclass `InteractiveObject` from `server/room/objects/base.py`
  - [ ] Override `async def interact(player_id, game) -> dict`
  - [ ] Load player state via `get_player_object_state(session, player_id, room_key, object_id)`
  - [ ] If already opened (`state.get("opened")`) → return `{"status": "already_looted", "message": "Already looted"}`
  - [ ] If not opened → generate loot from `self.config["loot_table"]`, add to player inventory, save state as `{"opened": True}`, return loot details
- [ ] Task 2: Create simple loot table system (AC: #1)
  - [ ] Define loot tables as a dict in `server/room/objects/chest.py` or a simple lookup
  - [ ] A loot table maps to a list of `{"item_key": str, "quantity": int}` items
  - [ ] For prototype: hardcode a few loot tables (e.g., `"common_chest"` → healing potion + iron shard)
- [ ] Task 3: Implement inventory update in chest interaction (AC: #1)
  - [ ] Read player's current inventory from `Player.inventory` JSON column
  - [ ] Add loot items (increment quantity for each item_key)
  - [ ] Save updated inventory back to DB
- [ ] Task 4: Register `ChestObject` in the object registry (AC: #4)
  - [ ] In `server/room/objects/__init__.py`, import and register: `register_object_type("chest", ChestObject)`
- [ ] Task 5: Add chest object to test room JSON data (AC: #1)
  - [ ] Add an interactive chest object to `data/rooms/test_room.json` objects array
- [ ] Task 6: Write tests `tests/test_chest.py` (AC: #1-4)
  - [ ] Test opening chest first time returns loot
  - [ ] Test opening chest second time returns "Already looted"
  - [ ] Test two different players can open the same chest independently
  - [ ] Test loot is added to player inventory
  - [ ] Test chest is registered in OBJECT_HANDLERS
- [ ] Task 7: Verify all tests pass
  - [ ] Run `pytest tests/test_chest.py -v`
  - [ ] Run `pytest tests/ -v` to verify no regressions (129 existing tests)

## Dev Notes

### Architecture Compliance

| Component | File Location |
|-----------|--------------|
| ChestObject class | `server/room/objects/chest.py` |
| Object registration | `server/room/objects/__init__.py` |
| Test room data | `data/rooms/test_room.json` |

### Chest JSON Format (from architecture.md §4.2)

```json
{
  "id": "chest_01",
  "type": "chest",
  "category": "interactive",
  "x": 3, "y": 3,
  "state_scope": "player",
  "config": {
    "loot_table": "common_chest",
    "locked": false
  }
}
```

### Interact Result Format

First open:
```python
{"status": "looted", "items": [{"item_key": "healing_potion", "quantity": 1}]}
```

Already opened:
```python
{"status": "already_looted", "message": "Already looted"}
```

### Existing Infrastructure to Reuse

- **InteractiveObject base**: `server/room/objects/base.py` — subclass and override `interact()`
- **Object registry**: `server/room/objects/registry.py` — call `register_object_type("chest", ChestObject)`
- **State helpers**: `server/room/objects/state.py` — `get_player_object_state()` / `set_player_object_state()` for per-player chest state
- **Player model**: `server/player/models.py` — `Player.inventory` is JSON column `{item_key: quantity}`
- **Player repo**: `server/player/repo.py` — may need to add `update_inventory()` or do inline update
- **Database session**: `server.core.database.async_session` for DB operations inside `interact()`
- **handle_interact**: Already delegates to `obj.interact(player_db_id, game)` and wraps result in `interact_result`

### Anti-Patterns to Avoid

- **DO NOT** implement loot rarity, drop rates, or complex loot generation — simple table lookup for prototype
- **DO NOT** add chest animations, sound effects, or visual state — server only
- **DO NOT** implement locked chests requiring keys — `locked: false` for now
- **DO NOT** add chest respawn/reset timers — permanent one-time loot per architecture spec
- **DO** use `state_scope: "player"` so each player has independent chest state

### Previous Story Intelligence

From Story 3.1:
- `InteractiveObject.interact(player_id, game)` signature — `player_id` is the DB primary key (int)
- `create_object(obj_dict)` factory builds typed objects from JSON using `OBJECT_HANDLERS`
- `handle_interact` already handles login check, object lookup, delegates to `interact()`, wraps in `interact_result`
- State helpers use `async_session` context manager for DB operations
- `RoomInstance._interactive_objects` indexes by `obj["id"]` for objects with `category == "interactive"`
- 129 existing tests must not regress

### Project Structure Notes

- New files: `server/room/objects/chest.py`, `tests/test_chest.py`
- Modified files: `server/room/objects/__init__.py` (register chest type), `data/rooms/test_room.json` (add chest)

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#4.2 State Scope]
- [Source: _bmad-output/planning-artifacts/architecture.md#4.1 Object Categories]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.2]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Debug Log References
None

### Completion Notes List
- `server/room/objects/chest.py`: ChestObject with per-player one-time loot, loot table lookup, inventory update
- `server/room/objects/__init__.py`: Registers "chest" type in OBJECT_HANDLERS on import
- `server/net/handlers/interact.py`: Added `import server.room.objects` to trigger registration
- `data/rooms/test_room.json`: Added interactive chest object with common_chest loot table
- Fixed test_interact.py state round-trip tests to clean up leftover DB data between runs
- 7 new tests (136 total), all passing — chest open, already looted, two players, inventory update, registration, loot generation

### File List
- `server/room/objects/chest.py` (new) — ChestObject with loot tables and inventory update
- `server/room/objects/__init__.py` (modified) — Registers chest type
- `server/net/handlers/interact.py` (modified) — Import objects package for registration
- `data/rooms/test_room.json` (modified) — Added chest_01 interactive object
- `tests/test_chest.py` (new) — 7 chest interaction tests
- `tests/test_interact.py` (modified) — Fixed state round-trip tests with DB cleanup
