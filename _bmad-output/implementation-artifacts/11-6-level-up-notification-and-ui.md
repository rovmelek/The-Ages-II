# Story 11.6: Level-Up Notification & UI

Status: done

## Story

As a player,
I want to see my level, all stats, and XP progress in the UI, and have a clear level-up experience,
so that progression feels visible and rewarding.

## Acceptance Criteria

1. **HUD redesign**: The stats HUD (`#stats-display` in `web-demo/index.html:60-80`) currently shows HP bar, XP text, and ATK text. Replace with:
   - HP bar (keep existing `#hp-section` with `#hp-bar` and `#hp-text`)
   - Level display: "LVL: 3" (new `#level-section`)
   - XP progress bar with text overlay: `████░░░░░░ 231/1000` (replace plain `#xp-text` with a progress bar like the HP bar)
   - Remove `#atk-section` entirely (attack is deprecated since Story 11.2)

2. **XP bar animation**: When XP changes, the XP bar briefly flashes/highlights with a CSS animation (~0.5s). Use existing animation patterns from `web-demo/css/style.css:618-631` (`damage-flash`, `heal-pulse` keyframes) as a template.

3. **Collapsible Stats panel**: The 6 ability scores (STR, DEX, CON, INT, WIS, CHA) are in a collapsible "Stats" panel, hidden by default. Each stat shows numeric value and brief effect description:
   - STR: N (+N physical dmg)
   - DEX: N (-N incoming dmg)
   - CON: N (+N×5 max HP)
   - INT: N (+N magic dmg)
   - WIS: N (+N healing)
   - CHA: N (+N×3% XP)
   
   Toggle by clicking a "Stats" button in the HUD or typing `/stats`.

4. **`xp_gained` handler**: Add handler in `dispatchMessage()` (`web-demo/js/game.js:398-434`):
   - Update XP bar immediately
   - If `source === "combat"`: NO chat notification (combat XP already shown in `combat_end` rewards — avoid double-notification)
   - If non-combat source (exploration, interaction): show in chat: "+52 XP (exploration: Discovered Dark Cave)"

5. **`level_up_available` handler**: Add handler that shows a level-up modal/panel:
   - "Level Up!" congratulation message
   - 6 stat buttons showing: stat name, current value -> new value, and effect description (e.g., "STR: 1 -> 2 (+1 physical dmg per point)")
   - Click to toggle selection (highlighted border/background)
   - Max 3 selectable — clicking a 4th shows "Max 3 selected" feedback
   - Stats at cap (10) grayed out and unclickable
   - "Confirm" button (disabled until >= 1 stat selected) sends `{"action": "level_up", "stats": [...]}`
   - Modal is dismissible — player can close and reopen via `/levelup` command or a persistent "Level Up!" badge on the HUD

6. **"Level Up!" badge**: When a level-up is pending, show a flashing "Level Up!" badge near the level display. Clicking reopens the level-up modal. Badge disappears after stat choice is confirmed.

7. **`level_up_complete` handler**: Add handler that:
   - Updates HUD with new level, stats, max_hp
   - Shows celebration message in chat: "You reached Level 2! STR+1, DEX+1, CON+1"
   - Removes "Level Up!" badge (unless another level-up is queued — server will send another `level_up_available`)

8. **Entity `level` in `room_state`**: Currently `room.get_state()` (`server/room/room.py:161-178`) serializes entities with only `{id, name, x, y}`. The `entity_entered` broadcast (`server/net/handlers/auth.py:338-349`) already includes `level`. Add `level` to `get_state()` entity data for consistency.

9. **`/levelup` slash command**: Add client-side `/levelup` command that reopens the level-up modal if a level-up is pending. If not pending, show "No level-up available" in chat.

10. **`/stats` display update**: The existing `handleStatsResult()` (`web-demo/js/game.js:851-859`) already shows all 6 abilities in chat. Also toggle open the collapsible Stats panel when `/stats` is used.

11. **All existing web client functionality remains working**. `pytest tests/` passes.

## Tasks / Subtasks

