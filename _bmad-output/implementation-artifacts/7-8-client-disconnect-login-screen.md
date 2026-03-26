# Story 7.8: Client Returns to Login on Permanent Disconnect

Status: done

## Story

As a player using the web demo client,
I want the client to return me to the login screen when the WebSocket connection is permanently lost,
so that I clearly know I've been disconnected and can re-authenticate cleanly.

## Acceptance Criteria

1. **Given** the WebSocket connection drops and all reconnect attempts are exhausted (currently MAX_RECONNECT = 5),
   **When** the final reconnect fails,
   **Then** the client resets to the login screen (shows `#auth-screen`, hides `#game-screen`),
   **And** reconnect attempt counter is reset,
   **And** a status message shows "Connection lost. Please log in again."

2. **Given** the server sends `{type: "server_shutdown", reason: "..."}`,
   **When** the client receives this message,
   **Then** the client immediately stops reconnect attempts (do NOT auto-reconnect to a shutting-down server),
   **And** returns to the login screen,
   **And** shows a status message: "Server is shutting down. Please try again later."

3. **Given** the client has returned to the login screen after disconnect,
   **When** the player enters credentials and clicks Login,
   **Then** a new WebSocket connection is established,
   **And** normal login flow proceeds (no stale state from previous session).

4. **Given** the client has in-memory game state from a previous session,
   **When** the client returns to the login screen,
   **Then** all game state is cleared (gameState reset to initial values),
   **And** the game viewport, combat overlay, and chat are hidden/cleared,
   **And** stored credentials (`gameState.credentials`) are preserved for convenience (pre-fill login form).

5. **Given** the WebSocket drops but reconnect attempts have NOT been exhausted,
   **When** auto-reconnect is still in progress,
   **Then** existing behavior is preserved: exponential backoff retry with auto re-login using stored credentials,
   **And** status shows "Reconnecting... (attempt N/5)".

6. **Given** the client is in active combat when disconnected permanently,
   **When** the client returns to the login screen,
   **Then** the combat overlay is hidden,
   **And** combat state is cleared from gameState.

## Tasks / Subtasks

- [ ] Task 1: Add `resetToLogin()` function (AC: 1, 4, 6)
  - [ ] Create a function that: hides `#game-screen`, shows `#auth-screen`, clears game viewport/chat/combat overlay
  - [ ] Reset `gameState` fields: `currentRoom`, `entities`, `myEntityId`, `inCombat`, `combatState` → initial values
  - [ ] Preserve `gameState.credentials` for login form pre-fill
  - [ ] Reset `reconnectAttempts = 0`

- [ ] Task 2: Handle exhausted reconnects (AC: 1, 5)
  - [ ] In `ws.onclose` handler (game.js ~line 155), after `reconnectAttempts >= MAX_RECONNECT`, call `resetToLogin()`
  - [ ] Show status message "Connection lost. Please log in again."
  - [ ] Existing reconnect logic (exponential backoff, auto re-login) stays unchanged for attempts < MAX_RECONNECT

- [ ] Task 3: Handle `server_shutdown` message (AC: 2)
  - [ ] Add case for `type: "server_shutdown"` in the message handler switch
  - [ ] Set a flag (e.g., `serverShuttingDown = true`) to prevent auto-reconnect
  - [ ] Call `resetToLogin()`
  - [ ] Show "Server is shutting down. Please try again later." with the shutdown reason
  - [ ] In `ws.onclose`, check `serverShuttingDown` flag — if true, skip reconnect attempts
  - [ ] Clear `serverShuttingDown` flag when user manually initiates a new login

- [ ] Task 4: Clean login after reset (AC: 3)
  - [ ] Verify that `connectWebSocket()` + login flow works cleanly after `resetToLogin()`
  - [ ] Ensure no stale WebSocket references remain (`ws` is already set to `null` in `onclose`)
  - [ ] Pre-fill username field from `gameState.credentials.username` if available

## Dev Notes

### Architecture Patterns

- **Web client** (`web-demo/js/game.js`) is a single-file vanilla JS application — all state and UI logic in one file
- **No framework** — DOM manipulation via `document.getElementById()` and direct `.style` / `.classList` changes
- **Screen switching**: `#auth-screen` and `#game-screen` are toggled via `display: none/flex`. Login success hides auth, shows game (around line 1117-1130 in message handler)
- **gameState** object holds all client-side state: `currentRoom`, `entities`, `myEntityId`, `inCombat`, `combatState`, `credentials`, etc.

