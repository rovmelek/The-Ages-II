# Story 10.1: Player Logout

Status: ready-for-dev

## Story

As a player,
I want to logout cleanly from the game,
so that my state is saved and I can return to the login screen without closing the browser.

## Acceptance Criteria

1. **Given** a logged-in player, **When** the server receives `{"action": "logout"}`, **Then** the player's state is saved to DB (position, stats, inventory), the player's entity is removed from the room, other players receive `entity_left`, the player is removed from `player_entities` and `connection_manager`, the player receives `{"type": "logged_out"}`, and the WebSocket remains open (player returns to auth state, can login again).

2. **Given** a player is in combat, **When** they send a logout action, **Then** the player is removed from combat (treated as flee), the player receives `{"type": "combat_fled"}` before `{"type": "logged_out"}`, combat continues for other participants (remaining participants receive `combat_update`), if the player was the last participant the combat instance is cleaned up and the mob resets (`is_alive=true`, `in_combat=false`), and logout proceeds normally after combat removal (state save, room removal, `entity_left` broadcast).

3. **Given** a player is not logged in, **When** they send a logout action, **Then** the client receives `{"type": "error", "detail": "Not logged in"}`.

4. **Given** the web client receives a `logged_out` message, **When** the UI updates, **Then** the game viewport is hidden and the login form is shown, a "Logout" button is visible in the game UI during gameplay, and `/logout` command is available via chat input.

## Tasks / Subtasks

