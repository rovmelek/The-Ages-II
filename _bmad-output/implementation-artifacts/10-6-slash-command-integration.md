# Story 10.6: Slash Command Integration

Status: done

## Story

As a player,
I want all game actions available as slash commands in the chat input,
so that every mechanic is accessible via text commands for engine-agnostic testing.

## Acceptance Criteria

1. **Given** the slash command parser from Story 10.3 exists (with 7 commands already registered: `help`, `logout`, `whisper`, `inventory`, `use`, `flee`, `pass`), **When** the story is complete, **Then** the following 4 new commands are added to the `COMMANDS` registry, completing the full command set required by the epics AC (plus the existing client-local `/help`):

   | Command | Server Action | Behavior |
   |---------|--------------|----------|
   | `/interact <direction>` | `interact` with `direction` | Interacts with adjacent object |
   | `/look` | `look` | Shows nearby objects, NPCs, players |
   | `/who` | `who` | Lists players in room |
   | `/stats` | `stats` | Shows player stats |

2. **Given** the player types `/interact right`, **When** the parser processes it, **Then** it sends `{"action": "interact", "direction": "right"}`.

3. **Given** the player types `/interact` with no direction argument, **When** the parser processes it, **Then** the player sees a local usage hint: "Usage: /interact <direction>".

4. **Given** the player types `/look`, **When** the parser processes it, **Then** it sends `{"action": "look"}` and the server response (`look_result`) is displayed in the chat log showing nearby objects, NPCs, and players.

5. **Given** the player types `/who`, **When** the parser processes it, **Then** it sends `{"action": "who"}` and the server response (`who_result`) is displayed in the chat log listing players in the room.

6. **Given** the player types `/stats`, **When** the parser processes it, **Then** it sends `{"action": "stats"}` and the server response (`stats_result`) is displayed in the chat log showing HP, max_hp, attack, and XP.

7. **Given** the web client receives a `look_result` message, **When** the UI updates, **Then** the chat log shows formatted results: objects listed with type and direction, NPCs with name, alive/dead status and direction, players with name and direction. Empty categories are omitted.

8. **Given** the web client receives a `who_result` message, **When** the UI updates, **Then** the chat log shows the room name header and each player name with coordinates.

9. **Given** the web client receives a `stats_result` message, **When** the UI updates, **Then** the chat log shows HP (current/max), attack, and XP values.

10. **Given** the web client receives a `help_result` message (from the server's `help_actions` action — no slash command triggers this; it's a dispatch handler for forward compatibility), **When** the UI updates, **Then** the chat log shows the list of available server actions.

11. **And** `/help` output includes all newly registered commands (automatic — `/help` iterates the `COMMANDS` registry).

12. **And** existing commands (`help`, `logout`, `whisper`, `inventory`, `use`, `flee`, `pass`) remain unchanged. Note: the epics AC shows `/whisper` sending `"whisper_to": "alice"` (raw name), but the existing 10.3 implementation correctly resolves the name to an entity_id (e.g., `player_5`) because the server expects an entity_id. Do NOT change the whisper handler to match the literal epics AC example.

13. **And** `pytest tests/` passes with zero failures (no server changes in this story).

## Tasks / Subtasks

