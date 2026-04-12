# Story 16.10a: Combat Turn Timeout Enforcement

Status: done

## Story

As a **player in party combat**,
I want disconnected or idle players' turns to auto-pass after 30 seconds,
So that combat doesn't stall indefinitely when someone goes AFK or loses connection.

## Acceptance Criteria

1. **Given** a player's combat turn begins (via `_advance_turn` or `start_turn_timer`),
   **When** `COMBAT_TURN_TIMEOUT_SECONDS` (default 30, `server/core/config.py:32`) elapses without action,
   **Then** the turn auto-passes (same behavior as `pass_turn`),
   **And** all combat participants receive the `combat_turn` broadcast.

2. **Given** a timeout is scheduled for a player's turn,
   **When** the player acts (play_card, pass_turn, use_item, flee),
   **Then** the timer is cancelled at the START of the action — BEFORE validation,
   **And** if validation fails (wrong turn, insufficient energy), the timer is re-scheduled.

3. **Given** `CombatManager.start_combat()` creates an instance and adds participants,
   **When** `set_turn_timeout_callback()` is called AFTER `start_combat()`,
   **Then** `start_turn_timer()` activates the first turn timeout,
   **And** `add_participant()` does NOT schedule a timeout.

4. **Given** `combat_start` and `combat_turn` outbound messages,
   **When** a turn timeout is active,
   **Then** messages include `turn_timeout_at` (Unix timestamp float).

5. **Given** combat ends or a participant is removed,
   **When** cleanup runs,
   **Then** any pending turn timeout is cancelled.

6. **Given** all 959+ existing tests,
   **When** Story 16.10a is implemented,
   **Then** all tests pass.

## Tasks / Subtasks

- [x] Task 1: Add timer fields and methods to `CombatInstance` (AC: #1, #2, #3, #5)
  - [x] 1.1: Add `_turn_timeout_handle`, `_turn_timeout_callback`, `_turn_timeout_at` fields to `__init__`
  - [x] 1.2: Add `set_turn_timeout_callback(callback)` method
  - [x] 1.3: Add `start_turn_timer()` public method — calls `_schedule_turn_timeout()`
  - [x] 1.4: Add `_schedule_turn_timeout()` — uses `loop.call_later(COMBAT_TURN_TIMEOUT_SECONDS, callback, current_turn, self)`, stores `_turn_timeout_at = time.time() + timeout`
  - [x] 1.5: Add `_cancel_turn_timeout()` — cancels handle, clears `_turn_timeout_at`
  - [x] 1.6: Call `_schedule_turn_timeout()` at end of `_advance_turn()`
  - [x] 1.7: Call `_cancel_turn_timeout()` at START of `play_card()`, `pass_turn()`, `use_item()` — before validation; re-schedule if validation fails (ValueError)
  - [x] 1.8: Call `_cancel_turn_timeout()` in `remove_participant()`
  - [x] 1.9: Add `turn_timeout_at` to `get_state()` output

- [x] Task 2: Add timeout callback in `server/net/handlers/combat.py` (AC: #1)
  - [x] 2.1: Add `_on_turn_timeout(entity_id, instance)` — sync callback for `loop.call_later`, creates task for async handler
  - [x] 2.2: Add `_handle_turn_timeout(entity_id, instance, game)` — async: calls `instance.pass_turn()`, `_broadcast_combat_state()`, `_check_combat_end()`
  - [x] 2.3: The callback needs a reference to `game` — use a closure or partial when registering

- [x] Task 3: Register callback and start timer on combat start (AC: #3, #4)
  - [x] 3.1: In `server/net/handlers/movement.py`, after `start_combat()`, call `instance.set_turn_timeout_callback(...)` then `instance.start_turn_timer()`
  - [x] 3.2: Include `turn_timeout_at` in `combat_start` messages (already in `get_state()` from Task 1.9)

- [x] Task 4: Add tests for turn timeout (AC: #1, #2, #5, #6)
  - [x] 4.1: Test timeout fires and auto-passes turn
  - [x] 4.2: Test player action cancels timeout
  - [x] 4.3: Test validation failure re-schedules timeout
  - [x] 4.4: Test timeout cancelled on combat end / participant removal
  - [x] 4.5: Test `turn_timeout_at` in `get_state()`

- [x] Task 5: Run full test suite (AC: #6)
  - [x] 5.1: Run `make test` — all 959+ tests pass

## Dev Notes

### Timer Pattern

Use `loop.call_later` + `loop.create_task` consistent with `TradeManager._handle_timeout` (`server/trade/manager.py`). The `call_later` callback is sync, so it creates a task for the async auto-pass logic.

### Callback Registration

Since 16.4 is done, the timeout callback lives in `server/net/handlers/combat.py` (near `_check_combat_end`). It needs access to `game` for broadcasting — use `functools.partial` or a closure.

In `movement.py`, register with:
```python
instance.set_turn_timeout_callback(
    lambda eid, inst: _on_turn_timeout(eid, inst, game)
)
```
where `_on_turn_timeout` is imported from `server.net.handlers.combat`.

### Cancel-Before-Validate Pattern

Timer must be cancelled at the START of `play_card`/`pass_turn`/`use_item` — BEFORE the `get_current_turn()` check. If validation raises ValueError, re-schedule. This prevents a race in party combat where the timeout fires between action start and turn advance.

### Existing Tests Impact

Existing combat tests don't set a timeout callback (no `set_turn_timeout_callback` call), so `_schedule_turn_timeout` will be a no-op (`_turn_timeout_callback is None`). No existing tests need changes.

### Files to Modify

- `server/combat/instance.py` — Timer fields, scheduling methods, `get_state()` update
- `server/net/handlers/combat.py` — `_on_turn_timeout` callback + `_handle_turn_timeout` async handler
- `server/net/handlers/movement.py` — Register callback + start timer after combat start

### References

- [Source: _bmad-output/planning-artifacts/epic-16-tech-spec.md#Story-16.10a] — Full spec
- [Source: server/combat/instance.py] — CombatInstance (437 lines)
- [Source: server/trade/manager.py] — TradeManager timeout pattern reference
- [Source: server/core/config.py:32] — `COMBAT_TURN_TIMEOUT_SECONDS: 30`

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Completion Notes List

- Added timer fields (`_turn_timeout_handle`, `_turn_timeout_callback`, `_turn_timeout_at`) to CombatInstance
- `_schedule_turn_timeout` uses `loop.call_later` pattern (consistent with TradeManager)
- Cancel-before-validate: timeout cancelled at START of play_card/pass_turn/use_item, re-scheduled on ValueError
- `_advance_turn` schedules new timeout for the next turn (only if combat not finished)
- `remove_participant` cancels pending timeout
- `get_state()` includes `turn_timeout_at` when active
- `make_turn_timeout_callback(game)` creates closure for `loop.call_later` → `loop.create_task` pattern
- Callback registered in movement.py after `start_combat()`, then `start_turn_timer()` activates first timeout
- Existing tests unaffected — no callback set means `_schedule_turn_timeout` is a no-op
- 9 new tests, 968 total passing

### File List

- `server/combat/instance.py` — Modified: timer fields, scheduling methods, get_state update
- `server/net/handlers/combat.py` — Modified: `make_turn_timeout_callback`, `_handle_turn_timeout`
- `server/net/handlers/movement.py` — Modified: register callback + start timer on combat start
- `tests/test_turn_timeout.py` — New: 9 tests for timeout scheduling and behavior