- [x] Task 1: Update stats HUD HTML structure (AC: #1, #3, #6)
  - [x] In `web-demo/index.html:59-81`, restructure `#stats-display`:
    - Add `#level-section` with `.stat-label` "LVL" and `#level-text` (default "1")
    - Replace `#xp-section` content: change plain `#xp-text` to an XP progress bar (use `.hp-bar-track`/`.hp-bar-fill` pattern from HP section). Add `#xp-bar-track` > `#xp-bar` fill + `#xp-text` overlay
    - Remove `#atk-section` entirely
    - Add `#stats-toggle-btn` button "Stats" below the main HUD metrics
    - Add `#stats-detail-panel` (hidden by default) containing 6 stat rows with `#stat-str`, `#stat-dex`, etc.
    - Add `#levelup-badge` element (hidden by default) next to `#level-section` — text "Level Up!" with CSS flash animation
  - [x] Add level-up modal HTML after `#combat-overlay` (~line 173):
    - `#levelup-overlay` (same pattern as `#combat-overlay`: fixed, full-screen, hidden)
    - `#levelup-panel` containing:
      - `<h2>` "Level Up!"
      - `#levelup-stats-grid` — 6 stat button divs (`.levelup-stat-btn`) each with stat name, current->new value, effect text
      - `#levelup-feedback` — for "Max 3 selected" messages
      - `#levelup-confirm-btn` — Confirm button (disabled initially)
      - `#levelup-close-btn` — X/close button to dismiss

- [x] Task 2: Add CSS for new UI elements (AC: #1, #2, #3, #5, #6)
  - [x] In `web-demo/css/style.css`, add styles:
    - `#level-section` — inline display next to HP
    - XP bar: reuse `.hp-bar-track`/`.hp-bar-fill` pattern but with different color (e.g., gold/amber `#d4a030`)
    - `@keyframes xp-flash` — brief gold flash animation (~0.5s)
    - `.xp-flash-anim` class — applies the flash animation
    - `#stats-toggle-btn` — small button style
    - `#stats-detail-panel` — collapsible panel styling (with `display: none` default, `display: block` when `.open`)
    - `.stat-row` — row style for each ability score
    - `#levelup-badge` — flashing badge style using `@keyframes blink` (already exists at line 38) or new pulse animation, gold/amber color
    - `#levelup-overlay` — same pattern as `#combat-overlay` (lines 399-422)
    - `#levelup-panel` — same pattern as `#combat-panel`
    - `.levelup-stat-btn` — clickable stat button with `.selected` (highlighted border) and `.disabled` (grayed out) states
    - `#levelup-confirm-btn` — confirm button with `:disabled` state
    - `#levelup-feedback` — small warning text

- [x] Task 3: Implement XP bar and level display updates in JS (AC: #1, #2, #10)
  - [x] In `web-demo/js/game.js`, modify `updateStatsPanel()` (lines 1387-1437):
    - Add level display update: `document.getElementById('level-text').textContent = stats.level || 1`
    - Replace XP text update with XP bar calculation:
      ```javascript
      const level = stats.level || 1;
      const xpNext = stats.xp_next || (level * 1000);
      const xpPrev = (level - 1) * 1000;  // previous threshold
      const xpInLevel = (stats.xp || 0) - xpPrev;
      const xpNeeded = xpNext - xpPrev;
      const xpPct = Math.min(100, Math.max(0, (xpInLevel / xpNeeded) * 100));
      document.getElementById('xp-bar').style.width = xpPct + '%';
      document.getElementById('xp-text').textContent = `${stats.xp || 0}/${xpNext}`;
      ```
    - Remove ATK display update (lines 1435-1436 referencing `#atk-text`)
    - Update Stats detail panel with all 6 ability scores and effect descriptions
  - [x] Add XP flash animation trigger: compare old XP to new XP, if changed add `.xp-flash-anim` class, remove after animation ends

- [x] Task 4: Add `xp_gained` message handler (AC: #4)
  - [x] In `dispatchMessage()` (line 398-434), add `'xp_gained': handleXpGained`
  - [x] Create `handleXpGained(data)`:
    - Increment XP: `gameState.player.stats.xp = (gameState.player.stats.xp || 0) + data.amount`
    - Call `updateStatsPanel()` to refresh XP bar (will trigger flash animation)
    - If `data.source !== 'combat'`: append chat message `+${data.amount} XP (${data.source}: ${data.detail})`
    - If `data.source === 'combat'`: no chat message (combat_end already shows rewards text)
  - [x] Server `xp_gained` message format (from `server/core/xp.py:57-63`): `{"type": "xp_gained", "amount": <int>, "source": <str>, "detail": <str>}`. No `new_xp` field — client must increment locally.

- [x] Task 5: Add `level_up_available` message handler and modal (AC: #5, #6)
  - [x] In `dispatchMessage()`, add `'level_up_available': handleLevelUpAvailable`
  - [x] Create `handleLevelUpAvailable(data)`:
    - Store pending level-up data in `gameState.pendingLevelUp = data`
    - Show "Level Up!" badge on HUD (`#levelup-badge`)
    - Open the level-up modal:
      - Populate 6 stat buttons from `data.current_stats` (STR, DEX, CON, INT, WIS, CHA)
      - Each button shows: stat name, `current -> current+1`, effect description
      - Stats at `data.stat_cap` (10) are grayed out (`.disabled` class)
      - Clear any previous selections
      - Show `#levelup-overlay`
    - Track selected stats in `gameState.levelUpSelections = []`
  - [x] Add stat button click handler:
    - If stat is disabled (at cap), ignore
    - If already selected, deselect (remove from array, remove `.selected` class)
    - If not selected and selections.length < 3, select (add to array, add `.selected`)
    - If not selected and selections.length >= 3, show "Max 3 selected" in `#levelup-feedback`
    - Enable/disable Confirm button based on selections.length > 0
  - [x] Add Confirm button click handler:
    - Send `{"action": "level_up", "stats": gameState.levelUpSelections}`
    - Hide modal
  - [x] Add close button click handler:
    - Hide modal but keep badge visible (level-up still pending)

- [x] Task 6: Add `level_up_complete` message handler (AC: #7)
  - [x] In `dispatchMessage()`, add `'level_up_complete': handleLevelUpComplete`
  - [x] Create `handleLevelUpComplete(data)`:
    - Update `gameState.player.stats.level = data.level`
    - Update changed stats from `data.stat_changes` (e.g., `gameState.player.stats.strength = data.stat_changes.strength`)
    - Update `gameState.player.stats.max_hp = data.new_max_hp`
    - Update `gameState.player.stats.hp = data.new_max_hp` (full heal on level-up)
    - Call `updateStatsPanel()`
    - Build celebration chat message: "You reached Level N! STR+1, DEX+1, CON+1" from `data.stat_changes`
    - Append to chat
    - Clear `gameState.pendingLevelUp = null`
    - Hide `#levelup-badge`
    - Note: if another level-up is queued, the server will send a new `level_up_available` immediately, which will re-show the badge and modal

- [x] Task 7: Add `/levelup` client-side command (AC: #9)
  - [x] In the COMMANDS object (`web-demo/js/game.js:140-233`), add `/levelup` command:
    - If `gameState.pendingLevelUp` exists, reopen the level-up modal with stored data
    - If not, show in chat: "No level-up available"
  - [x] Also trigger Stats panel toggle on `/stats` command (AC: #10)

- [x] Task 8: Add `level` to `room_state` entity data (AC: #8)
  - [x] In `server/room/room.py`, modify `get_state()` entity serialization (lines 161-178) to include `level`:
    - For `PlayerEntity` entities, include `stats.get("level", 1)` — need to access stats, which requires the entity to carry stats or the room to have access
    - Check how `PlayerEntity` stores stats: `PlayerEntity` dataclass has `stats: dict` field. In `get_state()`, entities are iterated as `self._entities.values()`. Each entity is a `PlayerEntity` with `.stats`.
    - Add: `"level": e.stats.get("level", 1) if hasattr(e, 'stats') else 1` to the entity dict
  - [x] Verify `entity_entered` in `server/net/handlers/auth.py:338-349` already includes `level` — confirmed, no change needed there

- [x] Task 9: Update `handleStatsResult` to toggle Stats panel (AC: #10)
  - [x] In `handleStatsResult()` (`web-demo/js/game.js:851-859`):
    - After syncing stats, also open the collapsible Stats detail panel (`#stats-detail-panel.open`)
    - Existing chat display already shows all 6 abilities — no change needed there

- [x] Task 10: Run `pytest tests/` to ensure no regressions (AC: #11)

## Dev Notes

### Key Architecture Patterns

- **Web client is vanilla HTML/CSS/JS** — no frameworks, no bundlers, no npm. All UI in `web-demo/js/game.js`, single file.
- **Message dispatch**: `dispatchMessage()` at `web-demo/js/game.js:398-434` maps `data.type` string to handler functions. Add new entries for `xp_gained`, `level_up_available`, `level_up_complete`.
- **UI state**: `gameState` object holds all client state. Key properties: `gameState.player.stats` (synced from server), `gameState.mode` (set by `setMode()`), `gameState.room` (current room data).
- **Modal pattern**: Combat overlay (`#combat-overlay`) at `web-demo/index.html:137-173` uses `hidden` class toggling. Reuse this exact pattern for the level-up modal.
- **CSS animation pattern**: Existing keyframes at `web-demo/css/style.css:618-631` — `damage-flash` (red 0.5s) and `heal-pulse` (green 0.5s). Use similar approach for XP flash (gold 0.5s).
- **Stats panel update**: `updateStatsPanel()` at `web-demo/js/game.js:1387-1437` is called from multiple places: login, combat updates, stats query, room transitions. It's the central HUD refresh point.

### Server-Side Changes (Minimal)

- **Only one server file change**: `server/room/room.py` `get_state()` to include `level` in entity data. This is a one-line addition.
- **No handler changes** — all handlers (level_up, xp, stats) are already implemented from Stories 11.3-11.5.
- **`xp_gained` message format** (from `server/core/xp.py:grant_xp`): `{"type": "xp_gained", "amount": <int>, "source": "<str>", "detail": "<str>"}`. The client should increment XP locally: `stats.xp += data.amount`.
- **`level_up_available` format** (from `server/core/xp.py:91-113`, `send_level_up_available`): `{"type": "level_up_available", "new_level": <int>, "choose_stats": 3, "current_stats": {"strength": N, ...}, "stat_cap": 10}`.
- **`level_up_complete` format** (from `server/net/handlers/levelup.py:handle_level_up`): `{"type": "level_up_complete", "level": <int>, "stat_changes": {"strength": N, ...}, "new_max_hp": <int>}`. May also include `"skipped_at_cap": [...]`.

### Integration Points

- **`combat_end` already handles combat XP display** (`web-demo/js/game.js:1013-1018`): "Victory! Gained N XP". The `xp_gained` handler must NOT duplicate this for combat source.
- **`handleLoginSuccess()`** (`web-demo/js/game.js:453-473`): Already stores `data.stats` which includes `level`, `xp`, all 6 abilities. The HUD just needs to render them.
- **`handleStatsResult()`** (`web-demo/js/game.js:851-859`): Already shows all stats in chat. `stats_result` now includes `xp_next` (added in Story 11.5). Use `xp_next` for XP bar calculation.
- **XP double-count risk**: `combat_end` handler (line 1038) does `gameState.player.stats.xp = (gameState.player.stats.xp || 0) + (data.rewards?.xp || 0)`. The new `xp_gained` handler will also increment XP. Both fire for combat XP, causing double-count. **Solution**: Remove the manual XP increment in `combat_end` handler (line 1038) and let `xp_gained` be the single source of all XP updates. Keep `combat_end`'s chat display of "Victory! Gained N XP" unchanged — just remove the `gameState.player.stats.xp` assignment.

### XP Bar Calculation

- `xp_next` is provided by the server in `stats_result` response (Story 11.5). For level L, `xp_next = L * 1000` (with default `XP_LEVEL_THRESHOLD_MULTIPLIER=1000`).
- XP bar shows progress within current level: `progress = (current_xp - prev_threshold) / (next_threshold - prev_threshold)`.
- Previous threshold = `(level - 1) * 1000`. For level 1: 0. For level 2: 1000.
- The client can compute this from `stats.level` and `stats.xp` without needing `xp_next` from server (though `xp_next` is available in `stats_result`). For the HUD, calculate locally using `level * 1000` as next threshold.

### What NOT to Change

- Do NOT change any server handler logic (combat, xp, level_up handlers are complete from Stories 11.3-11.5)
- Do NOT change server config values
- Do NOT add new server message types
- Do NOT modify test files (this is a client-only story except for the `get_state()` level addition)
- Do NOT change the `/stats` server action — only the client-side display

### Previous Story Intelligence

From Story 11.5:
- `server/net/handlers/levelup.py` — complete handler for `level_up` action. Validates stats, applies boosts, persists to DB, sends `level_up_complete`, handles queued level-ups.
- `server/core/xp.py` — `grant_xp` sends `xp_gained` messages and detects level-up thresholds. `send_level_up_available` sends the notification.
- `pending_level_ups` tracked in `game.player_entities[entity_id]` dict (in-memory, recalculated on login).
- 598 tests passing after Story 11.5.

### Project Structure Notes

- Modified files: `web-demo/index.html`, `web-demo/css/style.css`, `web-demo/js/game.js`, `server/room/room.py`
- No new files created
- Flat test directory convention — no test changes expected (server logic unchanged)

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Epic 11, Story 11.6, lines 2220-2287]
- [Source: web-demo/js/game.js:398-434 — dispatchMessage handler map]
- [Source: web-demo/js/game.js:1387-1437 — updateStatsPanel]
- [Source: web-demo/js/game.js:851-859 — handleStatsResult]
- [Source: web-demo/js/game.js:1009-1051 — handleCombatEnd]
- [Source: web-demo/js/game.js:453-473 — handleLoginSuccess]
- [Source: web-demo/js/game.js:140-233 — COMMANDS object (slash command definitions)]
- [Source: web-demo/index.html:59-81 — stats HUD HTML]
- [Source: web-demo/index.html:137-173 — combat overlay pattern]
- [Source: web-demo/css/style.css:150-172 — stat labels and HP bar styling (HP bar track/fill at 155-172)]
- [Source: web-demo/css/style.css:399-422 — combat overlay styling]
- [Source: web-demo/css/style.css:618-631 — animation keyframes]
- [Source: server/room/room.py:161-178 — get_state entity serialization]
- [Source: server/net/handlers/auth.py:338-349 — entity_entered broadcast]
- [Source: server/core/xp.py — grant_xp and send_level_up_available]
- [Source: server/net/handlers/levelup.py — handle_level_up]
- [Source: _bmad-output/implementation-artifacts/11-5-xp-level-thresholds-and-level-up-mechanic.md — previous story]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Redesigned stats HUD: removed ATK display, added LVL display with flashing "Level Up!" badge, replaced plain XP text with gold XP progress bar with flash animation on XP change
- Added collapsible Stats panel showing all 6 ability scores with effect descriptions, toggled by "Stats" button or `/stats` command
- Added `xp_gained` handler: increments XP locally, updates XP bar, shows chat notification for non-combat sources only (avoids double-notification with combat_end)
- Removed manual XP increment from `combat_end` handler to prevent double-count (xp_gained is now the single source of XP updates)
- Added `level_up_available` handler with full level-up modal: 6 stat buttons with current->new values and effect descriptions, max 3 selectable, stats at cap (10) grayed out, confirm/close buttons
- Added `level_up_complete` handler: updates stats/level/max_hp, shows celebration chat message, clears badge and modal
- Added `/levelup` client-side command to reopen level-up modal when pending
- Added `level` to `room_state` entity serialization in `server/room/room.py` `get_state()` for consistency with `entity_entered` broadcast
- Added `pendingLevelUp` and `levelUpSelections` to gameState, cleared on logout/reset
- 599 tests passing (2 known hanging tests excluded), 0 failures

### File List

- web-demo/index.html (modified — restructured stats HUD, added level-up overlay)
- web-demo/css/style.css (modified — added level, XP bar, stats panel, level-up modal, xp-flash animation styles)
- web-demo/js/game.js (modified — added xp_gained/level_up_available/level_up_complete handlers, /levelup command, stats panel toggle, XP bar logic, removed combat_end XP double-count)
- server/room/room.py (modified — added level to get_state entity serialization)
