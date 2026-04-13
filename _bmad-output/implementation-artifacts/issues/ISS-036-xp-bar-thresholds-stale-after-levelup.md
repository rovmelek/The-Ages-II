# ISS-036: XP Bar Thresholds Stale After Level-Up

**Severity**: Medium — UI displays misleading XP values (e.g., "2206 / 1000")
**Status**: Done
**Found**: Playtesting

## Symptoms

After leveling up, the XP bar shows total accumulated XP against the level-1 threshold instead of progress within the current level. Example: a level 3 player with 2206 total XP sees "2206 / 1000" instead of "206 / 1000".

## Root Cause

`xp_for_next_level` and `xp_for_current_level` are only sent to the client on initial login via `build_stats_payload()` (`server/player/service.py:145-146`). Two server messages that change level/XP do NOT include updated thresholds:

1. **`xp_gained`** (`server/net/xp_notifications.py:48-54`) — sends `new_total_xp` but no thresholds. After gaining enough XP to cross a level boundary, the old thresholds become stale.
2. **`level_up_complete`** (`server/net/handlers/levelup.py:90-102`) — sends new `level` but no thresholds. The client updates `stats.level` but not `xp_for_next_level` / `xp_for_current_level`.

The client (`web-demo/js/game.js:1688-1710`) correctly computes `xpInLevel = currentXp - xpPrev` and `xpNeeded = xpNext - xpPrev`, but uses stale values from login.

## Proposed Fix

**Server side:**
1. Add `xp_for_next_level` and `xp_for_current_level` to the `xp_gained` message in `notify_xp()`.
2. Add `xp_for_next_level` and `xp_for_current_level` to the `level_up_complete` response in `handle_level_up()`.
3. Update outbound schemas `XpGainedMessage` and `LevelUpCompleteMessage` to include these fields.

**Client side:**
4. In `handleXpGained()`: read and apply updated thresholds from the message.
5. In `handleLevelUpComplete()`: read and apply updated thresholds from the message.

## Impact

- `server/net/xp_notifications.py` — add thresholds to `xp_gained` payload in `notify_xp()`
- `server/net/handlers/levelup.py` — add thresholds to `level_up_complete` payload in `handle_level_up()`
- `server/net/outbound_schemas.py` — add `xp_for_next_level`/`xp_for_current_level` to `XpGainedMessage` and `LevelUpCompleteMessage`
- `server/core/constants.py` — `PROTOCOL_VERSION` bumped from 1.1 → 1.2 (new fields on existing message types)
- `web-demo/js/game.js` — update `handleXpGained()` and `handleLevelUpComplete()` to apply thresholds
- `tests/test_outbound_schemas.py` — updated `test_xp_gained`, `test_level_up_complete`, `test_level_up_complete_with_skipped` to include required threshold fields
