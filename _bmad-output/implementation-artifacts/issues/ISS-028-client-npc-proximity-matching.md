# ISS-028: Client-Side NPC Proximity Matching on Combat End

**Severity:** Medium
**Component:** web-demo/js/game.js
**Found during:** Codebase review (adversarial analysis)

## Description

`handleCombatEnd()` at lines 1175-1184 has client-side NPC proximity matching:

```js
if (!npc && gameState.combat && gameState.player) {
    const mobName = gameState.combat.mob?.name;
    if (mobName) {
        npc = gameState.room.npcs.find(
            (n) => n.name === mobName && n.is_alive &&
                Math.abs(n.x - gameState.player.x) <= 1 &&
                Math.abs(n.y - gameState.player.y) <= 1
        );
    }
}
```

This fires when `data.defeated_npc_id` is missing. Verified at `server/net/handlers/combat.py:135-136` — the server sends `defeated_npc_id` for all NPC victories where `instance.npc_id` is truthy. The fallback encodes combat range rules (Manhattan distance ≤ 1) that belong to the server.

## Root Cause

Compensatory logic from before the server reliably sent `defeated_npc_id`. The server now always sets `npc_id` on combat instances initiated through NPC interaction.

## Proposed Fix

Remove the proximity fallback entirely. Keep only the `data.defeated_npc_id` lookup path. If no `defeated_npc_id` is provided, no NPC marking is needed (the combat wasn't against an NPC, or the server will handle it via room state broadcast).

## Impact

- Removes game logic (combat range rules) from the thin client
- Eliminates potential false positives from proximity matching
