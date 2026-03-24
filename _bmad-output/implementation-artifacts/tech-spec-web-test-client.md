---
title: 'Web Test Client for The Ages II'
slug: 'web-test-client'
created: '2026-03-23'
status: 'done'
stepsCompleted: [1, 2, 3, 4]
tech_stack:
  - HTML5
  - CSS3 (Grid, transitions, keyframe animations)
  - Vanilla JavaScript (ES6+, with JSDoc type annotations and @ts-check)
  - FastAPI StaticFiles mount
files_to_modify:
  - 'server/app.py (add StaticFiles mount)'
  - 'server/net/handlers/auth.py (change default room to town_square)'
  - 'data/rooms/test_room.json (add exit to town_square, update tile_data)'
  - 'data/rooms/town_square.json (add exit to test_room, update tile_data)'
  - 'data/rooms/dark_cave.json (add exit to other_room, update tile_data)'
  - 'data/rooms/other_room.json (add exit to dark_cave, update tile_data)'
  - 'tests/test_login.py (update default room assertion from test_room to town_square)'
  - 'tests/test_integration.py (update default room assertion from test_room to town_square)'
files_to_create:
  - 'web-demo/index.html'
  - 'web-demo/css/style.css'
  - 'web-demo/js/game.js'
  - 'web-demo/jsconfig.json'
code_patterns:
  - 'WebSocket JSON protocol: client sends {action, ...params}, server sends {type, ...data}'
  - 'Tile types as integers: FLOOR=0, WALL=1, EXIT=2, MOB_SPAWN=3, WATER=4'
  - 'Entity IDs: player_N format (e.g., player_1) — constructed client-side from login_success integer player_id'
  - 'Room state: full 2D tile grid + entity/NPC/object lists on entry'
  - 'Combat state: participants with hp/max_hp/shield, mob stats, hands with card defs'
  - 'Card data: card_key, name, cost, effects (list of {type,subtype,value,...}), description'
  - 'NPC data: id, npc_key, name, x, y, is_alive'
  - 'Objects: id, type, x, y, category (static/interactive), state_scope, config'
test_patterns:
  - 'Manual testing via browser — no automated client tests in scope'
  - 'Multi-tab testing for multiplayer validation'
  - 'Server message log panel for protocol debugging'
---

# Tech-Spec: Web Test Client for The Ages II

**Created:** 2026-03-23

## Overview

### Problem Statement

The server implements the full gameplay loop (6 epics, 34 stories, all done), but it has only been validated through pytest and raw WebSocket tools (websocat, curl). There is no visual way to experience the game, test multiplayer interactions, or demo the project to others.

### Solution

Build a web-based test client served by the FastAPI server — a single page with HTML/CSS/JS that connects via WebSocket and provides a game-like dark-themed UI with a tile grid viewport, combat card interface, chat, and inventory panels.

### Scope

**In Scope:**

- Static file serving from FastAPI (`static/` mount)
- Auth flow (register/login forms)
- 25x25 CSS Grid viewport centered on player, rendering 100x100 rooms
- Movement via keyboard (arrow keys / WASD)
- Entity rendering (players, NPCs, objects) with visual distinction
- Chat panel (room chat + whispers)
- Combat UI with styled clickable cards, pass turn, flee, item use in combat
- Inventory panel with item usage outside combat
- Object interaction (chests, levers)
- Dark game-like theme
- Health/stats display
- Server message log for debugging
- Multi-tab safe (in-memory state, no localStorage)

**Out of Scope:**

- Sound/audio
- Sprite animation / walking frames
- Full map zoom/pan
- Mobile responsiveness
- REST API integration (trades, filters, profiles)
- Account management beyond register/login
- Room editor
- Card skill tree UI

## Context for Development

### Codebase Patterns

**Server architecture:** Domain-driven Python with FastAPI. Central `Game` class in `server/app.py` owns all managers (RoomManager, CombatManager, ConnectionManager, MessageRouter, Scheduler, EventBus, EffectRegistry).

**WebSocket protocol:** Single endpoint `/ws/game`. Client sends JSON with `action` field. Server responds with JSON with `type` field. All communication is over this one connection.

**Client → Server actions (11 total):**

| Action | Required Fields |
|--------|----------------|
| `register` | `username`, `password` |
| `login` | `username`, `password` |
| `move` | `direction` ("up"/"down"/"left"/"right") |
| `chat` | `message`, optional `whisper_to` (entity_id) |
| `interact` | `target_id` |
| `play_card` | `card_key` |
| `pass_turn` | (none) |
| `flee` | (none) |
| `inventory` | (none) |
| `use_item` | `item_key` |
| `use_item_combat` | `item_key` |

**Server → Client message types (17 total):**

