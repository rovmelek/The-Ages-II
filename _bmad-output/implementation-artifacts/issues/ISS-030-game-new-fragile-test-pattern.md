# ISS-030: Game.__new__ Fragile Test Pattern

**Severity:** Medium
**Status:** Done
**Found during:** Epic 16 Retrospective (2026-04-12)

## Problem

11 test instances across 4 files use `Game.__new__(Game)` to create a `Game` object without calling `__init__`, then manually set only the attributes they need. Every time a new field is added to `Game.__init__`, these tests break with `AttributeError`.

This happened in:
- Story 16.9: Added `token_store` and `_cleanup_handles` — heartbeat tests broke
- Story 16.10: Added `_shutting_down` check in `handle_disconnect` — heartbeat tests broke again

## Affected Files

| File | Instances | Used by |
|------|-----------|---------|
| `tests/test_heartbeat.py` | 5 | `_make_game`, `test_heartbeat_sends_ping`, `test_heartbeat_timeout_closes_ws`, `test_disconnect_cancels_heartbeat`, `test_shutdown_cancels_all` |
| `tests/test_grace_period.py` | 2 | `_make_game`, `test_shutdown_cancels_cleanup_handles` |
| `tests/test_events.py` | 2 | `test_rare_spawn_emits_announcement`, `test_event_error_isolation` |
| `tests/test_spawn.py` | 2 | `test_kill_npc_schedules_respawn`, `test_kill_npc_non_persistent` |

## Root Cause

Tests need a real `Game` object (not `MagicMock`) because they test methods defined on `Game` itself (`handle_disconnect`, `shutdown`, `_start_heartbeat`, `_cancel_heartbeat`, `_heartbeat_loop`, `kill_npc`, `_register_events`). A `MagicMock` wouldn't have these methods with real logic.

`Game.__new__` skips `__init__` to avoid importing/initializing all managers (RoomManager, CombatManager, etc.) which would require database setup.

## Proposed Fix

Replace `Game.__new__(Game)` with a helper function `make_bare_game()` in `tests/conftest.py` that calls `Game.__new__(Game)` once and sets ALL `__init__` attributes to safe defaults (MagicMock for managers, empty dicts for internal state). When new fields are added to `Game.__init__`, only this one function needs updating.

```python
def make_bare_game(**overrides):
    """Create a Game with all __init__ attrs set to safe defaults."""
    from server.app import Game
    game = Game.__new__(Game)
    # Mirror every field from Game.__init__
    game.router = MagicMock()
    game.connection_manager = MagicMock()
    game.room_manager = MagicMock()
    game.scheduler = MagicMock()
    game.event_bus = MagicMock()
    game.effect_registry = MagicMock()
    game.combat_manager = MagicMock()
    game.trade_manager = MagicMock()
    game.party_manager = MagicMock()
    game.player_manager = MagicMock()
    game.session_factory = MagicMock()
    game._shutting_down = False
    game.loot_tables = {}
    game.npc_templates = {}
    game._heartbeat_tasks = {}
    game._pong_events = {}
    game.token_store = MagicMock()
    game._cleanup_handles = {}
    for key, value in overrides.items():
        setattr(game, key, value)
    return game
```

Tests then call `make_bare_game()` and override only what they need:
```python
game = make_bare_game(npc_templates=self.npc_templates)
```

## Impact

- 11 instances across 4 files replaced
- Future `Game.__init__` field additions only need updating in `make_bare_game`
- No behavior change — tests call the same real `Game` methods
