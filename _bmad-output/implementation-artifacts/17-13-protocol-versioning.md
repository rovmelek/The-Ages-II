# Story 17.13: Protocol Versioning

Status: done

## Story

As a game client developer,
I want the server to include a protocol version in login/reconnect responses,
so that my client can detect protocol mismatches and warn users to update.

## Acceptance Criteria

1. A `PROTOCOL_VERSION` string constant exists (e.g., `"1.0"`) in `server/core/constants.py`.

2. The `login_success` response includes a `"protocol_version"` field with the constant's value — for both login and register paths.

3. `LoginSuccessMessage` in `server/net/outbound_schemas.py` includes `protocol_version: str` field.

4. The protocol spec generator (`scripts/generate_protocol_doc.py`) picks up the new field automatically via schema introspection (no manual doc changes needed).

5. All existing tests pass (`make test`).

6. Protocol spec regenerated (`make protocol-doc`) and validated (`make check-protocol`).

## Tasks / Subtasks

- [x] Task 1: Add `PROTOCOL_VERSION` constant to `server/core/constants.py` (AC: #1)
  - [x] Add `PROTOCOL_VERSION = "1.0"` string constant

- [x] Task 2: Add `protocol_version` to `LoginSuccessMessage` in `server/net/outbound_schemas.py` (AC: #3)
  - [x] Add `protocol_version: str` field (required, no default — forces callers to provide it)

- [x] Task 3: Update `_build_login_response()` in `server/net/handlers/auth.py` (AC: #2)
  - [x] Import `PROTOCOL_VERSION` from `server.core.constants`
  - [x] Add `"protocol_version": PROTOCOL_VERSION` to the result dict in `_build_login_response()`

- [x] Task 4: Update `handle_register` inline response in `server/net/handlers/auth.py` (AC: #2)
  - [x] The register handler builds its own inline `login_success` dict (lines ~192-209) — add `"protocol_version": PROTOCOL_VERSION` there too

- [x] Task 5: Update tests (AC: #5)
  - [x] Update any tests that assert on exact login_success dict structure to include `protocol_version`
  - [x] Run `make test` — all tests must pass

- [x] Task 6: Regenerate protocol spec (AC: #4, #6)
  - [x] Run `make protocol-doc` and `make check-protocol`

## Dev Notes

### Files to Modify

| File | Change |
|------|--------|
| `server/core/constants.py` | Add `PROTOCOL_VERSION = "1.0"` |
| `server/net/outbound_schemas.py` | Add `protocol_version: str` to `LoginSuccessMessage` |
| `server/net/handlers/auth.py` | Add `protocol_version` to `_build_login_response()` and `handle_register` inline dict |

### Current Response Construction

Two code paths produce `login_success`:

1. **`_build_login_response()`** (auth.py lines ~101-128) — used by `handle_login` and `handle_reconnect`
2. **`handle_register` inline dict** (auth.py lines ~192-209) — builds its own dict, does NOT call `_build_login_response()`

Both must include `"protocol_version": PROTOCOL_VERSION`.

### Testing Considerations

- Search for tests asserting on exact `login_success` response dicts — they'll need `"protocol_version": "1.0"` added
- Key test files: `tests/test_auth.py`, `tests/test_session_tokens.py`, `tests/test_reconnect.py`
- Tests checking individual fields (e.g., `resp["entity_id"]`) will be unaffected

### What NOT to Do

- Do NOT add `protocol_version` to non-login messages (room_state, combat_state, etc.)
- Do NOT make `protocol_version` configurable in settings — it's a code constant that changes with protocol changes

### References

- [Source: _bmad-output/planning-artifacts/epics.md#FR138] — Protocol versioning requirement
- [Source: CLAUDE.md#Epic 17 Key Decisions] — ADR-17-5 scoping

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6
### Debug Log References
### Completion Notes List
- Added PROTOCOL_VERSION = "1.0" to server/core/constants.py
- Added protocol_version field to LoginSuccessMessage schema
- Updated _build_login_response() and handle_register inline dict
- Fixed 3 tests constructing LoginSuccessMessage directly
- Protocol spec regenerated, 1066 tests pass
### File List
- server/core/constants.py (MODIFIED)
- server/net/outbound_schemas.py (MODIFIED)
- server/net/handlers/auth.py (MODIFIED)
- tests/test_outbound_schemas.py (MODIFIED)
- tests/test_session_tokens.py (MODIFIED)
- _bmad-output/planning-artifacts/protocol-spec.md (REGENERATED)
