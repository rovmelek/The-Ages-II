# Story 16.1: WebSocket Inbound Schemas

Status: done

## Story

As a server developer,
I want all 21 WebSocket inbound actions validated by Pydantic schemas at the framework level,
so that handlers can trust input is valid without manual `data.get()` checks, and malformed messages get clear error responses.

## Acceptance Criteria

1. Pydantic schema exists for all 21 inbound actions in `server/net/schemas.py`
2. `ACTION_SCHEMAS` dict maps action string to schema class
3. `ValidationError` returns `{"type": "error", "detail": "..."}` to client with specific field errors
4. Field-presence and type validation removed from handlers — schema handles these (no redundant `data.get()` + manual empty checks for schema-validated fields)
5. Config-dependent range checks REMAIN in handlers — `MAX_CHAT_MESSAGE_LENGTH`, `MIN_USERNAME_LENGTH`, `MIN_PASSWORD_LENGTH` reference runtime `settings.*` values that cannot be baked into class-level schema definitions
6. Actions without required fields (e.g., `inventory`, `pass_turn`, `flee`, `logout`, `look`, `who`, `stats`, `help_actions`, `map`) have schemas with only `action` field
7. Direction validation (`"up"/"down"/"left"/"right"`) happens in schema `field_validator`, not handler
8. `InteractMessage` uses `model_validator` to require at least one of `target_id` or `direction` (rejects both-empty-string)
9. All 808+ tests pass unchanged

## Tasks / Subtasks

- [x] Task 1: Create `server/net/schemas.py` with all 21 schemas (AC: 1, 2, 6, 7, 8)
  - [x] 1.1 `InboundMessage` base class with `action: str`
  - [x] 1.2 Auth schemas: `LoginMessage(username, password)`, `RegisterMessage(username, password)`, `LogoutMessage`
  - [x] 1.3 Movement: `MoveMessage(direction)` with `field_validator` for up/down/left/right
  - [x] 1.4 Chat: `ChatMessage(message, whisper_to?)`, `PartyChatMessage(message)`
  - [x] 1.5 Combat: `PlayCardMessage(card_key)`, `PassTurnMessage`, `FleeMessage`, `UseItemCombatMessage(item_key)`
  - [x] 1.6 Inventory: `InventoryMessage`, `UseItemMessage(item_key)`
  - [x] 1.7 Interact: `InteractMessage(target_id?, direction?)` with `model_validator` requiring at least one
  - [x] 1.8 Query: `LookMessage`, `WhoMessage`, `StatsMessage`, `HelpMessage`, `MapMessage`
  - [x] 1.9 Level-up: `LevelUpMessage(stats: list[str])`
  - [x] 1.10 Social: `TradeMessage(args?)`, `PartyMessage(args?)`
  - [x] 1.11 `ACTION_SCHEMAS` dict mapping all 21 action strings to schema classes
- [x] Task 2: Update `server/app.py` websocket_endpoint to validate via schemas (AC: 3)
  - [x] 2.1 Import `ACTION_SCHEMAS` and `ValidationError`
  - [x] 2.2 After JSON parse + action extraction, look up schema and validate
  - [x] 2.3 On `ValidationError`, send error to client and `continue`
  - [x] 2.4 On valid, replace `data` with `validated.model_dump()` before routing
- [x] Task 3: Remove redundant manual validation from handlers (AC: 4, 5)
  - [x] 3.1 `auth.py`: Remove empty `username`/`password` checks from `handle_login` (lines 117-121)
  - [x] 3.2 `movement.py`: No removal needed — no manual validation existed
  - [x] 3.3 `chat.py`: Keep `MAX_CHAT_MESSAGE_LENGTH` check, keep empty-after-strip check
  - [x] 3.4 `combat.py`: Remove `card_key` and `item_key` empty checks
  - [x] 3.5 `inventory.py`: Remove `item_key` empty check from `handle_use_item`
  - [x] 3.6 `interact.py`: Kept defensive guard for direct handler calls; schema handles framework-level validation
  - [x] 3.7 `levelup.py`: Remove `isinstance(stats, list)` type check
  - [x] 3.8 `party.py`: No changes needed
  - [x] 3.9 `trade.py`: No changes needed
