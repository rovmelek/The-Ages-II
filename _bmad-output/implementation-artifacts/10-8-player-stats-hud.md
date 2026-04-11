# Story 10.8: Player Stats HUD

Status: done

## Story

As a player,
I want to always see my HP, XP, and attack stats during gameplay,
so that I know my current state without needing to type commands.

## Acceptance Criteria

1. **Given** a player logs in and enters the game, **When** the game viewport is displayed, **Then** a stats HUD panel is always visible showing: HP bar with current/max (e.g., "85 / 100") with color coding (green > 50%, yellow 25-50%, red < 25%), XP display (e.g., "XP: 150"), and Attack stat (e.g., "ATK: 10").

2. **Given** the player takes damage or heals (combat or item use), **When** the stats update is received, **Then** the HUD updates in real-time.

3. **Given** the player gains XP from combat victory, **When** the `combat_end` message is received, **Then** the XP display updates immediately.

4. **Given** the player logs in, **When** `login_success` is received, **Then** stats from the login response populate the HUD immediately (no `/stats` command needed).

5. **Given** the existing `hp-section` element in `web-demo/index.html`, **When** the story is complete, **Then** it is expanded into a full stats HUD that is always visible (not hidden by default). The HUD is positioned to not overlap the tile viewport or chat area.

6. **And** `pytest tests/` passes with zero new failures.

## Tasks / Subtasks

