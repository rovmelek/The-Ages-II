# ISS-018: NPC Templates Dual Access Pattern

**Severity:** Low (code clarity / future confusion risk)
**Found during:** Epic 14 retrospective
**Status:** Done

## Problem

NPC template data is accessible through two paths:
1. `_NPC_TEMPLATES` module-level global in `server/room/objects/npc.py` (line 45)
2. `game.npc_templates` instance attribute in `server/app.py` (line 50)

At runtime these are the **same dict object** (not a copy), so there is no data inconsistency today. However, the dual access creates:

- **Confusion for future developers** — two ways to look up the same data, no clear canonical path
- **Test fragility** — tests must maintain both references (`_NPC_TEMPLATES.clear()` then `game.npc_templates = _NPC_TEMPLATES`)
- **Isolation hazard** — multiple `Game()` instances in tests share the module global
- **Incomplete ADR delivery** — ADR-14-8 and FR112 specified that `game.npc_templates` **replaces** `_NPC_TEMPLATES`, but the module global was never removed

## Root Cause

Story 14.5 partially implemented ADR-14-8: it added `game.npc_templates` and migrated `scheduler.py` to use it, but did not remove the underlying `_NPC_TEMPLATES` global or migrate the functions that read from it (`get_npc_template`, `create_npc_from_template`). The constraint was that `room/manager.py:load_room()` calls `create_npc_from_template()` during startup without a `game` reference.

## Current Access Map

### Write path (1 location)
- `npc.py:48-61` — `load_npc_templates()` populates `_NPC_TEMPLATES`, returns it
- `app.py:72` — `self.npc_templates = load_npc_templates(npcs_dir)` (assigns same object)

### Read paths (6 production locations)

| Caller | File:Line | Access Path |
|--------|-----------|-------------|
| Scheduler rare spawn loop | `scheduler.py:133` | `game.npc_templates` |
| Scheduler respawn check | `scheduler.py:105` | `get_npc_template()` → `_NPC_TEMPLATES` |
| Scheduler NPC creation | `scheduler.py:190` | `create_npc_from_template()` → `_NPC_TEMPLATES` |
| Game.kill_npc | `app.py:266` | `get_npc_template()` → `_NPC_TEMPLATES` |
| Room loading | `manager.py:37` | `create_npc_from_template()` → `_NPC_TEMPLATES` |
| Movement encounter | `movement.py:198` | `get_npc_template()` → `_NPC_TEMPLATES` |

### Test files (2 files import `_NPC_TEMPLATES` directly)
- `tests/test_spawn.py:18,48,61`
- `tests/test_events.py:156,159,193`

## Proposed Fix

Eliminate `_NPC_TEMPLATES` module global. Make `game.npc_templates` the single source. Thread the templates dict through functions that need it.

### Changes

1. **`server/room/objects/npc.py`**:
   - `load_npc_templates()` — return a new dict instead of populating a global
   - `get_npc_template()` — remove (callers use dict lookup directly)
   - `create_npc_from_template()` — add `templates: dict` parameter
   - Remove `_NPC_TEMPLATES` global

2. **`server/app.py`**:
   - `kill_npc()` — use `self.npc_templates.get(npc.npc_key)` instead of `get_npc_template()`
   - `startup()` — pass `self.npc_templates` to `load_room()`

3. **`server/room/manager.py`**:
   - `load_room()` — add `npc_templates: dict` parameter, pass to `create_npc_from_template()`

4. **`server/core/scheduler.py`**:
   - `_schedule_respawn_internal()` — use `self._game.npc_templates.get()` instead of `get_npc_template()`
   - `_run_rare_spawn_checks()` — pass `self._game.npc_templates` to `create_npc_from_template()`
   - Remove `get_npc_template` import

5. **`server/net/handlers/movement.py`**:
   - Use `game.npc_templates.get()` instead of `get_npc_template()`
   - Remove `get_npc_template` import

6. **Tests** (`test_spawn.py`, `test_events.py`):
   - Stop importing `_NPC_TEMPLATES`
   - Use `load_npc_templates()` return value assigned directly to `game.npc_templates`

## Impact

- Mechanical refactor — zero behavioral change
- All existing tests must pass
- Eliminates the module global entirely
- Single source of truth: `game.npc_templates`
