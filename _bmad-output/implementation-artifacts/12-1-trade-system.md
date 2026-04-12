# Story 12.1: Trade System

Status: done

## Story

As a player,
I want to initiate a mutual trade session with another player in my room,
so that I can exchange items with other players through a fair, consent-based process.

## Acceptance Criteria

1. **Given** two players are in the same room, **When** Player A sends `/trade @PlayerB`, **Then** Player B receives a `trade_request` message containing Player A's name, **And** Player B can `/trade accept` to enter negotiation or `/trade reject` to decline.

2. **Given** a trade request is pending, **When** 30 seconds pass without a response, **Then** the request auto-cancels and both players are notified.

3. **Given** both players are in a negotiating session, **When** Player A sends `/trade offer healing_potion 2`, **Then** the item is validated (exists in inventory, sufficient quantity, `tradeable` flag is true), **And** the offer is added to Player A's offer list, **And** both players receive a `trade_update` message showing current offers from both sides.

4. **Given** both players are in a negotiating session, **When** Player A sends `/trade offer healing_potion 2 fire_essence 1` (multi-item syntax), **Then** both items are validated and added to Player A's offer list.

5. **Given** a player's offer list contains items, **When** the player sends `/trade remove healing_potion`, **Then** the item is removed from their offer list, **And** both players' ready state is reset.

6. **Given** a player tries to offer more items than `MAX_TRADE_ITEMS` (default 10), **When** the offer would exceed the limit, **Then** the offer is rejected with an error message.

7. **Given** a player sends `/trade offer` with insufficient quantity, **When** the player has fewer items than offered, **Then** the offer is rejected with "You only have N of item_name".

8. **Given** both players are in a session, **When** either player sends `/trade ready`, **Then** that player's ready flag is set, **And** both players are notified of the ready state change.

9. **Given** both players have sent `/trade ready`, **When** both ready flags are set, **Then** the trade executes atomically (see Story 12.2 for validation).

10. **Given** either player sends `/trade cancel`, **Then** the session is cancelled and both players are notified.

11. **Given** a player adds or removes an offer, **When** either player was previously marked ready, **Then** both players' ready state is reset (bait-and-switch prevention).

12. **Given** a trade session completes, is cancelled, rejected, or times out, **When** a player tries to initiate a new trade, **Then** a 5-second cooldown applies before a new `/trade @player` is allowed.

13. **Given** a player is not in an active trade session, **When** they send `/trade` (no subcommand), **Then** they receive "You are not in a trade session".

14. **Given** a player is in an active trade session, **When** they send `/trade` (no subcommand), **Then** they see current offers from both sides and ready status.

15. **Given** the client sends a trade action with raw args string, **When** the trade handler processes it, **Then** the handler parses the first arg as subcommand and remaining args as parameters (server-side parsing), **And** invalid subcommands return an error: "Unknown trade command. Use /help for options".

16. **Given** existing item JSON files don't include a `tradeable` field, **When** items are loaded from JSON at startup, **Then** `tradeable` defaults to `True` — all existing items are tradeable by default.

17. **Given** the existing `_cleanup_player` disconnect handler, **When** Story 12.1 adds trade cancellation, **Then** the full cleanup order is established: (1) cancel trades, (2) remove from combat [existing], (3) party cleanup [placeholder for 12.3], (4) save state [existing], (5) remove from room [existing], (6) notify [existing].

18. **Given** the system needs player name resolution, **When** any `/trade @player` is processed, **Then** `ConnectionManager` provides a name → entity_id index for lookup (maintained on connect/disconnect).

## Tasks / Subtasks

