# ISS-031: Fragile Token Error String Matching

**Severity:** Medium
**Status:** Done
**Found during:** Codebase Architecture Review (2026-04-12)

## Problem

The web demo client at `web-demo/js/game.js:605` matches the exact error detail string `'Invalid or expired token'` to trigger credential-based login fallback when token reconnection fails:

```javascript
if (data.detail === 'Invalid or expired token' && gameState.credentials) {
    sessionToken = null;
    sendAction('login', gameState.credentials);
    return;
}
```

The server sends this string from `handle_reconnect()` in `server/net/handlers/auth.py:171`:

```python
await websocket.send_json(
    with_request_id({"type": "error", "detail": "Invalid or expired token"}, data)
)
```

This is fragile string coupling. If the server error message changes (e.g., to "Session expired" or "Token invalid"), the client's reconnection fallback silently breaks — the user gets a generic error instead of automatic re-login.

The server already has a structured `ErrorCode` StrEnum in `server/net/errors.py` with 5 protocol-level codes and a `send_error()` helper. The token expiry error should use this system instead of a raw dict.

## Affected Files

| File | Role |
|------|------|
| `server/net/errors.py` | Add `AUTH_TOKEN_EXPIRED` and `AUTH_TOKEN_MISSING` to `ErrorCode` StrEnum |
| `server/net/handlers/auth.py:163-165` | Use `send_error()` with `AUTH_TOKEN_MISSING` for missing token |
| `server/net/handlers/auth.py:170-173` | Use `send_error()` with `AUTH_TOKEN_EXPIRED` for invalid/expired token |
| `web-demo/js/game.js:605` | Match on `data.code === 'AUTH_TOKEN_EXPIRED'` instead of `data.detail` |
| `tests/test_session_tokens.py:233,249,293` | Update 3 assertions to check for `code` field |

**Out of scope:** `handle_reconnect` line 258-259 ("Player not found") and all raw error dicts in `handle_register`/`handle_login` — these are not fragile string-matched by any client and should be addressed in a separate pass if needed.

## Root Cause

When the reconnection system was implemented (Story 16.9), the `ErrorCode` system didn't exist yet. Story 17.11 added `ErrorCode` and `send_error()` but only applied them to the WebSocket validation loop in `app.py` and the `@requires_auth` middleware — the reconnect handler in `auth.py` was not retrofitted.

## Proposed Fix

1. Add `AUTH_TOKEN_EXPIRED = "AUTH_TOKEN_EXPIRED"` and `AUTH_TOKEN_MISSING = "AUTH_TOKEN_MISSING"` to `ErrorCode` in `server/net/errors.py`
2. In `handle_reconnect()` at `server/net/handlers/auth.py`, import `send_error` and `ErrorCode`, then:
   - Lines 163-165 (missing token): replace raw `send_json()` with `await send_error(websocket, ErrorCode.AUTH_TOKEN_MISSING, "Missing session_token", data)`
   - Lines 170-173 (invalid/expired token): replace raw `send_json()` with `await send_error(websocket, ErrorCode.AUTH_TOKEN_EXPIRED, "Invalid or expired token", data)`
   This adds machine-readable `code` fields while preserving the `detail` string for backward compatibility.
3. In `web-demo/js/game.js:605`, change:
   ```javascript
   if (data.detail === 'Invalid or expired token' && gameState.credentials) {
   ```
   to:
   ```javascript
   if (data.code === 'AUTH_TOKEN_EXPIRED' && gameState.credentials) {
   ```
4. Update 3 test assertions in `tests/test_session_tokens.py` to verify `msg["code"] == "AUTH_TOKEN_EXPIRED"`.

## Impact

- 4 files changed (errors.py, auth.py, game.js, test_session_tokens.py)
- Backward compatible — `send_error()` includes both `code` and `detail`
- Eliminates fragile string matching between server and client
- Establishes pattern for future domain-level error codes
