# ISS-023: Inventory Handler Hardcoded HP Defaults

**Severity:** Medium
**Component:** server/net/handlers/inventory.py
**Found during:** Codebase review (adversarial analysis)

## Description

The `handle_use_item` function at lines 80-81 uses hardcoded values:

```python
player_stats.setdefault("hp", 100)
player_stats.setdefault("max_hp", 100)
```

These should reference `settings.DEFAULT_BASE_HP` from `server/core/config.py` (currently `100`). While the values happen to match today, this violates the project convention established in Epic 14 (Story 14.1) that all game balance values must reference `settings.*`.

## Root Cause

These `setdefault` calls were written before the centralization effort in Epic 14 and were missed during the config sweep.

## Proposed Fix

Replace hardcoded `100` with `settings.DEFAULT_BASE_HP`:

```python
player_stats.setdefault("hp", settings.DEFAULT_BASE_HP)
player_stats.setdefault("max_hp", settings.DEFAULT_BASE_HP)
```

Add `from server.core.config import settings` if not already imported.

## Impact

- If `DEFAULT_BASE_HP` is changed, these fallbacks silently drift
- Violates centralized config convention
