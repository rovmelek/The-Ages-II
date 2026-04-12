# Story 12.2: Trade Validation

Status: done

## Story

As a player,
I want my trades to be safe and atomic,
so that items cannot be duplicated, lost, or stolen through exploits or edge cases.

## Acceptance Criteria

1. **Given** both players are ready and trade execution begins, **When** the server validates the trade, **Then** both players must still be in the same room, online, and not in combat, **And** all offered items are re-validated from live inventory (sufficient quantity, item exists, `tradeable` flag), **And** if any offered quantity exceeds current inventory at execution time, the entire trade fails — no partial trades, **And** both players are notified with a `trade_result` message (success or failure with reason).

2. **Given** both players' offers are valid, **When** the trade executes, **Then** items are removed from both players' inventories and added to the other's in a single DB transaction, **And** in-memory inventory state is updated only after DB commit succeeds, **And** both players receive updated inventory data.

3. **Given** Player A sends `/trade @PlayerA` (self-trade attempt), **When** the server processes the request, **Then** the trade is rejected with "Cannot trade with yourself", **And** validation checks `player_db_id` (not entity_id) to catch duplicate login edge cases.

4. **Given** a player disconnects during an active trade session, **When** the disconnect is processed, **Then** the trade session is immediately cancelled, **And** the remaining player is notified: "Trade cancelled — player disconnected".

5. **Given** a player changes room during an active trade session, **When** the room transition is processed, **Then** the trade session is immediately cancelled, **And** both players are notified: "Trade cancelled — player left the room", **And** `TradeManager.cancel_trades_for(entity_id)` is called in the movement handler before the room transfer.

6. **Given** a player enters combat during an active trade session, **When** combat begins, **Then** the trade session is immediately cancelled, **And** both players are notified: "Trade cancelled — player entered combat", **And** `TradeManager.cancel_trades_for(entity_id)` is called in the movement handler on combat entry.

7. **Given** a player is kicked via duplicate login protection, **When** the kick is processed, **Then** all pending trades for that `player_db_id` are cancelled, **And** the other player in the session (if any) is notified.

8. **Given** a player is already in a trade session, **When** another player sends `/trade @player` targeting them, **Then** the request is auto-rejected: "Player is already in a trade session".

9. **Given** the server crashes during trade execution, **When** the DB transaction did not commit, **Then** both inventories are unchanged (ACID guarantee), **And** on restart, trade state is gone (ephemeral) — no stale sessions.

## Tasks / Subtasks

