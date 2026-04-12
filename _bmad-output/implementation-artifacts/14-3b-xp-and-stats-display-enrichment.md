# Story 14.3b: XP & Stats Display Enrichment

Status: done

## Story

As a game client developer,
I want server messages to include absolute XP totals, level thresholds, and stat effect descriptions,
So that the client displays XP progress and stat information without hardcoding the XP formula or stat bonus values.

## Acceptance Criteria

1. **Given** a player gains XP (combat, exploration, or interaction), **When** the server sends `xp_gained`, **Then** the message includes `new_total_xp` (absolute XP total after gain), **And** the existing `amount`, `source`, `detail` fields are preserved (additive-only).

2. **Given** a player requests stats, **When** the server sends `stats_result`, **Then** the `stats` sub-object includes `xp_for_next_level` and `xp_for_current_level` computed from the XP curve config, **And** the existing `xp_next` field is preserved (additive-only).

3. **Given** the server sends `level_up_available`, **Then** the message includes `xp_for_next_level` and `xp_for_current_level` for the player's current level (not `new_level`), **And** existing fields are preserved.

4. **Given** the server sends `level_up_available`, **Then** the message includes `stat_effects` — a dict mapping each of the 6 stat names to a human-readable effect description derived from config values (e.g., `{"constitution": "+5 max HP per point", "charisma": "+3% XP per point"}`), **And** existing fields are preserved.

5. **Given** each enriched message type, **When** the corresponding server code path executes, **Then** an existing test (not a new test file) asserts the new fields are present with correct values (ADR-14-14).

6. **Given** the web client, **When** Story 14.3b is implemented, **Then** the client is updated minimally — uses `new_total_xp` instead of accumulating XP from deltas, uses server-provided `xp_for_next_level`/`xp_for_current_level` in the XP bar instead of hardcoded `level * 1000`, and uses `stat_effects` descriptions instead of hardcoded strings. Keep fallbacks for backward compatibility.

## Tasks / Subtasks

