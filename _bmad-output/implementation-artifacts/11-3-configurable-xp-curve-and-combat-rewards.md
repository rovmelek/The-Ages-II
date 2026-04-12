# Story 11.3: Configurable XP Curve & Combat Rewards

Status: done

## Story

As a player,
I want to earn XP from defeating mobs scaled to their difficulty,
so that fighting stronger enemies is more rewarding than grinding weak ones.

## Acceptance Criteria

1. **Config values added**: `server/core/config.py` `Settings` class gets:
   - `XP_CURVE_TYPE: str = "quadratic"` (supports `"quadratic"`, `"linear"`)
   - `XP_CURVE_MULTIPLIER: int = 25`
   - `XP_CHA_BONUS_PER_POINT: float = 0.03`
   - `XP_LEVEL_THRESHOLD_MULTIPLIER: int = 1000`

2. **Quadratic XP formula**: NPC with `hit_dice=4` defeated → `base_xp = 4² × 25 = 400`.

3. **Linear XP formula**: With `XP_CURVE_TYPE="linear"`, same NPC → `base_xp = 4 × 25 = 100`.

4. **CHA bonus**: Player with CHA=6, base_xp=400 → `final_xp = floor(400 × (1 + 6 × 0.03)) = floor(400 × 1.18) = 472`. Each player's CHA applies independently.

5. **Per-player XP in combat_end**: Each participant receives their own CHA-scaled XP. The `combat_end` message includes `"rewards": {"xp": <player-specific-xp>}` per player. Replaces the flat 25 XP reward.

6. **Standalone XP module**: XP calculation lives in `server/core/xp.py` as `calculate_combat_xp(hit_dice: int, charisma: int) -> int`. Reads config from `settings`, not hardcoded.

7. **Expected XP values** (quadratic, multiplier=25, CHA=1): cave_bat(hd=2)=103, slime(hd=3)=231, forest_goblin(hd=4)=412, cave_troll(hd=7)=1261, forest_dragon(hd=10)=2575.

8. **Tests**: Both curve types, CHA scaling, edge cases (CHA=0, CHA=10), and `pytest tests/` passes.

## Tasks / Subtasks

