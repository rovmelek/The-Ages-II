# Story 14.6: Concurrency Safety

Status: done

## Story

As a developer,
I want trade execution and NPC encounter initiation protected by async locks,
So that concurrent WebSocket coroutines cannot cause TOCTOU race conditions at `await` yield points.

## Acceptance Criteria

1. **Given** `NpcEntity` dataclass in `server/room/objects/npc.py` (lines 11-26), **When** Story 14.6 is implemented, **Then** it has a `_lock: asyncio.Lock` field (created via `field(default_factory=asyncio.Lock, repr=False, compare=False)`), **And** the NPC encounter handler in `_handle_mob_encounter` (`server/net/handlers/movement.py`, lines 134-228) acquires `npc._lock` before checking `in_combat` and releases after setting it, **And** the critical section is short (protects only the check-and-set of `npc.in_combat`, not the full encounter setup).

2. **Given** `TradeManager` in `server/trade/manager.py` (class at line 28, `__init__` at line 37), **When** Story 14.6 is implemented, **Then** it has a `_trade_locks: dict[str, asyncio.Lock]` keyed by `trade_id` (epic AC suggested sorted player ID pairs, but `trade_id` is simpler — each trade already has a unique ID that maps to its lifecycle), **And** `_execute_trade` in `server/net/handlers/trade.py` (lines 377-486) acquires the lock before inventory validation and releases after the DB write, **And** the critical section protects validation-through-write (lines 381-450), not the full trade session lifecycle.

3. **Given** two coroutines simultaneously moving onto the same NPC, **When** both attempt to initiate combat, **Then** only one enters combat; the other returns silently (NPC already in combat — existing guard at line 146 handles this once `in_combat` is set atomically).

4. **Given** two coroutines simultaneously executing a trade, **When** both race through validation and DB write, **Then** the lock serializes access — one completes first, the second sees updated inventory.

5. **Given** the `asyncio.gather` test pattern, **When** concurrency tests are written, **Then** at least 2 tests use `asyncio.gather` to verify lock behavior (one for NPC encounter, one for trade).

6. **Given** all existing tests, **When** Story 14.6 is implemented, **Then** all tests pass (including the 10 known-broken tests from prior stories — do NOT fix those here).

## Tasks / Subtasks

### Part A: NPC Encounter Lock (AC: #1, #3, #6)

- [x] Task 1: Add `_lock` field to `NpcEntity` dataclass
  - [x] 1.1: In `server/room/objects/npc.py`, add `import asyncio` at top (after existing imports).
  - [x] 1.2: Add field to `NpcEntity` dataclass (after `spawn_config`): `_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False, compare=False)`. The underscore prefix signals it's internal; `repr=False` keeps it out of logs; `compare=False` excludes from equality checks.
  - [x] 1.3: Verify `to_dict()` does NOT expose `_lock` (it already only returns `id`, `npc_key`, `name`, `x`, `y`, `is_alive` — no change needed).