### Current WebSocket Handling (game.js)

- **`connectWebSocket()`** (~line 109): Creates WebSocket, sets up handlers
- **`ws.onclose`** (~line 155-165): Sets `ws = null`, updates status. If logged in and `reconnectAttempts < MAX_RECONNECT` (5), calls `setTimeout(connectWebSocket, delay)` with exponential backoff: `delay = Math.min(1000 * 2^attempts, 15000)`
- **`ws.onopen`** (~line 143-153): Resets reconnect counter, auto re-logins with stored `gameState.credentials`
- **`ws.onerror`** (~line 167-169): No-op — relies on `onclose`
- **MAX_RECONNECT** = 5 (defined near top of file)
- **Credentials stored** at login/register (lines ~1117, 1129) in `gameState.credentials = {username, password}`

### Critical Constraints

- **DO NOT** change the reconnect backoff logic for attempts < MAX_RECONNECT — existing behavior works well
- **DO NOT** clear `gameState.credentials` on disconnect — needed for auto re-login and login form pre-fill
- **DO** clear all game state (entities, combat, room) to prevent stale data on re-login
- **DO** handle the case where disconnect happens during combat (hide combat overlay)
- **Order matters**: clear state → switch screens → show message (so message is visible on the login screen)

### Existing Code to Reuse

- Screen toggle pattern already exists in login success handler (~line 1117-1130 in game.js)
- `updateStatus()` function exists for status messages
- `gameState` object structure is already defined at file top
- Combat overlay hide: likely `document.getElementById('combat-overlay').style.display = 'none'` or similar

### What NOT to Build

- No "reconnecting..." modal/overlay — current status text is sufficient
- No "are you sure you want to leave?" confirmation — this is an involuntary disconnect, not a user action
- No session persistence in localStorage — server is the source of truth
- No graceful degradation (offline mode) — game requires server connection

### Dependency on Story 7.7

This story depends on Story 7.7 (Graceful Server Shutdown) for the `server_shutdown` message type. If implementing before 7.7, the `server_shutdown` handler can still be added — it just won't fire until the server sends that message. No blocker.

### Project Structure Notes

- All changes in `web-demo/js/game.js` — single file modification
- No server-side changes needed (server_shutdown message is added in Story 7.7)
- No new files needed
- No CSS changes needed (screen toggle uses existing styles)

### References

- [Source: web-demo/js/game.js#connectWebSocket — ~line 109-180]
- [Source: web-demo/js/game.js#ws.onclose — ~line 155-165]
- [Source: web-demo/js/game.js#login_success handler — ~line 1117-1130]
- [Source: web-demo/js/game.js#gameState — near top of file]
- [Source: Story 7.7 — server_shutdown message definition]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Completion Notes List
- Task 1: Added `resetToLogin()` function — clears game state, hides combat overlay, switches to auth screen, preserves credentials, pre-fills login form
- Task 2: Updated `ws.onclose` to call `resetToLogin()` when `reconnectAttempts >= MAX_RECONNECT`, with "Connection lost" message
- Task 3: Added `server_shutdown` message handler — sets `serverShuttingDown` flag to prevent reconnect, calls `resetToLogin()` with shutdown reason. Flag cleared on manual login/register.
- Task 4: Login/register forms now reconnect WebSocket if closed (after permanent disconnect or shutdown), ensuring clean session. Also added `kicked` and `respawn` message handlers for completeness.
- Code Review Fixes: Fixed `ws.onopen` to respect `pendingAction` (register vs login); added `renderRoom()`/`updateStatsPanel()` to `handleRespawn`; added CONNECTING guard in `connectWebSocket()`; `resetToLogin()` now closes active WebSocket and clears moveErrorTimer; added `test_game_shutdown_saves_player_state` test

### File List
- `web-demo/js/game.js` — Added `resetToLogin()`, `handleServerShutdown()`, `handleKicked()`, `handleRespawn()`, `serverShuttingDown` flag, updated `ws.onclose`, login/register form handlers, fixed `ws.onopen` pendingAction handling
- `tests/test_game.py` — Added `test_game_shutdown_saves_player_state` test for Story 7.7
