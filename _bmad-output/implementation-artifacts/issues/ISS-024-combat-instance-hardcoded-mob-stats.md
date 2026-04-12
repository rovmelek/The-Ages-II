# ISS-024: CombatInstance Hardcoded Fallback Mob Stats

**Severity:** Low-Medium
**Component:** server/combat/instance.py
**Found during:** Codebase review (adversarial analysis)

## Description

`CombatInstance.__init__` at line 30 has a hardcoded fallback:

```python
self.mob_stats: dict = dict(mob_stats) if mob_stats else {"hp": 50, "max_hp": 50, "attack": 10}
```

The values `50` and `10` are not derived from config. All callers (`CombatManager.create_combat`, `CombatManager.start_combat`) always provide `mob_stats`, so the fallback only fires in direct construction (tests). However, this still violates the centralized config convention.

## Root Cause

This defensive default predates the Epic 14 config centralization and was missed during the sweep.

## Proposed Fix

Use config-derived values for the fallback:

```python
self.mob_stats: dict = dict(mob_stats) if mob_stats else {
    "hp": settings.DEFAULT_BASE_HP,
    "max_hp": settings.DEFAULT_BASE_HP,
    "attack": settings.DEFAULT_ATTACK,
}
```

Add `from server.core.config import settings` import.

## Impact

- Defensive default only; all production callers provide explicit stats
- Brings the module into compliance with centralized config convention
