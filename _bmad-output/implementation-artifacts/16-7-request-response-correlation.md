# Story 16.7: Request-Response Correlation (Optional `request_id`)

Status: done

## Story

As a **game client developer**,
I want the server to echo back an optional `request_id` field from my request in its direct response,
So that I can correlate async WebSocket responses with the requests that triggered them.

## Acceptance Criteria

1. **Given** any inbound WebSocket message with an optional `request_id` string field,
   **When** the server processes it and sends a direct response to the requesting player,
   **Then** the response includes the same `request_id` value.

2. **Given** an inbound message without `request_id` (or `request_id` is `null`),
   **When** the server sends a direct response,
   **Then** the response does NOT contain a `request_id` key (no `null` value sent).

3. **Given** a message that triggers broadcasts to other players (e.g., `entity_moved`, `entity_entered`, `party_update`),
   **When** the broadcast is sent,
   **Then** it never includes `request_id`.

4. **Given** a malformed JSON message (unparseable),
   **When** the server sends the "Invalid JSON" error,
   **Then** it correctly omits `request_id` (data unavailable).

5. **Given** a JSON message missing the `action` field but containing `request_id`,
   **When** the server sends the "Missing action field" error,
   **Then** it includes `request_id` in the error response.

6. **Given** a JSON message with a valid `action` but failing schema validation,
   **When** the server sends the `ValidationError` response,
   **Then** it includes `request_id` if present in the raw data.

7. **Given** the router receives an unknown action with `request_id`,
   **When** it sends the "Unknown action" error,
   **Then** it includes `request_id`.

