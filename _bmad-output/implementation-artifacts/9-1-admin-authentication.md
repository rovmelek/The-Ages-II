# Story 9.1: Admin Authentication

Status: done

## Story

As a server operator,
I want to authenticate as an admin using a shared secret,
so that only authorized users can trigger server management commands.

## Acceptance Criteria

1. **Given** the server configuration,
   **When** the story is complete,
   **Then** `ADMIN_SECRET` is added to `Settings` (Pydantic BaseSettings) in `server/core/config.py` with default `""` (empty string = disabled).

2. **Given** an admin REST endpoint is called without the correct secret,
   **When** the request is processed,
   **Then** it is rejected with 403 Forbidden.

3. **Given** `ADMIN_SECRET` is not configured (empty/None),
   **When** any admin endpoint is called,
   **Then** it is rejected with 403 Forbidden and a log warning "Admin endpoints disabled — ADMIN_SECRET not configured".

4. **Given** the admin secret is provided correctly via `Authorization: Bearer <secret>` header,
   **When** the request is processed,
   **Then** the admin action proceeds normally.

5. **And** all existing tests pass after implementation.

## Tasks / Subtasks

- [x] Task 1: Add ADMIN_SECRET to config (AC: 1)
  - [x] In `server/core/config.py`: add `ADMIN_SECRET: str = ""` to `Settings` class
  - [x] Empty string means admin features are disabled

- [x] Task 2: Create admin dependency (AC: 2, 3, 4)
  - [x] Create `server/net/handlers/admin.py`
  - [x] Implement `verify_admin_secret()` as a FastAPI dependency using `Depends`
  - [x] Extract secret from `Authorization: Bearer <secret>` header
  - [x] If `settings.ADMIN_SECRET` is empty/falsy: log warning "Admin endpoints disabled — ADMIN_SECRET not configured", raise `HTTPException(403)`
  - [x] If secret doesn't match: raise `HTTPException(403, detail="Forbidden")`
  - [x] If secret matches: return (allow request to proceed)

- [x] Task 3: Create admin router with placeholder endpoint (AC: 2, 3, 4)
  - [x] In `server/net/handlers/admin.py`: create `admin_router = APIRouter(prefix="/admin", tags=["admin"])`
  - [x] Add `GET /admin/status` endpoint (protected by `verify_admin_secret`) returning `{"status": "ok", "admin": true}` — serves as auth verification endpoint
  - [x] In `server/app.py`: import and include `admin_router` on the FastAPI app (after app creation, before mount)

- [x] Task 4: Write tests (AC: 1-5)
  - [x] Create `tests/test_admin.py`
  - [x] Test: request without Authorization header → 403
  - [x] Test: request with wrong secret → 403
  - [x] Test: request with correct secret → 200
  - [x] Test: ADMIN_SECRET empty → 403 + warning logged
  - [x] Test: existing tests still pass (`pytest tests/`) — 379 passed

## Dev Notes

### Architecture Compliance

- **Config pattern**: Follow existing `Settings` class in `server/core/config.py` — Pydantic BaseSettings, module-level `settings = Settings()` singleton
- **Handler location**: `server/net/handlers/admin.py` — follows existing handler module pattern
- **REST endpoints**: Use FastAPI `APIRouter` with prefix — this is the first REST-based handler (all others are WebSocket). Include the router on the `app` object in `server/app.py`
- **No WebSocket**: Admin commands use REST (POST/GET), NOT WebSocket messages

### Key Implementation Details

- `ADMIN_SECRET` default is `""` (empty string) — server starts fine without it, admin endpoints just reject all requests
- Use `fastapi.security.HTTPBearer` or manual header parsing for `Authorization: Bearer <secret>` extraction
- Use `hmac.compare_digest()` for constant-time secret comparison (prevent timing attacks)
- FastAPI `Depends()` pattern for reusable auth dependency across all admin endpoints (9.2 and 9.3 will reuse this)
- Log warning at request time (not startup) when ADMIN_SECRET is not configured

### Existing Patterns to Follow

- `from __future__ import annotations` as first import in every new module
- `__init__.py` in every package directory (already exists for `server/net/handlers/`)
- Logging: `logger = logging.getLogger(__name__)`
- Error responses for REST: `HTTPException` (not `{"type": "error", ..."}` which is WebSocket pattern)

### Testing Patterns

- Use `httpx.AsyncClient` with `app` for REST endpoint testing (not WebSocket test client)
- Use `from server.app import app` and override settings for tests
- `monkeypatch` or environment variables to set `ADMIN_SECRET` in tests
- `pytest-asyncio` with `asyncio_mode = "auto"`

### Project Structure Notes

- New file: `server/net/handlers/admin.py` (admin router + auth dependency)
- Modified: `server/core/config.py` (add ADMIN_SECRET)
- Modified: `server/app.py` (include admin_router)
- New test: `tests/test_admin.py`

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 9.1]
- [Source: _bmad-output/planning-artifacts/architecture.md#3.1 Directory Structure]
- [Source: _bmad-output/project-context.md#Technology Stack & Versions]
- [Source: server/core/config.py — existing Settings class]
- [Source: server/app.py — app setup and handler registration pattern]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Added `ADMIN_SECRET: str = ""` to Settings in `server/core/config.py`
- Created `server/net/handlers/admin.py` with `verify_admin_secret` dependency and `admin_router` with `GET /admin/status`
- Uses `hmac.compare_digest()` for constant-time secret comparison
- Logs warning when ADMIN_SECRET not configured
- Included admin_router in `server/app.py`
- 5 new tests in `tests/test_admin.py` — all pass
- 379 existing tests pass (0 regressions)

### File List

- server/core/config.py (modified — added ADMIN_SECRET)
- server/net/handlers/admin.py (new — admin router + auth dependency)
- server/app.py (modified — include admin_router)
- tests/test_admin.py (new — 5 admin auth tests)