- [x] Task 2: Protect NPC encounter check-and-set with lock
  - [x] 2.1: In `server/net/handlers/movement.py`, `_handle_mob_encounter` function (line 134), restructure the NPC guard at lines 144-173. The current code has a TOCTOU window: it checks `npc.in_combat` at line 146, then does async work (trade cancellation, party gathering) spanning ~27 lines before setting `npc.in_combat = True` at line 173.
  - [x] 2.2: Move the `npc.in_combat = True` assignment to immediately after the guard check, inside an `async with npc._lock:` block. The `npc is None` check MUST stay BEFORE the lock (can't acquire lock on None). The lock protects ONLY the check-and-set:
    ```python
    npc = room.get_npc(npc_id)
    if npc is None:
        return
    async with npc._lock:
        if not npc.is_alive or npc.in_combat:
            return
        npc.in_combat = True
    ```
  - [x] 2.3: Keep all subsequent code (trade cancellation, party gathering, card loading, combat creation) OUTSIDE the lock — these are long async operations that don't need the lock.
  - [x] 2.4: If combat creation fails after `npc.in_combat = True`, ensure `npc.in_combat` is reset to `False` (add try/except around the combat setup code after the lock release). This handles the edge case where card loading or combat instance creation raises.

### Part B: Trade Execution Lock (AC: #2, #4, #6)

- [x] Task 3: Add `_trade_locks` dict to `TradeManager`
  - [x] 3.1: In `server/trade/manager.py`, `TradeManager.__init__` (line 37), add `self._trade_locks: dict[str, asyncio.Lock] = {}` (keyed by `trade_id`). Note: `asyncio` is already imported (line 4).
  - [x] 3.2: Add a method `get_trade_lock(self, trade_id: str) -> asyncio.Lock` that returns the existing lock or creates one (lazy initialization pattern):
    ```python
    def get_trade_lock(self, trade_id: str) -> asyncio.Lock:
        if trade_id not in self._trade_locks:
            self._trade_locks[trade_id] = asyncio.Lock()
        return self._trade_locks[trade_id]
    ```
  - [x] 3.3: Clean up the lock entry in `_cleanup_trade` (line 72-79) — this is the single chokepoint for ALL trade removal (called by `complete_trade`, `cancel_trades_for`, `cancel_trade`, `reject_trade`, and `_handle_timeout`). Add `self._trade_locks.pop(trade.trade_id, None)` inside `_cleanup_trade` after the existing `self._trades.pop(trade.trade_id, None)` on line 77.

- [x] Task 4: Protect `_execute_trade` with lock
  - [x] 4.1: In `server/net/handlers/trade.py`, `_execute_trade` function (line 377), acquire the trade lock before validation (line 381) and hold it through the DB write (line 450). The lock must cover the state check, inventory validation, inventory computation, and DB write — the critical section that must be atomic.
  - [x] 4.2: Wrap the validation-through-DB-write section (lines 379-450) with:
    ```python
    lock = game.trade_manager.get_trade_lock(trade.trade_id)
    async with lock:
        # existing validation and DB write code
    ```
  - [x] 4.3: The in-memory inventory update (lines 452-463) and success notifications (lines 465-486) can remain outside the lock — they are safe after the DB commit.

### Part C: Concurrency Tests (AC: #5, #6)

- [x] Task 5: NPC encounter concurrency test
  - [x] 5.1: Create `tests/test_concurrency.py` (new file — this is a new test pattern for the codebase).
  - [x] 5.2: Write a test that uses `asyncio.gather` to simulate two players stepping onto the same NPC simultaneously. Setup: create a `Game` instance, register two player entities in the same room with an alive NPC on a mob_spawn tile. Use `AsyncMock` for WebSockets. Call `_handle_mob_encounter` concurrently for both players using `asyncio.gather`. Assert that only one combat instance is created (`game.combat_manager` has exactly one instance) and the NPC's `in_combat` flag is `True`.
  - [x] 5.3: Use the existing test patterns from the codebase (mock `game.transaction`, `AsyncMock` for WebSocket, direct function calls to handlers).

- [x] Task 6: Trade execution concurrency test
  - [x] 6.1: Write a test in `tests/test_concurrency.py` that uses `asyncio.gather` to simulate two simultaneous `_execute_trade` calls on the same trade. Setup: create a `Game` instance with two players who have items, create a Trade object in `both_ready` state. Call `_execute_trade` concurrently using `asyncio.gather`. Assert that only one execution succeeds (the trade completes once, not twice — items are transferred correctly without duplication).

### Part D: Verification (AC: #6)

- [x] Task 7: Run `make test` and confirm all tests pass
  - [x] 7.1: Run `make test`. Expected: all currently-passing tests still pass; the 10 known-broken tests from prior stories remain as-is; new concurrency tests pass.
  - [x] 7.2: If any previously-passing test breaks, diagnose and fix — the lock additions should be transparent to existing code.

## Dev Notes

### Architecture Compliance
- **ADR-14-7**: NPC lock on dataclass field, trade lock dict on `TradeManager` — matches the epic's architectural decision.
- Short critical sections only — lock should protect the minimum code necessary to prevent the race.
- No new manager classes or service layers — locks are added to existing structures.

### The TOCTOU Race Conditions

**NPC Encounter Race (movement.py:134-228):**
The current code checks `npc.in_combat` at line 146 and sets `npc.in_combat = True` at line 173. Between these lines there are:
- `await _cancel_trade_for(entity_id, game)` (line 150) — yields to event loop
- Party member gathering with `await _cancel_trade_for(mid, game)` (line 170) — yields to event loop
This means two coroutines processing simultaneous movement can both pass the guard and both enter combat with the same NPC, creating two `CombatInstance` objects for one NPC.

**Fix**: Move `npc.in_combat = True` to immediately after the check, inside an `async with npc._lock:` block. This makes the check-and-set atomic relative to asyncio task switching.

**Trade Execution Race (trade.py:377-486):**
The `_execute_trade` function sets `trade.state = "executing"` at line 379, then does async DB work. If `_execute_trade` were somehow called twice for the same trade (e.g., both players send `ready` in rapid succession and the handler dispatches twice before either completes), the second call could also pass validation. The trade lock prevents this.

### Lock Scope Design

**NPC lock scope — NARROW (3 lines):**
```python
async with npc._lock:
    if not npc.is_alive or npc.in_combat:
        return
    npc.in_combat = True
# Everything else (trade cancel, party gather, card load, combat create) is OUTSIDE the lock
```
Rationale: The lock only needs to protect the check-and-set. Once `in_combat` is `True`, subsequent coroutines will see it via the existing guard and return.

**Trade lock scope — MEDIUM (validation + DB write, ~70 lines):**
```python
async with lock:
    trade.state = "executing"
    # ... validation ...
    # ... compute new inventories ...
    # ... DB transaction ...
# In-memory inventory update and notifications are OUTSIDE the lock
```
Rationale: Validation and DB write must be atomic — if validation passes, the DB write must happen before another execution attempt re-validates.

### What NOT to Change
- No changes to `CombatManager`, `CombatInstance`, or combat handlers — they don't have concurrency issues at this level
- No changes to `PartyManager` — party operations are single-threaded by design
- No changes to `ConnectionManager` — connection tracking is not at risk
- No changes to existing test files — lock additions are transparent
- Don't add locks to `Game.player_entities` — dict mutations happen in handler context, not across yield points
- Don't add locks to room entity tracking — same reasoning

### Error Recovery After Lock

If combat setup fails AFTER `npc.in_combat = True` is set (e.g., card loading throws), the NPC will be stuck in `in_combat = True` with no actual combat. Wrap the post-lock combat setup in try/except and reset `npc.in_combat = False` on failure:
```python
async with npc._lock:
    if not npc.is_alive or npc.in_combat:
        return
    npc.in_combat = True

try:
    # Cancel trades, gather party, load cards, start combat...
except Exception:
    npc.in_combat = False
    raise
```

### Test Pattern: `asyncio.gather` for Concurrency

This is a new test pattern for the codebase. Example structure:
```python
async def test_two_players_same_npc_only_one_combat():
    # Setup game, room, NPC, two player entities with mock WebSockets
    results = await asyncio.gather(
        _handle_mob_encounter(ws1, game, eid1, entity1, info1, room, mob_enc),
        _handle_mob_encounter(ws2, game, eid2, entity2, info2, room, mob_enc),
    )
    # Assert only one combat instance created
    assert len(game.combat_manager._instances) == 1
    assert npc.in_combat is True
```
Note: `asyncio.gather` runs coroutines concurrently on the same event loop — each yields at `await` points, simulating real concurrent WebSocket message processing.

### Files to Modify

**Production files (3):**
| File | Changes |
|------|---------|
| `server/room/objects/npc.py` | Add `import asyncio`; add `_lock` field to `NpcEntity` |
| `server/net/handlers/movement.py` | Add `async with npc._lock:` around check-and-set in `_handle_mob_encounter` |
| `server/trade/manager.py` | Add `_trade_locks` dict and `get_trade_lock()` method to `TradeManager`; clean up locks on trade removal |

**Production files (1 — handler):**
| File | Changes |
|------|---------|
| `server/net/handlers/trade.py` | Wrap `_execute_trade` validation+DB section with trade lock |

**Test files (1 — new):**
| File | Changes |
|------|---------|
| `tests/test_concurrency.py` | New file with NPC encounter + trade execution concurrency tests |

### Previous Story Intelligence (14.5)

- Pure refactor completed with zero assertion changes — 14.6 is NOT a refactor, it adds new behavior (locking)
- `_handle_mob_encounter` is in `movement.py` (not `combat.py`) — combat.py has the combat resolution helpers
- `PlayerSession` dataclass is the standard way to access player info (use `.entity`, `.db_id`, `.inventory`, `.room_key`)
- Test setup: mock `game.transaction = MagicMock(return_value=mock_ctx)` for unit tests
- ~805 tests currently passing (per memory), with 10 known-broken from prior stories

### References
- [Source: _bmad-output/planning-artifacts/epics.md#Story 14.6] — AC, FR114, ADR-14-7
- [Source: server/room/objects/npc.py:11-26] — `NpcEntity` dataclass (no lock field currently)
- [Source: server/net/handlers/movement.py:134-228] — `_handle_mob_encounter` (TOCTOU: check line 146, set line 173)
- [Source: server/net/handlers/trade.py:377-486] — `_execute_trade` (no lock currently)
- [Source: server/trade/manager.py:28] — `TradeManager` class (line 28), `__init__` (line 37), `_cleanup_trade` (line 72)
- [Source: _bmad-output/project-context.md] — project rules and patterns
- [Source: _bmad-output/implementation-artifacts/14-5-decompose-handler-business-logic.md] — previous story learnings

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List
- Added `_lock: asyncio.Lock` field to `NpcEntity` dataclass with `repr=False, compare=False`
- Restructured `_handle_mob_encounter` to atomically check-and-set `npc.in_combat` under `async with npc._lock:` — TOCTOU window eliminated
- Added try/except around combat setup code to reset `npc.in_combat = False` on failure after lock release
- Added `_trade_locks: dict[str, asyncio.Lock]` to `TradeManager.__init__` with `get_trade_lock()` lazy creation method
- Lock cleanup added to `_cleanup_trade` (single chokepoint for all 6 trade removal paths)
- Wrapped `_execute_trade` validation-through-DB-write in `async with lock:` — serializes concurrent execution
- Added state guard (`if trade.state not in ("both_ready",): return`) inside lock to prevent double-execution
- Created `tests/test_concurrency.py` with 8 tests: NPC encounter concurrency (5 tests), trade execution concurrency (3 tests)
- Fixed existing tests: added `_lock = asyncio.Lock()` to `_FakeNpc` in `test_party_combat.py` and MagicMock NPC in `test_trade.py`
- 781 passed, 8 pre-existing failures (unchanged from prior stories), 2 collection errors (test_chest, test_loot — server.items.loot deleted in 14.2)

### File List
- server/room/objects/npc.py (modified — added `import asyncio`, `_lock` field to `NpcEntity`)
- server/net/handlers/movement.py (modified — atomic check-and-set with `npc._lock` in `_handle_mob_encounter`, try/except for error recovery)
- server/trade/manager.py (modified — added `_trade_locks` dict, `get_trade_lock()` method, lock cleanup in `_cleanup_trade`)
- server/net/handlers/trade.py (modified — wrapped `_execute_trade` critical section with trade lock, added state guard)
- tests/test_concurrency.py (new — 8 concurrency tests using `asyncio.gather`)
- tests/test_party_combat.py (modified — added `import asyncio`, `_lock` to `_FakeNpc`)
- tests/test_trade.py (modified — added `npc._lock = asyncio.Lock()` to MagicMock NPC)
