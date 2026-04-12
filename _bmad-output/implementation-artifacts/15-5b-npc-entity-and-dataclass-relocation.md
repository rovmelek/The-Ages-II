# Story 15.5b: NpcEntity & Dataclass Relocation

Status: done

## Story

As a developer,
I want `NpcEntity` relocated from `room/objects/` to `room/`, and Trade/Party dataclasses split into their own files,
So that the domain model is accurately organized and consistent across modules.

## Acceptance Criteria

1. **Given** `NpcEntity` is a `@dataclass` in `server/room/objects/npc.py` alongside `InteractiveObject` subclasses (ChestObject, LeverObject) despite not extending `RoomObject` or `InteractiveObject`,
   **When** Story 15.5b is implemented,
   **Then** `NpcEntity` and all co-located functions (`create_npc_from_template`, `load_npc_templates`, `_derive_stats_from_hit_dice`) are relocated to `server/room/npc.py` (at the room level, not inside `objects/`),
   **And** all imports across 16 files are updated (4 server + 12 test — see import map below),
   **And** the old `server/room/objects/npc.py` file is deleted.

2. **Given** `Trade` dataclass is co-located in `server/trade/manager.py` (line 12),
   **When** Story 15.5b is implemented,
   **Then** `Trade` is moved to `server/trade/session.py`,
   **And** `TradeManager` in `server/trade/manager.py` imports `Trade` from `server.trade.session`,
   **And** no external files need import changes (no file imports `Trade` by name outside `manager.py`).

3. **Given** `Party` dataclass is co-located in `server/party/manager.py` (line 16),
   **When** Story 15.5b is implemented,
   **Then** `Party` is moved to `server/party/party.py`,
   **And** `PartyManager` in `server/party/manager.py` imports `Party` from `server.party.party`,
   **And** `tests/test_party.py` (line 8) updates its import from `server.party.manager` to `server.party.party`.

4. **Given** all existing tests (807+),
   **When** Story 15.5b is implemented,
   **Then** all tests pass with no assertion value changes.

## Tasks / Subtasks