| Type | Key Fields |
|------|------------|
| `login_success` | `player_id` (integer DB primary key, e.g. `1` — NOT the entity ID string), `username`. **Client must construct entity ID as `` `player_${player_id}` `` (e.g., `"player_1"`) for use in combat turn ownership, entity matching, and whisper targeting.** |
| `room_state` | `room_key`, `name`, `width`, `height`, `tiles` (2D int[][]), `entities` ([{id,name,x,y}]), `npcs` ([{id,npc_key,name,x,y,is_alive}]), `exits` ([{target_room,x,y,direction}] — raw JSON from room file, direction is compass-style metadata), `objects` ([{id,type,x,y,category,blocking}] — interactive objects additionally have `state_scope` and `config` fields) |
| `entity_moved` | `entity_id`, `x`, `y` |
| `entity_entered` | `entity` ({id,name,x,y}) |
| `entity_left` | `entity_id` |
| `combat_start` | `instance_id`, `current_turn`, `participants` ([{entity_id,hp,max_hp,shield}]), `mob` ({name,hp,max_hp}), `hands` ({entity_id: [{card_key,name,cost,effects,description}]}) |
| `combat_turn` | `result` (action details — see below) + full combat state (same structure as `combat_start`, including `hands` for ALL participants). `result` contains: `action` ("play_card"/"pass_turn"/"use_item"), `entity_id`, and action-specific fields. **Mob attack fields per action type**: For `play_card` and `use_item`: `result.mob_attack` ({target,damage,shield_absorbed,target_hp}) is **conditionally present** — only when the action completes a full turn cycle, the mob attacks a random player. No `cycle_mob_attack` key is ever emitted for these actions. For `pass_turn`: `result.mob_attack` is **ALWAYS present** (mob immediately attacks the passer as a penalty). Additionally, `result.cycle_mob_attack` (same shape) is **conditionally present** if the pass also completes a cycle — the mob attacks a random player. Both fields CAN be present simultaneously on `pass_turn` only (passer gets hit + cycle-end random target gets hit = two separate attacks in one result). **Important**: `cycle_mob_attack` is exclusive to `pass_turn` — never appears in `play_card` or `use_item` results. |
| `combat_end` | `victory` (bool — `true` if mob HP reached 0, `false` if all players died), `rewards` (dict — `{xp: 25}` on victory, `{}` on defeat) |
| `combat_fled` | (no extra fields) |
| `combat_update` | full combat state (same structure as `combat_start`, including `hands` for ALL participants) |
| `chat` | `sender` (string — the player's display name/username, NOT entity_id), `message`, `whisper` (bool) |
| `inventory` | `items` (list) |
| `item_used` | `item_key` (string), `item_name` (string), `effect_results` (list of dicts, one per effect — each has `type` field: `"heal"` → `{type,value,target_hp}`, `"damage"` → `{type,value,shield_absorbed,target_hp}`, `"shield"` → `{type,value,total_shield}`, `"dot"` → `{type,subtype,value,duration}`, `"draw"` → `{type,value}`) |
| `interact_result` | `object_id`, `result` (dict) |
| `announcement` | `message` |
| `error` | `detail` |
| `tile_changed` | `x` (int), `y` (int), `tile_type` (int) — broadcast to all players in the room when a lever toggles a tile (e.g., wall ↔ floor). Client must update the tile at (x, y) in `gameState.room.tiles[y][x]` and re-render that tile div with the new tile-type class. |

**Tile type system:**

| ID | Type | Walkable | Display Color |
|----|------|----------|---------------|
| 0 | FLOOR | Yes | Dark gray (#2a2a2a) |
| 1 | WALL | No | Dark stone (#1a1a1a with inset border) |
| 2 | EXIT | Yes | Green glow (#1a3a1a with green border) |
| 3 | MOB_SPAWN | Yes | Same as floor (invisible to player) |
| 4 | WATER | No | Dark blue (#1a1a3a) |

**Entity rendering icons:**

| Entity Type | Icon | Color |
|-------------|------|-------|
| Player (self) | @ | Bright cyan (#00ffff) |
| Player (other) | @ | Blue (#4488ff) |
| NPC (hostile, alive) | ! | Red (#ff4444) |
| NPC (dead) | x | Dark gray (#555) |
| Static object (tree) | ♣ | Green (#44aa44) |
| Static object (rock) | ● | Gray (#888) |
| Interactive (chest) | ■ | Gold (#ffaa00) |
| Interactive (lever) | ↕ | Orange (#ff8800) |
| Flower | ✿ | Pink (#ff88cc) |
| Fountain | ≋ | Cyan (#44dddd) |

### Files to Reference

| File | Purpose |
| ---- | ------- |
| `server/app.py` | FastAPI app, WebSocket endpoint, Game orchestrator — **modify to add StaticFiles mount** |
| `server/core/config.py` | Server settings (HOST, PORT, BASE_DIR) — BASE_DIR points to project root |
| `server/net/handlers/auth.py` | Login/register handlers — **modify default room from `test_room` to `town_square`** |
| `server/net/handlers/movement.py` | Move handler, exit transitions, mob encounters |
| `server/net/handlers/chat.py` | Room chat and whisper handler |
| `server/net/handlers/combat.py` | play_card, pass_turn, flee, use_item_combat |
| `server/net/handlers/inventory.py` | inventory list and use_item (outside combat) |
| `server/net/handlers/interact.py` | Object interaction handler |
| `server/room/tile.py` | TileType enum (FLOOR=0, WALL=1, EXIT=2, MOB_SPAWN=3, WATER=4) |
| `server/room/room.py` | Room.get_state() — defines room_state payload shape |
| `server/room/objects/npc.py` | NpcEntity.to_dict() — NPC serialization for client |
| `server/combat/instance.py` | CombatInstance.get_state() — combat state payload shape |
| `server/combat/cards/card_def.py` | CardDef.to_dict() — card serialization for client |
| `server/combat/cards/card_hand.py` | CardHand.get_hand() — hand serialization |
| `server/player/entity.py` | PlayerEntity dataclass (id, name, x, y, stats, in_combat) |
| `data/rooms/town_square.json` | Primary test room: 100x100, exit at (50,99) south to dark_cave |
| `data/rooms/dark_cave.json` | Secondary room: 100x100, exit at (50,0) north to town_square |
| `data/cards/starter_cards.json` | 15 card definitions with effects |
| `data/items/base_items.json` | 4 item definitions (2 consumable, 2 material) |
| `data/npcs/base_npcs.json` | 5 NPC templates (3 persistent, 2 rare) |

### Technical Decisions

- **Rendering**: CSS Grid with ~25x25 tile viewport centered on the player. Viewport shifts as the player moves via CSS `transform: translate(...)` with smooth transitions.
- **File structure**: `web-demo/index.html`, `web-demo/css/style.css`, `web-demo/js/game.js` — served by FastAPI's `StaticFiles` mount. *(Note: originally planned as `static/`, renamed to `web-demo/` during implementation to better communicate its purpose as a proof-of-concept test tool, distinct from the planned Godot production client.)*
- **Static mount strategy**: Mount `StaticFiles(directory="web-demo")` at `/static` URL path. Serve `index.html` via a dedicated `GET /` route that returns `FileResponse("web-demo/index.html")`. This avoids conflicts with existing routes (`/health`, `/ws/game`). Both `http://localhost:8000/` and `http://localhost:8000/static/index.html` serve the page. **Asset path resolution**: The HTML must include `<base href="/static/">` in the `<head>` tag. This ensures relative paths (`css/style.css`, `js/game.js`) resolve to `/static/css/style.css` and `/static/js/game.js` regardless of whether the page is accessed via `/` or `/static/index.html`. Without this tag, accessing via `GET /` would resolve relative paths from `/` (e.g., `/css/style.css`) which doesn't hit the StaticFiles mount — CSS and JS would fail silently.
- **State management**: All state held in JS memory (no localStorage) to ensure multi-tab safety. Key state object: `gameState` with `player` (id as entity ID string e.g. `"player_1"`, dbId as integer, name, x, y, stats), `room` (key, name, width, height, tiles, entities, npcs, objects, exits), `combat` (instance_id, participants, mob, hand, current_turn), `inventory` (items list), `credentials` (username, password — for auto-reconnect), `pendingAction` ('register' or 'login' — tracks which auth action is in flight).
- **Styling**: Dark game-like theme with styled panels, color-coded tiles, emoji/icon entities, CSS animations for feedback (damage flash, heal pulse).
- **Cards**: Rendered as styled clickable card elements showing name, cost badge, effect list, and description. Cards are disabled/grayed when it's not the player's turn. **Card cost is purely informational** — the server has no mana/energy resource system and does not enforce cost. `play_card` never checks cost. Display the cost badge for visual flavor (values are 1 or 2 in current data) but do not implement any client-side cost tracking or validation.
- **Starting room**: Change default in `auth.py` from `test_room` to `town_square`.
- **Panel layout**: Three-column layout. Left: stats/inventory. Center: game viewport (map). Right: chat log + message log. Combat overlay appears centered over the map when in combat.
- **Movement directions**: Arrow keys and WASD mapped to server's `"up"/"down"/"left"/"right"` (defined in `server/room/room.py` `DIRECTION_DELTAS`). W/ArrowUp → `"up"`, S/ArrowDown → `"down"`, A/ArrowLeft → `"left"`, D/ArrowRight → `"right"`. Note: the server does NOT use cardinal names like "north"/"south" — it uses "up"/"down"/"left"/"right" exclusively. Keyboard input disabled when chat input is focused or when in combat (movement blocked server-side too, but prevent sending unnecessary requests).
- **UI state modes**: The page has distinct visual modes — `auth` (login/register forms visible, game hidden), `explore` (map + chat + inventory visible), `combat` (combat overlay on top of map). Transitions between modes based on server messages.
- **Room transition message sequence**: When a player steps on an exit tile, the server does NOT send `entity_moved` for the exit tile step. Instead, the mover receives only `room_state` (full new room). Other players in the old room receive `entity_left`. Other players in the new room receive `entity_entered`. Exact order: (1) old room broadcast `entity_left` (excl. mover), (2) mover receives `room_state` for new room, (3) new room broadcast `entity_entered` (excl. mover). The client's `handleRoomState` fully replaces `gameState.room` and re-renders — no special exit handling needed beyond what `handleRoomState` already does.

### Error Handling Requirements

- **WebSocket connection failure**: On initial connection failure or unexpected close, display a status banner "Disconnected — reconnecting..." above the game area. Attempt reconnection with exponential backoff (1s, 2s, 4s, 8s, max 15s). After 5 failed attempts, show "Connection lost. Click to retry." and stop auto-reconnecting.
- **Failed login/register**: Display the server's `error.detail` message below the auth form inputs in red text. Do not clear the form fields so the user can correct and retry.
- **Wall collision / invalid move**: The server sends an `error` message with detail like "Cannot move there." Display briefly as a subtle flash or status text near the viewport — do not use a modal or alert. Fade out after 2 seconds.
- **Unknown server message types**: Log to the message log panel with a yellow "UNKNOWN" prefix. Do not crash — silently ignore for gameplay purposes.
- **Combat action errors**: Display the error detail in the combat overlay status area (e.g., "Not your turn", "Invalid card"). Do not close the combat overlay.
- **WebSocket send while disconnected**: Queue the message and warn the user with a status indicator. Discard queued messages if reconnection takes longer than 10 seconds.

### Reconnection Behavior

- On WebSocket `onclose`, if the player was logged in (`gameState.player` is set), auto-attempt reconnection using exponential backoff (1s → 2s → 4s → 8s → capped at 15s).
- On successful reconnect, the player must re-send `login` with the same credentials. Store username/password in `gameState` (memory only, not localStorage) for automatic re-login.
- On reconnect + re-login success, the server sends fresh `room_state`, restoring the UI to current state. **Known limitation**: The server creates a new empty `Inventory()` on every login (auth.py line 108), so items obtained from chests during the session are lost on reconnect. The client re-requests inventory and gets an empty list — this is expected server behavior, not a client bug. Persistent inventory is not implemented in the current server.
- If reconnect fails after 5 attempts, stop retrying and show a manual retry button.
- Display connection status in the UI header: "Connected" (green dot), "Reconnecting..." (yellow dot), "Disconnected" (red dot).

## Implementation Plan

### Tasks

- [ ] Task 1: Server-side static file serving
  - File: `server/app.py`
  - Action: Add `from starlette.responses import FileResponse` and `from fastapi.staticfiles import StaticFiles`. Mount static files: `app.mount("/static", StaticFiles(directory="static"), name="static")`. Add route `GET /` that returns `FileResponse("static/index.html")`. Place mount AFTER the `/health` and `/ws/game` routes so they take precedence.
  - Notes: No new dependencies — StaticFiles is included with FastAPI/Starlette.

- [ ] Task 2: Change default player room and spawn position
  - File: `server/net/handlers/auth.py`
  - Action: On line 86, change `room_key = player.current_room_id or "test_room"` to `room_key = player.current_room_id or "town_square"`. Additionally, new players have DB default position (0, 0) — but town_square tile (0, 0) is a WALL. After constructing the `PlayerEntity`, if the player's position is (0, 0) and the room has spawn_points, override the entity's x/y with the room's first `player` spawn point coordinates. If no spawn points exist, use the room center (width//2, height//2) as a safe fallback. This prevents new players from spawning inside a wall.
  - Notes: Only affects new players or players with no saved room. Existing players with saved positions are unaffected. The position override only applies when position is (0, 0) — the DB default for accounts that have never moved.

- [ ] Task 3: Connect all 4 rooms in a circular topology
  - Files: `data/rooms/test_room.json`, `data/rooms/town_square.json`, `data/rooms/dark_cave.json`, `data/rooms/other_room.json`
  - Action: Add exits to create a circular loop. Keep all existing exits. Add new ones:
    - **test_room** → **town_square**: Add exit at (0, 2) going west. Set tile (0, 2) to type 2 (exit). Entry point in town_square at (98, 50). Verified reachable: path from player spawn (2,2) → (1,2) → (0,2) is all FLOOR tiles with no walls blocking.
    - **town_square** → **test_room**: Add exit at (99, 50) going east. Set tile (99, 50) to type 2 (exit). Entry point in test_room at (1, 2).
    - **dark_cave** → **other_room**: Add exit at (99, 50) going east. Set tile (99, 50) to type 2 (exit). Entry point in other_room at (1, 1).
    - **other_room** → **dark_cave**: Add exit at (4, 0) going north. Set tile (4, 0) to type 2 (exit). Entry point in dark_cave at (98, 50). Note: position (4, 0) is on the top edge of the 5x5 grid, so direction is "north" (not "east").
  - Notes: This creates the circular loop: test_room ↔ other_room ↔ dark_cave ↔ town_square ↔ test_room. Each room now has 2 exits. Tile type 2 = EXIT (walkable, triggers room transition). Must update both the `exits` array and the `tile_data` grid to mark the new exit tile positions.
  - Room topology after change:
    ```
    test_room ←(east/west)→ other_room
        ↕ (west/east)              ↕ (north/east)
    town_square ←(south/north)→ dark_cave
    ```

- [ ] Task 4: Create HTML page structure
  - File: `static/index.html` (new)
  - Action: Create the page with three main sections:
    - **Auth screen** (`#auth-screen`): Register and login forms, centered on page. Visible on load.
    - **Game screen** (`#game-screen`): Hidden until login. Three-column layout:
      - Left panel (`#left-panel`): Player stats (name, HP bar, shield, position), inventory list with use buttons, room info (name, coordinates).
      - Center panel (`#game-viewport`): Overflow-hidden container with the tile grid inside. Fixed viewport size (25x25 tiles at 20px each = 500x500px).
      - Right panel (`#right-panel`): Chat log with input field (text input + send button, whisper dropdown), server message log (collapsible, shows raw JSON for debugging).
    - **Combat overlay** (`#combat-overlay`): Hidden until combat starts. Overlays the center panel. Shows: mob info (name, HP bar), player combat stats (HP bar, shield), card hand (styled card elements), action buttons (Pass Turn, Flee), inventory items usable in combat.
  - Notes: Include `<base href="/static/">` in the `<head>` so relative asset paths resolve correctly from both `/` and `/static/index.html`. Link to `css/style.css` and `js/game.js` (relative, resolved via base). Include meta viewport tag. Set page title to "The Ages II".

- [ ] Task 5: Create CSS dark theme and layout
  - File: `static/css/style.css` (new)
  - Action: Implement complete styling:
    - **Base**: Dark background (#0a0a0a), light text (#e0e0e0), monospace font for game elements, sans-serif for UI.
    - **Auth screen**: Centered card with dark panel background (#1a1a1a), subtle border (#333), styled inputs and buttons.
    - **Game layout**: CSS Grid three-column layout. Left panel ~200px, center flexible (min 500px), right panel ~280px. Full viewport height.
    - **Tile grid**: CSS Grid of 20x20px cells. Tile type classes: `.tile-floor`, `.tile-wall`, `.tile-exit`, `.tile-spawn`, `.tile-water` with distinct background colors and borders. Entity overlay classes for players, NPCs, objects with icon colors.
    - **Panels**: Dark backgrounds (#1a1a1a), bordered (#333), rounded corners, internal padding. Scrollable where content overflows.
    - **HP bars**: Colored bars (green > 50%, yellow 25-50%, red < 25%) inside dark track containers.
    - **Cards**: Card-shaped divs (~120x170px) with dark background, border, header (name + cost), body (effects), footer (description). Hover effect (slight lift/glow). Clickable cursor. Disabled state (opacity + no pointer events).
    - **Chat**: Message list with sender name in color, whispers in italic/purple. Input area at bottom with text field and send button.
    - **Combat overlay**: Semi-transparent dark backdrop over map. Centered combat panel with mob stats, player stats, card hand row, action buttons.
    - **Animations**: `@keyframes damage-flash` (red flash on hit), `@keyframes heal-pulse` (green glow on heal), smooth viewport transition (`transition: transform 0.15s ease`).
    - **Scrollbars**: Thin, dark styled scrollbars for panels.

- [ ] Task 6: Create JS game client — WebSocket and state management
  - File: `static/js/game.js` (new)
  - Action: Implement core client infrastructure:
    - **jsconfig.json**: Create `static/jsconfig.json` with `{"compilerOptions": {"checkJs": true, "strict": true, "target": "ES2020", "module": "ES2020"}, "include": ["js/**/*.js"]}`. This enables IDE type-checking for all `.js` files in the `static/js/` directory.
    - **JSDoc types**: Add `// @ts-check` at top of file. Define JSDoc `@typedef` for key data shapes: `GameState`, `PlayerState`, `RoomState`, `CombatState`, `CardDef`, `Entity`, `NpcData`, `RoomObject`. Use `@typedef {Object}` syntax with `@property` for each field, e.g.: `/** @typedef {Object} Entity @property {string} id @property {string} name @property {number} x @property {number} y */`. Annotate all functions with `@param` and `@returns`.
    - **State object**: `const gameState = { ws: null, player: null, room: null, combat: null, inventory: [], mode: 'auth' }`.
    - **WebSocket connection**: `connectWebSocket()` function. Construct URL with protocol detection: `const wsProto = location.protocol === 'https:' ? 'wss' : 'ws'; const wsUrl = \`${wsProto}://${location.host}/ws/game\`;`. This ensures the client works behind HTTPS reverse proxies (e.g., ngrok for remote demos). Sets up `onopen`, `onclose`, `onerror`, `onmessage` handlers. Auto-reconnect on close with backoff.
    - **Message dispatcher**: `onmessage` parses JSON, logs to message log panel, dispatches to handler by `type` field: `handleLoginSuccess`, `handleRoomState`, `handleEntityMoved`, `handleEntityEntered`, `handleEntityLeft`, `handleCombatStart`, `handleCombatTurn`, `handleCombatEnd`, `handleCombatFled`, `handleCombatUpdate`, `handleChat`, `handleInventory`, `handleItemUsed`, `handleInteractResult`, `handleTileChanged`, `handleAnnouncement`, `handleError`.
    - **Send helper**: `sendAction(action, data)` — merges `{action}` with data, sends as JSON.
    - **UI mode switching**: `setMode(mode)` — shows/hides auth screen, game screen, combat overlay based on mode ('auth', 'explore', 'combat').

- [ ] Task 7: Implement auth flow
  - File: `static/js/game.js`
  - Action: Add auth UI logic:
    - Wire register form submit: collect username/password, call `sendAction('register', {username, password})`.
    - Wire login form submit: collect username/password, call `sendAction('login', {username, password})`.
    - **Register vs Login flow difference**: The server's `handle_register` sends `login_success` but does NOT place the player in a room or send `room_state`. The player is created in the DB but not placed in the game world. The client must detect this: after receiving `login_success` from a register action, show a success message ("Account created! Logging in..."), **set `gameState.pendingAction = 'login'` first**, then immediately auto-send `sendAction('login', {username, password})` to complete the login flow. Only `handle_login` places the player in a room and sends `room_state`. Track which action triggered the response using a `gameState.pendingAction` flag ('register' or 'login'). **Critical: `pendingAction` MUST be updated to `'login'` BEFORE sending the auto-login, otherwise the second `login_success` response will be treated as another register → infinite loop.**
    - `handleLoginSuccess(data)`: Check `gameState.pendingAction`. If `'register'`: show success message, auto-send login, return. If `'login'`: construct entity ID as `` `player_${data.player_id}` `` and store `gameState.player = {id: entityId, name: data.username, dbId: data.player_id}`. Wait for `room_state` to switch mode.
    - `handleError(data)`: Display error in auth screen if in auth mode, or in message log if in game mode.
    - Connect WebSocket on page load. Show auth forms immediately.
    - Store credentials in `gameState.credentials = {username, password}` (memory only) for auto-reconnect re-login.

- [ ] Task 8: Implement room rendering and viewport
  - File: `static/js/game.js`
  - Action: Add room rendering:
    - `handleRoomState(data)`: Store full room state in `gameState.room`. **Extract player position**: find the current player in `data.entities` by matching `entity.id === gameState.player.id`, then store their `x`/`y` into `gameState.player.x` and `gameState.player.y`. This is the only source of the player's position — `login_success` does not include coordinates. Call `renderRoom()`. Switch to 'explore' mode. Update room info panel.
    - `renderRoom()`: Build the full tile grid as a CSS Grid container (`#tile-grid`). Create one div per tile with appropriate tile-type class. Overlay entities, NPCs, and objects on their tile positions. Center viewport on player position using CSS transform.
    - `updateViewport()`: Calculate transform to center the 25x25 viewport on the player. Each tile is 20px × 20px. Viewport is 500px × 500px (25 tiles × 20px). Formula: `translateX = 240 - playerX * 20` and `translateY = 240 - playerY * 20` where 240 = (500/2 - 20/2), centering the player tile in the viewport. Clamp to prevent scrolling past grid edges: `translateX = Math.max(-(gridWidth * 20 - 500), Math.min(240, translateX))`. The upper bound is **240** (not 0) — when the player is near x=0, the translate is positive to keep the grid's left edge inside the viewport. The lower bound is `-(gridWidth * 20 - 500)` — when the player is near the right edge, the grid shifts left to show the last columns. Same pattern for Y. Apply `transform: translate(Xpx, Ypx)` to the tile grid container. Use CSS `transition: transform 0.15s ease` for smooth scrolling.
    - `handleEntityMoved(data)`: The server sends `entity_moved` to ALL players in the room **including the mover** (no exclude). Find entity in `gameState.room.entities` by `data.entity_id`, update its x/y. Re-render the affected tiles (old position and new position). If `data.entity_id === gameState.player.id`: also update `gameState.player.x` and `gameState.player.y`, then call `updateViewport()` to re-center. The client should NOT optimistically update position on keypress — wait for the server's `entity_moved` confirmation.
    - `handleEntityEntered(data)`: Add entity to `gameState.room.entities`. Render entity on its tile.
    - `handleEntityLeft(data)`: Remove entity from `gameState.room.entities`. Clear entity from its tile.
    - Entity rendering: Each tile div can contain an entity span with the appropriate icon and color class. Entities overlay on top of the base tile color. **Self-identification**: The `room_state` entities array includes the current player. To render self vs other players, compare each entity's `id` against `gameState.player.id` — matching entity gets the cyan `@` (self), non-matching players get blue `@` (other). This same comparison is used for whisper dropdown filtering and viewport centering.
    - **Multiple entities on same tile**: When multiple entities occupy the same position (e.g., two players on the same tile, or a player standing on an object), render them in priority order — only show the highest-priority icon: (1) Player (self) — always visible, (2) Player (other), (3) NPC, (4) Interactive object, (5) Static object. Lower-priority entities are hidden behind the top one. This keeps tile rendering simple (one icon per tile). In small rooms (5x5), players often share spawn tiles, so this case is common.
    - Performance: Build tile grid once on `room_state`. For subsequent updates (entity_moved, entity_entered, entity_left), only update the specific affected tile divs — do not rebuild the entire grid.

- [ ] Task 9: Implement keyboard movement
  - File: `static/js/game.js`
  - Action: Add movement input:
    - `document.addEventListener('keydown', handleKeyDown)`.
    - `handleKeyDown(e)`: If mode is not 'explore', return. If chat input is focused, return. Map keys: ArrowUp/W → `"up"`, ArrowDown/S → `"down"`, ArrowLeft/A → `"left"`, ArrowRight/D → `"right"`. Call `sendAction('move', {direction})`. Prevent default for arrow keys (stops page scrolling). **Important**: The server uses `"up"/"down"/"left"/"right"` — NOT `"north"/"south"/"east"/"west"`. See `DIRECTION_DELTAS` in `server/room/room.py`.
    - Debounce (recommended): Set a `movePending` flag to `true` when sending a move, reset to `false` on receiving `entity_moved` for the player's entity_id, OR on `error`, OR on `room_state` (room transition), OR on `combat_start`. **Critical**: Room transitions do NOT send `entity_moved` — the mover receives `room_state` instead. If `movePending` only resets on `entity_moved`, movement is permanently blocked after any room transition. While `movePending` is `true`, ignore further key presses. Without debounce, fast keystrokes between stepping onto a mob tile and receiving `combat_start` will queue extra `move` actions that the server rejects with "Cannot move while in combat" — these error flashes appear right as the combat overlay opens, creating confusing UX noise.

- [ ] Task 10: Implement chat panel
  - File: `static/js/game.js`
  - Action: Add chat functionality:
    - `handleChat(data)`: Append message to chat log. Format: `[sender]: message`. Style whispers differently (italic, purple color). Auto-scroll chat log to bottom.
    - `handleAnnouncement(data)`: Append to chat log with distinct styling (gold/yellow, bold, prefixed with a star).
    - Wire chat input: On submit (Enter key or send button), read message text. If whisper target selected in dropdown, send `sendAction('chat', {message, whisper_to: targetEntityId})`. Otherwise, send `sendAction('chat', {message})`.
    - Whisper dropdown: Populate with current entities in room (from `gameState.room.entities`). Display each entity's `name` as the option label, use `id` (entity_id string, e.g., `"player_2"`) as the option value sent to the server. Exclude the current player from the list (filter out entries where `id === gameState.player.id`). Option "Room (all)" as default (sends no `whisper_to` field). Update options when entities enter/leave — if the currently selected whisper target leaves, reset to "Room (all)".
    - Focus management: When chat input is focused, movement keys should NOT trigger movement.

- [ ] Task 11: Implement combat UI
  - File: `static/js/game.js`
  - Action: Add combat functionality:
    - `handleCombatStart(data)`: Store combat state in `gameState.combat`. Switch to 'combat' mode. Render combat overlay: mob info, player stats, card hand, action buttons.
    - `renderCombatOverlay()`: Show mob name + HP bar. Show player HP bar + shield. Render the **local player's** card hand from `gameState.combat.hands[gameState.player.id]` — the `hands` dict is keyed by entity_id and contains ALL participants' hands, but only render the current player's cards. Each card shows name, cost badge, effects, description. Wire click on each card → `sendAction('play_card', {card_key})`. Render "Pass Turn" button → `sendAction('pass_turn', {})`. Render "Flee" button → `sendAction('flee', {})`. Show combat inventory items (usable_in_combat) with use buttons.
    - `handleCombatTurn(data)`: Update `gameState.combat` with new state (participants, mob, hands, current_turn). Update HP bars, shield values. Update card hand display. Show action result (e.g., "Fire Bolt dealt 20 damage"). Handle mob attacks in `data.result` — behavior differs by action type: **For `play_card`/`use_item`**: check `data.result.mob_attack` — if present, this is a cycle-end attack (mob attacks a random player). Display: "Goblin attacked [target] for [damage] damage (shield absorbed [shield_absorbed])". No `cycle_mob_attack` key exists for these actions. **For `pass_turn`**: `data.result.mob_attack` is **always present** (immediate penalty: mob attacks the passer). Additionally check `data.result.cycle_mob_attack` — if present, this is a separate cycle-end attack on a random player. **Both can be present simultaneously** — render both attack messages sequentially. `cycle_mob_attack` is exclusive to `pass_turn` results. Both fields have shape: `{target, damage, shield_absorbed, target_hp}`. Trigger damage-flash animation on the affected player's HP bar for each attack. Apply CSS damage/heal animations as appropriate.
    - `handleCombatEnd(data)`: Check `data.victory` (boolean). If `true`: show victory message with rewards from `data.rewards.xp` (e.g., "Victory! Gained 25 XP"). **Update NPC state**: the server sets `npc.is_alive = False` at encounter time but sends no room update after combat. The client must manually mark the mob NPC as dead: find the NPC in `gameState.room.npcs` whose `name` matches `gameState.combat.mob.name` and is within 1 tile of the player's position, set its `is_alive = false`, then re-render that tile (show gray `x` instead of red `!`). If `false`: show defeat message (e.g., "Defeated!") — `data.rewards` is an empty object `{}` on defeat, so do not attempt to read `data.rewards.xp`. The NPC is already marked dead server-side regardless of outcome (locked at encounter time). Clear `gameState.combat`. After brief delay (2s), switch back to 'explore' mode. Remove combat overlay. Call `renderRoom()` to refresh the map (room state may have changed during combat). **Player death note**: The server does NOT kill, respawn, or relocate the player on combat defeat. The player's `in_combat` flag is cleared and they remain at the same position in the same room. `entity.stats` is unaffected (combat used a local copy of stats). On the next mob encounter, the server re-applies default stats (hp=100, max_hp=100). There is no death penalty beyond losing the combat — this is by design in the current server implementation.
    - `handleCombatFled(data)`: Clear `gameState.combat`. Switch back to 'explore' mode. Show "You fled from combat" in chat/message log.
    - `handleCombatUpdate(data)`: Update full combat state — replaces `gameState.combat` participants, mob, hands, and current_turn. This fires when another participant acts, flees, OR **disconnects mid-combat**. The `participants` array may shrink (a disconnected player is removed). The client must re-render the full combat overlay on every `combat_update`, not just update HP values — specifically, check if any participant from `gameState.combat.participants` is no longer in `data.participants` and clean up their UI elements.
    - Turn ownership: The `current_turn` field in combat state contains the `entity_id` of the participant whose turn it is. Compare `gameState.combat.current_turn === gameState.player.id` to determine if it's the local player's turn. When it IS the player's turn, enable card clicks and action buttons. When it is NOT, disable them (add `.disabled` class — reduced opacity, `pointer-events: none`, show "Waiting for turn..." text).
    - Card rendering: Each card is a div with class `.card`. Show `name` in header, `cost` as a badge, `effects` as a list (format each effect: "damage fire 20", "heal 15", "shield 12", "dot poison 4 for 3 turns", "draw 1 card"), `description` in footer.

- [ ] Task 12: Implement inventory panel and item usage
  - File: `static/js/game.js`
  - Action: Add inventory functionality:
    - Request inventory on login: After receiving `room_state`, send `sendAction('inventory', {})`.
    - `handleInventory(data)`: Store items in `gameState.inventory`. Each item in `data.items` has these fields: `item_key` (string), `name` (string), `category` ("consumable" or "material"), `quantity` (int), `charges` (int), `description` (string). **Note**: The inventory response does NOT include `usable_in_combat` or `usable_outside_combat` flags — those exist on the server's `ItemDef` but are not serialized in the inventory payload. Therefore: show a "Use" button on all `category === "consumable"` items and let the server reject invalid uses with an error message. Material items (`category === "material"`) have no use action.
    - Render inventory panel in left sidebar. Each item shows name, quantity, and a "Use" button (for consumables only).
    - Wire use button: `sendAction('use_item', {item_key})`.
    - `handleItemUsed(data)`: Format feedback from `data.effect_results` — iterate the list and format each by `type`: heal → "Healed {value} HP (HP: {target_hp})", damage → "Dealt {value} damage", shield → "Gained {value} shield (total: {total_shield})", dot → "Applied {subtype} for {value} over {duration} turns", draw → "Drew {value} card(s)". Display as: "Used {data.item_name}: {formatted effects}". Re-request inventory to get updated quantities: `sendAction('inventory', {})`. Apply heal/damage animation if relevant.
    - Combat inventory: When in combat, show all consumable items from `gameState.inventory` in the combat overlay (since we can't distinguish combat-usable from non-combat-usable — the server will reject invalid ones). Wire to `sendAction('use_item_combat', {item_key})`.

- [ ] Task 13: Implement object interaction
  - File: `static/js/game.js`
  - Action: Add interaction:
    - Interactive objects (category === "interactive") on the tile grid should be visually clickable. When clicked, send `sendAction('interact', {target_id: object.id})`.
    - `handleInteractResult(data)`: `data.object_id` is the target's ID, `data.result` is an object whose shape depends on the object type:
      - **Chest**: `{status: "looted", items: [{item_key, quantity}, ...]}` on success, or `{status: "already_looted", message: "Already looted"}` if already opened. On success, display "Opened chest — received [item names]" and re-request inventory (`sendAction('inventory', {})`).
      - **Lever**: `{status: "toggled", active: bool, target_x: int, target_y: int}` on success, or `{status: "error", message: string}` on failure. On success, display "Pulled lever — [active/deactivated]". Note: levers also trigger a separate `tile_changed` broadcast (see below).
    - Show result in message log and as a brief notification.
    - `handleTileChanged(data)`: Update `gameState.room.tiles[data.y][data.x] = data.tile_type`. Find the tile div at grid position (x, y) and update its CSS class to reflect the new tile type (e.g., wall → floor or floor → wall). This is broadcast to ALL players in the room when a lever is toggled.
    - Proximity check (optional client-side): Only allow interaction if player is adjacent to the object (within 1 tile). The server validates this too, but client-side check avoids unnecessary error messages.

- [ ] Task 14: Implement stats display and HP bars
  - File: `static/js/game.js`
  - Action: Add stats rendering:
    - Left panel shows: Player name, current position (x, y), current room name. HP bar and shield are only shown when available (see below).
    - **Stats source chain**: `PlayerEntity.stats` is an empty dict by default — new players have no HP/max_hp until combat starts. The server applies defaults (`hp=100, max_hp=100, attack=10, shield=0`) locally in the movement handler at mob encounter time (never persisted to DB). These defaults feed into `combat_start`'s `participants` array. Therefore:
      - **Outside combat (no prior combat)**: No HP data exists. Show "No combat stats" or hide the HP bar section entirely.
      - **During combat**: Read HP/shield from `gameState.combat.participants` — find the entry where `entity_id === gameState.player.id`. This is the canonical source during combat.
      - **After combat**: The combat instance is destroyed. `entity.stats` remains empty (combat used a local copy). HP bar reverts to hidden/"No combat stats". This is correct — the server re-defaults to 100 HP on next combat encounter.
    - `updateStatsPanel()`: Called after login, room transitions, combat updates, and item usage. Reads player identity from `gameState.player`, room info from `gameState.room`, and combat HP from `gameState.combat.participants` when in combat mode.
    - HP bar component: `renderHPBar(current, max, containerEl)` — creates a filled bar div inside a track. Width = (current/max * 100)%. Color: green (#44aa44) if > 50%, yellow (#aaaa44) if 25-50%, red (#aa4444) if < 25%.

- [ ] Task 15: Implement server message log
  - File: `static/js/game.js`
  - Action: Add debug message log:
    - Collapsible panel in right sidebar below chat.
    - Toggle button: "Message Log" header that expands/collapses.
    - Every message received from server is logged with timestamp and formatted JSON.
    - Every message sent to server is also logged (prefixed with "SENT:").
    - Auto-scroll to bottom. Limit to last 200 messages to prevent memory growth.
    - Style: Small monospace font, dark background, color-coded by message type (errors in red, combat in orange, chat in white, system in gray).

### Acceptance Criteria

- [ ] AC 1: Given the server is running, when a user navigates to `http://localhost:8000/`, then the test client page loads with the auth screen showing register and login forms.

- [ ] AC 2: Given the auth screen is showing, when a user fills in username (3+ chars) and password (6+ chars) and clicks Register, then a `register` action is sent via WebSocket, the server responds with `login_success` (account created), the client automatically sends a `login` action with the same credentials, the server responds with `login_success` + `room_state`, and the UI switches to the game screen. The user sees a brief "Account created! Logging in..." message during the auto-login.

- [ ] AC 3: Given a registered account exists, when a user fills in credentials and clicks Login, then a `login` action is sent, the server responds with `login_success` followed by `room_state`, and the UI switches from auth screen to game screen showing the tile grid.

- [ ] AC 4: Given the game screen is showing with a 100x100 room, when the room renders, then a 25x25 tile viewport is visible centered on the player's position with color-coded tiles (floor, wall, exit, water) and entity icons (players, NPCs, objects).

- [ ] AC 5: Given the player is in explore mode, when the user presses arrow keys or WASD, then a `move` action is sent with the correct direction and the viewport smoothly scrolls to stay centered on the player's new position.

- [ ] AC 6: Given the player is in explore mode and the chat input is focused, when the user presses WASD or arrow keys, then no movement action is sent (keys are captured by the chat input instead).

- [ ] AC 7: Given two players are logged in to the same room (in separate browser tabs), when Player A moves, then Player B's viewport shows Player A's entity icon update to the new position.

- [ ] AC 8: Given two players are in the same room, when Player A sends a chat message, then both players see the message appear in their chat log with Player A's name as sender.

- [ ] AC 9: Given two players are in the same room, when Player A sends a whisper to Player B, then only Player A and Player B see the message, styled as a whisper (italic, purple).

- [ ] AC 10: Given the player walks onto an exit tile, when the server responds with a new `room_state`, then the viewport re-renders with the new room's tiles, entities, and objects, and the room name updates in the stats panel.

- [ ] AC 11: Given the player moves adjacent to a hostile alive NPC, when combat initiates, then the UI switches to combat mode showing: mob name and HP bar, player HP and shield, a hand of styled card elements (showing name, cost, effects, description), and Pass Turn/Flee buttons.

- [ ] AC 12: Given the player is in combat, when the player clicks a card, then a `play_card` action is sent and the combat UI updates with the result (HP changes, shield changes, hand updates, action description).

- [ ] AC 13: Given the player is in combat, when the player clicks Flee, then a `flee` action is sent, combat mode exits, and the player returns to explore mode.

- [ ] AC 14: Given combat ends (mob HP reaches 0), when the server sends `combat_end`, then the combat overlay shows victory/rewards and after a brief pause the UI returns to explore mode.

- [ ] AC 15: Given the player is in explore mode, when the user clicks an interactive object (chest, lever) on the map, then an `interact` action is sent and the result is displayed in the message log.

- [ ] AC 16: Given the player has consumable items, when the inventory panel shows the items with "Use" buttons, then clicking "Use" sends a `use_item` action and the inventory updates after use.

- [ ] AC 17: Given the player is in combat with usable items, when the combat overlay shows combat inventory items, then clicking "Use" sends a `use_item_combat` action and the combat state updates.

- [ ] AC 18: Given any server message is received, when it arrives, then it is logged in the server message log panel with timestamp and formatted content.

- [ ] AC 19: Given a rare NPC spawns, when the server sends an `announcement`, then all connected tabs display the announcement prominently in the chat log.

- [ ] AC 20: Given two separate browser tabs are open, when each tab registers a different account and logs in, then each tab maintains its own independent game state. **Test steps:** (1) Open Tab A, register user "alpha", login → verify game screen shows town_square. (2) Open Tab B, register user "beta", login → verify game screen shows town_square and Tab A shows "beta" as a second entity. (3) In Tab A, move north → verify Tab A viewport updates, Tab B shows alpha's entity move, Tab B's own player position is unchanged. (4) In Tab B, send chat message → verify Tab B sees its own message, Tab A sees the message. (5) Close Tab B → verify Tab A continues to function, Tab A sees entity_left for beta. No localStorage, sessionStorage, or cookies are used — refresh any tab and it returns to the auth screen.

- [ ] AC 21: Given all 4 rooms are connected in a circular loop, when the player traverses exits from town_square → test_room → other_room → dark_cave → town_square, then each room transition loads the correct room with proper entry coordinates and the full loop returns to the starting room.

## Additional Context

### Dependencies

- **Python package**: No new Python dependencies. `FastAPI` already includes `StaticFiles` via Starlette.
- **Client-side**: Zero dependencies. Vanilla HTML/CSS/JS only. No build tools, no npm, no bundler.
- **Runtime**: Server must be running (`python run.py`) for the test client to connect.

### Testing Strategy

- **Existing server tests to update**: Changing the default room from `test_room` to `town_square` in auth.py will break two test assertions:
  - `tests/test_login.py` line 215: `assert room_resp["room_key"] == "test_room"` → change to `"town_square"`
  - `tests/test_integration.py` line 165: `assert room_resp["room_key"] == "test_room"` → change to `"town_square"`
  - Run `pytest tests/` after Task 2 to verify no other tests break.
- **No automated client tests**: This is a test/demo tool itself. Validation is done by using it.
- **Manual test checklist**:
  1. Start server, navigate to `http://localhost:8000/` — page loads
  2. Register a new account — success message
  3. Login — game screen appears with town_square
  4. Move with WASD/arrows — player moves, viewport scrolls
  5. Open second tab, register/login as different user — see first player on grid
  6. Chat between tabs — messages appear in both
  7. Whisper — only sender and target see it
  8. Walk to NPC — combat starts
  9. Play cards — combat updates
  10. Win or flee — return to explore mode
  11. Click chest — interact result shown
  12. Use item from inventory — feedback shown
  13. Walk to exit tile — room transition occurs
  14. Check message log — all server messages visible

### Notes

- Default player room changed from `test_room` to `town_square` so new players immediately see the full 100x100 room experience.
- All 4 rooms connected in a circular loop: town_square ↔ test_room ↔ other_room ↔ dark_cave ↔ town_square. Each room has 2 exits.
- The room_state payload for 100x100 rooms is ~50KB (one-time load per room transition). The client builds the tile grid DOM once on room_state, then only updates specific tile divs for entity movement — does not rebuild the grid.
- Whisper target is an entity_id (e.g., "player_2"), not a username. The chat panel includes a dropdown populated from the current room's entity list.
- Combat is entered automatically when the player moves adjacent to a hostile alive NPC. The server initiates combat — there is no explicit "attack" action from the client.
- **Room events during combat**: While the combat overlay is shown, the server may still send `entity_moved`, `entity_entered`, `entity_left`, and `chat` messages for other players in the room. The client should continue updating `gameState.room` state in memory (so the data stays current) but should NOT re-render the tile grid while in combat mode. When combat ends and the UI switches back to explore mode, call `renderRoom()` once to reflect any changes that occurred during combat.
- Movement keys (WASD/arrows) are only active in explore mode and when chat input is not focused. During combat, movement is blocked server-side but the client also prevents sending unnecessary move requests.
- The tile grid renders the full 100x100 room in the DOM but only a 25x25 viewport is visible. The grid is positioned using CSS transform to center on the player. This approach was chosen over rendering only visible tiles because the grid is static (tiles don't change) and 10,000 simple divs with background colors are lightweight enough. **Performance note:** 10,000 DOM nodes is within acceptable limits for modern browsers (Chrome/Firefox handle 50K+ nodes), but if noticeable lag occurs on initial render, a fallback strategy is available: render only the visible 25x25 viewport + 5-tile buffer (35x35 = 1,225 tiles) and re-render on each move. This is not implemented initially because full-grid rendering is simpler and the expected performance is adequate for a test/demo tool.
- JavaScript uses JSDoc type annotations with `// @ts-check` for type safety without a build step. Key data shapes (GameState, PlayerState, RoomState, CombatState, CardDef, Entity) are defined as `@typedef` at the top of `game.js`.
- **Duplicate login (same account, two tabs)**: The server has no duplicate-login protection. If the same account logs in from two tabs, the second login silently overwrites the first tab's WebSocket connection and entity in all server-side maps. The first tab becomes a ghost — it stops receiving messages but doesn't know it's disconnected (no `onclose` fires because the server didn't close the socket, it just stopped sending to it). This is a known server limitation. The client does not need to handle this case — just document it in the manual test checklist as a known issue to avoid during testing.