- [x] Task 1: Add stats to `login_success` server message (AC: #4)
  - [x] 1.1: In `server/net/handlers/auth.py`, in the login branch (line ~280-286), add `"stats"` key to the `login_success` JSON payload: `{"hp": stats.get("hp", 100), "max_hp": stats.get("max_hp", 100), "attack": stats.get("attack", 10), "xp": stats.get("xp", 0)}`
  - [x] 1.2: The register branch (line ~150-156) also sends `login_success` — this is for auto-login after register, so add stats there too using `_DEFAULT_STATS` values

- [x] Task 2: Store player stats in client gameState on login (AC: #4)
  - [x] 2.1: In `web-demo/js/game.js` `handleLoginSuccess()` (line ~448), extract `data.stats` and store on `gameState.player` as `stats` property: `gameState.player.stats = data.stats || {hp: 100, max_hp: 100, attack: 10, xp: 0}`

- [x] Task 3: Expand stats HUD HTML (AC: #1, #5)
  - [x] 3.1: In `web-demo/index.html`, modify the `#stats-display` section (lines 61-74) to:
    - Remove `class="hidden"` from `#hp-section` — it should always be visible
    - Add `#xp-section` div with stat-label "XP" and `#xp-text` stat-value element
    - Add `#atk-section` div with stat-label "ATK" and `#atk-text` stat-value element
    - Keep `#shield-section` as-is (combat only, hidden by default)
    - Remove `#no-stats-text` element — stats will always be visible

- [x] Task 4: Rewrite `updateStatsPanel()` to always show stats (AC: #1, #2, #3, #5)
  - [x] 4.1: In `web-demo/js/game.js` `updateStatsPanel()` (line ~1328), rewrite to:
    - **Always** show HP bar using `gameState.player.stats` (not only during combat)
    - During combat, prefer combat participant data for HP/Shield (more current due to shield)
    - Outside combat, use `gameState.player.stats` for HP display
    - Always show XP from `gameState.player.stats.xp`
    - Always show ATK from `gameState.player.stats.attack`
    - Apply HP bar color coding: green (>50%), yellow (25-50%), red (<25%) — the `setHpBarColor()` function already exists
    - Remove the `$noStats` / "No combat stats" fallback logic

- [x] Task 5: Sync `gameState.player.stats` from server messages (AC: #2, #3)
  - [x] 5.1: In `handleCombatTurn()` (line 920) and `handleCombatUpdate()` (line 1039), after updating `gameState.combat`, find the current player's participant entry and sync hp/max_hp back to `gameState.player.stats`
  - [x] 5.2: In `handleCombatEnd()`, sync final stats (hp, xp) back to `gameState.player.stats` from the combat_end data
  - [x] 5.3: In `handleStatsResult()`, update `gameState.player.stats` in addition to printing to chat
  - [x] 5.4: In `handleRespawn()`, update `gameState.player.stats.hp` and `gameState.player.stats.max_hp` to full HP (respawn is full HP reset)
  - [x] 5.5: In `handleItemUsed()` (line 1259), for heal effects, sync `data.effect_results[].target_hp` to `gameState.player.stats.hp` and call `updateStatsPanel()`
  - [x] 5.6: Call `updateStatsPanel()` after each stats sync (most call sites already do this)

- [x] Task 6: Add tests (AC: #6)
  - [x] 6.1: Add test in `tests/test_auth.py` (or existing auth test file) verifying `login_success` message now includes `"stats"` key with hp, max_hp, attack, xp
  - [x] 6.2: Run `pytest tests/` — all tests pass

## Dev Notes

### Critical Implementation Details

**Server change is minimal:** Only `server/net/handlers/auth.py` needs modification. Add `"stats"` to the two `login_success` payloads. The stats dict is already computed at line 209-217 in the login branch. For the register branch, use inline default values (see Register branch stats below).

**Register branch stats:** The register flow at line 150-156 sends `login_success` before any entity/stats setup. Since this is a brand-new player, use hardcoded defaults: `{"hp": 100, "max_hp": 100, "attack": 10, "xp": 0}`. These match `_DEFAULT_STATS` defined at line 209 inside `handle_login` (note: `_DEFAULT_STATS` is local to `handle_login` and not accessible from `handle_register` — use inline dict literal).

**Client stat sources by context:**
- **Login:** `data.stats` from `login_success` message → stored in `gameState.player.stats`
- **Exploration:** `gameState.player.stats` (persisted from login, updated by combat end / item use / respawn)
- **Combat:** `gameState.combat.participants.find(p => p.entity_id === gameState.player.id)` has authoritative hp/max_hp/shield — sync hp/max_hp back to `gameState.player.stats` on each `combat_turn` and `combat_update` message
- **Combat end:** `data.rewards.xp` is the XP gained — add to current `gameState.player.stats.xp`; hp comes from final combat state sync
- **Respawn:** Player HP resets to max_hp — update `gameState.player.stats.hp = gameState.player.stats.max_hp`

**HP bar color coding:** The `setHpBarColor($hpBar, pct)` helper already exists (look for it in game.js). It adds/removes CSS classes `hp-medium` and `hp-low`. Reuse it — do NOT reimplement.

**`updateStatsPanel()` rewrite approach:**
```javascript
function updateStatsPanel() {
  if (!gameState.player) return;
  // ... existing name/position/room updates ...
  
  const stats = gameState.player.stats;
  if (!stats) return;
  
  // HP: prefer combat data during combat (includes shield), else use stats
  let hp, maxHp;
  if (gameState.combat && gameState.player) {
    const me = gameState.combat.participants.find(p => p.entity_id === gameState.player.id);
    if (me) { hp = me.hp; maxHp = me.max_hp; }
  }
  hp = hp ?? stats.hp;
  maxHp = maxHp ?? stats.max_hp;
  
  // Update HP bar (always visible)
  const pct = maxHp > 0 ? (hp / maxHp) * 100 : 0;
  $hpBar.style.width = `${pct}%`;
  setHpBarColor($hpBar, pct);
  $hpText.textContent = `${hp} / ${maxHp}`;
  
  // Shield (combat only)
  // ... existing shield logic ...
  
  // XP and ATK (always visible)
  $xpText.textContent = stats.xp ?? 0;
  $atkText.textContent = stats.attack ?? 10;
}
```

**XP update on combat_end:** The server sends `data.rewards.xp` as the XP gained (delta), NOT total XP. The client must ADD this to current stats: `gameState.player.stats.xp = (gameState.player.stats.xp || 0) + (data.rewards?.xp || 0)`. Look at the existing `handleCombatEnd()` (line ~990-1030) — it currently only displays XP in chat, doesn't track it.

**Item use outside combat:** When a player uses a healing potion outside combat, the server sends an `item_used` message (NOT `use_item_result`). The client handler is `handleItemUsed()` (line 1259). The `data.effect_results` array includes `target_hp` for heal effects — use this to sync `gameState.player.stats.hp`. After handling, the client already calls `sendAction('inventory', {})` to refresh inventory.

### Files to Modify

- `server/net/handlers/auth.py` — add `"stats"` to both `login_success` JSON payloads (lines ~150-156 and ~280-286)
- `web-demo/index.html` — expand `#stats-display` section: remove hidden from hp-section, add xp-section and atk-section, remove no-stats-text
- `web-demo/js/game.js` — update `handleLoginSuccess()`, rewrite `updateStatsPanel()`, sync stats in combat/respawn handlers
- `web-demo/css/style.css` — minor styling for XP/ATK display (use existing `.stat-label` and `.stat-value` classes)

### Files NOT to Create

No new files. This story modifies existing files only.

### What NOT to Do

- Do NOT create a separate HUD overlay or floating panel — use the existing left panel `#stats-display` section
- Do NOT add a `/stats` auto-query on login — stats should come in the `login_success` message directly
- Do NOT modify `server/net/handlers/query.py` — the `handle_stats` action is independent and still works via `/stats` command
- Do NOT remove the `handleStatsResult()` function — `/stats` command still works and prints to chat
- Do NOT add new stat types (level, mana, etc.) — only HP, XP, ATK per FR73
- Do NOT modify combat overlay HP display — that's separate (`#combat-hp-bar`, `#combat-hp-text`) and already works
- Do NOT remove `#shield-section` — it still shows during combat in the left panel

### Existing Code Patterns to Follow

- **HP bar color:** `setHpBarColor($hpBar, pct)` — search game.js for this function. Uses CSS classes `.hp-medium` (yellow) and `.hp-low` (red).
- **Stats on `PlayerEntity`:** `entity.stats` is a plain dict with keys: `hp`, `max_hp`, `attack`, `xp`. See `server/net/handlers/query.py:109-118`.
- **`gameState.player`:** Currently has `{id, dbId, name, x, y}`. Add `stats` property.
- **DOM update pattern:** All DOM updates use `document.getElementById()` inline (no cached refs for stats elements). Follow this pattern.

### Testing Patterns

- **Auth handler test:** In existing test files, find tests that check `login_success` message format. Add assertion that response includes `"stats"` key with expected fields. Pattern: mock WebSocket, call `handle_login()`, check `ws.send_json.call_args`.
- **No client-side tests:** The web client has no test framework — verification is manual or via server-side message format tests.

### Previous Story Learnings

- **From 10.7:** 534 passed, 2 pre-existing failures (TestChestInteraction DB issues), 2 deselected. Zero new failures.
- **From 10.7:** Dual-write pattern (DB + runtime) is important — but this story only reads stats, doesn't write them.
- **From 10.1:** `_cleanup_player()` centralizes cleanup. Logout handler already saves stats before cleanup.
- **Git pattern:** One commit per story.

### Project Structure Notes

- Server change is a single file (`auth.py`) — no new modules needed
- Web client changes span HTML, CSS, and JS — all in `web-demo/`
- No architecture changes — this is a UI enhancement using existing data

### References

- [Source: web-demo/index.html#stats-display] — existing stats section (lines 61-74)
- [Source: web-demo/js/game.js#updateStatsPanel] — current stats panel update function (lines 1328-1374)
- [Source: web-demo/js/game.js#handleLoginSuccess] — login success handler (lines 448-466)
- [Source: web-demo/js/game.js#handleStatsResult] — stats command result handler (lines 841-844)
- [Source: server/net/handlers/auth.py#login_success] — server login success messages (lines 150-156, 280-286)
- [Source: server/net/handlers/auth.py#_DEFAULT_STATS] — default player stats (line 209)
- [Source: server/net/handlers/query.py#handle_stats] — stats query handler (lines 95-118)
- [Source: _bmad-output/planning-artifacts/epics.md#Story 10.8] — acceptance criteria (lines 1836-1867)

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- Pre-existing test failures: 2 TestChestInteraction DB issues (unchanged from Story 10.7 baseline)
- Pre-existing deselected: 1 known hanging test

### Completion Notes List

- Added `"stats"` key to both `login_success` payloads in auth.py (register branch with hardcoded defaults, login branch with actual player stats)
- Client `handleLoginSuccess()` now stores `data.stats` on `gameState.player.stats`
- Expanded HTML stats HUD: `#hp-section` always visible, added `#xp-section` and `#atk-section`, removed `#no-stats-text`
- Rewrote `updateStatsPanel()` to always show HP/XP/ATK — prefers combat participant data for HP during combat, falls back to `gameState.player.stats`
- Added `syncCombatStatsToPlayer()` helper called from `handleCombatTurn()` and `handleCombatUpdate()`
- `handleCombatEnd()` syncs final HP and adds XP delta to player stats
- `handleStatsResult()` now updates `gameState.player.stats` in addition to chat display
- `handleRespawn()` resets HP to max_hp in player stats
- `handleItemUsed()` syncs heal effect `target_hp` to player stats
- 2 new tests in `tests/test_auth.py`: register and login both include stats in login_success
- 537 passed, 2 pre-existing failures, 1 deselected — zero new failures

### Change Log

- 2026-04-10: Story 10.8 implemented — player stats HUD always visible with real-time updates
- 2026-04-10: Code review fixes — added syncCombatStatsToPlayer + updateStatsPanel to handleCombatFled; deduplicated participants.find() in updateStatsPanel

### File List

- server/net/handlers/auth.py (modified — added stats to both login_success payloads)
- web-demo/index.html (modified — expanded stats HUD with XP and ATK sections)
- web-demo/js/game.js (modified — stats on login, syncCombatStatsToPlayer, updateStatsPanel rewrite, stats sync in 5 handlers)
- tests/test_auth.py (modified — 2 new tests for stats in login_success)
