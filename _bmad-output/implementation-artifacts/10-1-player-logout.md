# Story 10.1: Player Logout

Status: ready-for-dev

## Story

As a player,
I want to logout cleanly from the game,
so that my state is saved and I can return to the login screen without closing the browser.

## Acceptance Criteria

1. **Given** a logged-in player, **When** the server receives `{"action": "logout"}`, **Then** the player's state is saved to DB (position, stats, inventory), the player's entity is removed from the room, other players receive `entity_left`, the player is removed from `player_entities` and `connection_manager`, the player receives `{"type": "logged_out"}`, and the WebSocket remains open (player returns to auth state, can login again on the same connection).

2. **Given** a player is in combat, **When** they send a logout action, **Then** combat stats are synced from `combat_instance.participant_stats` back to `entity.stats` before save, `entity.in_combat` is set to `False`, the player is removed from combat, combat continues for other participants (remaining participants receive `combat_update`), if the player was the last participant the combat instance is cleaned up and the mob's `in_combat` flag is cleared (matching flee behavior — `is_alive` is NOT reset), and the `logged_out` message is sent (no separate `combat_fled` — the client handles combat cleanup in the `logged_out` handler to avoid visual flicker).

3. **Given** a player is dead in combat (HP = 0), **When** they send a logout action, **Then** HP is restored to `max_hp` before saving state (mimicking respawn), then logout proceeds normally. This prevents the player from being stuck at 0 HP on next login.

4. **Given** a player is not logged in, **When** they send a logout action, **Then** the client receives `{"type": "error", "detail": "Not logged in"}`.

5. **Given** a logged-in player sends `{"action": "login"}` on the same WebSocket (re-login without logout), **When** `handle_login` detects the existing session is on the same WebSocket, **Then** the server performs an inline logout (cleanup without socket close) and proceeds with the new login — it does NOT call `_kick_old_session` (which would close the active socket).

6. **Given** the web client receives a `logged_out` message, **When** the UI updates, **Then** the game viewport is hidden, combat overlay is dismissed if active, the login form is shown, credentials are cleared (preventing auto-login), a "Logout" button is visible in the game UI during gameplay, and `/logout` command is available via chat input.

## Tasks / Subtasks

