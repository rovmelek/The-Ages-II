# Story 17.12: Sanitize Pydantic Validation Errors

Status: done

## Story

As a game client developer,
I want Pydantic validation errors sanitized before reaching my client,
so that internal schema details (field names, validation rules, type info) are not leaked.

## Acceptance Criteria

1. When a Pydantic `ValidationError` occurs during WebSocket message validation in `websocket_endpoint()`, the error sent to the client uses a sanitized human-readable summary instead of raw `str(e)` output.

2. The sanitized format extracts field names and messages from `e.errors()` and joins them as `"field: message; field2: message2"` (semicolon-separated, one entry per validation error).

3. The error is sent via `send_error(websocket, ErrorCode.VALIDATION_ERROR, sanitized_detail, data)` — using the infrastructure from Story 17.11.

4. Internal Pydantic details (type annotations, `type=value_error`, `input=...`, `url=...`) are NOT included in the client-facing message.

5. All existing tests pass (`make test` — 1062+ tests, 0 failures).

6. Protocol spec remains valid (`make check-protocol` passes — no schema changes needed since `ErrorMessage` already has `code` field from Story 17.11).

## Tasks / Subtasks

- [x] Task 1: Create `sanitize_validation_error()` helper in `server/net/errors.py` (AC: #1, #2, #4)
  - [x] Add function `sanitize_validation_error(e: ValidationError) -> str` that extracts `e.errors()` and formats as `"field: msg; field2: msg2"`
  - [x] For each error dict in `e.errors()`: use `err["loc"][-1]` for field name (last element of location tuple) and `err["msg"]` for message
  - [x] Strip Pydantic's `"Value error, "` prefix from `msg` if present (Pydantic prepends this for custom validators)
  - [x] If `e.errors()` returns empty list, fall back to `"Validation failed"`

- [x] Task 2: Replace `str(e)` with `sanitize_validation_error(e)` in `server/app.py` (AC: #1, #3)
  - [x] In `websocket_endpoint()` at the `except ValidationError as e:` block, change `str(e)` to `sanitize_validation_error(e)`
  - [x] Add import of `sanitize_validation_error` from `server.net.errors`

- [x] Task 3: Update tests (AC: #5)
  - [x] Add unit tests for `sanitize_validation_error()` in a new or existing test file
  - [x] Test single-field error, multi-field error, empty errors, and `"Value error, "` prefix stripping
  - [x] Update `tests/test_request_id.py::test_validation_error_includes_request_id` if it asserts on `str(e)` format (currently it only checks `request_id` echoing, so likely unaffected)
  - [x] Run `make test` — all 1066 tests pass

- [x] Task 4: Verify protocol spec (AC: #6)
  - [x] Run `make check-protocol` — confirmed up to date

## Dev Notes

### Architecture Decisions

- **ADR-17-8**: This story depends on Story 17.11's `send_error()` helper and `ErrorCode.VALIDATION_ERROR`. Story 17.11 is complete.
- **ADR-17-5**: Only the single validation error site in `app.py` is changed — no handler-level error changes.

### Files to Modify

| File | Change |
|------|--------|
| `server/net/errors.py` | Add `sanitize_validation_error()` function |
| `server/app.py` | Replace `str(e)` with `sanitize_validation_error(e)` in `websocket_endpoint()` |

### Current Code Being Changed

**`server/app.py` in `websocket_endpoint()`** — line ~532-535:
```python
except ValidationError as e:
    await send_error(
        websocket, ErrorCode.VALIDATION_ERROR, str(e), data
    )
```

The `str(e)` produces verbose multi-line Pydantic output like:
```
2 validation errors for LoginMessage
username
  Field required [type=missing, input_value={'action': 'login'}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.11/v/missing
password
  Field required [type=missing, input_value={'action': 'login'}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.11/v/missing
```

After sanitization, this becomes: `"username: Field required; password: Field required"`

### Pydantic `e.errors()` Structure

`e.errors()` returns a list of dicts, each with:
```python
{
    "type": "missing",
    "loc": ("username",),   # tuple of field path
    "msg": "Field required",
    "input": {...},
    "url": "https://errors.pydantic.dev/..."
}
```

For custom validators with `raise ValueError(...)`, `msg` is prefixed: `"Value error, <message>"`.

### Import Pattern

```python
from server.net.errors import ErrorCode, send_error, sanitize_validation_error
```

### Testing Considerations

- `tests/test_request_id.py::test_validation_error_includes_request_id` (line ~109) — constructs error using `str(e)` directly (NOT through `websocket_endpoint`). This test verifies `with_request_id` echoing, not the error detail format. It is **unaffected** by this change.
- The integration test path through `websocket_endpoint` will now produce sanitized output — any test sending an invalid schema message and checking the exact `detail` string would need updating.
- Search for any tests that assert on the exact `str(e)` output of a `ValidationError` through the WebSocket endpoint.

### What NOT to Do

- Do NOT change the `send_error()` function itself
- Do NOT change any handler files
- Do NOT add new error codes — `VALIDATION_ERROR` already exists
- Do NOT change `ErrorMessage` schema — `code` field already present

### References

- [Source: _bmad-output/implementation-artifacts/codebase-adversarial-review-2026-04-12.md#F21] — Pydantic validation errors exposed raw
- [Source: _bmad-output/planning-artifacts/epics.md#FR148] — Sanitize ValidationError before sending
- [Source: CLAUDE.md#Epic 17 Key Decisions] — ADR-17-8

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Added `sanitize_validation_error()` to `server/net/errors.py` — extracts field/msg from `e.errors()`, strips `"Value error, "` prefix
- Replaced `str(e)` with `sanitize_validation_error(e)` in `server/app.py` websocket_endpoint
- Added 4 unit tests in `tests/test_websocket.py::TestSanitizeValidationError`
- All 1066 tests pass, protocol spec validated

### File List

- `server/net/errors.py` (MODIFIED) — added `sanitize_validation_error()` function
- `server/app.py` (MODIFIED) — replaced `str(e)` with `sanitize_validation_error(e)`, updated import
- `tests/test_websocket.py` (MODIFIED) — added `TestSanitizeValidationError` class with 4 tests
