# Issue: Victory XP rewards returned in message but never applied to player stats

**ID:** ISS-006
**Severity:** High
**Status:** Open
**Delivery:** Epic 4 (Combat System)
**Test:** Manual — win combat, check player stats for XP increase
**Created:** 2026-03-25
**Assigned:** BMad Developer

## Description

When a player wins combat, the server sends `{type: "combat_end", victory: true, rewards: {xp: 25}}`. However, the 25 XP is never actually added to the player's stats object or persisted to the database. The reward exists only in the message.

## Expected

After winning combat:
1. Player's stats should include updated XP (e.g., `stats.xp += 25`)
2. XP should be persisted to the database
3. The web client should display the updated XP

## Actual

- `combat_end` message includes `rewards: {xp: 25}` — purely informational
- `PlayerEntity.stats` dict is never updated with XP
- No database write occurs for the reward
- Player XP remains at whatever it was before combat

## Impact

**Progression is broken.** Players have no way to gain XP or advance. Combat victories feel unrewarding because nothing actually changes. This undermines the core gameplay loop.

## Design Reference

- Combat handler: `server/net/handlers/combat.py` — `_check_combat_end()` constructs rewards dict but doesn't apply it
- Player entity: `server/player/entity.py` — `stats` dict exists but no XP field is managed
- Architecture: references XP and leveling as part of progression system

## Steps to Reproduce

1. Login and enter combat with a mob
2. Win the combat (reduce mob HP to 0)
3. Observe `combat_end` message — includes `rewards: {xp: 25}`
4. Check player stats — XP has not changed
5. Disconnect and reconnect — no XP recorded

## Root Cause

In the combat handler's `_check_combat_end()`, the rewards dict is constructed and included in the broadcast message, but no code applies the reward to the player entity or persists it:

```python
rewards = {"xp": 25}
await websocket.send_json({"type": "combat_end", "victory": True, "rewards": rewards})
# Missing: entity.stats["xp"] = entity.stats.get("xp", 0) + 25
# Missing: DB persistence of updated stats
```

## Recommendation

After sending `combat_end` with victory=true:
1. Update `entity.stats["xp"]` for each surviving participant
2. Persist updated stats to the database via `player_repo`
3. Consider broadcasting updated stats to the player

Note: This is related to FR52 (Stats Persistence) in Epic 7, but the immediate fix is simply applying the reward — persistence can follow.

## Related Issues

- ISS-005 (DoT effects) — both are combat resolution gaps
- FR52 (Epic 7) — stats persistence would make this complete

---

**Priority for fix:** This release (High — core progression loop broken)
