# Story 16.9: Session Tokens for Reconnection

Status: done

## Story

As a **player whose connection dropped**,
I want to reconnect using a session token instead of re-typing my password,
So that brief network interruptions don't require full re-authentication.

## Acceptance Criteria

1. **Given** a player successfully logs in,
   **When** the `login_success` response is sent,
   **Then** it includes a `session_token` field (cryptographically random, `secrets.token_urlsafe(32)`).

2. **Given** a player sends `{"action": "reconnect", "session_token": "..."}`,
   **When** the token is valid and a disconnected session exists (Case 1: grace period resume),
   **Then** the deferred cleanup timer is cancelled, `disconnected_at` cleared, `entity.connected` set to `True`, WebSocket re-registered, `entity_entered` broadcast to room,
   **And** the player receives `login_success` (with new token) + `room_state` + combat state if applicable.

3. **Given** a valid token but no session exists (Case 2: grace expired / full DB restore),
   **When** `handle_reconnect` runs,
   **Then** the player is restored from DB using Story 16.5's helpers (`_resolve_stats`, `_resolve_room_and_place`, `_hydrate_inventory`, `_build_login_response`),
   **And** a new session is created (same as login, skip password check).

4. **Given** an invalid or expired token (Case 3),
   **When** `handle_reconnect` runs,
   **Then** the client receives `{"type": "error", "detail": "Invalid or expired token"}`.

5. **Given** a valid token used for reconnection,
   **When** the reconnect succeeds (Case 1 or Case 2),
   **Then** the old token is consumed (revoked) and a new token is issued in the response (single-use — prevents replay attacks).

6. **Given** a WebSocket that already has a different player's session,
   **When** a reconnect for a different player arrives on that WebSocket,
   **Then** the existing session is cleaned up first (prevents session hijacking).

7. **Given** a player explicitly logs out,
   **When** logout completes,
   **Then** the player's token is revoked via `token_store.revoke_for_player(db_id)`.

8. **Given** the `TokenStore` over time,
   **When** `issue()` is called,
   **Then** `_purge_expired()` runs first — removes all expired tokens, preventing unbounded memory growth.

9. **Given** all existing tests,
   **When** Story 16.9 is implemented,
   **Then** all tests pass unchanged.

10. **Given** the web-demo client,
    **When** the player receives a `login_success` with `session_token`,
    **Then** the client stores the token and uses it for reconnection via `{"action": "reconnect", "session_token": "..."}` instead of re-sending credentials.

11. **Given** `SESSION_TOKEN_TTL_SECONDS` (default 300),
    **When** a token expires,
    **Then** `validate()` returns `None` and the token is cleaned up.

12. **Given** a player that logs in,
    **When** an existing token exists for that player,
    **Then** `issue()` revokes the old token before issuing a new one (one active token per player).

## Tasks / Subtasks