- [x] Task 4: Write unit tests for schemas (AC: 1, 3, 7, 8)
  - [x] 4.1 Test valid input for each schema
  - [x] 4.2 Test missing required fields
  - [x] 4.3 Test wrong types
  - [x] 4.4 Test direction validator rejects invalid values
  - [x] 4.5 Test InteractMessage model_validator rejects both-empty-string
  - [x] 4.6 Test LevelUpMessage accepts list of strings
- [x] Task 5: Run full test suite and verify all 870 pass (AC: 9)

## Dev Notes

### Architecture Constraints

- **New file only**: `server/net/schemas.py` — the only new file. All other changes are modifications.
- **No handler signature changes**: Handlers still receive `(websocket, data, *, game)`. The `data` dict is now guaranteed to have validated fields.
- **No new dependencies**: Pydantic is already in the project (used for `Settings` in `server/core/config.py`).
- **`admin.py` is REST-only** — no WebSocket schemas needed for admin endpoints.

### Schema Design Decisions

- **`action` field on every schema**: Each schema has `action: str = "action_name"` as a literal default. This allows the `ACTION_SCHEMAS` lookup to work after extracting action from the raw dict.
- **Required string fields use `min_length=1`**: Fields like `username`, `password`, `card_key`, `item_key`, `direction`, and `message` (on `ChatMessage`/`PartyChatMessage`) must use `Field(min_length=1)` or `min_length=1` on the type annotation to reject empty strings at schema level. This replaces the handler's `if not field:` checks that Task 3 removes. Without `min_length=1`, Pydantic accepts `""` as a valid string.
- **Optional fields use `| None = None`**: e.g., `whisper_to: str | None = None` on ChatMessage. For `InteractMessage`, use `target_id: str = ""` and `direction: str = ""` (NOT `| None`) to match the current handler semantics where both default to `""` and truthiness checks determine which path to take.
- **`args` on Trade/Party defaults to `""`**: Matches current `data.get("args", "")` behavior. Handler still does `.strip()` and subcommand parsing.
- **`stats` on LevelUpMessage is `list[str]`**: Schema validates it's a list. The handler still validates individual stat names against `_VALID_LEVEL_UP_STATS` and count (config-dependent).

### Integration Point — websocket_endpoint

The validation goes in `server/app.py` websocket_endpoint (lines 385-406), between the `"action" not in data` check (line 399-403) and the `game.router.route()` call (line 404). Note: `websocket_endpoint` does NOT extract `action` into a local variable — it only checks `if "action" not in data`. You must extract it:

```python
from server.net.schemas import ACTION_SCHEMAS
from pydantic import ValidationError

# Insert after the "action" not in data check (after line 403, before line 404):
action = data["action"]  # Safe — the "action" not in data check above guarantees presence
schema_cls = ACTION_SCHEMAS.get(action)
if schema_cls:
    try:
        validated = schema_cls(**data)
        data = validated.model_dump()
    except ValidationError as e:
        await websocket.send_json({"type": "error", "detail": str(e)})
        continue
```

If `action` is not in `ACTION_SCHEMAS` (unknown action), the router handles it with its existing "Unknown action" error.

### Handler Cleanup Rules

**REMOVE** these patterns (schema now validates):
- `data.get("field", "")` followed by `if not field:` for required fields
- `isinstance(stats, list)` type checks
- Direction validation in movement handler

**KEEP** these patterns (config-dependent, runtime values):
- `len(message) > settings.MAX_CHAT_MESSAGE_LENGTH` in `chat.py`
- `len(username) < settings.MIN_USERNAME_LENGTH` in `auth.py:handle_register`
- `len(password) < settings.MIN_PASSWORD_LENGTH` in `auth.py:handle_register`
- Empty-after-strip checks in chat/party_chat (schema enforces `min_length=1` on the raw string, but after `.strip()` a whitespace-only string becomes `""` — handler must still check)
- All game-logic validation (in combat, has item, etc.)

