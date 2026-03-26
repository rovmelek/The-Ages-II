# Issue: Chest loot written to DB but not added to runtime Inventory object

**ID:** ISS-007
**Severity:** Critical
**Status:** Open
**Delivery:** Epic 5 (Items & Inventory)
**Test:** Manual — open chest, then check inventory via {action: "inventory"}
**Created:** 2026-03-25
**Assigned:** BMad Developer

## Description

When a player opens a chest via the interact action, the loot items are written to the database `player.inventory` JSON column. However, the items are NOT added to the in-memory `Inventory` object that the `inventory` action reads from. As a result, looted items are invisible to the player until they disconnect and reconnect (and even then, inventory is recreated empty — see ISS/FR54).

## Expected

After opening a chest:
1. Loot items appear in the `interact_result` response
2. Player sends `{action: "inventory"}`
3. Server responds with inventory including the newly looted items
4. Items are usable immediately

## Actual

1. Loot items appear in `interact_result` — correct
2. Player sends `{action: "inventory"}`
3. Server responds with EMPTY inventory (or whatever was there before)
4. Items exist in DB `player.inventory` column but NOT in runtime `Inventory` object
5. Items are effectively lost — can't be used or seen

## Impact

**Critical UX issue.** Players open chests and see "you got Healing Potion!" but then can't find or use the item. This makes the entire chest/loot system appear broken.

## Design Reference

- Chest handler: `server/room/objects/chest.py` — `generate_loot()` writes to DB `player.inventory`
- Inventory handler: `server/net/handlers/inventory.py` — reads from `game.player_entities[entity_id]["inventory"]`
- Inventory class: `server/items/inventory.py` — in-memory dict, created empty on login
- Two separate inventory systems exist: DB `player.inventory` (JSON column) and runtime `Inventory` object

## Steps to Reproduce

1. Login to the game
2. Navigate to a chest (e.g., chest_01 in town_square at 25,30)
3. Click the chest / send `{action: "interact", target_id: "chest_01"}`
4. Observe interact_result — shows loot items
5. Send `{action: "inventory"}`
6. Observe inventory response — items are NOT listed

## Root Cause

The chest's `generate_loot()` writes directly to the DB player model's inventory dict:

```python
# In chest.py
player_db.inventory[item_key] = player_db.inventory.get(item_key, 0) + qty
await session.commit()
```

But the runtime `Inventory` object (stored in `game.player_entities[entity_id]["inventory"]`) is a completely separate in-memory structure. Nothing bridges the two.

## Recommendation

After chest loot is generated, also add items to the runtime Inventory:

```python
# After DB write, also update runtime inventory
player_info = game.player_entities.get(entity_id)
if player_info:
    inventory = player_info["inventory"]
    for item_key, qty in loot.items():
        item_def = get_item_def(item_key)  # Look up from item repo
        if item_def:
            inventory.add(item_def, qty)
```

Alternatively, unify the two inventory systems into one source of truth (recommended as part of FR54).

## Related Issues

- FR54 (Epic 7) — Inventory persistence. Fixing that would also address this by loading DB inventory into runtime on login.
- ISS-005 — Both are "data recorded but not used" patterns

---

**Priority for fix:** This release (Critical — core loot system appears broken to players)
