# Story 3.5: Tiered NPC Spawn System

Status: done

## Story

As a player,
I want NPCs to respawn after being killed and rare world bosses to appear on a schedule,
So that the world feels persistent and there are always things to fight.

## Acceptance Criteria

1. NPC with `spawn_type: "persistent"` is killed → after `respawn_seconds` elapses → NPC respawns at original position with full HP → players in room receive `entity_entered` message
2. NPC with `spawn_type: "rare"` and `check_interval_hours: 12`, `spawn_chance: 0.15` → scheduler runs spawn check → random roll determines spawn (15% chance) → `SpawnCheckpoint` updated with `last_check_at`/`next_check_at` → if spawned, NPC appears in configured room
3. Server restarts → scheduler loads `SpawnCheckpoint` records from DB → spawn timers resume from where they left off (not reset to zero) → if a check was due during downtime, it runs on startup
4. Rare NPC has `max_active: 1` and is already spawned → scheduler runs another check → no additional instance spawns

## Tasks / Subtasks

- [x] Task 1: Create `server/core/scheduler.py` — periodic task runner (AC: #1, #2, #3)
  - [x] `Scheduler` class with `start(game)` / `stop()` methods
  - [x] `start()` launches an `asyncio.Task` loop that runs periodic checks
  - [x] On start, load all `SpawnCheckpoint` rows from DB and schedule any overdue checks immediately
  - [x] Provide `schedule_respawn(room_key, npc_id, delay_seconds)` for persistent NPC respawn timers
  - [x] Provide `_run_rare_spawn_checks()` for periodic rare NPC spawn rolls
  - [x] `stop()` cancels the background task
- [x] Task 2: Implement persistent NPC respawn logic (AC: #1)
  - [x] When an NPC dies (is_alive set to False), call `scheduler.schedule_respawn(room_key, npc_id, respawn_seconds)`
  - [x] After delay, reset NPC's `is_alive = True`, restore stats to template defaults (full HP)
  - [x] Broadcast `{"type": "entity_entered", "entity": npc.to_dict()}` to room players
  - [x] Add `respawn_npc(room_key, npc_id)` method to handle the actual respawn
- [x] Task 3: Implement rare NPC spawn check logic (AC: #2, #4)
  - [x] `_run_rare_spawn_checks()` iterates all NPC templates with `spawn_type: "rare"`
  - [x] For each, load/create `SpawnCheckpoint` from DB
  - [x] If `next_check_at <= now`: roll `random.random() < spawn_chance`
  - [x] If spawned and `max_active` not exceeded: create NPC in target room, set `currently_spawned = True`
  - [x] Update `last_check_at = now`, `next_check_at = now + check_interval_hours`
  - [x] Persist checkpoint to DB
- [x] Task 4: Add rare NPC template to `data/npcs/base_npcs.json` (AC: #2)
  - [x] Add a rare NPC template, e.g., `"forest_dragon"` with `spawn_type: "rare"`, `check_interval_hours: 12`, `spawn_chance: 0.15`, `max_active: 1`, `despawn_after_hours: 6`
  - [x] Add `room_key` field to rare NPC template config to specify where it spawns
- [x] Task 5: Integrate Scheduler into Game lifecycle (AC: #3)
  - [x] `Game.__init__()`: create `self.scheduler = Scheduler()`
  - [x] `Game.startup()`: call `await self.scheduler.start(self)` after rooms are loaded
  - [x] `Game.shutdown()`: call `self.scheduler.stop()`
- [x] Task 6: Expose NPC kill hook for respawn scheduling (AC: #1)
  - [x] Add `kill_npc(room_key, npc_id)` method to Game
  - [x] Sets `npc.is_alive = False`, looks up spawn_config, calls `scheduler.schedule_respawn()` if persistent
  - [x] This is the hook combat (Epic 4) will call when an NPC dies
- [x] Task 7: Handle server restart checkpoint recovery (AC: #3)
  - [x] On `scheduler.start()`, query all `SpawnCheckpoint` rows
  - [x] For overdue checks (`next_check_at <= now`), run spawn check immediately
  - [x] For future checks, schedule them for the remaining time
- [x] Task 8: Write tests `tests/test_spawn.py` (AC: #1-4)
  - [x] Test persistent NPC respawn after delay (mock asyncio.sleep or use short timer)
  - [x] Test rare NPC spawn roll (mock random, test spawn/no-spawn outcomes)
  - [x] Test max_active prevents duplicate rare spawns
  - [x] Test SpawnCheckpoint persistence and recovery
  - [x] Test scheduler start/stop lifecycle
- [x] Task 9: Verify all tests pass
  - [x] Run `pytest tests/test_spawn.py -v` — 12 passed
  - [x] Run `pytest tests/ -v` to verify no regressions — 165 passed

## Dev Notes

### Architecture Compliance

| Component | File Location |
|-----------|--------------|
| Scheduler | `server/core/scheduler.py` (NEW) |
| SpawnCheckpoint model | `server/room/spawn_models.py` (ALREADY EXISTS) |
| NPC templates | `data/npcs/base_npcs.json` (modify — add rare NPC) |
| NpcEntity | `server/room/objects/npc.py` (existing) |
| Game orchestrator | `server/app.py` (modify — integrate scheduler) |
| Tests | `tests/test_spawn.py` (NEW) |

### Existing Infrastructure to Reuse

- **`SpawnCheckpoint` model** already exists at `server/room/spawn_models.py` with columns: `id`, `npc_key`, `room_key`, `last_check_at`, `next_check_at`, `currently_spawned`. Already imported in `server/core/database.py:init_db()`.
- **`NpcEntity`** dataclass at `server/room/objects/npc.py` — has `is_alive`, `stats`, `spawn_config` fields
- **`create_npc_from_template()`** and `get_npc_template()` in `server/room/objects/npc.py`
- **`RoomInstance.add_npc()`** / `remove_npc()` / `get_npc()` in `server/room/room.py`
- **`ConnectionManager.broadcast_to_room()`** for notifying players of respawns
- **`async_session`** from `server/core/database.py` for DB operations
- **`RoomManager`** already spawns NPCs in `load_room()` from spawn_points

### NPC Template Spawn Types (from architecture.md §4.3)

| Spawn Type | Behavior | Config Fields |
|------------|----------|---------------|
| **Persistent** | Spawns at room load. Respawns on fixed timer after death. | `respawn_seconds` |
| **Rare/Epic** | System checks every N hours, rolls against spawn chance. | `check_interval_hours`, `spawn_chance`, `despawn_after_hours`, `max_active`, `room_key` |

Rare NPC template example:
```json
{
  "npc_key": "forest_dragon",
  "name": "Ancient Forest Dragon",
  "behavior_type": "hostile",
  "spawn_type": "rare",
  "spawn_config": {
    "check_interval_hours": 12,
    "spawn_chance": 0.15,
    "despawn_after_hours": 6,
    "max_active": 1,
    "room_key": "test_room",
    "x": 2,
    "y": 3
  },
  "stats": {"hp": 500, "max_hp": 500, "attack": 25, "defense": 15},
  "loot_table": "dragon_loot"
}
```

### Scheduler Pattern

Use `asyncio.create_task()` with a loop that sleeps between checks. For persistent respawns, use `asyncio.get_event_loop().call_later()` or `asyncio.ensure_future(asyncio.sleep(delay))`. Keep it simple — no external scheduling libraries.

```python
class Scheduler:
    def __init__(self):
        self._task: asyncio.Task | None = None
        self._respawn_tasks: dict[str, asyncio.Task] = {}
        self._game: Game | None = None

    async def start(self, game: Game) -> None:
        self._game = game
        await self._recover_checkpoints()
        self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        if self._task:
            self._task.cancel()
        for t in self._respawn_tasks.values():
            t.cancel()
```

### Handler Pattern (established)

All handlers: `async def handler(websocket, data, *, game: Game) -> None`
Registered in `Game._register_handlers()` via lambda closures.

### Anti-Patterns to Avoid

- **DO NOT** implement combat resolution — this story only provides the `kill_npc()` hook; Epic 4 calls it
- **DO NOT** implement global announcements — Story 3.6 handles that
- **DO NOT** use external scheduling libraries (APScheduler, etc.) — use asyncio primitives
- **DO NOT** block the event loop — all sleep/wait must be async
- **DO NOT** create a new model for SpawnCheckpoint — it already exists in `server/room/spawn_models.py`

### Previous Story Intelligence

From Story 3.4:
- NpcEntity dataclass with `id`, `npc_key`, `name`, `x`, `y`, `behavior_type`, `stats`, `loot_table`, `is_alive`, `spawn_config`
- `_NPC_TEMPLATES` global dict loaded by `load_npc_templates()`
- `RoomManager.load_room()` iterates spawn_points with `type == "npc"` and creates NPC entities
- `RoomInstance._npcs` dict stores NPCs, with `add_npc()`, `remove_npc()`, `get_npc()`
- NPC ID format: `"{room_key}_{npc_key}_{x}_{y}"`
- 153 existing tests must not regress

### Project Structure Notes

- New files: `server/core/scheduler.py`, `tests/test_spawn.py`
- Modified files: `server/app.py` (scheduler integration), `data/npcs/base_npcs.json` (add rare NPC)
- Existing file already handles DB schema: `server/room/spawn_models.py`

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#4.3 NPC Spawn System]
- [Source: _bmad-output/planning-artifacts/architecture.md#3.1 Directory Structure — scheduler]
- [Source: _bmad-output/planning-artifacts/architecture.md#9.6 SpawnCheckpoint]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.5]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Created `server/core/scheduler.py` with `Scheduler` class: persistent respawn via `schedule_respawn()` + `respawn_npc()`, rare spawn checks via `_run_rare_spawn_checks()`, checkpoint recovery via `_recover_checkpoints()`
- Added `forest_dragon` rare NPC template to `data/npcs/base_npcs.json`
- Integrated `Scheduler` into `Game` lifecycle (init, startup, shutdown)
- Added `Game.kill_npc()` hook that marks NPC dead and schedules respawn for persistent types
- Added NPC template loading to `Game.startup()`
- 12 new tests covering respawn, rare spawns, max_active, lifecycle, kill hook
- Fixed naive/aware datetime comparison issue (SQLite stores naive UTC)

### File List

- `server/core/scheduler.py` (NEW)
- `server/app.py` (MODIFIED — scheduler integration, kill_npc, NPC template loading)
- `data/npcs/base_npcs.json` (MODIFIED — added forest_dragon rare template)
- `tests/test_spawn.py` (NEW — 12 tests)
