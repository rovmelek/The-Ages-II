# Story 2.4: Room Chat & Whispers

Status: done

## Story

As a player,
I want to chat with other players in my room or whisper to a specific player,
So that I can communicate and coordinate with others.

## Acceptance Criteria

1. Client sends `{"action": "chat", "message": "Hello everyone!"}` and all players in the room receive `{"type": "chat", "sender": "hero", "message": "Hello everyone!", "whisper": false}`
2. Client sends `{"action": "chat", "message": "Secret info", "whisper_to": "player_2"}` and only the target player receives the chat with `whisper: true`
3. The sender also receives a copy of their whisper
4. Empty message is ignored (no broadcast)
5. Player not logged in receives error: `"Not logged in"`
6. Whisper to a nonexistent player returns error: `"Player not found"`

## Tasks / Subtasks

- [ ] Task 1: Create `server/net/handlers/chat.py` with `handle_chat` (AC: #1-6)
  - [ ] Define `async def handle_chat(websocket: WebSocket, data: dict, *, game: Game) -> None`
  - [ ] Look up entity_id via `game.connection_manager.get_entity_id(websocket)` — if None, send "Not logged in" error (AC: #5)
  - [ ] Get player info from `game.player_entities[entity_id]`
  - [ ] Extract `message` from data — if empty or missing, return silently (AC: #4)
  - [ ] Extract `whisper_to` from data — if present, handle as whisper (AC: #2, #3)
  - [ ] For whisper: look up target entity_id, validate it exists in connection_manager, send to target and sender
  - [ ] For room chat: broadcast to all players in room (AC: #1)
- [ ] Task 2: Register `handle_chat` in `Game._register_handlers()` (AC: #1)
  - [ ] Import `handle_chat` from `server.net.handlers.chat`
  - [ ] Register: `self.router.register("chat", lambda ws, d: handle_chat(ws, d, game=self))`
- [ ] Task 3: Write tests `tests/test_chat.py` (AC: #1-6)
  - [ ] Test room chat broadcasts to all players in room
  - [ ] Test chat message format includes sender name, message, whisper: false
  - [ ] Test whisper sends only to target player and sender
  - [ ] Test whisper message has whisper: true
  - [ ] Test empty message is ignored
  - [ ] Test not logged in returns error
  - [ ] Test whisper to nonexistent player returns error
- [ ] Task 4: Verify all tests pass
  - [ ] Run `pytest tests/test_chat.py -v`
  - [ ] Run `pytest tests/ -v` to verify no regressions (107 existing tests)

## Dev Notes

### Architecture Compliance

| Component | File Location |
|-----------|--------------|
| Chat handler | `server/net/handlers/chat.py` |
| Handler registration | `server/app.py` → `Game._register_handlers()` |

### Chat Message Format

Room chat (broadcast to all in room):
```python
{"type": "chat", "sender": "hero", "message": "Hello everyone!", "whisper": False}
```

Whisper (sent to target + sender only):
```python
{"type": "chat", "sender": "hero", "message": "Secret info", "whisper": True}
```

### Whisper Implementation

The `whisper_to` field contains a target entity_id (e.g., `"player_2"`):
```python
whisper_to = data.get("whisper_to")
if whisper_to:
    target_ws = game.connection_manager.get_websocket(whisper_to)
    if target_ws is None:
        await websocket.send_json({"type": "error", "detail": "Player not found"})
        return
    msg = {"type": "chat", "sender": entity_name, "message": message, "whisper": True}
    await target_ws.send_json(msg)
    await websocket.send_json(msg)  # Copy to sender
    return
```

### Room Chat Broadcast

```python
msg = {"type": "chat", "sender": entity_name, "message": message, "whisper": False}
await game.connection_manager.broadcast_to_room(room_key, msg)
```

Note: broadcast includes the sender — they should see their own message in chat.

### Anti-Patterns to Avoid

- **DO NOT** allow chat from unauthenticated connections
- **DO NOT** strip or truncate message content — keep it simple for now
- **DO NOT** implement chat history or persistence — not in scope
- **DO NOT** add profanity filtering — not in scope

### Previous Story Intelligence

From Story 2.1:
- Login check pattern: `game.connection_manager.get_entity_id(websocket)` → look up `game.player_entities`
- Handler signature: `async def handler(websocket, data, *, game)`
- ConnectionManager has `get_websocket(entity_id)` for direct sending
- 107 existing tests must not regress

### Project Structure Notes

- New files: `server/net/handlers/chat.py`, `tests/test_chat.py`
- Modified files: `server/app.py` (add chat handler registration)

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#8.2 Client Actions — chat]
- [Source: _bmad-output/planning-artifacts/architecture.md#8.3 Server Messages — chat]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.4]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Debug Log References
None

### Completion Notes List
- `server/net/handlers/chat.py`: handle_chat validates login, strips message whitespace, ignores empty, supports room broadcast and whisper
- Room chat broadcasts to all players in room (including sender) with `whisper: false`
- Whisper sends to target player + sender only with `whisper: true`
- Whisper to nonexistent player returns "Player not found"
- Registered "chat" action in Game._register_handlers()
- 9 new tests (116 total), all passing — room broadcast, message format, whisper to target, whisper exclusion, nonexistent target, empty/whitespace messages, not logged in, missing message field

### File List
- `server/net/handlers/chat.py` (new) — Chat and whisper WebSocket handler
- `server/app.py` (modified) — Added chat handler registration
- `tests/test_chat.py` (new) — 9 chat and whisper tests
