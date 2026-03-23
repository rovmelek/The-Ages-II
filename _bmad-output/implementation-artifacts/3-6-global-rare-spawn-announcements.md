# Story 3.6: Global Rare Spawn Announcements

Status: done

## Story

As a player,
I want to be notified when a rare or epic NPC spawns anywhere in the world,
So that I can race to find it before others.

## Acceptance Criteria

1. A rare NPC spawns in a room → ALL connected players receive `{"type": "announcement", "message": "An Ancient Forest Dragon has appeared in Dark Cave!"}` → announcement is not limited to players in that room
2. `server/core/events.py` defines an `EventBus` → when a rare spawn event is emitted → the EventBus broadcasts the announcement through `ConnectionManager` to all connected WebSockets
3. No players are connected → a rare NPC spawns → spawn still occurs but no announcement is sent (no error)

## Tasks / Subtasks

- [x] Task 1: Create `server/core/events.py` with `EventBus` class (AC: #2)
  - [x] `EventBus` class with `subscribe(event_type, callback)` and `async emit(event_type, **data)` methods
  - [x] Callbacks are async callables; `emit()` calls all subscribers for a given event type
  - [x] Keep it simple — dict of event_type → list of async callbacks
- [x] Task 2: Add `broadcast_to_all()` method to `ConnectionManager` (AC: #1, #3)
  - [x] Send a JSON message to ALL connected WebSockets (not scoped to a room)
  - [x] If no connections exist, do nothing (no error)
- [x] Task 3: Wire EventBus into Game and register announcement handler (AC: #1, #2)
  - [x] `Game.__init__()`: create `self.event_bus = EventBus()`
  - [x] On startup, subscribe to `"rare_spawn"` event with a handler that calls `connection_manager.broadcast_to_all()` with the announcement message
  - [x] Announcement format: `{"type": "announcement", "message": "<NPC name> has appeared in <room name>!"}`
- [x] Task 4: Emit rare spawn event from Scheduler (AC: #1)
  - [x] In `Scheduler._run_rare_spawn_checks()`, after a rare NPC spawns successfully, emit `"rare_spawn"` event via `game.event_bus`
  - [x] Pass `npc_name`, `room_name` (resolved from room instance) in the event data
- [x] Task 5: Write tests `tests/test_events.py` (AC: #1-3)
  - [x] Test EventBus subscribe and emit
  - [x] Test broadcast_to_all sends to all connections
  - [x] Test broadcast_to_all with no connections (no error)
  - [x] Test rare spawn triggers global announcement
  - [x] Test announcement message format
- [x] Task 6: Verify all tests pass
  - [x] Run `pytest tests/test_events.py -v` — 9 passed
  - [x] Run `pytest tests/ -v` to verify no regressions — 174 passed

## Dev Notes

### Architecture Compliance

| Component | File Location |
|-----------|--------------|
| EventBus | `server/core/events.py` (NEW) |
| ConnectionManager | `server/net/connection_manager.py` (MODIFY — add broadcast_to_all) |
| Scheduler | `server/core/scheduler.py` (MODIFY — emit rare_spawn event) |
| Game orchestrator | `server/app.py` (MODIFY — EventBus integration) |
| Tests | `tests/test_events.py` (NEW) |

### Existing Infrastructure to Reuse

- **`ConnectionManager`** at `server/net/connection_manager.py` — has `_connections: dict[str, WebSocket]`, `broadcast_to_room()`. Needs new `broadcast_to_all()` that iterates ALL connections, not filtered by room.
- **`Scheduler._run_rare_spawn_checks()`** at `server/core/scheduler.py` — already spawns rare NPCs. The emit point is right after `room.add_npc(npc)` and `cp.currently_spawned = True`.
- **`Game`** at `server/app.py` — central orchestrator that owns all managers. EventBus should be a new member alongside `scheduler`, `connection_manager`, etc.
- **`RoomInstance.name`** — available on room instances for the announcement message.

### EventBus Pattern

Simple pub-sub with async callbacks:

```python
class EventBus:
    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = {}

    def subscribe(self, event_type: str, callback: Callable) -> None:
        self._subscribers.setdefault(event_type, []).append(callback)

    async def emit(self, event_type: str, **data) -> None:
        for cb in self._subscribers.get(event_type, []):
            await cb(**data)
```

### broadcast_to_all Pattern

```python
async def broadcast_to_all(self, message: dict) -> None:
    for ws in self._connections.values():
        await ws.send_json(message)
```

### Announcement Format

`{"type": "announcement", "message": "An Ancient Forest Dragon has appeared in Test Room!"}`

### Anti-Patterns to Avoid

- **DO NOT** add complex event filtering or priority — simple pub-sub is sufficient
- **DO NOT** persist announcements — they are fire-and-forget
- **DO NOT** add rate limiting for announcements — deferred feature
- **DO NOT** modify the rare spawn logic itself — only add the event emission after successful spawn

### Previous Story Intelligence

From Story 3-5:
- `Scheduler._run_rare_spawn_checks()` handles rare spawn rolls and creates NPCs
- The spawn success block is after `room.add_npc(npc)` / `cp.currently_spawned = True`
- Scheduler has access to `self._game` which holds all managers
- `Game` owns `scheduler`, `connection_manager`, `room_manager`
- 165 existing tests must not regress

### Project Structure Notes

- New files: `server/core/events.py`, `tests/test_events.py`
- Modified files: `server/net/connection_manager.py`, `server/core/scheduler.py`, `server/app.py`

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#3.1 Directory Structure — events.py]
- [Source: _bmad-output/planning-artifacts/architecture.md#3.2 System Relationships — EventBus]
- [Source: _bmad-output/planning-artifacts/architecture.md#4.3 NPC Spawn System — Global announcements]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.6]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Created `server/core/events.py` with async pub-sub `EventBus` class
- Added `broadcast_to_all()` to `ConnectionManager` for global messaging
- Wired `EventBus` into `Game` with `_register_events()` subscribing to `"rare_spawn"`
- Updated `Scheduler._run_rare_spawn_checks()` to emit `"rare_spawn"` event after successful spawn
- Updated `tests/test_spawn.py` `_make_game` helper to include `event_bus` mock
- 9 new tests: EventBus core, broadcast_to_all, announcement integration

### File List

- `server/core/events.py` (NEW)
- `server/net/connection_manager.py` (MODIFIED — added broadcast_to_all)
- `server/app.py` (MODIFIED — EventBus integration, _register_events)
- `server/core/scheduler.py` (MODIFIED — emit rare_spawn event)
- `tests/test_events.py` (NEW — 9 tests)
- `tests/test_spawn.py` (MODIFIED — added event_bus to mock game)