- [x] Task 1: Create `server/player/tokens.py` — TokenStore class (AC: #1, #5, #8, #11, #12)
  - [x] 1.1: `generate_session_token()` using `secrets.token_urlsafe(32)`
  - [x] 1.2: `TokenStore.__init__` — `_tokens: dict[str, tuple[int, float]]` (token -> (db_id, expires_at))
  - [x] 1.3: `TokenStore.issue(db_id)` — purge expired, revoke existing for db_id, generate new, store with TTL
  - [x] 1.4: `TokenStore.validate(token)` — return db_id if valid and not expired, else None
  - [x] 1.5: `TokenStore.revoke(token)` — remove a specific token
  - [x] 1.6: `TokenStore.revoke_for_player(db_id)` — remove all tokens for a player
  - [x] 1.7: `TokenStore._purge_expired()` — filter out expired tokens

- [x] Task 2: Add config setting (AC: #11)
  - [x] 2.1: Add `SESSION_TOKEN_TTL_SECONDS: int = 300` to `Settings` in `server/core/config.py` (after `HEARTBEAT_TIMEOUT_SECONDS`)

- [x] Task 3: Add `TokenStore` and stub fields to `Game` and dataclasses (AC: #1, #2)
  - [x] 3.1: Import `TokenStore` from `server.player.tokens` in `server/app.py`
  - [x] 3.2: Add `self.token_store = TokenStore()` to `Game.__init__` (after `self._pong_events`)
  - [x] 3.3: Add `self._cleanup_handles: dict[str, asyncio.TimerHandle] = {}` to `Game.__init__` (stub for Story 16.10)
  - [x] 3.4: Add `disconnected_at: float | None = None` field to `PlayerSession` dataclass (`server/player/session.py`)
  - [x] 3.5: Add `connected: bool = True` field to `PlayerEntity` dataclass (`server/player/entity.py`)

- [x] Task 4: Add `ReconnectMessage` inbound schema (AC: #2)
  - [x] 4.1: Add `ReconnectMessage(InboundMessage)` with `action: str = "reconnect"` and `session_token: str = Field(min_length=1)` to `server/net/schemas.py`
  - [x] 4.2: Add `"reconnect": ReconnectMessage` to `ACTION_SCHEMAS` dict

- [x] Task 5: Add `session_token` to `LoginSuccessMessage` outbound schema (AC: #1)
  - [x] 5.1: Add `session_token: str | None = None` to `LoginSuccessMessage` in `server/net/outbound_schemas.py`

- [x] Task 6: Modify `handle_login` to issue and include token (AC: #1)
  - [x] 6.1: In `handle_login`, issue token via `game.token_store.issue(player.id)` and pass `session_token=token` to `_build_login_response()`

- [x] Task 7: Add `handle_reconnect` handler (AC: #2, #3, #4, #5, #6)
  - [x] 7.1: New function `handle_reconnect(websocket, data, *, game)` — NOT decorated with `@requires_auth`
  - [x] 7.2: Validate token presence and validity
  - [x] 7.3: Handle security cleanup (WebSocket already has different player session)
  - [x] 7.4: Case 1 — grace period resume with race condition guard
  - [x] 7.5: Case 2 — full DB restore using Story 16.5 helpers
  - [x] 7.6: Issue new token on success (both cases)
  - [x] 7.7: Start heartbeat after successful reconnect

- [x] Task 8: Register `reconnect` action handler (AC: #2)
  - [x] 8.1: Register `reconnect` handler in `Game._register_handlers()`
  - [x] 8.2: Import `handle_reconnect` alongside other auth handlers

- [x] Task 9: Revoke token on logout (AC: #7)
  - [x] 9.1: Add `game.token_store.revoke_for_player(player_info.db_id)` before cleanup in `handle_logout`

- [x] Task 10: Update web-demo client (AC: #10)
  - [x] 10.1: Store `session_token` from `login_success` response
  - [x] 10.2: Try token-based reconnect first; fall back to credentials on failure

- [x] Task 11: Write tests (AC: #1-#12)
  - [x] 11.1: Unit tests for `TokenStore`: issue, validate, revoke, expiry, revoke_for_player, single-use, purge_expired
  - [x] 11.2: Test `handle_login` includes `session_token` in response
  - [x] 11.3: Test `handle_reconnect` Case 2 (full DB restore)
  - [x] 11.4: Test invalid/expired token returns error
  - [x] 11.5: Test token single-use (consumed on reconnect)
  - [x] 11.6: Test logout revokes token
  - [x] 11.7: Test WebSocket with existing session — cleanup before reconnect
  - [x] 11.8: Run `make test` — all 1031 tests pass

## Dev Notes

### TokenStore Implementation

New file: `server/player/tokens.py` (~60 lines). In-memory token store, not DB-backed (ADR-16-2). Uses `secrets.token_urlsafe(32)` for cryptographic randomness, `time.time()` for expiry tracking.

```python
# Key structure:
_tokens: dict[str, tuple[int, float]]  # token -> (db_id, expires_at)
```

- `issue()` calls `_purge_expired()` first to bound memory, then revokes any existing token for the same `db_id` (one active token per player), then generates and stores a new token
- `validate()` returns `db_id` if token exists and not expired, else `None`
- `revoke()` and `revoke_for_player()` remove tokens from the dict
- TTL from `settings.SESSION_TOKEN_TTL_SECONDS` (default 300s = 5 min)

### handle_reconnect — Three Outcomes

`handle_reconnect` is NOT decorated with `@requires_auth` — it's a pre-auth handler (same as `handle_login` and `handle_register`).

**Case 1 — Grace period resume** (Story 16.9 adds `disconnected_at` as a stub field defaulting to `None`; this code path won't trigger until Story 16.10 sets `disconnected_at` to a non-None value during deferred disconnect):
- Session exists with `disconnected_at` set
- Cancel deferred cleanup timer from `game._cleanup_handles`
- Clear `disconnected_at`, set `entity.connected = True`
- Re-register WebSocket via `game.connection_manager.connect()`
- Broadcast `entity_entered` to room
- Send `login_success` + `room_state` + combat state

**Case 2 — Full DB restore** (primary path until 16.10):
- No session exists (grace expired or server restarted)
- Token proves identity — skip password check
- Reuse Story 16.5 helpers: `_resolve_stats`, `_resolve_room_and_place`, `_hydrate_inventory`, `_build_login_response`
- Same restore flow as `handle_login` lines 255-294

**Case 3 — Invalid/expired token:**
- Return `{"type": "error", "detail": "Invalid or expired token"}`

### Security: Existing Session Cleanup

Before reconnecting, check `game.connection_manager.get_entity_id(websocket)`. If the WebSocket already has a different player logged in, clean up that session first (same pattern as `handle_login` lines 249-254). This prevents session hijacking via stolen token on an already-authenticated connection.

### Integration with Story 16.10 (Grace Period)

Story 16.9 adds the following as **stub fields** (Task 3.3-3.5) so that Case 1 code compiles and is testable:
- `disconnected_at: float | None = None` on `PlayerSession` (`server/player/session.py`) — defaults to `None`
- `connected: bool = True` on `PlayerEntity` (`server/player/entity.py`) — defaults to `True`
- `self._cleanup_handles: dict[str, asyncio.TimerHandle] = {}` on `Game.__init__`

Story 16.10 will **populate** these fields with meaningful values:
- `handle_disconnect` will set `disconnected_at` to `time.time()` and `entity.connected = False`
- `handle_disconnect` will store cleanup timer handles in `_cleanup_handles`
- Until 16.10, `disconnected_at` is always `None`, so Case 1 never triggers (Case 2 is the only active reconnect path)

### Race Condition in Case 1

When popping `game._cleanup_handles[entity_id]` and cancelling the timer, there's a window where the cleanup timer could fire between token validation and the `pop()`. After cancelling the handle, re-check that the session still exists (`game.player_manager.get_session(entity_id)`) before proceeding. If it was cleaned up, fall through to Case 2 (full DB restore).

### handle_register Intentionally Omits Token

`handle_register` (`server/net/handlers/auth.py:167-217`) also sends `login_success` but does NOT create a full session (no room placement, no entity, no `player_manager.set_session`). It intentionally omits `session_token` — there's no session to reconnect to. The web-demo client must handle `login_success` without `session_token` (only store token if present in response).

### Heartbeat on Reconnect

After successful reconnect (both Case 1 and Case 2), call `game._start_heartbeat(entity_id)` to restart the heartbeat loop for the new WebSocket (same as `handle_login` line 294).

### Inbound Schema

Add `ReconnectMessage` to `server/net/schemas.py`:
```python
class ReconnectMessage(InboundMessage):
    action: str = "reconnect"
    session_token: str = Field(min_length=1)
```
Add to `ACTION_SCHEMAS`: `"reconnect": ReconnectMessage`.

### Outbound Schema

Add `session_token: str | None = None` to `LoginSuccessMessage` in `server/net/outbound_schemas.py:157-163`. This is the Pydantic outbound schema (documentation/validation only — handlers use raw dicts). Separately, `_build_login_response` (auth.py line 102) already accepts `session_token` as a dict-builder parameter — these are two independent changes (Task 5.1 for schema, Task 6.1 for dict-builder call).

### Files to Modify

| File | Change |
|------|--------|
| `server/player/tokens.py` | **New** — TokenStore class (~60 lines) |
| `server/core/config.py` | Add `SESSION_TOKEN_TTL_SECONDS: int = 300` after `HEARTBEAT_TIMEOUT_SECONDS` (line 81) |
| `server/app.py:38-54` | Import TokenStore, add `self.token_store = TokenStore()` and `self._cleanup_handles: dict = {}` to `Game.__init__` |
| `server/app.py:150-243` | Register `reconnect` handler, import `handle_reconnect` |
| `server/net/handlers/auth.py:100-132` | `_build_login_response` already accepts `session_token` param |
| `server/net/handlers/auth.py:238-294` | `handle_login` — issue token, pass to `_build_login_response` |
| `server/net/handlers/auth.py:140-153` | `handle_logout` — revoke token |
| `server/net/handlers/auth.py` | New `handle_reconnect` function |
| `server/net/schemas.py` | Add `ReconnectMessage`, update `ACTION_SCHEMAS` |
| `server/net/outbound_schemas.py:157-163` | Add `session_token` field to `LoginSuccessMessage` |
| `server/player/session.py:12-20` | Add `disconnected_at: float \| None = None` stub field |
| `server/player/entity.py` | Add `connected: bool = True` stub field to `PlayerEntity` |
| `web-demo/js/game.js` | Store token, use for reconnect |
| `tests/test_session_tokens.py` | **New** — TokenStore + reconnect handler tests |

### Key Patterns to Follow

- **Handler registration**: `self.router.register("reconnect", lambda ws, d: handle_reconnect(ws, d, game=self))` — same lambda pattern as all other handlers
- **No `@requires_auth`** on `handle_reconnect` — it's pre-auth (like login/register)
- **Token in login response**: `_build_login_response` already has `session_token` param (line 102), just need to pass it
- **`with_request_id`**: Wrap error and success responses with `with_request_id(response, data)` for request correlation (Story 16.7)
- **DB access**: Use `async with game.transaction() as session:` — never import `async_session` directly

### Project Structure Notes

- `server/player/tokens.py` goes in the player domain (token = player identity concept)
- Token is purely server-side; client just stores and sends it as opaque string
- No Alembic migration needed — TokenStore is in-memory only

### References

- [Source: _bmad-output/planning-artifacts/epic-16-tech-spec.md#Story-16.9] — Full implementation spec (lines 916-1143)
- [Source: _bmad-output/planning-artifacts/epics.md#Story-16.9] — BDD acceptance criteria (lines 4418-4470)
- [Source: server/net/handlers/auth.py:100-132] — `_build_login_response` already accepts `session_token` param
- [Source: server/net/handlers/auth.py:238-294] — `handle_login` flow to replicate in reconnect Case 2
- [Source: server/player/manager.py:55-78] — `cleanup_session` (called by handle_disconnect)
- [Source: server/app.py:38-54] — `Game.__init__` (add TokenStore)
- [Source: server/app.py:150-243] — `_register_handlers` (register reconnect)
- [Source: server/core/config.py:79-81] — Settings heartbeat section (add SESSION_TOKEN_TTL_SECONDS nearby)
- [Source: epic-16-tech-spec.md ADR-16-2] — In-memory TokenStore, not DB-backed

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Completion Notes List

- Created `server/player/tokens.py` with `TokenStore` class (~55 lines) — in-memory token store with issue/validate/revoke/purge
- Added `SESSION_TOKEN_TTL_SECONDS: int = 300` to Settings
- Added `token_store` and `_cleanup_handles` stub to `Game.__init__`
- Added `disconnected_at` stub to `PlayerSession`, `connected` stub to `PlayerEntity`
- Added `ReconnectMessage` inbound schema + `ACTION_SCHEMAS` entry (now 23 entries)
- Added `session_token` field to `LoginSuccessMessage` outbound schema
- Modified `handle_login` to issue and include token in response
- Added `handle_reconnect` handler with Case 1 (grace period resume), Case 2 (full DB restore), Case 3 (invalid token)
- Case 1 includes race condition guard: re-checks session after cancelling cleanup handle
- Case 2 reuses Story 16.5 helpers: `_resolve_stats`, `_resolve_room_and_place`, `_hydrate_inventory`, `_build_login_response`
- Registered `reconnect` handler in `Game._register_handlers()`
- Added token revocation to `handle_logout`
- Updated web-demo client: stores token, tries token reconnect first, falls back to credentials
- Updated `test_inbound_schemas.py`: 22→23 schema count + `reconnect` key
- 29 new tests in `test_session_tokens.py`, 1031 total passing

### File List

- `server/player/tokens.py` — **New**: TokenStore class
- `server/core/config.py` — Modified: added SESSION_TOKEN_TTL_SECONDS
- `server/app.py` — Modified: import TokenStore, add token_store + _cleanup_handles to Game.__init__, register reconnect handler
- `server/player/session.py` — Modified: added disconnected_at stub field
- `server/player/entity.py` — Modified: added connected stub field
- `server/net/schemas.py` — Modified: ReconnectMessage class + ACTION_SCHEMAS entry
- `server/net/outbound_schemas.py` — Modified: session_token field on LoginSuccessMessage
- `server/net/handlers/auth.py` — Modified: token in login, revoke on logout, handle_reconnect handler
- `web-demo/js/game.js` — Modified: sessionToken variable, token storage, token-based reconnect with fallback
- `tests/test_session_tokens.py` — **New**: 29 tests for TokenStore + reconnect handler
- `tests/test_inbound_schemas.py` — Modified: updated schema count 22→23 + reconnect key
