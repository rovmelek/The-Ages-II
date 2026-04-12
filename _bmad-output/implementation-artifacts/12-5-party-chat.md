# Story 12.5: Party Chat

Status: done

## Story

As a party member,
I want to send messages that only my party members can see regardless of what room they're in,
so that my party can coordinate across the game world.

## Acceptance Criteria

1. **Given** a player is in a party, **When** they send `/party Hey everyone, meet at dark_cave`, **Then** all party members receive a `party_chat` message with format `{type: "party_chat", from: "<sender_name>", message: "<text>"}`, **And** the message is delivered regardless of which room each member is in, **And** players NOT in the party do not receive the message.

2. **Given** a player is not in a party, **When** they send `/party Some message`, **Then** they receive an error: "You are not in a party".

3. **Given** a player sends a party chat message, **When** the server processes it, **Then** the sender's name is set server-side from the entity (no client impersonation possible), **And** the action is `party_chat` (dedicated action, not overloading existing `chat` action).

4. **Given** a party chat message exceeds `MAX_CHAT_MESSAGE_LENGTH` (default 500 characters), **When** the server processes it, **Then** the message is rejected: "Message too long (max 500 characters)".

5. **Given** a party has 4 members across 3 different rooms, **When** one member sends a party chat message, **Then** all 4 members (including sender) receive the message, **And** no other players in any of those rooms see the message.

6. **Given** a party member disconnects between message send and delivery, **When** the server iterates members to deliver, **Then** the send failure for the disconnected member is handled gracefully (no exception), **And** the message is delivered to all remaining connected members.

7. **Given** the web client receives a `party_chat` message, **When** the message is rendered in the chat log, **Then** it is visually distinct from room chat (e.g., prefixed with `[Party]` or color-coded).

8. **Given** Story 12.4's party handler receives an unrecognized subcommand from a player in a party, **When** Story 12.5 is implemented, **Then** the fallback routes to party chat instead of returning "Unknown party command".

## Tasks / Subtasks