- [x] Task 1: Harden `_execute_trade` with pre-validation (AC: #1)
  - [x] 1.1: Before any inventory mutation in `_execute_trade` (`server/net/handlers/trade.py:350`), add pre-validation: verify both players are still online (`game.player_entities`), in same room (`game.connection_manager.get_room()`), and not in combat (`entity.in_combat`)
  - [x] 1.2: Re-validate all offered items from live inventory — for each item in `offers_a` and `offers_b`, check `inventory.get_quantity(item_key) >= offered_qty` and `inventory.get_item(item_key).tradeable is True`
  - [x] 1.3: If any pre-validation fails, cancel trade via `game.trade_manager.cancel_trade()` and send `trade_result` with `status: "failed"` and specific reason to both players — no items moved

- [x] Task 2: Implement atomic DB transaction for trade swap (AC: #2, #9)
  - [x] 2.1: Refactor `_execute_trade` to separate in-memory swap from DB persistence — compute the new inventory dicts WITHOUT modifying `Inventory` objects first
  - [x] 2.2: Execute both inventory updates in a single DB transaction: use `async with game.session_factory() as session:` then call `session.execute(update(...))` directly for BOTH players, then ONE `session.commit()` — do NOT call `player_repo.update_inventory()` which commits after each call
  - [x] 2.3: Only after DB commit succeeds, apply changes to in-memory `Inventory` objects via `remove_item()` / `add_item()`
  - [x] 2.4: If DB commit fails (exception), do NOT modify in-memory inventories — send `trade_result` with `status: "failed"` and reason to both players
  - [x] 2.5: After successful swap, send `trade_result` with `status: "success"` AND updated inventory data to both players

- [x] Task 3: Add self-trade prevention by `player_db_id` (AC: #3)
  - [x] 3.1: In trade handler's `@player` subcommand (`server/net/handlers/trade.py:87-131`), after the existing `entity_id` equality check (line 126), add a `player_db_id` comparison: `player_info["db_id"] == target_info["db_id"]`

- [x] Task 4: Add trade cancellation on room transition (AC: #5)
  - [x] 4.1: In `_handle_exit_transition` (`server/net/handlers/movement.py:176`), add trade cancellation BEFORE removing entity from old room (before line 206)
  - [x] 4.2: Call `game.trade_manager.cancel_trades_for(entity_id)` and notify the other player with reason "Trade cancelled — player left the room"

- [x] Task 5: Add trade cancellation on combat entry (AC: #6)
  - [x] 5.1: In `_handle_mob_encounter` (`server/net/handlers/movement.py:115`), add trade cancellation BEFORE marking NPC/player as in combat (before line 131)
  - [x] 5.2: Call `game.trade_manager.cancel_trades_for(entity_id)` and notify the other player with reason "Trade cancelled — player entered combat"

- [x] Task 6: Verify existing disconnect/kick trade cancellation (AC: #4, #7)
  - [x] 6.1: Verify `_cleanup_player` (line 40 in `server/net/handlers/auth.py`) already cancels trades on disconnect — this was done in Story 12.1
  - [x] 6.2: Verify `_kick_old_session` (line 196 in `server/net/handlers/auth.py`) delegates to `_cleanup_player` which cancels trades — this was done in Story 12.1
  - [x] 6.3: Verify "already in trade" rejection is handled by `TradeManager.initiate_trade()` (lines 93-94 in `server/trade/manager.py`: `"Player is already in a trade session"`) — this was done in Story 12.1

- [x] Task 7: Write tests (AC: #1-9)
  - [x] 7.1: Test pre-validation: both players online, same room, not in combat at execution time
  - [x] 7.2: Test pre-validation: insufficient items at execution time (race between offer and execute)
  - [x] 7.3: Test pre-validation: untradeable item sneaked past offer (edge case)
  - [x] 7.4: Test atomic swap: both inventories updated correctly after successful trade
  - [x] 7.5: Test self-trade by `player_db_id` (same DB ID, different entity_id)
  - [x] 7.6: Test room transition cancels trade (movement handler integration)
  - [x] 7.7: Test combat entry cancels trade (mob encounter integration)
  - [x] 7.8: Test disconnect cancels trade (verify existing behavior)
  - [x] 7.9: Test kick cancels trade (verify existing behavior)

## Dev Notes

### Architecture Compliance

- **Handler pattern**: All changes in `_execute_trade` follow the existing handler pattern — `async def` with `game: Game` access
- **Session factory**: Use `async with game.session_factory() as session:` — never import `async_session` directly
- **Repo pattern exception**: For atomic trade swap, bypass `player_repo.update_inventory()` (which commits after each call) and use direct `session.execute(update(...))` + single `session.commit()`. This is an intentional deviation — the repo pattern doesn't support multi-entity atomic transactions
- **Import guard**: Use `TYPE_CHECKING` for `Game` type — `if TYPE_CHECKING: from server.app import Game`

### Current `_execute_trade` Issues (from 12.1)

The existing `_execute_trade` (`server/net/handlers/trade.py:350-429`) has these gaps that this story addresses:
1. **No pre-validation** at execution time — items could be consumed between offer and execute
2. **No atomic DB transaction** — `player_repo.update_inventory()` commits after each call (line 74 in `server/player/repo.py`), so if the second commit fails, inventories are inconsistent
3. **In-memory mutations before DB commit** — `Inventory.remove_item()` / `add_item()` are called before DB persistence, so a DB failure leaves corrupted in-memory state
4. **No rollback on partial failure** — if player B's `remove_item` fails after player A's items moved, no rollback

### Atomic Swap Implementation Strategy

```python
# 1. Pre-validate everything (no mutations yet)
# 2. Compute new inventory dicts
new_inv_a = dict(inv_a.to_dict())  # snapshot
new_inv_b = dict(inv_b.to_dict())
# Remove A's offers from A, add to B
for item_key, qty in trade.offers_a.items():
    new_inv_a[item_key] -= qty
    if new_inv_a[item_key] <= 0:
        del new_inv_a[item_key]
    new_inv_b[item_key] = new_inv_b.get(item_key, 0) + qty
# Remove B's offers from B, add to A (same pattern)
# 3. Single DB transaction
async with game.session_factory() as session:
    await session.execute(update(Player).where(Player.id == db_id_a).values(inventory=new_inv_a))
    await session.execute(update(Player).where(Player.id == db_id_b).values(inventory=new_inv_b))
    await session.commit()
# 4. Apply to in-memory Inventory objects only after commit succeeds
```

Note: Direct `session.execute()` + `session.commit()` bypasses `player_repo.update_inventory()` intentionally. The Player model import is needed: `from server.player.models import Player` and `from sqlalchemy import update`.

### Trade Cancellation Hook Pattern

For room transition and combat entry cancellation, use the same pattern as `_cleanup_player`:
```python
cancelled = game.trade_manager.cancel_trades_for(entity_id)
if cancelled:
    other_id = cancelled.player_b if cancelled.player_a == entity_id else cancelled.player_a
    await game.connection_manager.send_to_player(other_id, {
        "type": "trade_result", "status": "cancelled",
        "reason": "Trade cancelled — <reason>"
    })
```

### Files to Modify

- `server/net/handlers/trade.py` — refactor `_execute_trade` (pre-validation, atomic swap, in-memory-after-DB)
- `server/net/handlers/movement.py` — add trade cancellation in `_handle_exit_transition` (before line 206) and `_handle_mob_encounter` (before line 131)
- `tests/test_trade.py` — add validation and cancellation tests

### Files NOT Modified (verify-only)

- `server/net/handlers/auth.py` — disconnect/kick trade cancellation already implemented in 12.1
- `server/trade/manager.py` — no changes needed, existing `cancel_trades_for()` and `initiate_trade()` validation are sufficient

### Key Line Numbers

- `_execute_trade`: `server/net/handlers/trade.py:350-429`
- `_handle_exit_transition`: `server/net/handlers/movement.py:176-272`
- `_handle_mob_encounter`: `server/net/handlers/movement.py:115-173`
- `_cleanup_player` trade step: `server/net/handlers/auth.py:40-55`
- `_kick_old_session`: `server/net/handlers/auth.py:196-210`
- `TradeManager.initiate_trade`: `server/trade/manager.py:81-116`
- `TradeManager.cancel_trades_for`: `server/trade/manager.py:277-284`
- `player_repo.update_inventory`: `server/player/repo.py:63-74` (commits on line 74)
- `Inventory.to_dict`: `server/items/inventory.py:19`
- `Inventory.remove_item`: `server/items/inventory.py:52`
- `Inventory.add_item`: `server/items/inventory.py:42`
- `Player` model: `server/player/models.py`

### Testing Patterns

- **Handler tests**: Mock `Game` with real `TradeManager`, mock WebSocket with `AsyncMock`, mock `game.session_factory` with `MagicMock(return_value=mock_ctx)` (sync callable returning async context manager)
- **Movement handler tests**: Set up entities with active trade sessions, trigger `_handle_exit_transition` / `_handle_mob_encounter`, verify trade cancelled and other player notified
- **Atomic swap tests**: Verify in-memory inventory unchanged on DB failure, verify both inventories correct on success

### References

- [Source: `_bmad-output/planning-artifacts/epics.md` — Story 12.2, lines 2443-2509]
- [Source: `server/net/handlers/trade.py` — `_execute_trade`, lines 350-429]
- [Source: `server/net/handlers/movement.py` — `_handle_exit_transition`, lines 176-272; `_handle_mob_encounter`, lines 115-173]
- [Source: `server/net/handlers/auth.py` — `_cleanup_player`, lines 25-125]
- [Source: `server/player/repo.py` — `update_inventory`, lines 63-74]
- [Source: `server/trade/manager.py` — TradeManager class, lines 28-304]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Completion Notes List

- Refactored `_execute_trade` with full pre-validation (online, same room, not in combat, re-validate all offers)
- Implemented atomic DB swap using direct `session.execute()` + single `session.commit()` (bypasses repo per-call commits)
- In-memory `Inventory` objects only updated after DB commit succeeds
- Added self-trade prevention by `player_db_id` (catches duplicate login edge case)
- Added trade cancellation hooks in `_handle_exit_transition` and `_handle_mob_encounter`
- Fixed pre-existing exploration XP tests broken by trade cancellation hook addition
- 13 new tests, 739 total passing (0 regressions)

### File List

Modified files:
- server/net/handlers/trade.py (refactored _execute_trade, added pre-validation, atomic swap, db_id self-trade check)
- server/net/handlers/movement.py (trade cancellation on room transition and combat entry)
- tests/test_trade.py (13 new Story 12.2 tests)
- tests/test_exploration_xp.py (fixed mock for trade_manager compatibility)
