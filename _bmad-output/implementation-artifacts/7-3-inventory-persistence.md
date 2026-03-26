# Story 7.3: Inventory Persistence

Status: done

## Story

As a player,
I want my inventory to be saved and restored between sessions,
so that items I collect aren't lost when I log out or the server restarts.

## Acceptance Criteria

1. **Given** a player picks up an item (chest loot, combat reward),
   **When** the item is added to inventory,
   **Then** the inventory is saved to the DB immediately.

2. **Given** a player uses a consumable item,
   **When** the charge is consumed,
   **Then** the inventory is saved to the DB (in the same transaction as any stats changes).

3. **Given** a player logs in,
   **When** the server creates their entity,
   **Then** inventory is restored from the DB `inventory` JSON column using `Inventory.from_dict(data, item_lookup)`,
   **And** `from_dict` takes an item lookup callable `(str) -> ItemDef` to hydrate runtime objects without coupling Inventory to Game.

4. **Given** `Inventory` class currently has no `to_dict()`/`from_dict()` methods,
   **When** the story is complete,
   **Then** `to_dict()` serializes to `{item_key: quantity}` pairs suitable for DB storage,
   **And** `from_dict(data, item_lookup)` reconstructs the Inventory with hydrated ItemDef objects,
   **And** round-trip is verified: `from_dict(to_dict()) == original`.

5. **Given** a player dies in combat,
   **When** respawn occurs,
   **Then** items are retained (no item loss for prototype).

6. **Given** two concurrent sessions interact with the same chest (before FR55),
   **When** both attempt to loot,
   **Then** chest loot granting uses upsert pattern to prevent duplication.

7. **Given** `test_integration.py:165` asserts empty inventory on login,
   **When** the story is complete,
   **Then** the test is updated and `pytest tests/` passes.

## Tasks / Subtasks

- [ ] Task 1: Add `to_dict()` and `from_dict()` to Inventory (AC: 4)
  - [ ] `to_dict()` → `{item_key: quantity}` dict (matches DB JSON format)
  - [ ] `from_dict(data: dict, item_lookup: Callable[[str], ItemDef | None])` → reconstructs Inventory
  - [ ] `item_lookup` resolves item_key → ItemDef from the item repo without coupling to Game
  - [ ] Skip unknown item keys (item removed from game data) with a warning log
  - [ ] Unit test round-trip: `from_dict(inv.to_dict(), lookup) == inv`

- [ ] Task 2: Restore inventory on login (AC: 3) — Fixes ISS-007
  - [ ] In auth.py login handler, replace `Inventory()` with `Inventory.from_dict(player.inventory or {}, item_lookup)`
  - [ ] The `item_lookup` callable: `lambda key: game.item_repo.get(key)` or similar
  - [ ] This fixes ISS-007 — chest loot (already in DB) will now be visible at login

- [ ] Task 3: Sync chest loot to runtime inventory (AC: 1) — Fixes ISS-007
  - [ ] In `server/room/objects/chest.py`, after writing to DB, also add items to the in-memory `Inventory` object
  - [ ] Get player info from `game.player_entities[entity_id]`
  - [ ] Call `inventory.add(item_def, qty)` for each loot item
  - [ ] This makes looted items immediately visible without reconnecting

- [ ] Task 4: Save inventory on item use (AC: 2)
  - [ ] After `inventory.use()` or `inventory.remove()`, persist to DB
  - [ ] If stats also changed (e.g., healing potion), batch with stats save (depends on Story 7.2)

- [ ] Task 5: Save inventory on disconnect (AC: 1)
  - [ ] In `Game.handle_disconnect()`, serialize and save inventory to DB
  - [ ] Use `inventory.to_dict()` → `player_repo.update_inventory(session, player_id, data)`
  - [ ] Add `update_inventory()` to `player/repo.py`

- [ ] Task 6: Update tests (AC: 7)
  - [ ] Fix `test_integration.py:165` — inventory may not be empty on login if DB has items
  - [ ] Add round-trip test for `to_dict()` / `from_dict()`
  - [ ] Run `pytest tests/`

## Dev Notes

### Current Implementation — Two Disconnected Systems

1. **In-memory `Inventory`** (`server/items/inventory.py`): Dict of `{item_key: {def, qty}}`. Created empty on every login (auth.py line 119). Used for `inventory` action and combat item usage.
2. **DB `Player.inventory`** (models.py line 15): JSON column `{item_key: qty}`. Written to by chest.py. Never loaded into the in-memory Inventory.

These two systems are completely disconnected — items in one are invisible to the other.

### Inventory Class Internals

- `server/items/inventory.py`: `self._items: dict[str, dict]` where each value is `{"def": ItemDef, "qty": int}`
- `add(item_def, qty)`: Adds or increments
- `use(item_key)`: Decrements charges, removes if depleted
- `get_inventory()` (lines 64-77): Returns list of dicts for client display — NOT suitable for DB persistence
- No `to_dict()` or `from_dict()` exists

### Chest Loot Pattern (chest.py lines 56-64)

```python
inventory = dict(player.inventory or {})
for item in items:
    key = item["item_key"]
    inventory[key] = inventory.get(key, 0) + item["quantity"]
player.inventory = inventory
```

Writes to DB only. The `game` object is accessible via the handler context for runtime inventory sync.

### ISS-007 Fix

This story fully resolves ISS-007 (chest loot not in runtime). Two fixes: (1) Load DB inventory on login via `from_dict()`, (2) Sync chest loot to runtime inventory immediately. Mark ISS-007 as done when this story completes.

### Project Structure Notes

- Modified files: `server/items/inventory.py`, `server/net/handlers/auth.py`, `server/room/objects/chest.py`, `server/player/repo.py`, `server/app.py`
- No new files needed

### References

- [Source: server/items/inventory.py — full file]
- [Source: server/net/handlers/auth.py — line 119, Inventory()]
- [Source: server/room/objects/chest.py — lines 56-64]
- [Source: server/player/models.py — line 15, inventory JSON column]
- [Source: ISS-007 — chest loot not in runtime inventory]
- [Source: architecture.md#Section 6 — Item & Inventory System]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Completion Notes List
- Task 1: Added `to_dict()` → `{item_key: qty}` and `from_dict(data, item_lookup)` to Inventory class with unknown-key warning
- Task 2: Login handler now restores inventory from DB via `Inventory.from_dict()` with item definitions lookup — fixes ISS-007
- Task 3: Chest loot now syncs to runtime inventory immediately via `runtime_inv.add_item()` after DB write
- Task 4: Item use (both outside and in combat) persists inventory to DB via `update_inventory()`
- Task 5: Added `update_inventory()` to player repo; disconnect handler saves inventory alongside position and stats
- Task 6: Added `tests/test_inventory_persistence.py` with 7 round-trip tests; all existing tests pass

### File List
- `server/items/inventory.py` — Added `to_dict()`, `from_dict()` methods
- `server/player/repo.py` — Added `update_inventory()`
- `server/net/handlers/auth.py` — Inventory restore from DB on login
- `server/room/objects/chest.py` — Runtime inventory sync on loot
- `server/net/handlers/inventory.py` — Persist inventory after item use
- `server/net/handlers/combat.py` — Persist inventory after combat item use
- `server/app.py` — Save inventory on disconnect
- `tests/test_inventory_persistence.py` — New test file (7 tests)