- [x] Task 1: Add `new_total_xp` to `xp_gained` message (AC: #1)
  - [x] 1.1: In `server/core/xp.py`, in `grant_xp()`, at lines 56-61 where the `xp_gained` dict is built, add `"new_total_xp": player_entity.stats["xp"]` to the dict. The stats["xp"] was already updated at line 48, so this is the post-grant total.

- [x] Task 2: Add `xp_for_next_level` and `xp_for_current_level` to `stats_result` (AC: #2)
  - [x] 2.1: In `server/net/handlers/query.py`, in `handle_stats()` at lines 116-132, add two fields inside the `"stats"` sub-object: `"xp_for_next_level": level * settings.XP_LEVEL_THRESHOLD_MULTIPLIER` and `"xp_for_current_level": (level - 1) * settings.XP_LEVEL_THRESHOLD_MULTIPLIER`. Place them after the existing `"xp_next"` field. Keep `xp_next` (additive-only).

- [x] Task 3: Add `xp_for_next_level` and `xp_for_current_level` to `level_up_available` (AC: #3)
  - [x] 3.1: In `server/core/xp.py`, in `send_level_up_available()` at lines 97-110, compute `current_level = stats.get("level", 1)` (this is the player's current level, NOT `new_level`). Add `"xp_for_next_level": current_level * settings.XP_LEVEL_THRESHOLD_MULTIPLIER` and `"xp_for_current_level": (current_level - 1) * settings.XP_LEVEL_THRESHOLD_MULTIPLIER` to the dict.

- [x] Task 4: Add `stat_effects` to `level_up_available` (AC: #4)
  - [x] 4.1: In `server/core/xp.py`, in `send_level_up_available()`, add a `"stat_effects"` dict to the message. Use Python's `:g` format specifier for `STAT_SCALING_FACTOR` (strips trailing `.0` from floats: `1.0` → `"1"`, `1.5` → `"1.5"`):
    ```python
    ssf = settings.STAT_SCALING_FACTOR
    "stat_effects": {
        "strength": f"+{ssf:g} physical damage per point",
        "dexterity": f"-{ssf:g} incoming damage per point",
        "constitution": f"+{settings.CON_HP_PER_POINT} max HP per point",
        "intelligence": f"+{ssf:g} magic damage per point",
        "wisdom": f"+{ssf:g} healing per point",
        "charisma": f"+{round(settings.XP_CHA_BONUS_PER_POINT * 100)}% XP per point",
    },
    ```
    With defaults (`STAT_SCALING_FACTOR=1.0`, `CON_HP_PER_POINT=5`, `XP_CHA_BONUS_PER_POINT=0.03`), the output is:
    `{"strength": "+1 physical damage per point", "constitution": "+5 max HP per point", "charisma": "+3% XP per point", ...}`

- [x] Task 5: Add test assertion for `new_total_xp` in `xp_gained` (AC: #5)
  - [x] 5.1: In `tests/test_xp.py`, in `test_grant_xp_sends_message` (line 229), after the existing assertions at line 244, add: `assert msg["new_total_xp"] == 59` (CHA=6, amount=50, so final=59, and stats["xp"] started at 0 → now 59).

- [x] Task 6: Add test assertions for `xp_for_next_level` and `xp_for_current_level` in `stats_result` (AC: #5)
  - [x] 6.1: In `tests/test_query.py`, in `test_stats_returns_player_stats` (line 184), add after line 203: `assert s["xp_for_next_level"] == 3000` (level=3, threshold=1000) and `assert s["xp_for_current_level"] == 2000` (level 3, prev threshold = 2×1000).
  - [x] 6.2: In `tests/test_query.py`, in `test_stats_excludes_transient` (line 207), update the `expected_keys` set at line 218 to include `"xp_for_next_level"` and `"xp_for_current_level"`.
  - [x] 6.3: In `tests/test_level_up.py`, in `test_stats_result_includes_xp_next` (line 340), add after line 360: `assert msg["stats"]["xp_for_next_level"] == 2000` and `assert msg["stats"]["xp_for_current_level"] == 1000` (level=2, threshold=1000).

- [x] Task 7: Add test assertions for new fields in `level_up_available` (AC: #5)
  - [x] 7.1: In `tests/test_level_up.py`, in `test_send_level_up_available` (line 57), after the existing assertions at line 77, add:
    - `assert msg["xp_for_next_level"] == 1000` (current level=1, threshold at level 1 = 1×1000)
    - `assert msg["xp_for_current_level"] == 0` (level 1, previous = (1-1)×1000 = 0)
    - `assert "stat_effects" in msg`
    - `assert msg["stat_effects"]["constitution"] == "+5 max HP per point"`
    - `assert msg["stat_effects"]["charisma"] == "+3% XP per point"`
    - `assert msg["stat_effects"]["strength"] == "+1 physical damage per point"`

- [x] Task 8: Minimal web client updates (AC: #6)
  - [x] 8.1: In `web-demo/js/game.js`, `handleXpGained` (line 1657-1664): Replace the XP accumulation line `gameState.player.stats.xp = (gameState.player.stats.xp || 0) + (data.amount || 0)` with `gameState.player.stats.xp = data.new_total_xp ?? ((gameState.player.stats.xp || 0) + (data.amount || 0))` — use server-authoritative total with delta fallback.
  - [x] 8.2: In `web-demo/js/game.js`, `updateStatsPanel` (lines 1592-1598): Replace the hardcoded XP calculations:
    ```javascript
    const xpNext = level * 1000;
    const xpPrev = (level - 1) * 1000;
    ```
    with server-provided values with fallback:
    ```javascript
    const xpNext = stats.xp_for_next_level ?? (level * 1000);
    const xpPrev = stats.xp_for_current_level ?? ((level - 1) * 1000);
    ```
    Also update `if ($xpText) $xpText.textContent = \`${currentXp}/${xpNext}\`;` at line 1615 — this already uses `xpNext` so it will automatically use the new value.
  - [x] 8.3: In `web-demo/js/game.js`, `handleStatsResult` (line 972-981): When stats arrive with `xp_for_next_level` and `xp_for_current_level`, they're stored in `gameState.player.stats` via the spread `{ ...s }` at line 976, so no additional change is needed — `updateStatsPanel` will read them.
  - [x] 8.4: In `web-demo/js/game.js`, `updateStatsDetailPanel` (lines 1624-1630): Replace the hardcoded description functions with server-provided `stat_effects` from the last `level_up_available` message (stored in `gameState.pendingLevelUp`). Use fallback to current hardcoded descriptions:
    ```javascript
    const serverEffects = gameState.pendingLevelUp?.stat_effects;
    const descriptions = {
      str: { label: 'STR', key: 'strength', desc: (v) => serverEffects?.strength || `+${v} physical dmg` },
      dex: { label: 'DEX', key: 'dexterity', desc: (v) => serverEffects?.dexterity || `-${v} incoming dmg` },
      con: { label: 'CON', key: 'constitution', desc: (v) => serverEffects?.constitution || `+${v * 5} max HP` },
      int: { label: 'INT', key: 'intelligence', desc: (v) => serverEffects?.intelligence || `+${v} magic dmg` },
      wis: { label: 'WIS', key: 'wisdom', desc: (v) => serverEffects?.wisdom || `+${v} healing` },
      cha: { label: 'CHA', key: 'charisma', desc: (v) => serverEffects?.charisma || `+${Math.round(v * 3)}% XP` },
    };
    ```

- [x] Task 9: Run `make test` and verify all tests pass (AC: #5)

## Dev Notes

### Architecture Compliance
- **ADR-14-14**: Tests as message contract — add assertions to existing test functions, NOT new test files.
- **Additive-only changes**: All existing fields preserved. New fields added alongside, never replacing.
- **Cross-cutting rule**: Test assertions use literal values (e.g., `assert msg["new_total_xp"] == 59`), not `settings.*` references.
- **Config-derived descriptions**: `stat_effects` descriptions MUST be derived from `settings.*` values (FR100), not hardcoded strings.

### Key Implementation Details

**`xp_gained` has 1 emission path:**
- `grant_xp()` in `server/core/xp.py:56-61`. The `player_entity.stats["xp"]` is already updated at line 48 before the message is sent. `new_total_xp` = `player_entity.stats["xp"]`.

**`stats_result` has 1 emission path:**
- `handle_stats()` in `server/net/handlers/query.py:116-132`. The `level` variable is at line 115. XP threshold formula: `level * settings.XP_LEVEL_THRESHOLD_MULTIPLIER` (already used for `xp_next`). Previous level threshold: `(level - 1) * settings.XP_LEVEL_THRESHOLD_MULTIPLIER`.

**`level_up_available` has 1 emission path (called from 3 places):**
- `send_level_up_available()` in `server/core/xp.py:90-112`. Called from:
  1. `grant_xp()` in `xp.py:72` — when pending level-ups increase from 0
  2. `handle_login` in `auth.py:418` — re-check on login
  3. `handle_level_up` in `levelup.py:109` — after completing a level-up, if more are queued

The `new_level` in the message is `stats.get("level", 1) + 1` (line 93). For XP thresholds in this message, use `current_level = stats.get("level", 1)` — this is the player's CURRENT level (before the pending level-up). The thresholds should reflect where the player currently is:
- `xp_for_next_level` = `current_level * settings.XP_LEVEL_THRESHOLD_MULTIPLIER`
- `xp_for_current_level` = `(current_level - 1) * settings.XP_LEVEL_THRESHOLD_MULTIPLIER`

**Stat effect descriptions come from these config values:**
| Stat | Config Value | Description Format | Default |
|------|-------------|-------------------|---------|
| strength | `STAT_SCALING_FACTOR` (1.0) | `+{v:g} physical damage per point` | "+1 physical damage per point" |
| dexterity | `STAT_SCALING_FACTOR` (1.0) | `-{v:g} incoming damage per point` | "-1 incoming damage per point" |
| constitution | `CON_HP_PER_POINT` (5) | `+{v} max HP per point` | "+5 max HP per point" |
| intelligence | `STAT_SCALING_FACTOR` (1.0) | `+{v:g} magic damage per point` | "+1 magic damage per point" |
| wisdom | `STAT_SCALING_FACTOR` (1.0) | `+{v:g} healing per point` | "+1 healing per point" |
| charisma | `XP_CHA_BONUS_PER_POINT` (0.03) | `+{round(v*100)}% XP per point` | "+3% XP per point" |

Sources: `damage.py:24` (STR), `damage.py:38` (DEX), `levelup.py:86` (CON), `damage.py:26` (INT), `heal.py:17` (WIS), `xp.py:44` (CHA).

### Stat Scaling Factor Format
`STAT_SCALING_FACTOR` is a float (default `1.0`). Use Python's `g` format specifier to get clean output: `f"{settings.STAT_SCALING_FACTOR:g}"` → `"1"` for `1.0`, `"1.5"` for `1.5`.

### What NOT to Change
- Existing message field names or values (keep `xp_next` in `stats_result`)
- XP calculation logic in `grant_xp()` or `calculate_combat_xp()`
- Level-up flow or stat selection logic
- Any test assertion values for existing fields
- Client-side logic beyond minimal field adoption (use new fields with fallbacks)

### Web Client Guidance
All client changes are defensive (use new field with fallback to old behavior):
- `data.new_total_xp ?? (accumulation)` — use server-authoritative total
- `stats.xp_for_next_level ?? (level * 1000)` — use server-provided threshold
- `stats.xp_for_current_level ?? ((level - 1) * 1000)` — use server-provided previous threshold
- `serverEffects?.stat_name || hardcoded_desc` — use server descriptions with fallback

### Testing Strategy
Add assertions to these existing tests (ADR-14-14):
| Message | Test File | Test Function | New Assertions |
|---------|-----------|---------------|----------------|
| `xp_gained` | `tests/test_xp.py` | `test_grant_xp_sends_message` (line 229) | `new_total_xp == 59` |
| `stats_result` | `tests/test_query.py` | `test_stats_returns_player_stats` (line 184) | `xp_for_next_level == 3000`, `xp_for_current_level == 2000` |
| `stats_result` | `tests/test_query.py` | `test_stats_excludes_transient` (line 207) | `xp_for_next_level` and `xp_for_current_level` in expected keys |
| `stats_result` | `tests/test_level_up.py` | `test_stats_result_includes_xp_next` (line 340) | `xp_for_next_level == 2000`, `xp_for_current_level == 1000` |
| `level_up_available` | `tests/test_level_up.py` | `test_send_level_up_available` (line 57) | `xp_for_next_level == 1000`, `xp_for_current_level == 0`, `stat_effects` dict with 6 entries |

### Previous Story Intelligence (14.3a)
- Additive-only pattern: add fields to existing message dicts, never remove/rename
- Code path audit: verify ALL emission sites include new fields (here: each message has 1 emission function)
- Test assertions use literal values, not `settings.*`
- Web client uses `??` (nullish coalescing) or `||` for fallbacks
- All 805 tests pass after 14.3a

### Project Structure Notes
- Modified server files: `server/core/xp.py`, `server/net/handlers/query.py`
- Modified test files: `tests/test_xp.py`, `tests/test_query.py`, `tests/test_level_up.py`
- Modified client file: `web-demo/js/game.js`
- No new files created, no files deleted
- No changes to `server/net/handlers/levelup.py` (it calls `send_level_up_available` which handles the message)

### References
- [Source: _bmad-output/planning-artifacts/epics.md#Story 14.3b] — AC and FRs (FR94, FR99, FR100)
- [Source: _bmad-output/planning-artifacts/epics.md#ADR-14-14] — tests as message contract
- [Source: server/core/xp.py:56-61] — xp_gained emission in grant_xp()
- [Source: server/core/xp.py:90-112] — level_up_available emission in send_level_up_available()
- [Source: server/net/handlers/query.py:116-132] — stats_result emission in handle_stats()
- [Source: server/core/config.py:44-55] — XP & Stats config values
- [Source: server/core/effects/damage.py:24,26,38] — STR/INT/DEX stat bonus formulas
- [Source: server/core/effects/heal.py:17] — WIS stat bonus formula
- [Source: server/net/handlers/levelup.py:86] — CON max_hp formula
- [Source: server/core/xp.py:44] — CHA XP bonus formula
- [Source: web-demo/js/game.js:1592-1598] — hardcoded XP bar calculation (level * 1000)
- [Source: web-demo/js/game.js:1624-1630] — hardcoded stat descriptions
- [Source: web-demo/js/game.js:1657-1659] — XP accumulation from deltas
- [Source: _bmad-output/implementation-artifacts/14-3a-core-message-enrichment.md] — previous story patterns

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List
- Added `new_total_xp` field to `xp_gained` message in `grant_xp()` — uses `player_entity.stats["xp"]` (already updated before send)
- Added `xp_for_next_level` and `xp_for_current_level` to `stats_result` in `handle_stats()` — computed from `level * XP_LEVEL_THRESHOLD_MULTIPLIER` and `(level-1) * XP_LEVEL_THRESHOLD_MULTIPLIER`
- Added `xp_for_next_level`, `xp_for_current_level`, and `stat_effects` to `level_up_available` in `send_level_up_available()` — stat descriptions derived from config values using `:g` format for STAT_SCALING_FACTOR
- Added `new_total_xp == 59` assertion to `test_grant_xp_sends_message`
- Added `xp_for_next_level` and `xp_for_current_level` assertions to 3 existing stats tests (`test_stats_returns_player_stats`, `test_stats_excludes_transient`, `test_stats_result_includes_xp_next`)
- Added `xp_for_next_level`, `xp_for_current_level`, and `stat_effects` assertions to `test_send_level_up_available`
- Updated web client: `handleXpGained` uses `data.new_total_xp` with delta fallback; `updateStatsPanel` uses `stats.xp_for_next_level`/`stats.xp_for_current_level` with hardcoded fallback; `updateStatsDetailPanel` uses `serverEffects` from `pendingLevelUp.stat_effects` with hardcoded fallback
- All 805 tests pass, zero assertion changes to existing values

### File List
- server/core/xp.py (modified — added `new_total_xp` to `xp_gained`, added `xp_for_next_level`, `xp_for_current_level`, `stat_effects` to `level_up_available`)
- server/net/handlers/query.py (modified — added `xp_for_next_level`, `xp_for_current_level` to `stats_result`)
- tests/test_xp.py (modified — added `new_total_xp` assertion)
- tests/test_query.py (modified — added `xp_for_next_level`, `xp_for_current_level` assertions to 2 tests)
- tests/test_level_up.py (modified — added XP threshold and `stat_effects` assertions to 2 tests)
- web-demo/js/game.js (modified — updated 3 functions to use server-provided values with fallbacks)
