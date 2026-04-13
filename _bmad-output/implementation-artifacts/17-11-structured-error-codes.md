# Story 17.11: Structured Error Codes

Status: done

## Story

As a game client developer,
I want protocol/auth errors to include a machine-readable `"code"` field,
so that I can switch on error codes instead of matching human-readable strings.

## Acceptance Criteria

1. An `ErrorCode` StrEnum exists in `server/net/errors.py` with members for the 5 protocol/auth errors:
   - `INVALID_JSON` — JSON parse failure
   - `MISSING_ACTION` — no `action` field in message
   - `UNKNOWN_ACTION` — action not registered in router
   - `VALIDATION_ERROR` — Pydantic schema validation failed
   - `AUTH_REQUIRED` — player not logged in (auth middleware)

2. An async `send_error(websocket, code, detail, data=None)` helper in `server/net/errors.py` that:
   - Constructs `{"type": "error", "code": code.value, "detail": detail}`
   - Calls `with_request_id(response, data)` when `data` is provided
   - Sends via `websocket.send_json()`

3. The 5 protocol/auth error sites are retrofitted to use `send_error()`:
   - `server/app.py` in `websocket_endpoint()`: Invalid JSON (line ~518), Missing action field (line ~523), ValidationError (line ~537)
   - `server/net/message_router.py` in `MessageRouter.route()`: Unknown action (line ~26)
   - `server/net/auth_middleware.py` in `requires_auth` wrapper: Not logged in (lines ~27, ~31)

4. `ErrorMessage` in `server/net/outbound_schemas.py` gains an optional `code` field: `code: str | None = None`

5. Handler-level errors are NOT changed — they continue using inline `{"type": "error", "detail": ...}` dicts (per ADR-17-5: incremental migration)

6. All existing tests pass (`make test` — 1062+ tests, 0 failures)

7. Protocol spec regenerated: `make protocol-doc` (if available) or manual update to reflect `code` field in error messages

## Tasks / Subtasks