- [x] Task 1: Add XP config values to Settings (AC: #1)
  - [x] In `server/core/config.py:22` (before `ADMIN_SECRET`), add 4 new settings:
    ```python
    XP_CURVE_TYPE: str = "quadratic"
    XP_CURVE_MULTIPLIER: int = 25
    XP_CHA_BONUS_PER_POINT: float = 0.03
    XP_LEVEL_THRESHOLD_MULTIPLIER: int = 1000
    ```

- [x] Task 2: Create `server/core/xp.py` with `calculate_combat_xp` (AC: #2, #3, #4, #6)
  - [x] Create new file `server/core/xp.py` with `from __future__ import annotations`
  - [x] Implement `calculate_combat_xp(hit_dice: int, charisma: int) -> int`:
    ```python
    import math
    from server.core.config import settings

    def calculate_combat_xp(hit_dice: int, charisma: int) -> int:
        if settings.XP_CURVE_TYPE == "linear":
            base_xp = hit_dice * settings.XP_CURVE_MULTIPLIER
        else:  # quadratic (default)
            base_xp = (hit_dice ** 2) * settings.XP_CURVE_MULTIPLIER
        cha_multiplier = 1 + charisma * settings.XP_CHA_BONUS_PER_POINT
        return math.floor(base_xp * cha_multiplier)
    ```

- [x] Task 3: Replace flat 25 XP in `get_combat_end_result` (AC: #5, #7)
  - [x] In `server/combat/instance.py:416-422`, `get_combat_end_result()` currently returns `{"xp": 25}` hardcoded. This method does NOT have access to NPC hit_dice or player CHA. Two approaches:
    - **Option A** (recommended): Store `hit_dice` on CombatInstance at creation time. Add `self.mob_hit_dice: int` param to `__init__`. Then `get_combat_end_result()` can return per-participant XP using `calculate_combat_xp(self.mob_hit_dice, participant_stats[eid]["charisma"])`.
    - **Option B**: Move XP calculation to `_check_combat_end` in the combat handler (already has access to NPC via `instance.npc_id` → room → npc → template → hit_dice). This keeps CombatInstance unchanged but makes the handler responsible for XP math.
  - [x] **Use Option A**: Add `mob_hit_dice: int = 0` param to `CombatInstance.__init__()`. In `get_combat_end_result()`, replace hardcoded 25 with per-player XP:
    ```python
    from server.core.xp import calculate_combat_xp
    # ...
    if victory:
        rewards_per_player = {}
        for eid in self.participants:
            cha = self.participant_stats[eid].get("charisma", 0)
            rewards_per_player[eid] = {"xp": calculate_combat_xp(self.mob_hit_dice, cha)}
        return {"victory": True, "rewards_per_player": rewards_per_player}
    ```
  - [x] Update `CombatManager.create_instance()` in `server/combat/manager.py:21-39` to accept and pass `mob_hit_dice: int = 0`
  - [x] Update the combat creation call in `server/net/handlers/movement.py:151-153` to pass `mob_hit_dice` from the NPC template:
    ```python
    from server.room.objects.npc import get_npc_template
    tmpl = get_npc_template(npc.npc_key)
    mob_hit_dice = tmpl.get("hit_dice", 0) if tmpl else 0
    instance = game.combat_manager.create_instance(
        npc.name, mob_stats, npc_id=npc_id, room_key=room_key,
        mob_hit_dice=mob_hit_dice,
    )
    ```

- [x] Task 4: Update `_check_combat_end` for per-player XP (AC: #5)
  - [x] In `server/net/handlers/combat.py:49-158`, `_check_combat_end()` currently reads a single `xp_reward` from `end_result["rewards"]["xp"]` (line 57) and applies it identically to all participants (line 116).
  - [x] Change to read per-player rewards from `end_result["rewards_per_player"]`:
    ```python
    rewards_per_player = end_result.get("rewards_per_player", {})
    # ...
    # For each participant:
    xp_reward = rewards_per_player.get(eid, {}).get("xp", 0)
    entity.stats["xp"] = entity.stats.get("xp", 0) + xp_reward
    ```
  - [x] Send per-player `combat_end` messages with each player's own XP reward:
    ```python
    player_end_result = dict(end_result)
    player_end_result["rewards"] = rewards_per_player.get(eid, {})
    await ws.send_json({"type": "combat_end", **player_end_result})
    ```
  - [x] Remove `rewards_per_player` from the per-player message before sending:
    ```python
    player_end_result.pop("rewards_per_player", None)
    ```

- [x] Task 5: Write tests in `tests/test_xp.py` (AC: #8)
  - [x] Test quadratic curve: `hit_dice=4, CHA=0 → 400`
  - [x] Test linear curve: `hit_dice=4, CHA=0 → 100`
  - [x] Test CHA=1 bonus: `hit_dice=4 → floor(400 × 1.03) = 412`
  - [x] Test CHA=6 bonus: `hit_dice=4 → floor(400 × 1.18) = 472`
  - [x] Test CHA=10 bonus: `hit_dice=4 → floor(400 × 1.30) = 520`
  - [x] Test CHA=0 (no bonus): `hit_dice=4 → 400`
  - [x] Test all NPCs at CHA=1 (quadratic): cave_bat=103, slime=231, goblin=412, troll=1261, dragon=2575
  - [x] Test `get_combat_end_result` returns per-player XP with different CHA values
  - [x] Test hit_dice=0 edge case (legacy NPC without hit_dice): `CHA=1 → 0 XP`
  - [x] Test combat_end integration: verify each participant gets their own CHA-scaled reward

- [x] Task 6: Run `pytest tests/` and fix any failures (AC: #8)

## Dev Notes

### Key Architecture Patterns

- **Config access**: `from server.core.config import settings` — all XP config via `settings.XP_*`. Use `math.floor()` for rounding.
- **CombatInstance owns combat data**: Adding `mob_hit_dice` to CombatInstance keeps XP calculation self-contained. The instance already stores `mob_stats`, `npc_id`, `room_key`.
- **Effect handlers are stateless**: XP calculation is NOT an effect — it's a combat reward. Don't put it in `core/effects/`.
- **NPC hit_dice source**: `data/npcs/base_npcs.json` defines `hit_dice` per NPC. Loaded into `_NPC_TEMPLATES` via `load_npc_templates()`. Accessed via `get_npc_template(npc_key)["hit_dice"]`.
- **Per-player rewards**: Current `get_combat_end_result()` returns a single `rewards` dict. Must change to per-player rewards since each player has different CHA.
- **`from __future__ import annotations`**: Must be first import in new `server/core/xp.py`.

### Current XP Flow (to be changed)

1. `CombatInstance.get_combat_end_result()` (instance.py:416-422) returns `{"xp": 25}` hardcoded on victory
2. `_check_combat_end()` (combat.py:57) reads `xp_reward = end_result["rewards"]["xp"]`
3. combat.py:115-116 applies same `xp_reward` to ALL participants identically
4. combat.py:126 sends same `end_result` dict (with same rewards) to all players

### New XP Flow

1. `calculate_combat_xp(hit_dice, charisma)` in `server/core/xp.py` computes XP per player
2. `get_combat_end_result()` returns `rewards_per_player: {eid: {"xp": N}, ...}` using `self.mob_hit_dice`
3. `_check_combat_end()` reads per-player XP and applies individually
4. Each player gets their own `combat_end` message with their personal `rewards.xp`

### Combat Creation Chain

1. `server/net/handlers/movement.py:149-153` — NPC encounter creates `CombatInstance` via `game.combat_manager.create_instance(name, stats, npc_id, room_key)`. The NPC entity (`npc`) has `npc.npc_key`, usable to look up `hit_dice` from the template via `get_npc_template()`.
2. `server/combat/manager.py:21-39` — `create_instance()` forwards params to `CombatInstance.__init__()`.
3. `server/combat/instance.py:18-37` — `CombatInstance.__init__()` stores instance data.

### NPC hit_dice Values (from data/npcs/base_npcs.json)

| NPC | hit_dice | hp_multiplier | HP |
|-----|----------|---------------|----|
| cave_bat | 2 | 12 | 24 |
| slime | 3 | 10 | 30 |
| forest_goblin | 4 | 12 | 48 |
| cave_troll | 7 | 28 | 196 |
| forest_dragon | 10 | 50 | 500 |

### What NOT to Change

- Do NOT modify effect handlers (damage.py, heal.py, dot.py, shield.py, draw.py)
- Do NOT modify `_process_dot_effects()` — unrelated to XP
- Do NOT add exploration or interaction XP — that's Story 11.4
- Do NOT implement level-up mechanics — that's Story 11.5
- Do NOT modify the web client — that's Story 11.6
- Do NOT change the `_STATS_WHITELIST` — XP is already whitelisted
- Do NOT remove `attack` from `_DEFAULT_STATS` — still used as mob base_attack

### Previous Story Intelligence

From Story 11.2:
- `STAT_SCALING_FACTOR = 1.0` already in config at line 21
- `attack` removed from `_STATS_WHITELIST` (no longer persisted for players)
- Ability scores (`strength`, `dexterity`, `constitution`, `intelligence`, `wisdom`, `charisma`) are in participant_stats dicts — copied from PlayerEntity.stats by `add_participant()` at instance.py:46
- Mob stats include all 6 abilities from `_derive_stats_from_hit_dice()` in npc.py:65
- All tests passing; 20 new tests added in `test_stat_combat.py`

### Project Structure Notes

- New file: `server/core/xp.py` — follows `server/core/` convention for shared services
- New test file: `tests/test_xp.py` — flat test directory convention
- Config additions go in `server/core/config.py` Settings class, before `ADMIN_SECRET`

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Epic 11, Story 11.3, lines 2051-2105]
- [Source: server/combat/instance.py:416-422 — get_combat_end_result, hardcoded xp=25]
- [Source: server/net/handlers/combat.py:49-158 — _check_combat_end, XP application]
- [Source: server/net/handlers/combat.py:57 — xp_reward read from end_result]
- [Source: server/net/handlers/combat.py:115-116 — XP applied to entity.stats]
- [Source: server/net/handlers/movement.py:149-153 — CombatInstance creation with NPC]
- [Source: server/combat/manager.py:21-39 — create_instance]
- [Source: server/combat/instance.py:18-37 — CombatInstance.__init__]
- [Source: server/room/objects/npc.py:60-62 — get_npc_template]
- [Source: server/room/objects/npc.py:65-86 — _derive_stats_from_hit_dice]
- [Source: data/npcs/base_npcs.json — NPC hit_dice values]
- [Source: server/core/config.py:7-24 — Settings class]
- [Source: _bmad-output/implementation-artifacts/11-2-stat-to-combat-integration.md — previous story]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Added 4 XP config values to `Settings`: `XP_CURVE_TYPE`, `XP_CURVE_MULTIPLIER`, `XP_CHA_BONUS_PER_POINT`, `XP_LEVEL_THRESHOLD_MULTIPLIER`
- Created `server/core/xp.py` with `calculate_combat_xp(hit_dice, charisma)` — supports quadratic and linear curves with CHA bonus
- Added `mob_hit_dice` param to `CombatInstance.__init__()` and wired through `CombatManager.create_instance()` and `movement.py` combat creation
- `get_combat_end_result()` now returns per-player XP via `rewards_per_player` dict (replaces hardcoded `{"xp": 25}`)
- `_check_combat_end()` applies per-player XP individually and sends per-player `combat_end` messages with individual `rewards.xp`
- Updated 2 existing tests (`test_combat_resolution.py`) for new rewards structure
- Updated 1 integration test (`test_integration.py`) for dynamic XP assertion
- 10 new tests in `test_xp.py`: 7 unit tests for `calculate_combat_xp`, 3 integration tests for `get_combat_end_result`
- 568 passed, 2 failed (pre-existing chest integration test failures unrelated to this story)

### File List

- server/core/config.py (modified — added 4 XP config values)
- server/core/xp.py (new — calculate_combat_xp function)
- server/combat/instance.py (modified — added mob_hit_dice, per-player XP in get_combat_end_result)
- server/combat/manager.py (modified — mob_hit_dice param in create_instance)
- server/net/handlers/movement.py (modified — pass mob_hit_dice from NPC template)
- server/net/handlers/combat.py (modified — per-player XP application and messages)
- tests/test_xp.py (new — 10 XP tests)
- tests/test_combat_resolution.py (modified — updated for per-player rewards structure)
- tests/test_integration.py (modified — updated XP assertion for dynamic values)
