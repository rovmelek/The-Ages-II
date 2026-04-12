# ISS-016: bcrypt Default Rounds Make Test Suite 10x Slower Than Necessary

## Severity

Medium (developer productivity — 22s test suite could be ~2s)

## Description

The test suite takes ~22s to run. Profiling shows that ~21s of that is spent in bcrypt `hashpw`/`checkpw` operations. bcrypt defaults to 12 rounds, making each hash or verify ~0.2s. Across ~101 bcrypt operations in 4 test files, this dominates test execution time.

## Affected Files

- `tests/test_integration.py` — ~48 bcrypt ops (~9.8s)
- `tests/test_login.py` — ~28 bcrypt ops (~5.6s)
- `tests/test_auth.py` — ~15 bcrypt ops (~3.3s)
- `tests/test_stats_persistence.py` — ~10 bcrypt ops (~2.5s)

No other test files exceed 0.7s.

## Root Cause

`server/player/auth.py:7` calls `bcrypt.gensalt()` with no explicit rounds argument, defaulting to 12. This is correct for production security but unnecessary for tests, which only need to verify the hash/verify roundtrip works — not that the work factor is high.

## Proposed Fix

Add a session-scoped `conftest.py` fixture that monkeypatches `bcrypt.gensalt` to use 4 rounds (the minimum bcrypt allows) for the entire test session. This:

1. Reduces each bcrypt operation from ~0.2s to ~0.003s (67x faster)
2. Preserves the actual bcrypt algorithm (hash/verify roundtrip still tested)
3. Does not modify production code
4. Is applied once at session start via `autouse=True` — no changes needed in individual test files

Implementation: Create `tests/conftest.py` with:
```python
import bcrypt
import pytest

_original_gensalt = bcrypt.gensalt

@pytest.fixture(autouse=True, scope="session")
def _fast_bcrypt(monkeypatch_session):
    """Use minimum bcrypt rounds (4) during tests for speed."""
    monkeypatch_session.setattr(bcrypt, "gensalt", lambda rounds=4: _original_gensalt(rounds=4))
```

Note: `monkeypatch` is function-scoped by default. For session scope, we need `monkeypatch_session` — a custom fixture wrapping `MonkeyPatch` at session scope.

### Alternative Considered

**Mocking bcrypt entirely** (return plaintext): Faster but riskier — tests would no longer verify the hash/verify roundtrip works. The reduced-rounds approach preserves correctness while cutting cost.

## Impact

- 1 new file: `tests/conftest.py`
- No production code changes
- Expected test suite time: ~1-2s (down from ~22s)