- [x] Task 1: Add `/interact` command to `COMMANDS` registry (AC: #1, #2, #3)
  - [x] 1.1: In `web-demo/js/game.js`, add `interact` entry to `COMMANDS` object
  - [x] 1.2: Handler validates args — if no args, show "Usage: /interact <direction>" via `appendChat('Usage: /interact <direction>', 'system')`
  - [x] 1.3: If args provided, send `sendAction('interact', { direction: args[0] })` — use first arg only (direction is a single word: up/down/left/right)
  - [x] 1.4: Set description: "Interact with adjacent object", usage: "/interact <direction>"

- [x] Task 2: Add `/look` command (AC: #1, #4)
  - [x] 2.1: Add `look` entry to `COMMANDS` with handler: `() => sendAction('look')`
  - [x] 2.2: Set description: "Look at nearby surroundings", usage: "/look"

- [x] Task 3: Add `/who` command (AC: #1, #5)
  - [x] 3.1: Add `who` entry to `COMMANDS` with handler: `() => sendAction('who')`
  - [x] 3.2: Set description: "List players in room", usage: "/who"

- [x] Task 4: Add `/stats` command (AC: #1, #6)
  - [x] 4.1: Add `stats` entry to `COMMANDS` with handler: `() => sendAction('stats')`
  - [x] 4.2: Set description: "Show your stats", usage: "/stats"

- [x] Task 5: Add `look_result` message handler (AC: #7)
  - [x] 5.1: Create `handleLookResult(data)` function in `game.js`
  - [x] 5.2: Format objects: show "type to the direction" for each, comma-separated on one line. Handle "here" direction specially — use "(here)" not "to the here". Skip section if array is empty
  - [x] 5.3: Format NPCs: show each NPC as "name (alive/dead) direction-label". Skip section if array is empty
  - [x] 5.4: Format players: show each player as "name direction-label". Skip section if array is empty
  - [x] 5.5: If all three arrays are empty, show "Nothing nearby."
  - [x] 5.6: Register `look_result: handleLookResult` in the `dispatchMessage` handlers table

- [x] Task 6: Add `who_result` message handler (AC: #8)
  - [x] 6.1: Create `handleWhoResult(data)` function
  - [x] 6.2: Show header: `appendChat("Players in {room}:", 'system')` using `data.room`
  - [x] 6.3: Guard with `data.players?.length`, then show each player: `appendChat("  {name} at ({x}, {y})", 'system')`
  - [x] 6.4: Register `who_result: handleWhoResult` in dispatch table

- [x] Task 7: Add `stats_result` message handler (AC: #9)
  - [x] 7.1: Create `handleStatsResult(data)` function
  - [x] 7.2: Show: `appendChat("HP: {hp}/{max_hp} | ATK: {attack} | XP: {xp}", 'system')` using `data.stats`
  - [x] 7.3: Register `stats_result: handleStatsResult` in dispatch table

- [x] Task 8: Add `help_result` message handler (AC: #10)
  - [x] 8.1: Create `handleHelpResult(data)` function
  - [x] 8.2: Show header: `appendChat("Server actions:", 'system')` then guard with `data.actions?.length` before listing: `appendChat("  " + data.actions.join(", "), 'system')`
  - [x] 8.3: Register `help_result: handleHelpResult` in dispatch table

- [x] Task 9: Verify no regressions (AC: #12, #13)
  - [x] 9.1: Run `pytest tests/` — 518 passed, 2 pre-existing failures (TestChestInteraction DB issues), 2 deselected (known hangers). Zero new failures
  - [x] 9.2: Verify existing commands still present and unchanged in `COMMANDS` registry

## Dev Notes

### This Story is Client-Side Only

No server code changes. No new server actions. No new Python files. No pytest tests to write. All changes are in `web-demo/js/game.js` only.

The server-side handlers (`look`, `who`, `stats`, `help_actions`) were implemented in Story 10.4. The directional `interact` handler was implemented in Story 10.5. This story only wires the client-side slash commands and display handlers.

### Where to Add Commands in `COMMANDS` Registry

The `COMMANDS` object is at `web-demo/js/game.js` lines 140-201. Add new entries after the existing `pass` entry (line 199). Maintain alphabetical-ish order is NOT required — the existing commands are in a logical grouping. Add new commands at the end of the object before the closing brace.

### Command Implementations

**`/interact <direction>`:**
```javascript
interact: {
  handler: (args) => {
    if (!args.length) {
      appendChat('Usage: /interact <direction>', 'system');
      return;
    }
    sendAction('interact', { direction: args[0] });
  },
  description: 'Interact with adjacent object',
  usage: '/interact <direction>',
},
```
Note: direction validation (`up`, `down`, `left`, `right`) happens server-side in `handle_interact` (Story 10.5). The client just passes the arg through. The server returns `"Invalid direction: ..."` error if invalid.

**`/look`, `/who`, `/stats`:**
```javascript
look: {
  handler: () => sendAction('look'),
  description: 'Look at nearby surroundings',
  usage: '/look',
},
who: {
  handler: () => sendAction('who'),
  description: 'List players in room',
  usage: '/who',
},
stats: {
  handler: () => sendAction('stats'),
  description: 'Show your stats',
  usage: '/stats',
},
```

### Server Response Display Handlers

These handlers display the results of query commands. Add them in the functions section of `game.js` (after `handleNearbyObjects` at ~line 781, before `appendChat` at ~line 787).

**`handleLookResult`:**

Note: the server's `handle_look` uses `"here"` as the direction label for the player's own tile. Format "here" items differently to avoid awkward "to the here" phrasing — use "(here)" instead of "to the here".

```javascript
function handleLookResult(data) {
  const dirLabel = (d) => d === 'here' ? '(here)' : `to the ${d}`;
  if (data.objects?.length) {
    appendChat('Objects: ' + data.objects.map(o => `${o.type} ${dirLabel(o.direction)}`).join(', '), 'system');
  }
  if (data.npcs?.length) {
    appendChat('NPCs: ' + data.npcs.map(n => `${n.name} (${n.alive ? 'alive' : 'dead'}) ${dirLabel(n.direction)}`).join(', '), 'system');
  }
  if (data.players?.length) {
    appendChat('Players: ' + data.players.map(p => `${p.name} ${dirLabel(p.direction)}`).join(', '), 'system');
  }
  if (!data.objects?.length && !data.npcs?.length && !data.players?.length) {
    appendChat('Nothing nearby.', 'system');
  }
}
```

**`handleWhoResult`:**
```javascript
function handleWhoResult(data) {
  appendChat(`Players in ${data.room}:`, 'system');
  if (data.players?.length) {
    for (const p of data.players) {
      appendChat(`  ${p.name} at (${p.x}, ${p.y})`, 'system');
    }
  }
}
```

**`handleStatsResult`:**
```javascript
function handleStatsResult(data) {
  const s = data.stats;
  if (!s) return;
  appendChat(`HP: ${s.hp}/${s.max_hp} | ATK: ${s.attack} | XP: ${s.xp}`, 'system');
}
```

**`handleHelpResult`:**
```javascript
function handleHelpResult(data) {
  appendChat('Server actions:', 'system');
  if (data.actions?.length) {
    appendChat('  ' + data.actions.join(', '), 'system');
  }
}
```

### Dispatch Table Registration

Add 4 entries to the `handlers` object in `dispatchMessage()` (line 368-391):
```javascript
look_result: handleLookResult,
who_result: handleWhoResult,
stats_result: handleStatsResult,
help_result: handleHelpResult,
```

Insert after `nearby_objects: handleNearbyObjects` (line 385) and before `logged_out: handleLoggedOut` (line 386).

### Commands NOT Part of This Story

- `/logout`, `/whisper`, `/inventory`, `/use`, `/flee`, `/pass`, `/help` — already exist from Story 10.3. Do NOT modify them.
- No `/help_actions` client command is needed — the server action `help_actions` exists but the client `/help` command (local display of `COMMANDS` registry) already serves this purpose.

### What NOT to Do

- Do NOT modify any server files — this is purely client-side
- Do NOT modify `parseCommand()` — it already handles dispatch via the `COMMANDS` registry
- Do NOT change existing command handlers — they are working correctly
- Do NOT add a `/help_actions` slash command — the client `/help` already covers this. The `help_result` dispatch handler is added for completeness in case future code sends `help_actions` to the server, but no slash command triggers it
- Do NOT validate direction strings client-side — the server does validation and returns clear errors
- Do NOT add new CSS — the existing `.chat-system` class from Story 10.3 handles all system message styling

### Previous Story Learnings

- **From 10.3:** `COMMANDS` registry pattern — each entry has `handler`, `description`, `usage`. The `parseCommand()` function extracts command name (case-insensitive) and args array, then calls `cmd.handler(args)`. Handler references to `sendAction()` and `appendChat()` work because they're closures invoked at call-time.
- **From 10.4:** Server query handlers return `look_result`, `who_result`, `stats_result`, `help_result` message types. `look_result` has `objects`, `npcs`, `players` arrays. `who_result` has `room` and `players`. `stats_result` has `stats` object with `hp`, `max_hp`, `attack`, `xp`. `help_result` has `actions` array.
- **From 10.5:** Server `handle_interact` accepts `direction` field. Direction values are grid directions: `up`, `down`, `left`, `right`. Invalid directions return `"Invalid direction: ..."` error from server.
- **From 10.5:** `dispatchMessage` handlers table is an object literal inside the function — add entries there, NOT as a module-level map.

### Error Handling Already Exists

The `dispatchMessage` table already has `error: handleError` which displays `{"type": "error", "detail": "..."}` messages in the chat log. When a command triggers a server error (e.g., `/interact east` → "Invalid direction: east", or `/stats` when not logged in → "Not logged in"), the server returns an error message type that is already handled. No new error handling code is needed.

### Epics AC Note

The epics file AC says `/interact east` should send `"direction": "east"`. However, the server (Story 10.5) only accepts `up`, `down`, `left`, `right` — NOT compass directions. The client should pass the arg through as-is and let the server validate. If a player types `/interact east`, the server will return "Invalid direction: east". This is correct behavior.

### Project Structure Notes

- Modified: `web-demo/js/game.js` — 4 new COMMANDS entries + 4 new message handlers + 4 dispatch table entries
- No other files modified
- No server files changed
- No test files changed

### References

- [Source: web-demo/js/game.js#COMMANDS] — existing command registry (~line 140)
- [Source: web-demo/js/game.js#dispatchMessage] — message dispatch table (~line 367)
- [Source: web-demo/js/game.js#handleNearbyObjects] — nearby handler pattern reference (~line 775)
- [Source: web-demo/js/game.js#appendChat] — chat display helper (~line 787)
- [Source: web-demo/js/game.js#sendAction] — WebSocket action sender (~line 355)
- [Source: web-demo/js/game.js#handleError] — existing error display handler (already in dispatch table)
- [Source: _bmad-output/implementation-artifacts/10-3-slash-command-parser.md] — parser architecture
- [Source: _bmad-output/implementation-artifacts/10-4-server-query-actions.md] — server query response formats
- [Source: _bmad-output/implementation-artifacts/10-5-directional-object-interaction.md] — directional interact handler
- [Source: _bmad-output/planning-artifacts/epics.md#Story 10.6] — acceptance criteria

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- pytest runs via `.venv/bin/pytest` (system python3 lacks pytest module)
- No issues encountered — straightforward client-side additions

### Completion Notes List

- Added 4 new commands to `COMMANDS` registry: `interact`, `look`, `who`, `stats` — completing the full set of 11 slash commands
- `/interact` validates args (shows usage hint if missing), passes direction to server without client-side validation
- `/look`, `/who`, `/stats` are simple `sendAction()` calls with no arguments
- Added 4 message handler functions: `handleLookResult`, `handleWhoResult`, `handleStatsResult`, `handleHelpResult`
- `handleLookResult` uses `dirLabel()` helper to handle "here" direction gracefully — "(here)" instead of "to the here"
- All handlers use optional chaining (`?.length`) for defensive guards against missing/empty data
- `handleStatsResult` guards against missing `data.stats` with early return
- Registered all 4 handlers in `dispatchMessage()` handlers table
- 518 tests pass, 2 pre-existing failures (TestChestInteraction DB issues), 2 deselected (known hangers) — zero new failures

### Change Log

- 2026-04-10: Story 10.6 implemented — slash command integration (4 new commands + 4 message handlers)

### File List

- web-demo/js/game.js (modified — 4 new COMMANDS entries, 4 new handler functions, 4 dispatch table entries)