- [x] Task 1: Add `MAX_CHAT_MESSAGE_LENGTH` config setting (AC: #4)
  - [x] 1.1: Add `MAX_CHAT_MESSAGE_LENGTH: int = 500` to `Settings` in `server/core/config.py` (after `PARTY_INVITE_COOLDOWN_SECONDS` on line 36)

- [x] Task 2: Add `party_chat` action handler (AC: #1, #2, #3, #4, #5, #6)
  - [x] 2.1: In `server/net/handlers/party.py`, add `handle_party_chat(websocket, data, *, game)` async function:
    - Get `entity_id` from `game.connection_manager.get_entity_id(websocket)` — error if None
    - Get `player_info` from `game.player_entities.get(entity_id)` — error if None
    - Extract message from `data.get("message", "").strip()` — ignore if empty
    - Validate length: `len(message) > settings.MAX_CHAT_MESSAGE_LENGTH` → error "Message too long (max 500 characters)"
    - Get party via `game.party_manager.get_party(entity_id)` — error if None: "You are not in a party"
    - Get sender name from `player_info["entity"].name` (server-side, no client impersonation)
    - Build message: `{"type": "party_chat", "from": sender_name, "message": message}`
    - Iterate `party.members`, send to each via `game.connection_manager.send_to_player(mid, msg)` — wrap each send in try/except to handle disconnected members gracefully (same pattern as `ConnectionManager.broadcast_to_room` at line 73-84 of `server/net/connection_manager.py`)

- [x] Task 3: Register `party_chat` action in message router (AC: #3)
  - [x] 3.1: In `server/app.py` `_register_handlers()`, import `handle_party_chat` from `server.net.handlers.party` (add to existing import on line 136)
  - [x] 3.2: Register: `self.router.register("party_chat", lambda ws, d: handle_party_chat(ws, d, game=self))` (after `party` registration on line 208)

- [x] Task 4: Update party handler fallback to route to party chat (AC: #8)
  - [x] 4.1: In `server/net/handlers/party.py`, modify the `else` branch of the subcommand dispatch in `handle_party()` (lines 154-160). Instead of returning "Unknown party command", check if the sender is in a party via `game.party_manager.is_in_party(entity_id)`:
    - If in party: reconstruct the full message from `args_str` and call `handle_party_chat(websocket, {"message": args_str}, game=game)`
    - If not in party: return error "You are not in a party"

- [x] Task 5: Update web client (AC: #7)
  - [x] 5.1: In `web-demo/js/game.js`, add `party_chat` to the message handler map (after `party_invite_response` on line 475):
    ```javascript
    party_chat: handlePartyChat,
    ```
  - [x] 5.2: Add `handlePartyChat` function (near the other party handlers around line 587):
    ```javascript
    function handlePartyChat(data) {
      appendChat(`[Party] ${data.from}: ${data.message}`, 'party');
    }
    ```
  - [x] 5.3: In `web-demo/css/style.css`, add a `.chat-party` CSS rule with a distinct color (e.g., `color: #7289da` — a soft blue similar to Discord party/group chat) to visually distinguish party chat from room chat.

- [x] Task 6: Update `/party` client-side command to support chat shorthand (AC: #8)
  - [x] 6.1: The existing `/party` client command already sends `{action: "party", args: "<full text>"}` to the server (line 264 of `game.js`). The server-side fallback (Task 4) handles routing non-subcommand text as party chat. No client change needed — the existing handler already sends the full args string.

- [x] Task 7: Write tests (AC: #1-8)
  - [x] 7.1: Create `tests/test_party_chat.py` with tests for:
    - Party chat delivery to all members across rooms
    - Sender receives their own message
    - Non-party players don't receive the message
    - Not in party → error
    - Empty message → ignored
    - Message too long → error with max length
    - Sender name set server-side (from entity, not client data)
    - Graceful handling of disconnected member mid-delivery
    - Party handler fallback routes unknown subcommand to chat when in party
    - Party handler fallback returns "not in a party" when not in party
    - `party_chat` action via dedicated route (not just fallback)

## Dev Notes

### Architecture Compliance

- **Handler pattern**: `async def handle_party_chat(ws: WebSocket, data: dict, *, game: Game)` — same keyword-only `game` param as all other handlers.
- **Import guard**: `TYPE_CHECKING` already used in `server/net/handlers/party.py` (line 7). No new import guard needed.
- **`from __future__ import annotations`** already present in `server/net/handlers/party.py` (line 2).
- **Error format**: `{"type": "error", "detail": "..."}` — matches all existing handler error responses.
- **Party state is ephemeral** (in-memory only) — no DB operations needed.
- **Dedicated action**: `party_chat` is registered as its own action in the message router, separate from `party`. The party handler's fallback also routes to it for the `/party <message>` shorthand.

### Existing Code to Reuse

- **`PartyManager.get_party(entity_id)`** (`server/party/manager.py:104`): Returns `Party | None`. Use `party.members` (list of entity_ids) for delivery.
- **`PartyManager.is_in_party(entity_id)`** (`server/party/manager.py:111`): Quick check for party membership.
- **`ConnectionManager.send_to_player(entity_id, msg)`** (`server/net/connection_manager.py:59`): Sends to individual player, silently no-ops if player not connected (no exception thrown — the `ws` check on line 62 handles this).
- **`ConnectionManager.broadcast_to_room`** (`server/net/connection_manager.py:73-84`): Reference for graceful error handling pattern (try/except around each send, `pass` on exception). Note: `send_to_player` already handles missing connections gracefully (returns without sending if no ws found), but the try/except is still needed for `WebSocketDisconnect` or other send errors.
- **`_get_entity_name(game, entity_id)`** (`server/net/handlers/party.py:109`): Already exists, but for AC #3 use `player_info["entity"].name` directly since we already have the player_info.
- **`appendChat(text, type)`** (`web-demo/js/game.js:1019`): Renders chat with CSS class `chat-${type}`. Passing `'party'` will apply class `chat-party`.

### Fallback Routing Design

The party handler's subcommand dispatch (lines 142-160 of `server/net/handlers/party.py`) currently has known subcommands: `invite`, `accept`, `reject`, `leave`, `kick`, `disband`. The `else` branch currently returns "Unknown party command". After this story:

- If player is in a party → treat the full `args_str` as a chat message, pass to `handle_party_chat`
- If player is NOT in a party → return "You are not in a party"

This means `/party hello` sends "hello" as party chat, while `/party invite @Bob` still triggers the invite subcommand. The disambiguation is: check against known subcommands first, then fall through to chat.

### Message Format (Server → Client)

| Type | When | Payload |
|------|------|---------|
| `party_chat` | Party member sends chat | `{type: "party_chat", from: "<sender_name>", message: "<text>"}` |

### Graceful Send Failure

`ConnectionManager.send_to_player()` already returns silently if the entity_id has no WebSocket (line 62 checks `if ws:`). However, a `WebSocketDisconnect` could occur between the check and the actual send. Wrap each `send_to_player` call in try/except to match the `broadcast_to_room` pattern and prevent one disconnected member from blocking delivery to others.

### Testing Patterns

- **Unit tests**: Create mock `Game`, `ConnectionManager`, `PartyManager`, `WebSocket` (all `AsyncMock`). Call `handle_party_chat()` directly and verify `send_to_player` calls.
- **Fallback test**: Call `handle_party()` with unknown subcommand, verify it routes to party chat (check for `party_chat` message sent to all members).
- **Flat test file**: `tests/test_party_chat.py` — no nested directories.
- **No DB needed**: Party chat is purely in-memory.

### Project Structure Notes

- New files: `tests/test_party_chat.py`
- Modified files:
  - `server/core/config.py` (add `MAX_CHAT_MESSAGE_LENGTH`)
  - `server/net/handlers/party.py` (add `handle_party_chat`, modify fallback)
  - `server/app.py` (import + register `party_chat` action)
  - `web-demo/js/game.js` (add `party_chat` handler)
  - `web-demo/css/style.css` (add `.chat-party` style)

### References

- [Source: `_bmad-output/planning-artifacts/epics.md` — Story 12.5, lines 2659-2712]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — Epic 12 planned features, lines 626-666]
- [Source: `_bmad-output/project-context.md` — Epic 12 patterns, lines 197-220]
- [Source: `server/net/handlers/party.py` — Party handler with subcommand dispatch, lines 117-160]
- [Source: `server/net/handlers/chat.py` — Room chat handler pattern, lines 12-58]
- [Source: `server/net/connection_manager.py` — send_to_player + broadcast_to_room, lines 59-84]
- [Source: `server/party/manager.py` — PartyManager API, lines 104-127]
- [Source: `server/app.py` — Handler registration, lines 123-210]
- [Source: `server/core/config.py` — Settings class, lines 7-36]
- [Source: `web-demo/js/game.js` — Party message handlers, lines 545-587; COMMANDS, lines 263-267]
- [Source: `web-demo/css/style.css` — Chat styling]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Added `MAX_CHAT_MESSAGE_LENGTH = 500` to config
- Implemented `handle_party_chat` in `server/net/handlers/party.py` with message validation, party check, server-side sender name, and graceful disconnected-member handling
- Registered `party_chat` as dedicated action in message router
- Changed party handler fallback from "Unknown party command" to routing to party chat (when in party) or "not in a party" error (when not)
- Added `party_chat` message handler and `handlePartyChat` function to web client
- Added `.chat-party` CSS rule with distinct blue color (#7289da)
- Updated existing `test_unknown_subcommand` test to match new fallback behavior
- 17 new tests in `tests/test_party_chat.py` covering all ACs
- 762 tests pass total, zero regressions
- Code review fixes: removed unused imports from test file, updated `/party` usage string to include chat shorthand

### File List

New files:
- tests/test_party_chat.py

Modified files:
- server/core/config.py (added MAX_CHAT_MESSAGE_LENGTH)
- server/net/handlers/party.py (added handle_party_chat, modified fallback routing)
- server/app.py (import + register party_chat action)
- web-demo/js/game.js (party_chat handler + handlePartyChat function)
- web-demo/css/style.css (added .chat-party rule)
- tests/test_party_commands.py (updated unknown subcommand test for new fallback behavior)
