# ISS-015: datetime.utcnow() Deprecation Warnings in Tests

## Severity

Low (test warnings — no production impact)

## Description

6 test sites use `datetime.utcnow()`, which is deprecated in Python 3.12+ and scheduled for removal. This produces `DeprecationWarning` messages on every test run.

## Affected Files

- `tests/test_spawn.py` — lines 179, 218, 254, 291, 364 (5 occurrences)
- `tests/test_events.py` — line 197 (1 occurrence)

## Root Cause

The tests were written using `datetime.utcnow()` to create mock `SpawnCheckpoint` timestamp data. Python 3.12 deprecated this method because it returns a naive datetime that callers often mistakenly treat as timezone-aware.

The production code (`server/core/scheduler.py:118,204`) already uses the modern replacement: `datetime.now(UTC).replace(tzinfo=None)`. The tests were never updated to match.

## Proposed Fix

Replace `datetime.utcnow()` with `datetime.now(UTC).replace(tzinfo=None)` in all 6 test sites. This:

1. Matches the production code's pattern exactly (`server/core/scheduler.py:118`)
2. Produces the same naive UTC datetime that `utcnow()` produced (no semantic change)
3. Preserves type consistency with the `SpawnCheckpoint` model, which uses `DateTime` (naive) columns
4. Eliminates all 6 deprecation warnings

Additionally, add `UTC` to the `from datetime import` statement in both test files.

**Why not `datetime.now(UTC)` without `.replace(tzinfo=None)`?** The DB model stores naive datetimes. The scheduler produces naive datetimes. The mock checkpoint data must also be naive for comparisons to work correctly. Mixing aware and naive datetimes raises `TypeError` in Python.

**Why not make everything timezone-aware?** That would require changing the `SpawnCheckpoint` model to `DateTime(timezone=True)`, updating all scheduler comparisons, and dealing with SQLite timezone quirks — a larger refactor with no functional benefit for a UTC-only system.

## Impact

- 2 modified test files (6 lines changed + 2 import updates)
- No production code changes
- Eliminates all 6 remaining test warnings (reduces to 0 warnings)
