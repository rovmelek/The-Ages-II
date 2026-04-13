# Story 17.1: Centralize Type Constants

Status: done

## Story

As a developer,
I want all scattered string constants (stat names, effect types, spawn types, behavior types) defined in shared typed locations,
So that adding or renaming a type requires changing one place, and typos are caught at import time instead of runtime.

## Acceptance Criteria

1. **Given** the string literals `"strength"`, `"dexterity"`, `"constitution"`, `"intelligence"`, `"wisdom"`, `"charisma"` scattered across 9 files,
   **When** Story 17.1 is implemented,
   **Then** a `STAT_NAMES` tuple exists in `server/core/constants.py` containing all 6 stat names.

2. **Given** `_VALID_LEVEL_UP_STATS` in `levelup.py`,
   **When** Story 17.1 is implemented,
   **Then** it is defined as `set(STAT_NAMES)` imported from `server.core.constants`.

3. **Given** `_STATS_WHITELIST` in `player/repo.py`,
   **When** Story 17.1 is implemented,
   **Then** it includes `STAT_NAMES` via import — defined as `{"hp", "max_hp", "xp", "level", *STAT_NAMES}`.

4. **Given** `_default_stats()` in `auth.py`,
   **When** Story 17.1 is implemented,
   **Then** it constructs its dict by iterating `STAT_NAMES` with `settings.DEFAULT_STAT_VALUE`.

5. **Given** `_derive_stats_from_hit_dice()` in `npc.py`,
   **When** Story 17.1 is implemented,
   **Then** it uses `STAT_NAMES` for stat block generation.

6. **Given** stat payload construction in `_build_login_response()`, `handle_register()`, `handle_stats()`, and `send_level_up_available()`,
   **When** Story 17.1 is implemented,
   **Then** these use `STAT_NAMES` iteration instead of listing all 6 strings inline.

7. **Given** individual stat lookups in effect handlers (`damage.py`, `heal.py`) and combat (`instance.py`),
   **When** Story 17.1 is implemented,
   **Then** these remain as direct string references — individual stats referenced by game design intent, no change required.

8. **Given** the string literals `"damage"`, `"heal"`, `"shield"`, `"dot"`, `"draw"` across `core/effects/` and `combat/instance.py`,
   **When** Story 17.1 is implemented,
   **Then** an `EffectType` StrEnum exists in `server/core/constants.py` with members `DAMAGE`, `HEAL`, `SHIELD`, `DOT`, `DRAW`.

9. **Given** `create_default_registry()` in `registry.py`,
   **When** Story 17.1 is implemented,
   **Then** it uses `EffectType` members for registration keys.

10. **Given** each effect handler's return dict,
    **When** Story 17.1 is implemented,
    **Then** each handler uses `EffectType` in its `"type"` return value.

11. **Given** `_resolve_effect_targets()` in `instance.py`,
    **When** Story 17.1 is implemented,
    **Then** the self-targeting tuple uses `EffectType` members: `(EffectType.HEAL, EffectType.SHIELD, EffectType.DRAW)`.

12. **Given** `_process_dot_effects()` in `instance.py` checking `dot.get("type") != "dot"`,
    **When** Story 17.1 is implemented,
    **Then** it uses `dot.get("type") != EffectType.DOT`.

13. **Given** `resolve_card_effects()` in `instance.py` checking `effect_type == "draw"`,
    **When** Story 17.1 is implemented,
    **Then** it uses `effect_type == EffectType.DRAW`.

14. **Given** JSON data files (`data/cards/`, `data/items/`),
    **When** Story 17.1 is implemented,
    **Then** they are NOT modified — StrEnum compares equal to string values (ADR-17-1).

15. **Given** the string literal `"persistent"` in `kill_npc()` in `app.py` and `"rare"` in `_run_rare_spawn_checks()` in `scheduler.py`,
    **When** Story 17.1 is implemented,
    **Then** constants `SPAWN_PERSISTENT` and `SPAWN_RARE` exist in `server/core/constants.py` and both reference sites import and use them.

