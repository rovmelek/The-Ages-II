# ISS-026: Client XP Threshold Formula Fallback

**Severity:** Medium
**Component:** web-demo/js/game.js, server/net/handlers/auth.py
**Found during:** Codebase review (adversarial analysis)

## Description

`updateStatsPanel()` at lines 1592-1593 has XP threshold fallbacks:

```js
const xpNext = stats.xp_for_next_level ?? (level * 1000);
const xpPrev = stats.xp_for_current_level ?? ((level - 1) * 1000);
```

This mirrors `XP_LEVEL_THRESHOLD_MULTIPLIER = 1000` from server config. The fallback actively fires on every login because neither the new-player nor returning-player login responses include `xp_for_next_level` or `xp_for_current_level` (verified at `auth.py:224-236` and `auth.py:384-396`). The `stats_result` response from the `/stats` command does include them (`query.py:124-125`).

## Root Cause

The login response stats payload was not updated when XP threshold fields were added to the stats query response. The client compensated with a hardcoded formula.

## Proposed Fix

Two-part fix:
1. **Server**: Add `xp_for_next_level` and `xp_for_current_level` to both login response payloads in `auth.py`.
2. **Client**: Remove the formula fallback. Use `stats.xp_for_next_level ?? 0` (show empty progress bar if somehow missing, rather than guessing).

## Impact

- XP progress bar shows correct values immediately on login instead of relying on hardcoded formula
- If `XP_LEVEL_THRESHOLD_MULTIPLIER` changes, client no longer silently drifts