- [ ] Task 1: Server-side logout handler (AC: #1, #2, #3)
  - [ ] 1.1: Create `handle_logout` in `server/net/handlers/auth.py` — resolve entity_id from websocket, return error if not logged in
  - [ ] 1.2: Implement combat removal for in-combat players — follow `handle_disconnect` pattern (app.py:308-321), plus release NPC `in_combat` flag and clean up instance if last participant (follow flee handler pattern at combat.py:194-201), send `combat_fled` to the logging-out player
  - [ ] 1.3: Save player state to DB — position, stats, inventory in one async_session block (follow pattern at app.py:329-343)
  - [ ] 1.4: Remove from room + broadcast `entity_left` (follow app.py:346-353)
  - [ ] 1.5: Clean up connection_manager + player_entities, send `{"type": "logged_out"}` — do NOT close the WebSocket (player may re-login on same connection)
  - [ ] 1.6: Register `logout` action in `Game._register_handlers()` (app.py ~line 185)
- [ ] Task 2: Web client logout UI (AC: #4)
  - [ ] 2.1: Add "Logout" button to `web-demo/index.html` in the left panel player section (after line 55, near room name)
  - [ ] 2.2: Add `logged_out` message handler in `web-demo/js/game.js` — clear `gameState.credentials` (prevent auto-login on reconnect), call `resetToLogin('You have been logged out.')`
  - [ ] 2.3: Add click handler for logout button — `sendAction('logout', {})`
- [ ] Task 3: Tests (AC: #1, #2, #3)
  - [ ] 3.1: Test logout saves state and removes player (unit test, follow test_game.py disconnect pattern)
  - [ ] 3.2: Test logout while in combat removes from combat first
  - [ ] 3.3: Test logout when not logged in returns error
  - [ ] 3.4: Test double logout is safe (second call returns "Not logged in")
  - [ ] 3.5: Run full test suite — `pytest tests/` must pass with no regressions

## Dev Notes

### Architecture Patterns to Follow

**Logout is a voluntary disconnect.** The existing `handle_disconnect()` (app.py:301-355) and `_kick_old_session()` (auth.py:60-122) contain all the cleanup logic. The logout handler reuses the same sequence but:
- Is triggered by an explicit `{"action": "logout"}` message (not `WebSocketDisconnect`)
- Sends a `{"type": "logged_out"}` confirmation
- Does NOT close the WebSocket — the player returns to auth state and can re-login on the same connection

**Combat removal sequence** (from disconnect handler app.py:308-321):
```
combat_instance = game.combat_manager.get_player_instance(entity_id)
if combat_instance:
    combat_instance.remove_participant(entity_id)
    game.combat_manager.remove_player(entity_id)
    if not combat_instance.participants:
        game.combat_manager.remove_instance(combat_instance.instance_id)
    else:
        # broadcast combat_update to remaining participants
```

**Important difference from disconnect:** When the last player logs out of combat, the NPC must be released (`npc.in_combat = False`, `npc.is_alive = True`). The disconnect handler does NOT do this (known simplification). The flee handler does (combat.py:194-201). Follow the flee handler's pattern for this case.

**State save pattern** (used in disconnect, shutdown, and kick — all identical):
```python
async with async_session() as session:
    await player_repo.update_position(session, entity.player_db_id, room_key, entity.x, entity.y)
    await player_repo.update_stats(session, entity.player_db_id, entity.stats)
    if inventory:
        await player_repo.update_inventory(session, entity.player_db_id, inventory.to_dict())
```

**Connection manager cleanup order matters:** Call `connection_manager.disconnect(entity_id)` AFTER you are done using the connection manager for lookups and broadcasts. The `disconnect()` method removes the websocket from all internal maps.

### WebSocket Lifecycle Decision

The AC says "WebSocket remains open." This means after logout, the websocket is still connected but the player has no entity. They're back in auth state — they can send `login` or `register` again. This avoids the cost of re-establishing the WebSocket connection.

**Implication:** Do NOT call `websocket.close()` in the logout handler. Do NOT call `connection_manager.disconnect()` in a way that closes the socket. The `disconnect()` method on `ConnectionManager` only cleans up internal maps (it does not close the socket).

**Race condition safety:** After logout completes, if the `websocket_endpoint` loop continues receiving messages, the router will handle them normally. If the player sends `move` or `chat` while logged out, the handlers check for entity_id and return "Not logged in" errors. This is safe.

### Web Client Notes

**`resetToLogin(statusMessage)`** (game.js:211-256) is the exact function for returning to auth screen. It:
- Clears game state but preserves credentials (lines 231-237)
- Clears UI (tile grid, chat, combat)
- Switches to auth mode

**For logout specifically:** Must also clear `gameState.credentials` to prevent auto-login on reconnect (game.js:155-160 auto-sends login if credentials exist). The `handleKicked` handler does NOT clear credentials (by design — kicked users re-login). Logout should.

**Auto-reconnect safety:** `resetToLogin` sets `gameState.player = null` (line 233), which prevents the `ws.onclose` auto-reconnect logic (line 170). Since we're NOT closing the socket, `ws.onclose` won't fire anyway.

### Project Structure Notes

- New handler function goes in existing file: `server/net/handlers/auth.py` (alongside login, register, kick)
- Handler registration goes in existing method: `server/app.py:_register_handlers()`
- Logout button in existing HTML: `web-demo/index.html` left panel
- Message handler in existing JS: `web-demo/js/game.js` dispatch table
- No new files needed

### References

- [Source: server/app.py#handle_disconnect] Lines 301-355 — full disconnect cleanup sequence
- [Source: server/net/handlers/auth.py#_kick_old_session] Lines 60-122 — kick with explicit socket close
- [Source: server/net/handlers/combat.py#handle_flee] Lines 154-201 — combat exit with NPC release
- [Source: server/net/connection_manager.py] Lines 1-67 — connection tracking maps and methods
- [Source: web-demo/js/game.js#resetToLogin] Lines 211-256 — client auth state reset
- [Source: web-demo/js/game.js#dispatchMessage] Line 296 — message handler dispatch table
- [Source: tests/test_game.py] Lines 196-312 — disconnect test patterns
- [Source: _bmad-output/planning-artifacts/epics.md#Story 10.1] — acceptance criteria

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
