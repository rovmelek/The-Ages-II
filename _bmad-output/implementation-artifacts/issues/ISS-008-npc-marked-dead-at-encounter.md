# Issue: NPC marked dead at combat encounter, not at combat victory

**ID:** ISS-008
**Severity:** High
**Status:** Open
**Delivery:** Epic 4 (Combat System)
**Test:** Manual — enter combat with NPC, observe NPC state before combat resolves
**Created:** 2026-03-25
**Assigned:** BMad Developer

## Description

When a player moves onto a hostile NPC tile and combat starts, the NPC's `is_alive` flag is set to `False` immediately at encounter time in the movement handler. This happens BEFORE the combat resolves — meaning the NPC appears dead on the map even while combat is still in progress.

## Expected

1. Player moves onto NPC tile → combat starts
2. During combat: NPC should still appear alive on the map (or hidden by combat overlay)
3. Player wins combat → NPC is marked dead (`is_alive = False`)
4. Player loses or flees → NPC remains alive

## Actual

1. Player moves onto NPC tile → `npc.is_alive = False` is set immediately
2. NPC appears dead (x icon) on the map before combat resolves
3. If player flees: NPC is already dead — cannot re-encounter
4. The NPC effectively "dies" the moment you touch it, regardless of combat outcome

## Impact

**Medium-high gameplay impact:**
- Fleeing from combat still kills the NPC — free kills with no risk
- Other players in the room see the NPC die before combat even starts
- NPC death broadcast (FR56) would incorrectly fire at encounter, not victory
- Respawn timers start at encounter, not at actual death

## Design Reference

- Movement handler: `server/net/handlers/movement.py` — `_handle_mob_encounter()` line ~107 sets `npc.is_alive = False`
- Combat end handler: `server/net/handlers/combat.py` — `_check_combat_end()` does NOT set NPC death (already done)
- Game.kill_npc: `server/app.py` — schedules respawn, but is called at encounter not victory
- Architecture: FR56 (Epic 7) documents this as a known issue

## Steps to Reproduce

1. Login and find a hostile NPC (red `!` on map)
2. Move onto the NPC tile — combat starts
3. Observe the map behind combat overlay — NPC now shows as dead (x)
4. Click Flee to exit combat
5. Walk back to the NPC's tile — no combat triggers (NPC is already dead)
6. Wait for respawn timer — NPC eventually reappears

## Root Cause

In `server/net/handlers/movement.py`, the `_handle_mob_encounter()` function calls `game.kill_npc()` before creating the combat instance:

```python
async def _handle_mob_encounter(...):
    npc = room.get_npc(npc_id)
    ...
    # This should happen AFTER combat victory, not here
    await game.kill_npc(room_key, npc_id)  # Sets is_alive=False, starts respawn timer

    # Create combat instance
    instance = game.combat_manager.create_instance(mob_data)
    ...
```

## Recommendation

1. **Remove** the `game.kill_npc()` call from `_handle_mob_encounter()`
2. **Add** `game.kill_npc()` call to `_check_combat_end()` when `victory=True`
3. Consider adding a `in_combat` flag to NpcEntity to prevent other players from encountering an NPC that's already in a fight

## Related Issues

- FR56 (Epic 7) — NPC death broadcast. Must be fixed here first before broadcast makes sense.
- ISS-005 (DoT) — combat resolution has multiple gaps

---

**Priority for fix:** This release (High — flee exploit gives free NPC kills)