### What NOT To Do

- Do NOT add `request_id` field — that's Story 16.7
- Do NOT modify outbound messages — that's Story 16.2
- Do NOT add `pong` action — that's Story 16.8
- Do NOT add `reconnect` action — that's Story 16.9
- Do NOT change handler signatures or the `@requires_auth` decorator
- Do NOT validate config-dependent ranges in schemas (they read `settings.*` at runtime)

### Current Handler Line References

| Handler File | Action(s) | Fields | Lines with `data.get()` |
|-------------|-----------|--------|------------------------|
| `auth.py` | login | username, password | 114-115 |
| `auth.py` | register | username, password | 44-45 |
| `auth.py` | logout | (none) | — |
| `movement.py` | move | direction | 52 |
| `chat.py` | chat | message, whisper_to | 25, 36 |
| `combat.py` | play_card | card_key | 264 |
| `combat.py` | pass_turn | (none) | — |
| `combat.py` | flee | (none) | — |
| `combat.py` | use_item_combat | item_key | 340 |
| `inventory.py` | inventory | (none) | — |
| `inventory.py` | use_item | item_key | 49 |
| `interact.py` | interact | target_id, direction | 38-39 |
| `query.py` | look, who, stats, help_actions, map | (none) | — |
| `levelup.py` | level_up | stats | 43 |
| `trade.py` | trade | args | 62 |
| `party.py` | party | args | 63 |
| `party.py` | party_chat | message | 476 |

### Testing Strategy

- New test file: `tests/test_inbound_schemas.py` — unit tests for schema validation
- All 808+ existing tests exercise handlers end-to-end via WebSocket messages — they implicitly test schema validation since all messages now pass through schemas
- No existing test changes needed — schemas validate the same rules handlers currently validate manually

### Project Structure Notes

- `server/net/schemas.py` — new file in existing `server/net/` package
- `server/net/__init__.py` — currently empty, no changes needed
- All handler files in `server/net/handlers/` — only removing redundant validation lines

### References

- [Source: _bmad-output/planning-artifacts/epic-16-tech-spec.md#Story 16.1]
- [Source: server/app.py#websocket_endpoint lines 385-406]
- [Source: server/net/message_router.py#route]
- [Source: server/net/auth_middleware.py#requires_auth]
- [Source: server/core/config.py#Settings]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Created `server/net/schemas.py` with 21 Pydantic schemas + `ACTION_SCHEMAS` mapping
- Added schema validation to `server/app.py` websocket_endpoint (between action check and routing)
- Removed redundant empty checks from auth.py (login), combat.py (play_card, use_item_combat), inventory.py (use_item), levelup.py (isinstance)
- Kept interact.py defensive guard for direct handler calls (tests call handler directly, bypassing schema)
- Updated 4 existing tests (test_login.py, test_auth.py) to match new Pydantic error format
- Created `tests/test_inbound_schemas.py` with 53 unit tests
- All 870 tests pass (817 existing + 53 new)

### File List

- **New**: `server/net/schemas.py`
- **New**: `tests/test_inbound_schemas.py`
- **Modified**: `server/app.py` (schema validation in websocket_endpoint)
- **Modified**: `server/net/handlers/auth.py` (removed login empty check)
- **Modified**: `server/net/handlers/combat.py` (removed card_key/item_key empty checks)
- **Modified**: `server/net/handlers/inventory.py` (removed item_key empty check)
- **Modified**: `server/net/handlers/interact.py` (added comment to defensive guard)
- **Modified**: `server/net/handlers/levelup.py` (removed isinstance check)
- **Modified**: `tests/test_login.py` (updated empty credential error assertions)
- **Modified**: `tests/test_auth.py` (updated empty credential error assertions)
