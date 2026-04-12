# ISS-029: Dead Code — server/web/ and server/net/websocket.py

**Severity:** Low
**Component:** server/web/__init__.py, server/net/websocket.py
**Found during:** Codebase review (adversarial analysis)

## Description

Two vestigial files contain dead code:

### `server/web/__init__.py`
An empty module with no other files in the directory. The web demo is served directly from `app.py` via `StaticFiles` and `FileResponse` mounting. This module serves no purpose.

### `server/net/websocket.py`
Defines `create_websocket_endpoint()` which is never called. The WebSocket endpoint is defined inline in `server/app.py` at the `@app.websocket("/ws/game")` route. This file is vestigial from an earlier architecture.

## Root Cause

`server/web/` was likely scaffolded during project setup and never used. `server/net/websocket.py` was superseded when the WebSocket endpoint was moved inline to `app.py`.

## Proposed Fix

Delete both files:
- `server/web/__init__.py` (and remove the `server/web/` directory)
- `server/net/websocket.py`

## Impact

- Removes confusion for developers navigating the codebase
- No functional impact — code is unused
