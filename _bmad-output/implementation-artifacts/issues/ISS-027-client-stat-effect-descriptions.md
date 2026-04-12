# ISS-027: Client Hardcoded Stat Effect Descriptions

**Severity:** Low-Medium
**Component:** web-demo/js/game.js
**Found during:** Codebase review (adversarial analysis)

## Description

Two locations hardcode stat effect formulas:

### Stats Detail Panel (lines 1625-1631)

```js
con: { label: 'CON', key: 'constitution', desc: (v) => serverEffects?.constitution || `+${v * 5} max HP` },
cha: { label: 'CHA', key: 'charisma', desc: (v) => serverEffects?.charisma || `+${Math.round(v * 3)}% XP` },
```

These embed `CON_HP_PER_POINT = 5` and `XP_CHA_BONUS_PER_POINT = 0.03` as client-side formulas. The `serverEffects` source (`gameState.pendingLevelUp?.stat_effects`) is only populated during the level-up flow, so the fallback fires most of the time.

### Level-Up Modal (lines 1722-1728)

```js
constitution: { label: 'CON', effect: '+5 max HP per point' },
charisma: { label: 'CHA', effect: '+3% XP per point' },
```

Hardcoded descriptions that ignore `data.stat_effects` from the server's `level_up_available` message.

## Root Cause

The stats detail panel was built before `stat_effects` was available outside level-up. The level-up modal was built with local descriptions rather than reading the server-provided ones.

## Proposed Fix

1. **Stats Detail Panel**: Use generic, formula-free descriptions (e.g., "physical dmg bonus" instead of `+${v} physical dmg`). The stat value is already displayed separately.
2. **Level-Up Modal**: Read `data.stat_effects` from the server `level_up_available` message and use those descriptions. Fall back to generic text if somehow missing.

## Impact

- If `CON_HP_PER_POINT` or `XP_CHA_BONUS_PER_POINT` changes, client descriptions silently drift
- Level-up modal ignores server-provided descriptions
