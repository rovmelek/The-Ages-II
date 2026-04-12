# ISS-014: Re-login tests produce RuntimeWarning for unawaited coroutine

**Severity:** Low (test warning, no production impact)
**Found during:** Story 12.4 code review
**Date:** 2026-04-11

## Problem

Two tests in `tests/test_logout.py` produce RuntimeWarnings:

```
tests/test_logout.py::test_relogin_same_socket_after_logout
tests/test_logout.py::test_relogin_same_socket_without_logout
  /Users/hytseng/github/The-Ages-II/server/net/handlers/auth.py:338: RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited
```

## Root Cause

Both tests create `mock_player = AsyncMock()` to simulate a DB player record but do not set `mock_player.visited_rooms`. The call chain:

1. `handle_login` reads `player.visited_rooms` (auth.py line 336)
2. Since `visited_rooms` is not set on the mock, `AsyncMock.__getattr__` returns a new `AsyncMock`
3. `visited_rooms = player.visited_rooms or []` — `AsyncMock` is truthy, so the `or []` fallback is never reached; `visited_rooms` is the `AsyncMock`
4. `room_key not in visited_rooms` — `MagicMock.__contains__` returns `False` by default, so `not in` is `True` and the `if` block executes
5. `visited_rooms.append(room_key)` — `.append()` on an `AsyncMock` returns a coroutine (because `AsyncMock` makes all non-magic method calls return coroutines). That coroutine is never awaited, producing the RuntimeWarning

The tests still pass because the warning doesn't raise an exception, and `visited_rooms` (the `AsyncMock`) is stored in `game.player_entities` where it is never read again in these tests.

## Proposed Fix

Add `mock_player.visited_rooms = []` alongside the other explicitly-set mock attributes in both tests. This matches the real DB model's type (`list | None`) and prevents the `AsyncMock` from intercepting the `.append()` call.

```python
# In test_relogin_same_socket_after_logout (line ~299)
mock_player.inventory = {}
mock_player.visited_rooms = []    # <-- add this
mock_repo.get_by_username.return_value = mock_player

# In test_relogin_same_socket_without_logout (line ~338)
mock_player.inventory = {}
mock_player.visited_rooms = []    # <-- add this
mock_repo.get_by_username.return_value = mock_player
```

## Impact

- 1 modified file: `tests/test_logout.py` (2 lines added)
- No production code changes
- Eliminates 2 of 8 test warnings (reduces to 6 — remaining are `datetime.utcnow()` deprecations in `test_spawn.py`)

## Verification

- `make test` passes with 745 tests, 6 warnings (down from 8)
- No RuntimeWarnings from `test_logout.py`