- [ ] Task 1: Server-side logout handler (AC: #1, #2, #3, #4)
  - [ ] 1.1: Create `handle_logout` in `server/net/handlers/auth.py` — resolve entity_id via `connection_manager.get_entity_id(websocket)`, return error if None
  - [ ] 1.2: Combat cleanup for in-combat players (ORDER MATTERS):
    - Sync combat stats from `combat_instance.participant_stats` back to `entity.stats` — only sync `hp`, `max_hp`, `attack` (matching `_check_combat_end` pattern; transient keys like `shield`, `energy`, `active_effects` do not need syncing). MUST happen first — `remove_participant` destroys this data.
    - If `entity.stats["hp"]` <= 0 (dead in combat), restore to `entity.stats["max_hp"]` (MUST happen after sync, otherwise sync overwrites the restore)
    - Set `entity.in_combat = False`
    - Call `combat_instance.remove_participant(entity_id)` and `combat_manager.remove_player(entity_id)`
    - If no participants remain: clear NPC `in_combat` flag (do NOT reset `is_alive`), call `combat_manager.remove_instance()`
    - If participants remain: broadcast `combat_update` to remaining players
  - [ ] 1.3: Save player state to DB (position, stats, inventory) — best-effort with try/except (log error, continue logout even if save fails)
  - [ ] 1.4: Remove entity from room + broadcast `entity_left` to other players in room
  - [ ] 1.5: Send `{"type": "logged_out"}` via `websocket.send_json()` (NOT via `connection_manager` — it will be cleared next). Wrap in try/except — if the send fails (network dropped), continue with cleanup (the `handle_disconnect` path will handle remaining cleanup safely; a double `entity_left` broadcast is cosmetically harmless)
  - [ ] 1.6: Call `connection_manager.disconnect(entity_id)` and `player_entities.pop(entity_id, None)` — AFTER sending the message and AFTER save/room removal (intentionally different ordering from `handle_disconnect` which pops first)
  - [ ] 1.7: Register `logout` action in `Game._register_handlers()`
- [ ] Task 2: Fix re-login on same WebSocket (AC: #5)
  - [ ] 2.1: In `handle_login`, before calling `_kick_old_session`, check if `old_ws is websocket` (same object). If so, perform inline cleanup (same as logout Tasks 1.2-1.6 minus sending `logged_out`) instead of calling `_kick_old_session` (which would close the active socket)
- [ ] Task 3: Web client logout UI (AC: #6)
  - [ ] 3.1: Add "Logout" button to `web-demo/index.html` inside the player info section (near room name display)
  - [ ] 3.2: Add `logged_out` message handler in `web-demo/js/game.js` — do NOT call `resetToLogin()` directly (it closes the WebSocket). Instead: clear `gameState.credentials`, clear `gameState.player`, clear `gameState.room`, dismiss combat overlay if active, clear tile grid/chat/log, switch to auth mode via `setMode('auth')`, show status message "You have been logged out." The WebSocket must remain open so the player can re-login without reconnecting.
  - [ ] 3.3: Add click handler for logout button — `sendAction('logout', {})`
  - [ ] 3.4: Add `/logout` command to chat input — intercept messages starting with `/logout` in the chat send handler, call `sendAction('logout', {})` instead of sending as chat
- [ ] Task 4: Tests (AC: #1, #2, #3, #4, #5)
  - [ ] 4.1: Test logout saves state and removes player (unit test, follow test_game.py disconnect pattern)
  - [ ] 4.2: Test logout while in combat — removes from combat, clears `in_combat` flag, syncs combat stats, saves correct HP
  - [ ] 4.3: Test logout while dead in combat (HP=0) — HP restored to max_hp before save
  - [ ] 4.4: Test logout when last player in combat — NPC `in_combat` cleared, combat instance removed
  - [ ] 4.5: Test logout with remaining combat participants — they receive `combat_update`, combat continues
  - [ ] 4.6: Test logout when not logged in returns error
  - [ ] 4.7: Test double logout is safe (second call returns "Not logged in")
  - [ ] 4.8: Test re-login on same WebSocket after logout — login succeeds, receives `login_success` + `room_state`
  - [ ] 4.9: Test re-login on same WebSocket WITHOUT logout first (AC #5) — inline cleanup runs, login succeeds, socket not closed
  - [ ] 4.10: Run full test suite — `pytest tests/` must pass with no regressions

## Dev Notes

### Architecture Patterns to Follow

**Logout is a voluntary disconnect.** The existing `handle_disconnect()` and `_kick_old_session()` contain the cleanup logic. The logout handler reuses the same sequence but:
- Is triggered by an explicit `{"action": "logout"}` message (not `WebSocketDisconnect`)
- Sends a `{"type": "logged_out"}` confirmation
- Does NOT close the WebSocket — the player returns to auth state and can re-login on the same connection
- Does NOT send `combat_fled` — to avoid visual flicker, the `logged_out` handler on the client handles combat cleanup

### Combat Removal — Key Differences from Disconnect and Flee

The logout combat removal combines elements from both existing patterns:

| Step | Disconnect does | Flee does | Logout must do |
|------|----------------|-----------|----------------|
| Set `entity.in_combat = False` | No (entity destroyed) | Yes | **Yes** (entity stats saved first) |
| Sync combat stats to entity | No | No (stats lost on flee — acceptable since player keeps pre-combat stats) | **Yes** (stats must be current for DB save) |
| Handle dead player (HP=0) | No | Rejects flee if dead | **Restore HP to max_hp** |
| Release NPC `in_combat` (last player) | No | Yes | **Yes** (match flee) |
| Reset NPC `is_alive` (last player) | No | No | **No** (match flee — NPC keeps damage state) |
| Send `combat_fled` | No | Yes | **No** (avoid flicker, handle in `logged_out`) |

### Cleanup Ordering — Intentionally Different from handle_disconnect

The `handle_disconnect` method pops `player_entities` BEFORE saving state (app.py:323). This is a known simplification — it uses the popped data for the save. For logout, use this better ordering:

1. Combat cleanup (clear `in_combat`, sync stats, remove from instance)
2. Save state to DB (entity still in `player_entities` for reference)
3. Remove from room + broadcast `entity_left`
4. Send `{"type": "logged_out"}` via raw `websocket.send_json()`
5. Call `connection_manager.disconnect(entity_id)` (clears all maps)
6. Pop from `player_entities`

**Critical:** Step 4 MUST use `websocket.send_json()` directly, NOT `connection_manager.send_to_player()`. After step 5, the connection manager no longer knows about this entity. After step 6, `player_entities` no longer has the data.

### Note: `_kick_old_session` Does NOT Sync Combat Stats

`_kick_old_session` saves `entity.stats` before removing from combat, so it saves pre-combat values. This was deemed acceptable for the kick scenario (player is being forcibly disconnected). Do NOT use `_kick_old_session` as a template for combat stats sync — use the ordering specified in Task 1.2 instead.

### Re-login on Same WebSocket (Pre-existing Bug Fix)

`handle_login` checks `old_ws = game.connection_manager.get_websocket(entity_id)` to detect duplicate logins. If the player logs out and then logs in again on the same WebSocket, `old_ws` is `None` (cleared by logout's `disconnect()` call). This works correctly.

**But:** If the player sends `login` WITHOUT logging out first (skipping logout), `old_ws` is the same WebSocket object. `_kick_old_session` would call `old_ws.close(code=1000)`, closing the active connection. This is a pre-existing bug exposed by keeping WebSockets open.

**Fix:** In `handle_login`, before calling `_kick_old_session`, add:
```python
if old_ws is websocket:
    # Same socket re-login — perform inline cleanup, don't close the socket
    # (reuse logout cleanup logic without sending logged_out)
```

### State Save is Best-Effort

Wrap the state save in `try/except Exception` and log the error. Logout must proceed even if the DB save fails. This matches the pattern used in `handle_disconnect` and `shutdown`.

### Concurrent Logout + Disconnect Safety

If the network drops during the logout handler, `WebSocketDisconnect` fires after logout completes (or partially completes). `handle_disconnect` will call `get_entity_id(websocket)` which returns `None` (already cleaned up), so it returns early. All cleanup operations are idempotent (dict pops on missing keys, etc.). This is safe.

### Web Client Notes

**Do NOT call `resetToLogin()` for logout.** `resetToLogin()` closes the WebSocket (`gameState.ws.close()` at line 213-215), which contradicts the "keep socket open" design. Instead, the `logged_out` handler must manually: clear credentials, clear player/room state, dismiss combat overlay, clear UI elements, and switch to auth mode via `setMode('auth')`. This is similar to `resetToLogin` but without the socket close and reconnect-state clearing.

**`handleKicked`** (existing) calls `resetToLogin` — this is correct for kick (socket is being closed by the server anyway). Logout is different because the socket stays open.

**`/logout` chat command:** Intercept in the chat send handler — if the message is `/logout`, call `sendAction('logout', {})` instead of sending as chat. This is a minimal implementation ahead of the full slash command parser (Story 10.3).

### Project Structure Notes

- Handler in existing file: `server/net/handlers/auth.py`
- Handler registration in existing method: `server/app.py:_register_handlers()`
- Same-socket re-login fix in existing function: `server/net/handlers/auth.py:handle_login`
- Logout button in existing HTML: `web-demo/index.html` player info section
- Message handler in existing JS: `web-demo/js/game.js` dispatch table
- No new files needed

### References

- [Source: server/app.py#handle_disconnect] — full disconnect cleanup sequence
- [Source: server/net/handlers/auth.py#_kick_old_session] — kick with explicit socket close
- [Source: server/net/handlers/combat.py#handle_flee] — combat exit with NPC release
- [Source: server/net/connection_manager.py] — connection tracking maps and methods
- [Source: server/combat/instance.py#participant_stats] — combat stats separate from entity stats
- [Source: web-demo/js/game.js#resetToLogin] — client auth state reset
- [Source: web-demo/js/game.js#dispatchMessage] — message handler dispatch table
- [Source: tests/test_game.py] — disconnect test patterns
- [Source: _bmad-output/planning-artifacts/epics.md#Story 10.1] — acceptance criteria

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
