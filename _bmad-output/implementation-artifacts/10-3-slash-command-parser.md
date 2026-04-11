# Story 10.3: Slash Command Parser

Status: done

## Story

As a player,
I want to type `/commands` in the chat input to perform game actions,
so that I have an engine-agnostic way to access all game mechanics beyond clicking UI buttons.

## Acceptance Criteria

1. **Given** the web client chat input exists, **When** the player types a message starting with `/`, **Then** the message is intercepted by a client-side command parser before being sent as chat, and the parser extracts the command name and arguments.

2. **Given** the player types `/help`, **When** the parser processes it, **Then** a help message is displayed locally listing all available commands with brief descriptions, and no message is sent to the server (client-side only).

3. **Given** the player types an unknown command like `/foobar`, **When** the parser processes it, **Then** the player sees a local error: "Unknown command: /foobar. Type /help for available commands." and no message is sent to the server.

4. **Given** the player types a regular chat message (no `/` prefix), **When** the input is processed, **Then** it is sent as a normal chat message (existing behavior unchanged).

5. **Given** the parser exists, **When** the story is complete, **Then** the parser is extensible — adding a new command requires adding one entry to a command registry object, and the parser handles: command name extraction, argument splitting, command dispatch.

## Tasks / Subtasks

- [x] Task 1: Create command registry and parser (AC: #1, #5)
  - [x] 1.1: In `web-demo/js/game.js`, create a `COMMANDS` registry object mapping command names to `{handler, description, usage}` entries
  - [x] 1.2: Create `parseCommand(input)` function that: checks for `/` prefix, splits command name from args, looks up in `COMMANDS` registry, dispatches to handler or shows unknown command error
  - [x] 1.3: The parser must return `true` if the input was a command (consumed), `false` if it was a regular chat message
  - [x] 1.4: Handle empty command edge case — typing just `/` alone should show "Type /help for available commands." (not "Unknown command: /")

- [x] Task 2: Implement `/help` command (AC: #2)
  - [x] 2.1: Register a `help` entry in `COMMANDS` with handler that iterates the registry and builds a formatted help message
  - [x] 2.2: Display the help output via `appendChat()` — call once per command line (e.g., `appendChat("  /help — Show available commands", "system")`) since `appendChat` creates one `<div>` per call and `textContent` does not render line breaks. Add a header line first: `appendChat("Available commands:", "system")`

- [x] Task 3: Handle unknown commands (AC: #3)
  - [x] 3.1: In `parseCommand()`, if the command name is not in `COMMANDS`, call `appendChat()` with "Unknown command: /foobar. Type /help for available commands."
  - [x] 3.2: Return `true` (consumed) so the unknown command is NOT sent as chat

- [x] Task 4: Integrate parser into `sendChat()` (AC: #1, #4)
  - [x] 4.1: In `sendChat()` (line ~692), keep the existing input-clearing pattern (clear at the END, not before parseCommand). After trimming, call `parseCommand(msg)`. If it returns `true`, clear input and return early. The `$chatInput.value = ''` must happen after `parseCommand` returns, matching the existing pattern where input is cleared at the bottom of the function
  - [x] 4.2: Remove the existing hardcoded `/logout` check (lines 696-699) and migrate it into the `COMMANDS` registry as a `logout` entry with the same handler logic (`sendAction("logout", {})`)
  - [x] 4.3: Verify that regular chat messages (no `/` prefix) still flow through to the existing chat send path unchanged

- [x] Task 5: Register initial commands (AC: #5)
  - [x] 5.1: Register these commands in the `COMMANDS` registry (handlers will be stubs or fully implemented where trivial):
    - `help` — local help display (implemented in Task 2)
    - `logout` — sends `logout` action (migrated from existing code)
    - `whisper` — `/whisper <name> message` — resolves player name to entity_id via `gameState.room.entities`, then sends `sendAction('chat', { message, whisper_to: entityId })`. The `@` prefix on the name is optional (strip if present). Show local error if player not found or missing args
    - `inventory` — sends `inventory` action
    - `use` — `/use <item_key>` — sends `sendAction('use_item', { item_key: args.join(' ') })`. **Note**: the server field is `item_key` (not `item_name`) — see `server/net/handlers/inventory.py` line 63
    - `flee` — sends `flee` action (only valid in combat)
    - `pass` — sends `pass_turn` action (only valid in combat)
  - [x] 5.2: Commands that depend on future stories (10.4: `look`, `who`, `stats`; 10.5: `interact`) — **omit** from this story. Story 10.6 ("Slash Command Integration") will add all remaining commands to this parser.

- [x] Task 6: Add `.chat-system` CSS class (AC: #2, #3)
  - [x] 6.1: In `web-demo/css/style.css`, add a `.chat-system` rule for system messages (e.g., italic, muted/gray color) — `appendChat` applies class `chat-${type}` so passing `type="system"` produces class `chat-system`

- [x] Task 7: Tests — manual verification (AC: all)
  - [x] 7.1: No pytest tests needed — this is purely client-side JavaScript with no server changes
  - [x] 7.2: Verify `pytest tests/` still passes (no server code changed)
  - [x] 7.3: Manual test plan:
    - `/help` — displays formatted command list locally
    - `/foobar` — shows "Unknown command" error locally
    - `/logout` — sends logout action (same behavior as before)
    - `/whisper playername hi` — sends whisper (verify with/without `@` prefix)
    - `/inventory` — sends inventory action
    - `/use health_potion` — sends use_item with item_key
    - `/flee` outside combat — server returns error (expected)
    - `/pass` outside combat — server returns error (expected)
    - `/` alone — shows help hint, not "Unknown command: /"
    - `/HELP` — case-insensitive, shows help
    - Regular chat message — sent as normal chat (no interception)
    - Whisper via dropdown — still works (existing behavior preserved)

## Dev Notes

### Architecture — Client-Side Only

This story is **entirely client-side** (`web-demo/js/game.js`). No server code changes. No new server actions. No pytest tests to write for the parser itself.

The web client is vanilla HTML/CSS/JS — no bundler, no npm, no modules. Everything is in a single `game.js` file with global scope.

### Where to Add the Code

**Command registry and parser** — add near the top of game.js after the DOM references section (~line 135), before `connectWebSocket()`. Note: handlers reference `sendAction()` (line 262) and `appendChat()` (line 684), both defined later in the file — this is safe because handlers are closures invoked at call time, not at definition time. Do NOT move `COMMANDS` after these functions or reorganize sections.

```javascript
/** @type {Object<string, {handler: function(string[]): void, description: string, usage: string}>} */
const COMMANDS = {
  help: {
    handler: () => {
      appendChat('Available commands:', 'system');
      for (const [name, cmd] of Object.entries(COMMANDS)) {
        appendChat(`  ${cmd.usage} — ${cmd.description}`, 'system');
      }
    },
    description: 'Show available commands',
    usage: '/help',
  },
  logout: {
    handler: () => sendAction('logout', {}),
    description: 'Log out and return to login screen',
    usage: '/logout',
  },
  whisper: {
    handler: (args) => {
      if (args.length < 2) {
        appendChat('Usage: /whisper <name> <message>', 'system');
        return;
      }
      const targetName = args[0].replace(/^@/, '');
      const message = args.slice(1).join(' ');
      // Resolve name to entity_id from room entities
      const target = gameState.room?.entities?.find(
        (e) => e.name.toLowerCase() === targetName.toLowerCase()
      );
      if (!target) {
        appendChat(`Player "${targetName}" not found in this room.`, 'system');
        return;
      }
      sendAction('chat', { message, whisper_to: target.id });
    },
    description: 'Send a private message',
    usage: '/whisper <name> <message>',
  },
  inventory: {
    handler: () => sendAction('inventory'),
    description: 'Show your inventory',
    usage: '/inventory',
  },
  use: {
    handler: (args) => {
      if (!args.length) {
        appendChat('Usage: /use <item_key>', 'system');
        return;
      }
      sendAction('use_item', { item_key: args.join(' ') });
    },
    description: 'Use an item',
    usage: '/use <item_key>',
  },
  flee: {
    handler: () => sendAction('flee'),
    description: 'Flee from combat',
    usage: '/flee',
  },
  pass: {
    handler: () => sendAction('pass_turn'),
    description: 'Pass your turn in combat',
    usage: '/pass',
  },
};

function parseCommand(input) {
  if (!input.startsWith('/')) return false;
  const trimmed = input.slice(1).trim();
  if (!trimmed) {
    appendChat('Type /help for available commands.', 'system');
    return true;
  }
  const parts = trimmed.split(/\s+/);
  const cmdName = parts[0].toLowerCase();
  const args = parts.slice(1);
  const cmd = COMMANDS[cmdName];
  if (!cmd) {
    appendChat(`Unknown command: /${cmdName}. Type /help for available commands.`, 'system');
    return true;
  }
  cmd.handler(args);
  return true;
}
```

### Modifying `sendChat()` (line ~692)

Current code (lines 692-708) has a hardcoded `/logout` check and clears input at the END (line 707). Preserve that pattern — clear input after all logic, not before:

```javascript
function sendChat() {
  const msg = $chatInput.value.trim();
  if (!msg) return;

  // NEW: Command parser intercept (replaces old /logout check)
  if (parseCommand(msg)) {
    $chatInput.value = '';
    return;
  }

  // Existing chat send logic (whisper dropdown or room chat)
  const target = $whisperTarget.value;
  if (target) {
    sendAction('chat', { message: msg, whisper_to: target });
  } else {
    sendAction('chat', { message: msg });
  }
  $chatInput.value = '';
}
```

### `appendChat()` — Already Supports Styling

The existing `appendChat(text, type)` at line 684 already accepts a `type` parameter and applies CSS class `chat-${type}`. For system messages, pass `'system'` as the type — e.g., `appendChat("message", "system")` applies class `chat-system`. **Do NOT modify the `appendChat()` function signature** — it already works.

Add a `.chat-system` CSS rule in `web-demo/css/style.css` for visual distinction (e.g., italic, muted/gray color).

### `/whisper` Command — Name Resolution

The whisper command handles: `/whisper playername some message here` (or `/whisper @playername ...`)
- `args[0]` is the target name — strip `@` prefix if present (optional)
- `args.slice(1).join(' ')` is the message body
- If no target or no message, show usage error locally
- **Critical**: The server's `whisper_to` field expects an `entity_id` (e.g., `player_5`), NOT a player name. The command must resolve the name to entity_id by searching `gameState.room.entities` for a matching `name` field. Show local error "Player not found in this room" if no match. The existing whisper dropdown already works this way (it sends `entity_id` via `$whisperTarget.value`).

### Existing Patterns from Previous Stories

- `sendAction(action, data)` at line 262 — use this for all server-bound commands
- `appendChat(text)` at line 684 — use for local-only output
- The `/logout` handler at line 696 calls `sendAction('logout')` — migrate this exact logic
- `gameState.ws` is the WebSocket — `sendAction()` already guards `ws.readyState !== WebSocket.OPEN` (line 263), so commands don't need to recheck

### Previous Story Learnings (from 10.2)

- Interactive object adjacency check was added to interact handler — `/interact` will need to work with this in Story 10.5/10.6
- Test fixtures were updated for adjacency — no impact on this client-side story
- Manhattan distance model (4-directional) is established for direction resolution

### Commands NOT to Implement Yet

Story 10.4 adds server actions: `look`, `who`, `stats`, `help_actions`. Story 10.5 adds directional `interact`. Story 10.6 ("Slash Command Integration") will wire ALL remaining commands into this parser. This story builds the **extensible parser framework** — Story 10.6 plugs in the remaining commands.

### Project Structure Notes

- `web-demo/js/game.js` — command registry, parser function, sendChat modification
- `web-demo/css/style.css` — add `.chat-system` CSS rule for system message styling
- No server files modified
- No test files modified (verify `pytest tests/` still passes — no regressions from zero server changes)

### References

- [Source: web-demo/js/game.js#sendChat] — current chat send logic (lines 692-708)
- [Source: web-demo/js/game.js#appendChat] — chat display helper (lines 684-690)
- [Source: web-demo/js/game.js#sendAction] — WebSocket action sender (lines 262-267)
- [Source: web-demo/js/game.js#handleKeyDown] — keyboard guard for chat input (line 651)
- [Source: _bmad-output/planning-artifacts/epics.md#Story 10.3] — acceptance criteria
- [Source: _bmad-output/planning-artifacts/epics.md#Story 10.6] — slash command integration (future)

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Created extensible `COMMANDS` registry with 7 commands: help, logout, whisper, inventory, use, flee, pass
- Created `parseCommand()` function handling: `/` prefix detection, command name extraction (case-insensitive), argument splitting, dispatch, unknown command error, empty `/` edge case
- Migrated existing hardcoded `/logout` check from `sendChat()` into the registry
- `/whisper` resolves player name to entity_id via `gameState.room.entities` (server expects entity_id, not name)
- `/use` sends `item_key` field (verified against server handler)
- Added `.chat-system` CSS class for system message styling (italic, gray)
- Did NOT modify `appendChat()` — existing `type` parameter already supports this
- All 501 existing tests pass — zero regressions (no server code changed)
- Future stories (10.4, 10.5, 10.6) will add remaining commands to this parser

### Change Log

- 2026-04-10: Story 10.3 implemented — slash command parser with extensible registry

### File List

- web-demo/js/game.js (modified — added COMMANDS registry, parseCommand(), updated sendChat())
- web-demo/css/style.css (modified — added .chat-system rule)