- [x] Task 1: Create `server/net/errors.py` (AC: #1, #2)
  - [x] Define `ErrorCode(StrEnum)` with 5 members
  - [x] Implement `async send_error(websocket, code, detail, data=None)` helper
  - [x] Import `with_request_id` from `server.net.schemas`

- [x] Task 2: Retrofit protocol errors in `server/app.py` (AC: #3)
  - [x] Replace Invalid JSON error at `websocket_endpoint()` — call `send_error(websocket, ErrorCode.INVALID_JSON, "Invalid JSON")`
  - [x] Replace Missing action field error — call `send_error(websocket, ErrorCode.MISSING_ACTION, "Missing action field", data)`
  - [x] Replace ValidationError error — call `send_error(websocket, ErrorCode.VALIDATION_ERROR, str(e), data)` (Story 17.12 will sanitize `str(e)` later)

- [x] Task 3: Retrofit router error in `server/net/message_router.py` (AC: #3)
  - [x] Replace Unknown action error in `MessageRouter.route()` — call `send_error(websocket, ErrorCode.UNKNOWN_ACTION, f"Unknown action: {action}", data)`

- [x] Task 4: Retrofit auth middleware errors in `server/net/auth_middleware.py` (AC: #3)
  - [x] Replace both "Not logged in" sends in `requires_auth` wrapper — call `send_error(websocket, ErrorCode.AUTH_REQUIRED, "Not logged in")`
  - [x] Note: auth middleware wrapper HAS access to `data` dict (signature: `wrapper(websocket, data, *, game)`), but current behavior sends NO `request_id`. Preserve current behavior by passing `data=None` to avoid a behavioral change in this story.

- [x] Task 5: Update `ErrorMessage` in `server/net/outbound_schemas.py` (AC: #4)
  - [x] Add `code: str | None = None` field to `ErrorMessage` class

- [x] Task 6: Update tests (AC: #6)
  - [x] Update any tests that assert on the exact error dict structure for the 5 retrofitted sites (they now include `"code"`)
  - [x] Run `make test` — all 1062+ tests must pass

- [x] Task 7: Regenerate protocol spec (AC: #7)
  - [x] Run `make protocol-doc` or `make check-protocol` if available
  - [x] If protocol doc is manually maintained, update the error message section to document the `code` field

## Dev Notes

### Architecture Decisions

- **ADR-17-5**: FR143 scoped to 5 protocol/auth errors ONLY. Handler-level errors (~70+ sites across handlers) migrate incrementally in future epics. Do NOT touch handler files.
- **ADR-17-8**: Story 17.12 depends on this story's `send_error()` helper. The `ErrorCode.VALIDATION_ERROR` member must exist for 17.12 to use.
- **ADR-17-1**: Use `StrEnum` (Python 3.11+) so enum values compare equal to plain strings (`ErrorCode.INVALID_JSON == "INVALID_JSON"` is True).

### Files to Create

| File | Purpose |
|------|---------|
| `server/net/errors.py` | `ErrorCode` StrEnum + `send_error()` helper |

### Files to Modify

| File | Change |
|------|--------|
| `server/app.py` | `websocket_endpoint()` — replace 3 inline error dicts with `send_error()` calls |
| `server/net/message_router.py` | `MessageRouter.route()` — replace 1 inline error dict |
| `server/net/auth_middleware.py` | `requires_auth` wrapper — replace 2 inline error sends |
| `server/net/outbound_schemas.py` | `ErrorMessage` — add `code: str | None = None` field |

### Current Error Patterns Being Replaced

1. **`app.py` in `websocket_endpoint()`** — `json.JSONDecodeError` handler:
   ```python
   await websocket.send_json({"type": "error", "detail": "Invalid JSON"})
   ```
   Note: No `data` available (JSON didn't parse), so no `request_id`.

2. **`app.py` in `websocket_endpoint()`** — missing action:
   ```python
   await websocket.send_json(with_request_id({"type": "error", "detail": "Missing action field"}, data))
   ```

3. **`app.py` in `websocket_endpoint()`** — Pydantic validation:
   ```python
   await websocket.send_json(with_request_id({"type": "error", "detail": str(e)}, data))
   ```

4. **`message_router.py` in `MessageRouter.route()`** — unknown action:
   ```python
   await websocket.send_json(with_request_id({"type": "error", "detail": f"Unknown action: {action}"}, data))
   ```

5. **`auth_middleware.py` in `requires_auth` wrapper** — not logged in (x2):
   ```python
   await websocket.send_json({"type": "error", "detail": "Not logged in"})
   ```
   Note: `data` IS available in the wrapper (`wrapper(websocket, data, *, game)`), but current behavior sends no `request_id`. Preserve this by passing `data=None` to `send_error()`.

### Import Pattern

`send_error` and `ErrorCode` should be imported from `server.net.errors`:
```python
from server.net.errors import ErrorCode, send_error
```

In `app.py`, `with_request_id` is ONLY used in the 2 error paths being replaced, but the import line (`from server.net.schemas import ACTION_SCHEMAS, with_request_id`) also imports `ACTION_SCHEMAS` which IS used — so drop `with_request_id` from this import but keep the line. In `message_router.py`, the sole import `from server.net.schemas import with_request_id` is only used in the error path — remove it entirely. `auth_middleware.py` doesn't currently import `with_request_id`.

### Testing Considerations

- **Exact-equality tests that WILL break** (must add `"code"` to expected dicts):
  - `tests/test_websocket.py::test_websocket_malformed_json` — asserts `resp == {"type": "error", "detail": "Invalid JSON"}`
  - `tests/test_websocket.py::test_websocket_missing_action` — asserts `resp == {"type": "error", "detail": "Missing action field"}`
  - `tests/test_websocket.py::test_websocket_unknown_action` — asserts `resp == {"type": "error", "detail": "Unknown action: nonexistent"}`
  - `tests/test_websocket.py::test_router_unknown_action` — asserts `mock_ws.send_json.assert_called_once_with({"type": "error", "detail": "Unknown action: unknown_thing"})`
- **Substring-check test that will still pass**: `test_websocket_connect` uses `"Unknown action: ping" in resp["detail"]`
- **"Not logged in" tests that WILL break** (auth middleware `@requires_auth` — many tests across files):
  - `tests/test_trade.py:352` — `assert_called_with({"type": "error", "detail": "Not logged in"})`
  - `tests/test_interact.py:118` — `assert_called_with({"type": "error", "detail": "Not logged in"})`
  - `tests/test_movement.py:211` — exact dict match
  - `tests/test_map.py:79` — `assert_called_once_with({"type": "error", "detail": "Not logged in"})`
  - `tests/test_query.py:303` — `assert_called_once_with({"type": "error", "detail": "Not logged in"})`
  - `tests/test_chat.py:183` — exact dict match
  - `tests/test_logout.py:260,283` — exact dict match (2 tests)
  - `tests/test_party_commands.py:812,824` — exact dict match (2 tests)
  - `tests/test_party_chat.py:257,273` — substring check `"Not logged in" in msg["detail"]` (will still pass)
- The `"code"` field is additive — tests checking only `response["detail"]` will still pass

### What NOT to Do

- Do NOT change any handler files (`server/net/handlers/*.py`) — those are out of scope (ADR-17-5)
- Do NOT create error codes for handler-level errors (e.g., "Not in combat", "Item not found") — future epic work
- Do NOT change the `with_request_id` function itself
- Do NOT add error codes to trade/party manager return strings

### References

- [Source: _bmad-output/implementation-artifacts/codebase-adversarial-review-2026-04-12.md#F20] — Error messages lack machine-parseable codes
- [Source: _bmad-output/planning-artifacts/epics.md#FR143] — ErrorCode StrEnum + send_error() requirement
- [Source: CLAUDE.md#Epic 17 Key Decisions] — ADR-17-5, ADR-17-8

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Created `ErrorCode` StrEnum with 5 members (INVALID_JSON, MISSING_ACTION, UNKNOWN_ACTION, VALIDATION_ERROR, AUTH_REQUIRED)
- Created `send_error()` async helper with optional `data` for `request_id` correlation
- Retrofitted 6 error sites across 3 files (app.py: 3, message_router.py: 1, auth_middleware.py: 2)
- Updated `ErrorMessage` outbound schema with optional `code` field
- Updated 14 test assertions across 9 test files to include `"code"` in expected dicts
- Also fixed `test_outbound_schemas.py::TestSystem::test_error` (ErrorMessage model_dump includes `code: None`)
- Protocol spec regenerated and validated via `make protocol-doc` / `make check-protocol`
- All 1062 tests pass, 0 failures

### File List

- `server/net/errors.py` (NEW) — ErrorCode StrEnum + send_error() helper
- `server/app.py` (MODIFIED) — 3 error sites retrofitted, import updated
- `server/net/message_router.py` (MODIFIED) — 1 error site retrofitted, import updated
- `server/net/auth_middleware.py` (MODIFIED) — 2 error sites retrofitted, import added
- `server/net/outbound_schemas.py` (MODIFIED) — ErrorMessage.code field added
- `tests/test_websocket.py` (MODIFIED) — 4 assertions updated
- `tests/test_trade.py` (MODIFIED) — 1 assertion updated
- `tests/test_interact.py` (MODIFIED) — 1 assertion updated
- `tests/test_movement.py` (MODIFIED) — 1 assertion updated
- `tests/test_map.py` (MODIFIED) — 1 assertion updated
- `tests/test_query.py` (MODIFIED) — 1 assertion updated
- `tests/test_chat.py` (MODIFIED) — 1 assertion updated
- `tests/test_logout.py` (MODIFIED) — 2 assertions updated
- `tests/test_party_commands.py` (MODIFIED) — 2 assertions updated
- `tests/test_outbound_schemas.py` (MODIFIED) — 1 assertion updated
- `_bmad-output/planning-artifacts/protocol-spec.md` (REGENERATED)