- [x] Task 1: Add `tradeable` field to `ItemDef` and `Item` model (AC: #16)
  - [x] 1.1: Add `tradeable: bool = True` field to `ItemDef` dataclass in `server/items/item_def.py` (after `description` field, line 23)
  - [x] 1.2: Add `tradeable` column to `Item` model in `server/items/models.py` (after `description`, line 20)
  - [x] 1.3: Update `ItemDef.from_db()` to read `tradeable` from the DB model
  - [x] 1.4: Update `ItemDef.to_dict()` to include `tradeable`
  - [x] 1.5: Update `item_repo.load_items_from_json()` to read `tradeable` with `data.get("tradeable", True)` default
  - [x] 1.6: Delete `data/game.db` so schema recreates with new column (no Alembic)

- [x] Task 2: Add trade config settings (AC: #2, #6, #12)
  - [x] 2.1: Add to `Settings` class in `server/core/config.py` (after `ADMIN_SECRET`, line 30):
    - `TRADE_SESSION_TIMEOUT_SECONDS: int = 60`
    - `TRADE_REQUEST_TIMEOUT_SECONDS: int = 30`
    - `MAX_TRADE_ITEMS: int = 10`

- [x] Task 3: Add name→entity_id index to `ConnectionManager` (AC: #18)
  - [x] 3.1: Add `_name_to_entity: dict[str, str] = {}` to `__init__` in `server/net/connection_manager.py` (line 13)
  - [x] 3.2: Update `connect()` signature to accept `name: str` parameter; store `self._name_to_entity[name.lower()] = entity_id`
  - [x] 3.3: Update `disconnect()` to remove the name entry (reverse lookup from entity_id via `_connections` or store a parallel `_entity_to_name` dict)
  - [x] 3.4: Add `get_entity_id_by_name(self, name: str) -> str | None` method that does case-insensitive lookup
  - [x] 3.5: Update the `connect()` call site in `handle_login` (`server/net/handlers/auth.py`, line 287) to pass `name=player.username`

- [x] Task 4: Create `server/trade/` package with TradeManager (AC: #1-15)
  - [x] 4.1: Create `server/trade/__init__.py`
  - [x] 4.2: Create `server/trade/manager.py` with:
    - `Trade` dataclass: `trade_id: str`, `player_a: str` (entity_id), `player_b: str` (entity_id), `state: str`, `offers_a: dict[str, int]` (item_key→qty), `offers_b: dict[str, int]`, `ready_a: bool`, `ready_b: bool`, `created_at: float`, `timeout_handle: asyncio.TimerHandle | None`
    - State machine: `request_pending → negotiating → one_ready → both_ready → executing → complete`
    - `TradeManager` class with `asyncio.Lock`:
      - `initiate_trade(initiator_id, target_id) -> Trade | str` — validates same room, not in combat, not in trade, cooldown; creates session with `request_pending` state; schedules request timeout
      - `accept_trade(entity_id) -> Trade | str`
      - `reject_trade(entity_id) -> Trade | str`
      - `add_offer(entity_id, item_key, quantity) -> Trade | str` — validates inventory quantity, tradeable flag, MAX_TRADE_ITEMS; resets both ready flags
      - `remove_offer(entity_id, item_key) -> Trade | str` — resets both ready flags
      - `set_ready(entity_id) -> Trade | str`
      - `cancel_trade(entity_id) -> Trade | str`
      - `get_trade(entity_id) -> Trade | None`
      - `cancel_trades_for(entity_id)` — for disconnect/room-change cleanup; returns cancelled trade or None
      - `get_trade_status(entity_id) -> dict | None` — current offers + ready state
    - Cooldown tracking: `_cooldowns: dict[str, float]` (entity_id → timestamp)

- [x] Task 5: Create `server/net/handlers/trade.py` (AC: #1-15)
  - [x] 5.1: Create handler with signature `async def handle_trade(websocket: WebSocket, data: dict, *, game: Game) -> None`
  - [x] 5.2: Parse `data.get("args", "")` — split into subcommand + params (same pattern as existing handlers)
  - [x] 5.3: Subcommand dispatch:
    - No args + not in trade → "You are not in a trade session"
    - No args + in trade → show current status
    - `@PlayerName` → initiate trade (resolve name via `game.connection_manager.get_entity_id_by_name()`)
    - `accept` → accept pending request
    - `reject` → reject pending request
    - `offer <item_name> [qty] [item_name qty ...]` → add offer (resolve display names to item_keys, consistent with `/use` pattern from ISS-010)
    - `remove <item_name>` → remove offer
    - `ready` → set ready; if both ready, execute trade
    - `cancel` → cancel session
    - Unknown → "Unknown trade command. Use /help for options"
  - [x] 5.4: Item name resolution (server-side): iterate player's inventory — match by `item_key` first, then case-insensitive `item_def.name`. This is new server-side logic (the existing `/use` handler resolves names client-side in `game.js`, not server-side).
  - [x] 5.5: Trade execution (AC #9): when both ready, perform a basic inventory swap — remove offered items from each player's `Inventory`, add received items, persist both inventories via `player_repo.update_inventory()`. Note: Story 12.2 hardens this with re-validation of all items at execution time, atomic single-transaction DB swap, and crash safety. Story 12.1 implements the happy-path flow.
  - [x] 5.6: Send appropriate messages to both players at each state transition

- [x] Task 6: Add TradeManager to Game class (AC: #17)
  - [x] 6.1: Import and instantiate `TradeManager` in `Game.__init__()` in `server/app.py` (after `combat_manager`, line 39): `self.trade_manager = TradeManager()`
  - [x] 6.2: Register trade handler in `_register_handlers()` (after level_up registration, line 192): `self.router.register("trade", lambda ws, d: handle_trade(ws, d, game=self))`
  - [x] 6.3: Import trade handler at top of `_register_handlers()` method

- [x] Task 7: Update `_cleanup_player` disconnect order (AC: #17)
  - [x] 7.1: In `_cleanup_player` (`server/net/handlers/auth.py`, line 25), add trade cancellation as Step 0 (before combat cleanup on line 40):
    ```python
    # 0. Cancel active trades
    cancelled = game.trade_manager.cancel_trades_for(entity_id)
    if cancelled:
        # Notify the other player
        other_id = cancelled.player_b if cancelled.player_a == entity_id else cancelled.player_a
        await game.connection_manager.send_to_player(other_id, {
            "type": "trade_result", "status": "cancelled",
            "reason": "Trade cancelled — player disconnected"
        })
    ```

- [x] Task 8: Update web client (AC: #1, #3, #8, #10, #14, #15)
  - [x] 8.1: Add `/trade` to `COMMANDS` object in `web-demo/js/game.js` (before line 253, before closing `}`):
    ```javascript
    trade: {
      handler: (args) => sendAction('trade', { args: args.join(' ') }),
      description: 'Trade items with another player',
      usage: '/trade @player | accept | reject | offer <item> [qty] | remove <item> | ready | cancel',
    },
    ```
  - [x] 8.2: Add trade message handlers to `dispatchMessage()` (in handlers object, line 424):
    - `trade_request`: show incoming trade request in chat
    - `trade_update`: show current offers from both sides
    - `trade_result`: show trade completion/cancellation result
  - [x] 8.3: Create simple handler functions for trade message types (display in chat log with distinct formatting)

- [x] Task 9: Update `/help` output (AC: #15)
  - [x] 9.1: Server-side `/help` auto-includes registered actions (from `game.router._handlers.keys()`), so registering `trade` action automatically adds it
  - [x] 9.2: Client-side `/help` auto-includes new COMMANDS entries, so adding `trade` to COMMANDS is sufficient

- [x] Task 10: Write tests
  - [x] 10.1: Create `tests/test_trade.py` with tests for:
    - Trade initiation (same room, different room rejection)
    - Accept/reject flow
    - Offer validation (quantity, tradeable flag, MAX_TRADE_ITEMS)
    - Ready state and bait-and-switch reset
    - Cancel flow
    - Disconnect cleanup (cancel on disconnect)
    - Cooldown enforcement
    - Self-trade prevention
    - Name resolution (case-insensitive)
    - Status display (no subcommand with/without active session)
    - Invalid subcommand error
  - [x] 10.2: Create `tests/test_connection_manager.py` with tests for name→entity_id index
  - [x] 10.3: Test `tradeable` field defaults in ItemDef/Item loading

## Dev Notes

### Architecture Compliance

- **Handler pattern**: `async def handle_trade(websocket: WebSocket, data: dict, *, game: Game) -> None` — keyword-only `game` arg injected via lambda closure in `_register_handlers()`
- **Manager ownership**: `TradeManager` is an instance attribute of `Game` — accessed as `game.trade_manager`
- **State storage**: Trade state is **ephemeral** (in-memory only) — dissolved on server restart. ADR-1 rationale: 60s session lifespan doesn't justify persistence; DB atomicity handles crash safety
- **Session factory**: Use `async with game.session_factory() as session:` for all DB access — never import `async_session` directly
- **Repo pattern**: Repos are module-level async functions taking `session: AsyncSession` as first param; repos call `session.commit()` internally
- **Import guard**: Use `TYPE_CHECKING` for `Game` type imports — `if TYPE_CHECKING: from server.app import Game`
- **`from __future__ import annotations`** must be first import in every new module

### Existing Code to Reuse

- **`Inventory.remove_item(item_key, quantity) -> bool`** (`server/items/inventory.py:52`): Returns `False` if insufficient — use for offer validation
- **`Inventory.add_item(item_def, quantity)`** (`server/items/inventory.py:42`): For adding received items
- **`Inventory.get_quantity(item_key) -> int`** (`server/items/inventory.py:67`): Check available quantity
- **`Inventory.has_item(item_key) -> bool`** (`server/items/inventory.py:72`): Quick existence check
- **`ConnectionManager.send_to_player(entity_id, message)`** (`server/net/connection_manager.py:45`): Send trade messages to specific players
- **`ConnectionManager.get_room(entity_id) -> str | None`** (`server/net/connection_manager.py:32`): Verify same-room requirement
- **Item name resolution pattern**: The `/use` client command in `web-demo/js/game.js` (lines 195-198) resolves display names to `item_key` before sending. For `/trade offer`, since args arrive as raw text to the server, implement server-side name resolution: iterate the player's `Inventory._items`, match by `item_key` first, then case-insensitive `item_def.name`. This is a new server-side pattern — the existing `/use` server handler (`server/net/handlers/inventory.py:62`) does NOT do name resolution.
- **`player_repo.update_inventory(session, db_id, inventory_dict)`** (`server/player/repo.py`): Persist inventory changes after trade

### ConnectionManager Changes — Critical Details

Current `connect()` signature (`server/net/connection_manager.py:15`):
```python
def connect(self, entity_id: str, websocket: WebSocket, room_key: str) -> None
```
Must add `name: str` parameter. The single call site is in `handle_login` (`server/net/handlers/auth.py:287`):
```python
game.connection_manager.connect(entity_id, websocket, room_key)
```
Update to:
```python
game.connection_manager.connect(entity_id, websocket, room_key, name=player.username)
```

For `disconnect()`, add reverse lookup. Simplest approach: add `_entity_to_name: dict[str, str]` alongside `_name_to_entity` to enable O(1) cleanup in `disconnect()`.

### Trade State Machine

```
idle → request_pending → negotiating → one_ready → both_ready → executing → complete
                ↓              ↓            ↓            ↓
             (timeout)     (cancel)     (cancel)     (cancel)
                ↓              ↓            ↓            ↓
             cancelled     cancelled    cancelled    cancelled
```

- `request_pending`: After `/trade @player`, waiting for accept/reject. 30s timeout via `asyncio.get_running_loop().call_later()`.
- `negotiating`: Both players in session, can offer/remove items. Ready flags both `False`.
- `one_ready`: One player has sent `/trade ready`. Any offer/remove resets to `negotiating`.
- `both_ready`: Both players ready. Trade executes immediately (atomic inventory swap).
- `executing`: Transient state during DB transaction.
- `complete`: Terminal state. Trade done. Session cleaned up.

### Timeout Implementation

Use `asyncio.get_running_loop().call_later(seconds, callback)` — returns a `TimerHandle` stored on the `Trade` dataclass. Cancel with `handle.cancel()` when the trade is accepted/rejected/cancelled before timeout. The callback should call `cancel_trades_for()` and notify both players.

**Important**: `call_later` callback is a sync function. To send async messages, use `asyncio.create_task()` inside the callback or schedule a coroutine with `loop.create_task()`.

### Disconnect Cleanup Order

Current order in `_cleanup_player` (`server/net/handlers/auth.py:25-108`):
1. Combat cleanup (lines 40-73)
2. Save state to DB (lines 75-94)
3. Remove from room + broadcast (lines 96-104)
4. Clean up connection_manager + player_entities (lines 106-108)

New order after 12.1:
0. **Cancel active trades** (NEW — insert before step 1)
1. Combat cleanup (existing)
2. *(placeholder for party cleanup — Story 12.3)*
3. Save state to DB (existing)
4. Remove from room + broadcast (existing)
5. Clean up connection_manager + player_entities (existing)

Trade cancellation goes first because the trade partner needs to be notified while both players' connections are still valid.

### Message Types (Server → Client)

| Type | When | Payload |
|------|------|---------|
| `trade_request` | Player receives a trade offer | `{type, from_player: str, from_entity_id: str}` |
| `trade_update` | Offer added/removed or ready state changed | `{type, offers_a: dict, offers_b: dict, ready_a: bool, ready_b: bool, player_a: str, player_b: str}` |
| `trade_result` | Trade completed, cancelled, rejected, or timed out | `{type, status: "success"|"cancelled"|"rejected"|"timeout", reason: str}` |

### Testing Patterns

- **Handler tests**: Create `Game()` instance, register entities in `game.player_entities`, mock WebSocket with `AsyncMock`, mock `game.session_factory` with `MagicMock(return_value=mock_ctx)` (sync callable returning async context manager — NOT `AsyncMock()`)
- **TradeManager unit tests**: Test state transitions directly without handlers
- **Integration pattern**: Follow existing test structure in `tests/` — flat file, no nested directories
- **DB tests**: Use `create_async_engine("sqlite+aiosqlite:///:memory:")` for in-memory test DB

### Project Structure Notes

- New directories: `server/trade/` (with `__init__.py` and `manager.py`)
- New files: `server/net/handlers/trade.py`, `tests/test_trade.py`
- Modified files: `server/items/item_def.py`, `server/items/models.py`, `server/items/item_repo.py`, `server/core/config.py`, `server/net/connection_manager.py`, `server/net/handlers/auth.py`, `server/app.py`, `web-demo/js/game.js`
- `server/party/` directory is NOT created in this story — that's Story 12.3

### References

- [Source: `_bmad-output/planning-artifacts/epics.md` — Story 12.1 section, lines 2345-2441]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — Section 11, Epic 12 planned features]
- [Source: `_bmad-output/project-context.md` — Epic 12 patterns section]
- [Source: `server/net/connection_manager.py` — ConnectionManager class, lines 7-70]
- [Source: `server/items/item_def.py` — ItemDef dataclass, lines 11-52]
- [Source: `server/items/models.py` — Item DB model, lines 8-20]
- [Source: `server/items/item_repo.py` — load_items_from_json, lines 23-57]
- [Source: `server/core/config.py` — Settings class, lines 7-32]
- [Source: `server/net/handlers/auth.py` — _cleanup_player, lines 25-108; handle_login, lines 196-354]
- [Source: `server/app.py` — Game.__init__, lines 29-42; _register_handlers, lines 118-192]
- [Source: `web-demo/js/game.js` — COMMANDS, lines 146-253; dispatchMessage, lines 423-462]
- [Source: `server/items/inventory.py` — Inventory class, lines 12-105]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Completion Notes List

- Implemented full trade system: TradeManager with state machine, trade handler with subcommand parsing, ConnectionManager name index, ItemDef tradeable field, config settings, disconnect cleanup integration, and web client support
- 41 new tests covering TradeManager state transitions, handler subcommands, ConnectionManager name index, and ItemDef tradeable field
- 682 total tests pass (0 regressions)

### File List

New files:
- server/trade/__init__.py
- server/trade/manager.py
- server/net/handlers/trade.py
- tests/test_trade.py

Modified files:
- server/items/item_def.py (added tradeable field)
- server/items/models.py (added tradeable column)
- server/items/item_repo.py (tradeable in JSON loading)
- server/core/config.py (trade config settings)
- server/net/connection_manager.py (name→entity_id index)
- server/net/handlers/auth.py (trade cleanup in _cleanup_player, name param in connect)
- server/app.py (TradeManager import/init, trade handler registration)
- web-demo/js/game.js (trade command, message handlers)
