---
title: 'Increase Slime Density Across All Rooms'
slug: 'increase-slime-density'
created: '2026-04-10'
status: 'in-progress'
stepsCompleted: [1]
tech_stack: []
files_to_modify:
  - 'data/rooms/town_square.json'
  - 'data/rooms/dark_cave.json'
  - 'data/rooms/other_room.json'
code_patterns: []
test_patterns: []
---

# Tech-Spec: Increase Slime Density Across All Rooms

**Created:** 2026-04-10

## Overview

### Problem Statement

Slime encounters are too rare across the map. town_square (100x100) has only 2 slimes, dark_cave (100x100) has 12, test_room (5x5) has 1, and other_room (5x5) has 0. Players don't encounter enough slimes during exploration.

### Solution

Add more slime spawn_points to room JSON files in `data/rooms/`, targeting **6-8 for town_square** (capped to preserve safe hub feel), **~18-20 for dark_cave**, **1-2 for other_room**, keeping test_room at 1. Use a **mixed placement strategy** — place slimes in 2-3 small clusters of 2-3 slimes (within ~10 tiles of each other) plus a few scattered singles, rather than pure even distribution, to create a more organic and natural-feeling world.

### Scope

**In Scope:**
- Adding slime `spawn_points` entries to room JSON files
- Ensuring placement on walkable tiles without overlapping existing spawn points or blocking objects
- Validating all new coordinates against room `tile_data` for walkability
- Maintaining a safe zone around player spawn points (no slimes within 15 tiles of town_square player spawn at 50,50)

**Out of Scope:**
- Changing slime stats, loot tables, respawn timers, or NPC template
- Adding new NPC types
- Modifying room layouts or tile data

## Context for Development

### Codebase Patterns

- Room data is defined in JSON files under `data/rooms/`
- NPC spawns are defined in the `spawn_points` array with `{"type": "npc", "npc_key": "slime", "x": N, "y": N}`
- The slime NPC template exists in `data/npcs/base_npcs.json` (persistent spawn, 60s respawn)
- Room grid uses `grid[y][x]` (row-major); tile types: FLOOR=0, WALL=1, EXIT=2, MOB_SPAWN=3, WATER=4, STAIRS_UP=5, STAIRS_DOWN=6

### Files to Reference

| File | Purpose |
| ---- | ------- |
| `data/rooms/town_square.json` | Town square room — add 4-6 slime spawn points (total 6-8) |
| `data/rooms/dark_cave.json` | Dark cave room — add 6-8 slime spawn points |
| `data/rooms/other_room.json` | Other room — add 1-2 slime spawn points |
| `data/npcs/base_npcs.json` | Slime NPC template (reference only, no changes) |

### Technical Decisions

- Data-only change: no server code modifications needed
- Placement must avoid coordinates occupied by blocking objects or existing spawn points
- **Mixed placement strategy**: use 2-3 small clusters (2-3 slimes within ~10 tiles) plus scattered singles per large room, creating organic "nest" zones alongside solo encounters for natural-feeling density
- **Safe zone**: No slime spawns within 15 tiles of the player spawn point in town_square (50,50) to preserve the safe hub feel
- **Tile validation**: All new spawn coordinates must be verified against room `tile_data` — only walkable tiles (FLOOR=0, EXIT=2, MOB_SPAWN=3, STAIRS_UP=5, STAIRS_DOWN=6)
- **Total NPC budget per room** (post-change estimates):
  - town_square: ~14-16 NPCs (6 goblins + 6-8 slimes)
  - dark_cave: ~26-28 NPCs (8 bats + 18-20 slimes)
  - test_room: ~3 NPCs (1 goblin + 1 bat + 1 slime) — unchanged
  - other_room: ~3-4 NPCs (1 goblin + 1 bat + 1-2 slimes)

## Implementation Plan

### Tasks

_To be filled in Step 3_

### Acceptance Criteria

_To be filled in Step 3_

## Additional Context

### Dependencies

None — data-only change, no code dependencies.

### Testing Strategy

_To be filled in Step 3_

### Notes

_To be filled in Step 3_