8. **Given** all 968 existing tests,
   **When** Story 16.7 is implemented,
   **Then** all tests pass unchanged (they don't send `request_id`).

## Tasks / Subtasks

- [x] Task 1: Add `request_id` to inbound schema base (AC: #1, #2)
  - [x] 1.1: Add `request_id: str | None = None` to `InboundMessage` in `server/net/schemas.py:8-11`
  - [x] 1.2: Verify `model_dump()` includes `request_id` when present — existing `data = validated.model_dump()` at `server/app.py:411` passes it through to handlers

- [x] Task 2: Create `with_request_id` utility (AC: #1, #2)
  - [x] 2.1: Add `with_request_id(response: dict, data: dict) -> dict` in `server/net/schemas.py`
  - [x] 2.2: If `data.get("request_id")` is not `None`, set `response["request_id"] = data["request_id"]`; otherwise return response unchanged (no `null` key)

- [x] Task 3: Apply `with_request_id` to framework-level errors in `server/app.py` (AC: #4, #5, #6)
  - [x] 3.1: "Missing action field" error (line 402-404): extract `request_id` from `data` dict, apply to error response
  - [x] 3.2: `ValidationError` error (line 413-415): extract `request_id` from raw `data` dict (before validation), apply to error response
  - [x] 3.3: "Invalid JSON" error (line 397-399): leave unchanged — no `data` available

- [x] Task 4: Apply `with_request_id` to router unknown-action error (AC: #7)
  - [x] 4.1: In `server/net/message_router.py:24-25`, apply `with_request_id` to the "Unknown action" error response

- [x] Task 5: Apply `with_request_id` to all handler direct responses (AC: #1, #2, #3)
  - [x] 5.1: `server/net/handlers/auth.py` — `login_success`, `registered`, `logged_out`, error responses. Do NOT add to broadcasts (`entity_entered`, `entity_left`, `kicked`)
  - [x] 5.2: `server/net/handlers/movement.py` — error responses, `room_state` (to mover on room transition), `nearby_objects` (to mover). Do NOT add to broadcasts (`entity_moved`, `entity_entered`, `entity_left`) or `combat_start`
  - [x] 5.3: `server/net/handlers/chat.py` — error responses, whisper copy to sender. Do NOT add to room broadcast `chat` messages or whisper delivery to target
  - [x] 5.4: `server/net/handlers/combat.py` — `combat_fled` (to fleeing player), error responses. Do NOT add to `combat_turn`, `combat_end`, `combat_update` broadcasts via `_broadcast_combat_state` or `send_to_player`
  - [x] 5.5: `server/net/handlers/query.py` — `look_result`, `who_result`, `stats_result`, `help_result`, `map_data` (all are direct responses)
  - [x] 5.6: `server/net/handlers/inventory.py` — `inventory`, `item_used`, error responses (all direct)
  - [x] 5.7: `server/net/handlers/interact.py` — `interact_result`, error responses (all direct)
  - [x] 5.8: `server/net/handlers/trade.py` — `trade_result` and error responses to requesting player. Do NOT add to `trade_request`/`trade_update`/`trade_result` sent to trade partner via `send_to_player`
  - [x] 5.9: `server/net/handlers/party.py` — `party_status`, `party_invite_response`, error responses to requesting player. Do NOT add to `party_invite`, `party_update` sent to other members via `send_to_player`
  - [x] 5.10: `server/net/handlers/levelup.py` — `level_up_complete`, error responses (all direct)

- [x] Task 6: Update outbound schemas for documentation (AC: #1)
  - [x] 6.1: Add `request_id: str | None = None` to relevant outbound schema classes in `server/net/outbound_schemas.py` — only to direct-response types (not broadcast types)

- [x] Task 7: Write tests (AC: #1-#8)
  - [x] 7.1: Test sending message WITH `request_id` — verify echoed in response
  - [x] 7.2: Test sending message WITHOUT `request_id` — verify no `request_id` key in response
  - [x] 7.3: Test broadcast to OTHER players does NOT include `request_id`
  - [x] 7.4: Test "Missing action field" error includes `request_id`
  - [x] 7.5: Test "Unknown action" error includes `request_id`
  - [x] 7.6: Test `ValidationError` includes `request_id`
  - [x] 7.7: Run `make test` — all tests pass

## Dev Notes

### `with_request_id` utility

Place in `server/net/schemas.py` alongside the inbound schemas. Simple function:

```python
def with_request_id(response: dict, data: dict) -> dict:
    """Echo request_id from inbound data to outbound response if present."""
    rid = data.get("request_id")
    if rid is not None:
        response["request_id"] = rid
    return response
```

### Key distinction: direct response vs broadcast

- **Direct response**: Sent via `websocket.send_json(...)` to the player who made the request — gets `request_id`
- **Broadcast**: Sent via `connection_manager.broadcast_to_room(...)` or `connection_manager.send_to_player(other_entity_id, ...)` to other players — never gets `request_id`

Some handlers mix both patterns (e.g., `auth.py` sends `login_success` to requester AND `entity_entered` broadcast). Only the direct response gets `request_id`.

### model_dump() behavior

When `request_id` is added to `InboundMessage`, `validated.model_dump()` at `server/app.py:411` will include `"request_id": None` for messages without it. The `with_request_id` utility handles this correctly — it checks `data.get("request_id")` and only copies non-None values.

**Important**: `model_dump()` will include `request_id: None` in the data dict. The `with_request_id` function correctly handles this by checking `if rid is not None`.

### Backward compatibility

- `request_id` is optional (`str | None = None`) — all existing messages work unchanged
- Existing tests don't send `request_id`, so responses won't include it
- Web-demo client doesn't use `request_id` — no client changes needed

### Previous story patterns

- Story 16.10a used `functools.partial` / closures for callback registration — not relevant here
- Story 16.1 established the `InboundMessage` base class and `ACTION_SCHEMAS` mapping
- Story 16.2 established outbound schema classes as documentation

### Project Structure Notes

- `server/net/schemas.py` — inbound schemas + `with_request_id` utility
- `server/net/outbound_schemas.py` — outbound schema documentation
- `server/net/message_router.py` — routes by action, sends unknown-action errors
- `server/app.py` — websocket_endpoint with JSON parse, schema validation, and routing
- `server/net/handlers/` — 10 handler files (admin.py is REST-only, unchanged)
- `tests/` — flat structure, new file `tests/test_request_id.py`

### References

- [Source: _bmad-output/planning-artifacts/epic-16-tech-spec.md#Story-16.7] — Full spec
- [Source: server/net/schemas.py:8-11] — `InboundMessage` base class
- [Source: server/app.py:387-419] — WebSocket endpoint with schema validation
- [Source: server/net/message_router.py:19-28] — `route()` method with unknown-action error
- [Source: server/net/outbound_schemas.py] — Outbound schema documentation

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Completion Notes List

- Added `request_id: str | None = None` to `InboundMessage` base class — propagates to all 21 action schemas
- Created `with_request_id(response, data)` utility in `server/net/schemas.py`
- Applied to framework-level errors in `server/app.py` (missing action, validation error)
- Applied to unknown-action error in `server/net/message_router.py`
- Applied to all direct `websocket.send_json()` responses in 10 handler files
- Broadcasts (`broadcast_to_room`, `send_to_player` to other players) correctly excluded
- Added `request_id` field to 17 direct-response outbound schema classes for documentation
- `_handle_exit_transition` signature updated to accept `data` parameter (threaded from `handle_move`)
- Party sub-handlers (`_handle_invite`, `_handle_accept`, etc.) updated to accept `data` parameter
- 18 new tests in `tests/test_request_id.py`, 986 total passing
- Updated existing tests for signature changes and model_dump assertions

### File List

- `server/net/schemas.py` — Modified: added `request_id` to `InboundMessage`, added `with_request_id()` utility
- `server/app.py` — Modified: imported `with_request_id`, applied to framework-level error responses
- `server/net/message_router.py` — Modified: imported and applied `with_request_id` to unknown-action error
- `server/net/handlers/auth.py` — Modified: wrapped all direct responses with `with_request_id`
- `server/net/handlers/movement.py` — Modified: wrapped direct responses, threaded `data` to `_handle_exit_transition`
- `server/net/handlers/chat.py` — Modified: wrapped error and whisper echo responses
- `server/net/handlers/combat.py` — Modified: wrapped error and `combat_fled` responses
- `server/net/handlers/query.py` — Modified: wrapped all responses (all direct)
- `server/net/handlers/inventory.py` — Modified: wrapped all responses (all direct)
- `server/net/handlers/interact.py` — Modified: wrapped all responses (all direct)
- `server/net/handlers/trade.py` — Modified: wrapped all direct responses (not `send_to_player` calls)
- `server/net/handlers/party.py` — Modified: threaded `data` to sub-handlers, wrapped all direct responses
- `server/net/handlers/levelup.py` — Modified: wrapped all responses
- `server/net/outbound_schemas.py` — Modified: added `request_id` field to 17 direct-response schema classes
- `tests/test_request_id.py` — New: 18 tests for request_id echo-back
- `tests/test_inbound_schemas.py` — Modified: updated `test_login_dump` assertion for `request_id`
- `tests/test_outbound_schemas.py` — Modified: updated 3 assertions for `request_id` field
- `tests/test_exploration_xp.py` — Modified: updated `_handle_exit_transition` call signatures
- `tests/test_trade.py` — Modified: updated `_handle_exit_transition` call signature
