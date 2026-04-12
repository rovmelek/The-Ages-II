# ISS-012: server/app.py async_session import leaks module-level name

**Severity:** Low (latent confusion risk, no functional bug)
**Found during:** Story 11.7 code review
**Date:** 2026-04-11

## Problem

After Story 11.7 migrated all 11 modules from direct `async_session` imports to `game.session_factory`, `server/app.py` still has `from server.core.database import async_session` at line 13. This import is used only once — at line 40 to set the default: `self.session_factory = async_session`.

The import is functionally correct but leaves `async_session` as a name in the `server.app` module namespace. This creates two risks:

1. **Pattern confusion**: Someone reading `app.py` sees the old import pattern and may replicate it in new modules, reintroducing the test isolation gap that Story 11.7 fixed.

2. **Silent test trap**: A developer could write `patch("server.app.async_session", test_factory)` which would succeed (no AttributeError) but accomplish nothing — `Game.__init__()` already captured the reference at construction time, so the patch is too late to affect `game.session_factory`.

## Proposed Fix

Replace the direct import with a module import:

```python
# Before:
from server.core.database import async_session, init_db
# ...
self.session_factory = async_session

# After:
from server.core.database import init_db
from server.core import database as _database
# ...
self.session_factory = _database.async_session
```

This eliminates `async_session` from the `server.app` module namespace entirely. The `_database` prefix signals it's an internal detail used only for default initialization.

## Impact

- 1 file changed: `server/app.py` (2 lines)
- No test changes needed
- No functional behavior change

## Verification

- `grep -r "from server.core.database import async_session" server/` returns zero matches after fix
- All 599 tests pass