16. **Given** the string literal `"hostile"` in `room.py` and `npc.py`,
    **When** Story 17.1 is implemented,
    **Then** a constant `BEHAVIOR_HOSTILE` exists in `server/room/npc.py` (single-package usage per ADR-17-2) and `room.py` imports and uses it.

17. **Given** all 1062 existing tests,
    **When** Story 17.1 is implemented,
    **Then** all tests pass unchanged — StrEnum members compare equal to string values.

## Tasks / Subtasks

- [x] Task 1: Create `server/core/constants.py` (AC: #1, #8, #15)
  - [x] 1.1 Add `from __future__ import annotations` as first import
  - [x] 1.2 Add `from enum import StrEnum`
  - [x] 1.3 Define `STAT_NAMES: tuple[str, ...] = ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma")`
  - [x] 1.4 Define `EffectType(StrEnum)` with members `DAMAGE = "damage"`, `HEAL = "heal"`, `SHIELD = "shield"`, `DOT = "dot"`, `DRAW = "draw"`
  - [x] 1.5 Define `SPAWN_PERSISTENT = "persistent"` and `SPAWN_RARE = "rare"`

- [x] Task 2: Update stat name consumers to use `STAT_NAMES` (AC: #2, #3, #4, #5, #6)
  - [x] 2.1 `server/net/handlers/levelup.py`: `_VALID_LEVEL_UP_STATS = set(STAT_NAMES)` — import from `server.core.constants`
  - [x] 2.2 `server/player/repo.py`: `_STATS_WHITELIST = {"hp", "max_hp", "xp", "level", *STAT_NAMES}` — import from `server.core.constants`
  - [x] 2.3 `server/net/handlers/auth.py` in `_default_stats()`: iterate `STAT_NAMES` to build dict with `settings.DEFAULT_STAT_VALUE`
  - [x] 2.4 `server/net/handlers/auth.py` in `_build_login_response()`: use `STAT_NAMES` iteration for stats payload
  - [x] 2.5 `server/net/handlers/auth.py` in `handle_register()`: use `STAT_NAMES` iteration for stats response
  - [x] 2.6 `server/net/handlers/query.py` in `handle_stats()`: use `STAT_NAMES` iteration for stats response
  - [x] 2.7 `server/core/xp.py` in `send_level_up_available()`: use `STAT_NAMES` iteration for `current_stats` dict only — `stat_effects` has per-stat unique descriptions and must remain individual entries
  - [x] 2.8 `server/room/npc.py` in `_derive_stats_from_hit_dice()`: use `STAT_NAMES` iteration for stat block

- [x] Task 3: Update effect type consumers to use `EffectType` (AC: #9, #10, #11, #12, #13)
  - [x] 3.1 `server/core/effects/registry.py` in `create_default_registry()`: use `EffectType.DAMAGE`, etc.
  - [x] 3.2 `server/core/effects/damage.py`: return `"type": EffectType.DAMAGE`
  - [x] 3.3 `server/core/effects/heal.py`: return `"type": EffectType.HEAL`
  - [x] 3.4 `server/core/effects/shield.py`: return `"type": EffectType.SHIELD`
  - [x] 3.5 `server/core/effects/dot.py`: use `EffectType.DOT` in BOTH the `active_effects` append dict AND the return dict (two occurrences of `"type": "dot"`)
  - [x] 3.6 `server/core/effects/draw.py`: return `"type": EffectType.DRAW`
  - [x] 3.7 `server/combat/instance.py` in `_resolve_effect_targets()`: use `EffectType` for self-targeting tuple
  - [x] 3.8 `server/combat/instance.py` in `resolve_card_effects()`: use `EffectType.DRAW`
  - [x] 3.9 `server/combat/instance.py` in `_process_dot_effects()`: use `EffectType.DOT`
  - [x] 3.10 `server/net/handlers/movement.py` in `_handle_mob_encounter()`: use `EffectType.DAMAGE` in fallback card `effects` list

- [x] Task 4: Update spawn type consumers (AC: #15)
  - [x] 4.1 `server/app.py` in `kill_npc()`: import and use `SPAWN_PERSISTENT`
  - [x] 4.2 `server/core/scheduler.py` in `_run_rare_spawn_checks()`: import and use `SPAWN_RARE`

- [x] Task 5: Add `BEHAVIOR_HOSTILE` constant (AC: #16)
  - [x] 5.1 `server/room/npc.py`: define `BEHAVIOR_HOSTILE = "hostile"` and use in `create_npc_from_template()`
  - [x] 5.2 `server/room/room.py` in `move_entity()`: import `BEHAVIOR_HOSTILE` from `server.room.npc` and use it

- [x] Task 6: Verify all tests pass (AC: #17)
  - [x] 6.1 Run `make test` — all 1062 tests must pass unchanged

## Dev Notes

### Architecture & Design Decisions

- **ADR-17-1**: StrEnum compares equal to plain strings — `EffectType.DAMAGE == "damage"` is `True`. JSON data files (`data/cards/`, `data/items/`) are NOT modified. No deserialization changes needed.
- **ADR-17-2**: `core/constants.py` is for cross-cutting constants (used in 2+ packages). Domain-local constants stay in their package — `BEHAVIOR_HOSTILE` goes in `server/room/npc.py` because only `room/` uses it.
- `StrEnum` is available in Python 3.11+ stdlib (`from enum import StrEnum`) — no extra dependency.

### Files to Create

| File | Content |
|------|---------|
| `server/core/constants.py` | `STAT_NAMES` tuple, `EffectType` StrEnum, `SPAWN_PERSISTENT`, `SPAWN_RARE` (~25 lines) |

### Files to Modify

| File | Function/Location | Change |
|------|-------------------|--------|
| `server/net/handlers/levelup.py` | `_VALID_LEVEL_UP_STATS` | `set(STAT_NAMES)` from import |
| `server/player/repo.py` | `_STATS_WHITELIST` | `{"hp", "max_hp", "xp", "level", *STAT_NAMES}` |
| `server/net/handlers/auth.py` | `_default_stats()` | Iterate `STAT_NAMES` |
| `server/net/handlers/auth.py` | `_build_login_response()` | Iterate `STAT_NAMES` for stats payload |
| `server/net/handlers/auth.py` | `handle_register()` | Iterate `STAT_NAMES` for stats response |
| `server/net/handlers/query.py` | `handle_stats()` | Iterate `STAT_NAMES` for stats response |
| `server/core/xp.py` | `send_level_up_available()` | Iterate `STAT_NAMES` for `current_stats` only; `stat_effects` has per-stat descriptions, keep individual |
| `server/room/npc.py` | `_derive_stats_from_hit_dice()` | Iterate `STAT_NAMES` for stat block |
| `server/room/npc.py` | Module level + `create_npc_from_template()` | Add `BEHAVIOR_HOSTILE`, use it |
| `server/room/room.py` | `move_entity()` | Import and use `BEHAVIOR_HOSTILE` |
| `server/core/effects/registry.py` | `create_default_registry()` | Use `EffectType` members |
| `server/core/effects/damage.py` | `handle_damage()` return | `EffectType.DAMAGE` |
| `server/core/effects/heal.py` | `handle_heal()` return | `EffectType.HEAL` |
| `server/core/effects/shield.py` | `handle_shield()` return | `EffectType.SHIELD` |
| `server/core/effects/dot.py` | `handle_dot()` return | `EffectType.DOT` |
| `server/core/effects/draw.py` | `handle_draw()` return | `EffectType.DRAW` |
| `server/combat/instance.py` | `_resolve_effect_targets()`, `resolve_card_effects()`, `_process_dot_effects()` | Use `EffectType` members |
| `server/app.py` | `kill_npc()` | Import and use `SPAWN_PERSISTENT` |
| `server/core/scheduler.py` | `_run_rare_spawn_checks()` | Import and use `SPAWN_RARE` |
| `server/net/handlers/movement.py` | `_handle_mob_encounter()` | Use `EffectType.DAMAGE` in fallback card effects |

### DO NOT Modify

- `server/core/effects/damage.py` individual stat lookups (`"strength"`, `"intelligence"`, `"dexterity"`) — game-design-intent references, not type constants
- `server/core/effects/heal.py` individual stat lookup (`"wisdom"`) — same reason
- `server/combat/instance.py` individual stat lookups in `_mob_attack_target()` (`"strength"`, `"dexterity"`) and `get_combat_end_result()` (`"charisma"`) — same reason
- `server/core/xp.py` individual stat lookup (`"charisma"`) in `apply_xp()` — same reason
- `server/core/xp.py` `stat_effects` dict in `send_level_up_available()` — per-stat unique description strings, not iterable
- `server/net/handlers/auth.py` `_resolve_stats()` reference to `stats["constitution"]` — game-design-intent (constitution drives max_hp calc)
- `server/net/handlers/levelup.py` `handle_level_up()` reference to `stats.get("constitution", ...)` — same reason
- `server/net/outbound_schemas.py` `PlayerStatsPayload` — Pydantic model fields, not string literals
- `data/cards/*.json`, `data/items/*.json` — StrEnum compares equal to strings (ADR-17-1)

### Testing Strategy

- **Zero test changes expected** — StrEnum members compare equal to string values, so all assertions pass.
- Run `make test` to verify all 1062 tests pass.
- If any test fails, it indicates a StrEnum comparison edge case — investigate before fixing.

### Project Structure Notes

- New file `server/core/constants.py` follows existing `server/core/` conventions (`config.py`, `events.py`, `xp.py`)
- `from __future__ import annotations` must be first import per project rules
- Import chain: `core/constants.py` has zero intra-project imports (leaf module) — no circular import risk

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Story 17.1 AC]
- [Source: _bmad-output/planning-artifacts/epics.md — ADR-17-1, ADR-17-2]
- [Source: _bmad-output/implementation-artifacts/codebase-adversarial-review-2026-04-12.md — F3, F4 (type constants)]
- [Source: server/core/config.py — Settings class with DEFAULT_STAT_VALUE]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Debug Log References

### Completion Notes List
- Created `server/core/constants.py` with `STAT_NAMES`, `EffectType` StrEnum, `SPAWN_PERSISTENT`, `SPAWN_RARE`
- Updated 8 stat name consumer sites to use `STAT_NAMES` iteration
- Updated 10 effect type consumer sites to use `EffectType` members
- Updated 2 spawn type consumers to use constants
- Added `BEHAVIOR_HOSTILE` to `npc.py` and updated `room.py`
- All 1066 tests pass (0 failures, 0 test changes needed — StrEnum equality confirmed)

### File List
- `server/core/constants.py` (new)
- `server/net/handlers/levelup.py` (modified)
- `server/player/repo.py` (modified)
- `server/net/handlers/auth.py` (modified)
- `server/net/handlers/query.py` (modified)
- `server/core/xp.py` (modified)
- `server/room/npc.py` (modified)
- `server/room/room.py` (modified)
- `server/core/effects/registry.py` (modified)
- `server/core/effects/damage.py` (modified)
- `server/core/effects/heal.py` (modified)
- `server/core/effects/shield.py` (modified)
- `server/core/effects/dot.py` (modified)
- `server/core/effects/draw.py` (modified)
- `server/combat/instance.py` (modified)
- `server/app.py` (modified)
- `server/core/scheduler.py` (modified)
- `server/net/handlers/movement.py` (modified)