- [x] Task 1: Relocate NpcEntity to `server/room/npc.py` (AC: #1)
  - [x] 1.1: Create `server/room/npc.py` containing `NpcEntity`, `create_npc_from_template`, `load_npc_templates`, and `_derive_stats_from_hit_dice` — copy all content from `server/room/objects/npc.py`
  - [x] 1.2: Update 4 server file imports (see import map)
  - [x] 1.3: Update 12 test file imports (see import map)
  - [x] 1.4: Delete `server/room/objects/npc.py`
  - [x] 1.5: Verify `server/room/objects/__init__.py` does NOT reference npc (it only registers ChestObject and LeverObject — no change needed)

- [x] Task 2: Extract Trade dataclass to `server/trade/session.py` (AC: #2)
  - [x] 2.1: Create `server/trade/session.py` with the `Trade` dataclass (move lines 12-25 from `manager.py`) and required imports (`asyncio`, `time`, `dataclasses.dataclass`, `dataclasses.field`)
  - [x] 2.2: In `server/trade/manager.py`, remove `Trade` class definition, add `from server.trade.session import Trade`
  - [x] 2.3: No external import changes needed — `Trade` is not imported by name outside `manager.py`

- [x] Task 3: Extract Party dataclass to `server/party/party.py` (AC: #3)
  - [x] 3.1: Create `server/party/party.py` with the `Party` dataclass (move lines 16-23 from `manager.py`) and required imports (`time`, `dataclasses.dataclass`, `dataclasses.field`)
  - [x] 3.2: In `server/party/manager.py`, remove `Party` class definition, add `from server.party.party import Party`
  - [x] 3.3: Update `tests/test_party.py` line 8: change `from server.party.manager import Party, PartyManager` to import `Party` from `server.party.party` and `PartyManager` from `server.party.manager`

- [x] Task 4: Verify tests (AC: #4)
  - [x] 4.1: Run `make test` — all 807 tests pass with 0 failures, 0 warnings

## Dev Notes

### NPC Import Map (16 files to update)

**Server files (4):**

| File | Current Import | Type |
|------|---------------|------|
| `server/app.py` (line 70, inside `startup()`) | `from server.room.objects.npc import load_npc_templates` | Inline/lazy import |
| `server/core/scheduler.py` (line 12) | `from server.room.objects.npc import create_npc_from_template` | Top-level |
| `server/room/room.py` (line 14) | `from server.room.objects.npc import NpcEntity` | Under `TYPE_CHECKING` |
| `server/room/manager.py` (line 6) | `from server.room.objects.npc import create_npc_from_template` | Top-level |

**Test files (12):**

| File | Import Location | Symbols |
|------|----------------|---------|
| `tests/test_npc.py` (line 11) | Top-level | `NpcEntity, create_npc_from_template, load_npc_templates` |
| `tests/test_spawn.py` (line 16) | Top-level | `NpcEntity, create_npc_from_template, load_npc_templates` |
| `tests/test_combat_entry.py` (line 9) | Top-level | `NpcEntity` |
| `tests/test_integration.py` (line 18) | Top-level | `NpcEntity` |
| `tests/test_query.py` (line 15) | Top-level | `NpcEntity` |
| `tests/test_concurrency.py` (line 19) | Top-level | `NpcEntity` |
| `tests/test_logout.py` (line 174) | Inline (inside test function) | `NpcEntity` |
| `tests/test_room_system.py` (line 214) | Inline (inside test function) | `NpcEntity` |
| `tests/test_loot.py` (line 115) | Inline (inside test function) | `NpcEntity` |
| `tests/test_startup_wiring.py` (lines 198, 226) | Inline (inside test functions) | `create_npc_from_template, load_npc_templates` |
| `tests/test_sample_data.py` (line 165) | Inline (inside test function) | `load_npc_templates` |
| `tests/test_events.py` (line 156) | Inline (inside test function) | `load_npc_templates` |

All 16 imports change from `server.room.objects.npc` → `server.room.npc`.

### Trade/Party Import Impact

- **Trade**: Zero external import changes. Only `TradeManager` in `server/trade/manager.py` uses `Trade` by name.
- **Party**: One external import change: `tests/test_party.py` line 8 imports `Party` by name from `server.party.manager`.

### Architecture & Patterns

- **Pure refactor** — zero gameplay behavior changes
- NPC relocation has the largest blast radius (16 files) — use find-and-replace on `server.room.objects.npc` → `server.room.npc`
- Trade/Party splits are low-risk (few imports)
- `server/room/objects/__init__.py` only registers `ChestObject` and `LeverObject` — no NPC references to clean up
- The private helper `_derive_stats_from_hit_dice` must move with `NpcEntity` (it's called by `create_npc_from_template`)

### Anti-Patterns to Avoid

- Do NOT change any gameplay behavior — pure refactor
- Do NOT change assertion values in any test
- Do NOT add re-exports from old locations — clean break, update all imports
- Do NOT modify `server/room/objects/__init__.py` — it doesn't reference NPC symbols
- Do NOT change `TradeManager` or `PartyManager` class logic — only move the dataclasses
- All new files (`server/room/npc.py`, `server/trade/session.py`, `server/party/party.py`) MUST have `from __future__ import annotations` as the first import — project convention per `project-context.md`
- Ensure `server/trade/session.py` includes the `asyncio` and `time` imports needed by `Trade`'s field defaults
- Ensure `server/party/party.py` includes the `time` import needed by `Party`'s field defaults

### Previous Story Intelligence

From Story 15.5a:
- Pure refactor pattern: move/extract logic, update all call sites, verify all 807+ tests pass
- Single-concern changes keep the diff small and review easy
- Line numbers in epics may drift — verify against actual code before editing

From Story 15.4:
- `PartyManager` constructor takes `connection_manager` via dependency injection
- Party invite state (pending, outgoing, timeouts, cooldowns) lives on `PartyManager` — the `Party` dataclass is just the group data

### Project Structure Notes

- NPC relocation: `server/room/objects/` is for `InteractiveObject` subclasses (ChestObject, LeverObject). `NpcEntity` is a standalone dataclass that doesn't inherit from any objects base class — it belongs at the `server/room/` level
- Trade/Party split: follows the same pattern as other modules where dataclasses live in their own files (e.g., `server/player/session.py` for `PlayerSession`, `server/player/entity.py` for `PlayerEntity`)

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Story 15.5b (lines 3814-3841)]
- [Source: server/room/objects/npc.py — NpcEntity definition (line 13), load_npc_templates (line 46), create_npc_from_template (line 90)]
- [Source: server/trade/manager.py — Trade dataclass (line 12)]
- [Source: server/party/manager.py — Party dataclass (line 16)]
- [Source: _bmad-output/implementation-artifacts/15-5a-extract-effect-targeting.md — Previous story]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- All 807 tests pass (0 failures, 0 warnings, ~3.8s)
- `grep -c "server.room.objects.npc" server/ tests/` = 0 (no remaining old import paths in runtime/test code)
- Initial run had 5 failures: `PartyManager.set_cooldown()` used `time.time()` but `time` import was removed when extracting `Party` dataclass. Fixed by re-adding `import time` to `manager.py`.

### Completion Notes List

- Created `server/room/npc.py` — relocated `NpcEntity`, `create_npc_from_template`, `load_npc_templates`, `_derive_stats_from_hit_dice` from `server/room/objects/npc.py`
- Updated 16 import sites (4 server + 12 test files) from `server.room.objects.npc` → `server.room.npc`
- Deleted `server/room/objects/npc.py`
- Created `server/trade/session.py` — extracted `Trade` dataclass from `server/trade/manager.py`
- Updated `server/trade/manager.py` to import `Trade` from `server.trade.session`
- Created `server/party/party.py` — extracted `Party` dataclass from `server/party/manager.py`
- Updated `server/party/manager.py` to import `Party` from `server.party.party`; retained `import time` since `PartyManager.set_cooldown()` uses `time.time()`
- Updated `tests/test_party.py` to import `Party` from `server.party.party`
- Pure refactor — zero gameplay behavior changes

### File List

**New:**
- `server/room/npc.py` — NpcEntity and template functions relocated from `server/room/objects/npc.py`
- `server/trade/session.py` — Trade dataclass extracted from `server/trade/manager.py`
- `server/party/party.py` — Party dataclass extracted from `server/party/manager.py`

**Modified:**
- `server/app.py` — import path updated
- `server/core/scheduler.py` — import path updated
- `server/room/room.py` — import path updated
- `server/room/manager.py` — import path updated
- `server/trade/manager.py` — Trade class removed, import added from session.py
- `server/party/manager.py` — Party class removed, import added from party.py
- `tests/test_npc.py` — import path updated
- `tests/test_spawn.py` — import path updated
- `tests/test_combat_entry.py` — import path updated
- `tests/test_integration.py` — import path updated
- `tests/test_query.py` — import path updated
- `tests/test_concurrency.py` — import path updated
- `tests/test_logout.py` — import path updated
- `tests/test_room_system.py` — import path updated
- `tests/test_loot.py` — import path updated
- `tests/test_startup_wiring.py` — import path updated (2 sites)
- `tests/test_sample_data.py` — import path updated
- `tests/test_events.py` — import path updated
- `tests/test_party.py` — Party import path updated

**Deleted:**
- `server/room/objects/npc.py` — content relocated to `server/room/npc.py`
