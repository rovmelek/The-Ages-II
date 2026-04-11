# Story 10.9: NPC Spawn Density

Status: done

## Story

As a player,
I want more mobs spawned in larger rooms,
so that combat encounters happen at a reasonable rate while exploring.

## Acceptance Criteria

1. **Given** `data/rooms/town_square.json` is a 100x100 room, **When** the story is complete, **Then** the room has at least 12 NPC spawn points (up from current 8), spawn points include a mix of slimes and goblins, and spawn points are spread across the map (not clustered in one area).

2. **Given** `data/rooms/dark_cave.json` is a 100x100 room, **When** the story is complete, **Then** the room has at least 10 NPC spawn points, and spawn points include slimes, bats, and the existing rare cave_troll.

3. **Given** the increased spawn density, **When** a player explores town_square, **Then** they encounter a mob within approximately 20-30 tiles of walking from spawn, and mobs are distributed to make exploration consistently engaging.

4. **Given** test_room and other_room are 5x5, **When** the story is complete, **Then** their spawn points are not changed (small rooms don't need more density).

5. **And** the server starts successfully with the updated room data, **And** `pytest tests/` passes with zero new failures.

## Tasks / Subtasks

- [x] Task 1: Add spawn points to `data/rooms/town_square.json` (AC: #1, #3)
  - [x] 1.1: Add at least 4 new NPC spawn points to the `spawn_points` array (currently 8 NPCs, need 12+)
  - [x] 1.2: New spawns should include both `slime` and `forest_goblin` types for variety (currently 6 goblins + 2 slimes — add more slimes to balance the mix)
  - [x] 1.3: Distribute new spawns to fill gaps in the map — current spawns cluster at corners (15,15), (85,15), (15,85), (85,85) and mid-edges; add spawns in the central quadrant and underserved areas
  - [x] 1.4: Ensure new spawn coordinates are on walkable tiles (not on wall tiles, object positions, or the player spawn at 50,50)

- [x] Task 2: Verify `data/rooms/dark_cave.json` already meets requirements (AC: #2)
  - [x] 2.1: Confirm dark_cave has at least 10 NPC spawn points (currently 20 — 12 slimes + 8 bats — already exceeds minimum)
  - [x] 2.2: Confirm spawn types include slimes and bats (both present)
  - [x] 2.3: Confirm the rare cave_troll spawns in dark_cave via `data/npcs/base_npcs.json` rare spawn config (cave_troll has `room_key: "dark_cave"`, position `(50,50)`)
  - [x] 2.4: No changes needed to dark_cave.json

- [x] Task 3: Verify no changes to small rooms (AC: #4)
  - [x] 3.1: Do NOT modify `data/rooms/test_room.json` (5x5, 3 NPCs)
  - [x] 3.2: Do NOT modify `data/rooms/other_room.json` (5x5, 2 NPCs)

- [x] Task 4: Test and validate (AC: #5)
  - [x] 4.1: Run `pytest tests/` — all tests pass with zero new failures
  - [x] 4.2: Verify server starts successfully with updated room data (load room JSON, check NPC count)

## Dev Notes

### Critical Implementation Details

**This is a data-only story.** The only file that needs modification is `data/rooms/town_square.json`. No Python code changes are required.

**dark_cave already exceeds requirements.** It has 20 NPC spawn points (12 slimes + 8 cave_bats), well above the "at least 10" minimum. The cave_troll rare spawn is configured in `data/npcs/base_npcs.json` (not in room spawn_points) and already targets dark_cave. No changes needed.

**Current town_square spawn points (8 NPCs):**
| NPC Key | Position | Map Region |
|---------|----------|------------|
| forest_goblin | (15, 15) | NW corner |
| forest_goblin | (85, 15) | NE corner |
| forest_goblin | (15, 85) | SW corner |
| forest_goblin | (85, 85) | SE corner |
| forest_goblin | (40, 20) | North-center |
| forest_goblin | (60, 80) | South-center |
| slime | (30, 70) | West-center |
| slime | (70, 30) | East-center |
Player spawn: (50, 50)

**Gap analysis:** The center of the map (around 40-60, 40-60) and diagonal corridors have no mobs. A player walking from spawn (50,50) must travel ~20+ tiles to encounter anything. Adding spawns in the 40-60 range (but NOT at 50,50 which is the player spawn and fountain) and in the 20-40/60-80 intermediate zones would improve density.

**Spawn point JSON format:**
```json
{"type": "npc", "npc_key": "slime", "x": 45, "y": 35}
```

**Avoid coordinate conflicts.** Do not place NPC spawns at these occupied positions:
- Player spawn: (50, 50)
- Objects: (10,10), (20,15), (30,8), (60,40), (70,55), (50,50), (25,30), (75,60), (45,45)

**Valid NPC keys** (from `data/npcs/base_npcs.json`): `forest_goblin`, `cave_bat`, `slime`. All three are persistent spawn type with auto-respawn. Use only `forest_goblin` and `slime` for town_square (bats are thematically cave creatures).

**Tile data format.** The `tile_data` array in room JSON files is a flat array of `width * height` tile objects. Each tile has a `type` field (e.g., `"floor"`, `"wall"`). Spawn point coordinates must reference tiles of type `"floor"` (walkable). The 100x100 rooms are predominantly floor tiles with wall borders.

### Files to Modify

- `data/rooms/town_square.json` — add 4+ NPC spawn point entries to `spawn_points` array

### Files NOT to Modify

- `data/rooms/dark_cave.json` — already has 20 NPCs, exceeds 10 minimum
- `data/rooms/test_room.json` — small room, no changes per AC #4
- `data/rooms/other_room.json` — small room, no changes per AC #4
- No Python server files — spawn loading logic in `server/room/manager.py` already handles any number of spawn points
- No test files — existing tests use `>= 1` assertions that accommodate more spawns

### Files NOT to Create

No new files. This is a data-only change.

### What NOT to Do

- Do NOT modify the room dimensions, tile_data, exits, or objects in any room file
- Do NOT add spawn points to test_room or other_room (5x5 rooms)
- Do NOT change any Python code — the spawn system already handles arbitrary spawn point counts
- Do NOT add new NPC template types — use existing `forest_goblin` and `slime` for town_square
- Do NOT place spawns on wall tiles, object tiles, or the player spawn tile at (50,50)
- Do NOT modify dark_cave.json — it already has 20 spawn points exceeding the 10 minimum
- Do NOT add `cave_bat` to town_square — bats are thematically cave creatures

### Existing Code Patterns to Follow

- **Spawn point format:** `{"type": "npc", "npc_key": "<template_key>", "x": N, "y": N}` — see existing entries in any room JSON
- **NPC ID generation:** `server/room/manager.py` generates IDs as `{room_key}_{npc_key}_{x}_{y}` — unique coordinates automatically produce unique IDs
- **Spawn loading:** `RoomManager.load_room()` iterates `spawn_points` and calls `create_npc_from_template()` for each `type == "npc"` entry. No code changes needed.

### Testing Patterns

- **Existing tests pass with more spawns:** `tests/test_sample_data.py` asserts `len(npc_spawns) > 0` for town_square and `len(npc_spawns) >= 1` for dark_cave — both accommodate any count
- **Startup wiring tests:** `tests/test_startup_wiring.py` loads actual room JSON files and verifies NPC creation — more spawn points will work fine
- **No new tests needed:** This story only adds data; existing integration tests validate the spawn system

### Previous Story Learnings

- **From 10.8:** 537 passed, 2 pre-existing failures (TestChestInteraction DB issues), 1 deselected. Zero new failures.
- **From 10.7:** Loot tables were moved to `server/items/loot.py` — not relevant here but context for mob reward system.
- **Git pattern:** One commit per story.

### Project Structure Notes

- Room data lives in `data/rooms/` as JSON files
- NPC templates live in `data/npcs/base_npcs.json`
- No server code or test changes for this data-only story
- All paths align with documented architecture

### References

- [Source: data/rooms/town_square.json#spawn_points] — current 8 NPC spawn points + 1 player spawn
- [Source: data/rooms/dark_cave.json#spawn_points] — current 20 NPC spawn points + 1 player spawn
- [Source: data/npcs/base_npcs.json] — NPC templates: forest_goblin, cave_bat, slime, forest_dragon (rare), cave_troll (rare)
- [Source: server/room/manager.py#load_room] — spawn loading logic (lines 20-42)
- [Source: tests/test_sample_data.py#test_has_npc_spawns] — NPC spawn assertions (lines 90-95)
- [Source: _bmad-output/planning-artifacts/epics.md#Story 10.9] — acceptance criteria (lines 1868-1898)

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- Pre-existing test failures: 2 TestChestInteraction DB issues (unchanged from Story 10.8 baseline)
- Test results: 538 passed, 2 failed (pre-existing), 6 warnings

### Completion Notes List

- Added 6 new NPC spawn points to `data/rooms/town_square.json`: 4 slimes at (45,35), (55,65), (50,25), (50,75) and 2 goblins at (25,50), (75,50)
- Total NPC spawns in town_square: 14 (up from 8) — 8 forest_goblin + 6 slime
- New spawns fill the central quadrant and mid-zone gaps, ensuring mobs within ~15-25 tiles of player spawn (50,50)
- All new coordinates verified on walkable floor tiles with no object/spawn conflicts
- dark_cave already has 20 NPC spawns (12 slime + 8 bat) + cave_troll rare spawn — no changes needed
- test_room (3 NPCs) and other_room (2 NPCs) unchanged per AC #4
- 538 passed, 2 pre-existing failures, 0 new failures

### Change Log

- 2026-04-10: Story 10.9 implemented — added 6 NPC spawn points to town_square.json (data-only change)

### File List

- data/rooms/town_square.json (modified — added 6 NPC spawn points to spawn_points array)
