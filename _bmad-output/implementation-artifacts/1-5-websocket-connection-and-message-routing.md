# Story 1.5: WebSocket Connection & Message Routing

Status: done

## Story

As a player,
I want to connect to the game server via WebSocket and have my messages routed to the correct handler,
So that I can communicate with the server in real-time.

## Acceptance Criteria

1. The server accepts WebSocket connections at `/ws/game`
2. The client can send JSON messages with an "action" field
3. Messages are routed to the correct handler based on the "action" value
4. Unknown actions return: `{"type": "error", "detail": "Unknown action: {action}"}`
5. Malformed JSON returns: `{"type": "error", "detail": "Invalid JSON"}`
6. Messages missing the "action" field return an error
7. `server/net/connection_manager.py` tracks WebSocket-to-player-entity-ID mappings
8. `server/net/connection_manager.py` supports `send_to_player` and `broadcast_to_room`

## Tasks / Subtasks

- [x] Task 1: Create `server/net/connection_manager.py` (AC: #7, #8)
  - [x] Define `ConnectionManager` class
  - [x] Track `_connections: dict[str, WebSocket]` — maps entity_id -> WebSocket
  - [x] Track `_player_rooms: dict[str, str]` — maps entity_id -> room_key (for broadcast targeting)
  - [x] Implement `connect(entity_id: str, websocket: WebSocket, room_key: str)` — register a player connection
  - [x] Implement `disconnect(entity_id: str)` — remove a player connection
  - [x] Implement `get_websocket(entity_id: str) -> WebSocket | None`
  - [x] Implement `async send_to_player(entity_id: str, message: dict)` — send JSON to a specific player
  - [x] Implement `async broadcast_to_room(room_key: str, message: dict, exclude: str | None = None)` — send JSON to all players in a room
- [x] Task 2: Create `server/net/message_router.py` (AC: #3, #4, #5, #6)
  - [x] Define `MessageRouter` class
  - [x] Track `_handlers: dict[str, Callable]` — maps action string -> handler function
  - [x] Implement `register(action: str, handler: Callable)` — register a handler for an action
  - [x] Implement `async route(websocket: WebSocket, data: dict)` — look up handler by `data["action"]` and call it
  - [x] If action is not registered, send error: `{"type": "error", "detail": "Unknown action: {action}"}`
- [x] Task 3: Create WebSocket endpoint in `server/net/websocket.py` (AC: #1, #2, #5, #6)
  - [x] Define `async def websocket_endpoint(websocket: WebSocket)` — FastAPI WebSocket handler
  - [x] Accept the connection
  - [x] Loop receiving text messages, parse JSON
  - [x] On JSON parse error: send `{"type": "error", "detail": "Invalid JSON"}`
  - [x] On missing "action" field: send `{"type": "error", "detail": "Missing action field"}`
  - [x] On valid message: call `router.route(websocket, data)`
  - [x] On WebSocketDisconnect: clean up connection
  - [x] The endpoint uses module-level `router` and `connection_manager` instances (will be wired by Game orchestrator in Story 1.8)
- [x] Task 4: Create `server/app.py` with minimal FastAPI app for testing (AC: #1)
  - [x] Create a minimal FastAPI app that includes the WebSocket route at `/ws/game`
  - [x] This is a testable scaffold — the full Game orchestrator comes in Story 1.8
  - [x] Import and mount the websocket_endpoint
- [x] Task 5: Write tests `tests/test_websocket.py` (AC: #1-8)
  - [x] Test WebSocket connection acceptance at /ws/game
  - [x] Test valid JSON message routing to registered handler
  - [x] Test unknown action returns error
  - [x] Test malformed JSON returns error
  - [x] Test missing action field returns error
  - [x] Test ConnectionManager: connect, disconnect, get_websocket
  - [x] Test ConnectionManager: send_to_player, broadcast_to_room
  - [x] Use httpx AsyncClient + WebSocket test client
- [x] Task 6: Verify all tests pass
  - [x] Run `pytest tests/test_websocket.py -v`
  - [x] Run `pytest tests/ -v` to verify no regressions

## Dev Notes

### Architecture Compliance

| Component | File Location |
|-----------|--------------|
| ConnectionManager | `server/net/connection_manager.py` |
| MessageRouter | `server/net/message_router.py` |
| WebSocket endpoint | `server/net/websocket.py` |
| FastAPI app (minimal) | `server/app.py` |

### WebSocket Protocol

- **Endpoint**: `/ws/game`
- **Client -> Server**: JSON with `"action"` field (e.g., `{"action": "login", "username": "hero", "password": "secret"}`)
- **Server -> Client**: JSON with `"type"` field (e.g., `{"type": "error", "detail": "..."}`)

### ConnectionManager Design

```python
class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, WebSocket] = {}  # entity_id -> ws
        self._player_rooms: dict[str, str] = {}       # entity_id -> room_key

    def connect(self, entity_id: str, websocket: WebSocket, room_key: str):
        self._connections[entity_id] = websocket
        self._player_rooms[entity_id] = room_key

    def disconnect(self, entity_id: str):
        self._connections.pop(entity_id, None)
        self._player_rooms.pop(entity_id, None)

    async def send_to_player(self, entity_id: str, message: dict):
        ws = self._connections.get(entity_id)
        if ws:
            await ws.send_json(message)

    async def broadcast_to_room(self, room_key: str, message: dict, exclude: str | None = None):
        for eid, rk in self._player_rooms.items():
            if rk == room_key and eid != exclude:
                ws = self._connections.get(eid)
                if ws:
                    await ws.send_json(message)
```

### MessageRouter Design

```python
from typing import Callable

class MessageRouter:
    def __init__(self):
        self._handlers: dict[str, Callable] = {}

    def register(self, action: str, handler: Callable):
        self._handlers[action] = handler

    async def route(self, websocket: WebSocket, data: dict):
        action = data.get("action")
        handler = self._handlers.get(action)
        if handler is None:
            await websocket.send_json({"type": "error", "detail": f"Unknown action: {action}"})
            return
        await handler(websocket, data)
```

### WebSocket Endpoint Pattern

```python
from fastapi import WebSocket, WebSocketDisconnect
import json

async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "detail": "Invalid JSON"})
                continue
            if "action" not in data:
                await websocket.send_json({"type": "error", "detail": "Missing action field"})
                continue
            await router.route(websocket, data)
    except WebSocketDisconnect:
        pass  # cleanup handled by caller/Game orchestrator
```

### Testing with httpx

FastAPI provides `TestClient` with WebSocket support. For async tests, use `httpx.AsyncClient` with `ASGITransport`:

```python
from fastapi.testclient import TestClient
from server.app import app

def test_websocket():
    client = TestClient(app)
    with client.websocket_connect("/ws/game") as ws:
        ws.send_json({"action": "nonexistent"})
        resp = ws.receive_json()
        assert resp["type"] == "error"
```

Note: `TestClient` WebSocket tests are synchronous (no `async`). Use `TestClient` for WebSocket tests, not `httpx.AsyncClient`.

### Handler Signature Convention

All action handlers follow this signature:

```python
async def handle_action(websocket: WebSocket, data: dict) -> None:
    ...
```

Handlers are NOT created in this story — only the routing infrastructure. Actual handlers (auth, movement, chat, combat, inventory) are created in Stories 1.6-1.8 and later epics.

### server/app.py Scope

For this story, `server/app.py` is a **minimal scaffold** to enable WebSocket testing:

```python
from fastapi import FastAPI
app = FastAPI()
# Mount WebSocket route
```

The full Game orchestrator with startup/shutdown lifecycle comes in Story 1.8. For now, just wire up the WebSocket endpoint so tests can connect.

### Anti-Patterns to Avoid

- **DO NOT** create action handlers (auth, movement, etc.) — those are later stories
- **DO NOT** implement the full Game class or startup/shutdown — that's Story 1.8
- **DO NOT** create REST API endpoints — those are later
- **DO NOT** implement player authentication logic — that's Story 1.6
- **DO NOT** import RoomManager or any game logic in the WebSocket endpoint — keep it clean
- **DO NOT** use `protocol.py` yet — message schemas can be simple dicts for now

### Previous Story Intelligence

From Story 1.4:
- PlayerEntity dataclass: id (str), name, x, y, player_db_id (int), stats (dict), in_combat (bool)
- RoomManager: get_room, load_room, unload_room, transfer_entity
- RoomInstance: add_entity, remove_entity, get_player_ids, move_entity, get_state
- 33 existing tests must not regress
- All `__init__.py` files exist in server/net/ and server/net/handlers/

### Project Structure Notes

- New files: `net/connection_manager.py`, `net/message_router.py`, `net/websocket.py`, `server/app.py`, `tests/test_websocket.py`
- `server/net/__init__.py` and `server/net/handlers/__init__.py` already exist
- `run.py` already references `server.app:app` — this story creates that module

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#8. Networking Protocol]
- [Source: _bmad-output/planning-artifacts/architecture.md#3.1 Directory Structure]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.5]
- [Source: _bmad-output/implementation-artifacts/1-4-tile-system-and-room-instance.md#Dev Agent Record]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Debug Log References
None

### Completion Notes List
- ConnectionManager: dual dict tracking (entity_id->WebSocket, entity_id->room_key), also added update_room() for room transfers
- MessageRouter: simple action->handler dict with unknown action error response
- WebSocket endpoint: accept, loop, parse JSON, validate action field, route — handles all error cases
- server/app.py: minimal FastAPI scaffold with WebSocket route at /ws/game — enables run.py to work
- Used FastAPI TestClient for sync WebSocket tests, AsyncMock for unit tests
- 13 new tests (46 total), all passing

### File List
- `server/net/connection_manager.py` (new) — WebSocket-to-player mapping
- `server/net/message_router.py` (new) — Action-based message routing
- `server/net/websocket.py` (new) — WebSocket endpoint with JSON parsing
- `server/app.py` (new) — Minimal FastAPI app scaffold
- `tests/test_websocket.py` (new) — 13 WebSocket and networking tests
