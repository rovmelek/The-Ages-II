# ISS-025: Client Hardcodes Max Level-Up Selections (3)

**Severity:** Low
**Component:** web-demo/js/game.js
**Found during:** Codebase review (adversarial analysis)

## Description

`toggleLevelUpStat()` at line 1779 hardcodes the max selection count:

```js
} else if (gameState.levelUpSelections.length >= 3) {
    $feedback.textContent = 'Max 3 selected';
```

The server sends `choose_stats` (from `settings.LEVEL_UP_STAT_CHOICES = 3`) in the `level_up_available` message (`server/core/xp.py:111`). The client stores this in `gameState.pendingLevelUp` but ignores it, hardcoding `3` instead.

## Root Cause

The client was written before or without awareness of the `choose_stats` field in the server message.

## Proposed Fix

Read `gameState.pendingLevelUp.choose_stats` (with fallback to 3) and use it as the cap in `toggleLevelUpStat` and in the feedback message.

## Impact

- If `LEVEL_UP_STAT_CHOICES` is changed, client enforces wrong limit
