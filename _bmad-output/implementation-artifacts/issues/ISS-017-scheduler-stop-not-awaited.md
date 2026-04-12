# ISS-017: Scheduler.stop() Does Not Await Task Cancellation — Flaky test_integration

## Severity

Medium (test reliability — flaky failures in ~30-50% of full-suite runs)

## Description

`test_integration.py::TestErrorCases` intermittently fails with `OperationalError: (sqlite3.OperationalError) no active connection` during fixture setup. The error appears only in full-suite runs, never in isolation. The SAWarning `"The garbage collector is trying to clean up non-checked-in connection"` accompanies the failure.

## Affected Files

- `server/core/scheduler.py` — `stop()` is sync, cancels task without awaiting
- `server/app.py` — `shutdown()` calls `self.scheduler.stop()` (sync)
- `tests/test_integration.py` — victim of the flaky failure (not the cause)

## Root Cause

`Scheduler.stop()` (line 48 of `server/core/scheduler.py`) is a **synchronous** method that calls `self._task.cancel()` without awaiting the task's completion:

```python
def stop(self) -> None:
    self._running = False
    if self._task:
        self._task.cancel()   # ← requests cancel but does NOT wait
        self._task = None
    for t in self._respawn_tasks.values():
        t.cancel()            # ← same: fire-and-forget cancel
    self._respawn_tasks.clear()
```

`game.shutdown()` calls `self.scheduler.stop()` (sync), then continues. The lifespan exits, and the TestClient portal begins teardown. The portal forcibly cancels/terminates remaining tasks in its event loop — including the scheduler's `_loop()` task, which hasn't had CPU time to process its `CancelledError` yet.

If `_loop()` was inside `_run_rare_spawn_checks()` → `game.transaction()` at that moment, the underlying aiosqlite connection is terminated mid-operation by the portal cleanup:
- The connection's `rollback()` raises `CancelledError` (portal teardown)
- This produces `OperationalError: no active connection`
- The connection is never returned to the pool → SAWarning about GC cleanup
- The corrupted state sometimes propagates to the next test's `async_engine` fixture

## Proposed Fix

Make `stop()` async and await all task cancellations before returning:

```python
async def stop(self) -> None:
    """Cancel all scheduled tasks and wait for cleanup."""
    self._running = False
    if self._task:
        self._task.cancel()
        try:
            await self._task
        except (asyncio.CancelledError, Exception):
            pass
        self._task = None
    for t in list(self._respawn_tasks.values()):
        t.cancel()
    for t in list(self._respawn_tasks.values()):
        try:
            await t
        except (asyncio.CancelledError, Exception):
            pass
    self._respawn_tasks.clear()
```

Update `game.shutdown()` caller:
```python
await self.scheduler.stop()  # was: self.scheduler.stop()
```

This ensures the scheduler task has fully exited (including closing any open DB connections) before shutdown continues and the portal cleans up.

## Impact

- 2 files modified: `server/core/scheduler.py`, `server/app.py`
- Test files that call `scheduler.stop()` or `game.scheduler.stop()` directly need `await`
- No gameplay behavior changes — purely an async lifecycle fix
