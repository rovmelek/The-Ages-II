# Story 11.4: Exploration & Interaction XP Sources

Status: done

## Story

As a player,
I want to earn XP from discovering new rooms and interacting with objects for the first time,
so that exploration and curiosity are rewarded beyond just combat.

## Acceptance Criteria

1. **First-visit exploration XP**: Player transitions to a room they have never visited → receives `XP_EXPLORATION_REWARD` (default 50), CHA bonus applied, message `{"type": "xp_gained", "amount": <xp>, "source": "exploration", "detail": "Discovered <room_name>"}` sent.

2. **Repeat-visit no XP**: Player transitions to an already-visited room → no exploration XP, no `xp_gained` message for exploration.

3. **First-interaction XP**: Player interacts with a chest or lever for the first time → receives `XP_INTERACTION_REWARD` (default 25), CHA bonus applied, message `{"type": "xp_gained", "amount": <xp>, "source": "interaction", "detail": "Opened <object_type>"}` sent.

4. **Repeat-interaction no XP**: Player interacts with already-interacted object (e.g., chest returns "Already looted") → no interaction XP.

5. **visited_rooms persistence**: A `visited_rooms` JSON column (list of room_keys) added to the `Player` DB model. Saved on disconnect, restored on login. Code comment: "Consider PlayerRoomVisit table for production scale".

6. **Shared grant_xp function**: `server/core/xp.py` gets `async grant_xp(entity_id, player_entity, amount, source, detail, game, apply_cha_bonus=True)` that: optionally applies CHA bonus via `1 + charisma * settings.XP_CHA_BONUS_PER_POINT`, updates `player_entity.stats["xp"]`, persists stats to DB, sends `xp_gained` message via `game.connection_manager.get_websocket(entity_id)`.

7. **Combat XP refactored**: `_check_combat_end` in `server/net/handlers/combat.py` uses `grant_xp` with `apply_cha_bonus=False` (combat XP already has CHA applied by `calculate_combat_xp`).

8. **Config values**: `XP_EXPLORATION_REWARD: int = 50`, `XP_INTERACTION_REWARD: int = 25`, `XP_QUEST_REWARD: int = 100` (unused placeholder), `XP_PARTY_BONUS_PERCENT: int = 10` (unused placeholder) added to `Settings`.

9. **grant_xp accepts any source string** — no hardcoded enum.

10. **Tests**: First-visit XP, repeat-visit no XP, first-interact XP, repeat-interact no XP, grant_xp CHA bonus, `pytest tests/` passes.

## Tasks / Subtasks

- [x] Task 1: Add XP config values to Settings (AC: #8)
  - [x] In `server/core/config.py:26` (before `ADMIN_SECRET`), add 4 new settings:
    ```python
    XP_EXPLORATION_REWARD: int = 50
    XP_INTERACTION_REWARD: int = 25
    XP_QUEST_REWARD: int = 100
    XP_PARTY_BONUS_PERCENT: int = 10
    ```

- [x] Task 2: Add `visited_rooms` column to Player model (AC: #5)
  - [x] In `server/player/models.py:19` (after `position_y`), add:
    ```python
    visited_rooms: Mapped[list] = mapped_column(JSON, default=list)  # Consider PlayerRoomVisit table for production scale
    ```
  - [x] Add `from __future__ import annotations` as the first import (after docstring) — this file currently lacks it and the project convention requires it in all modified modules

- [x] Task 3: Add `update_visited_rooms` to player repo (AC: #5)
  - [x] In `server/player/repo.py`, add:
    ```python
    async def update_visited_rooms(
        session: AsyncSession, player_id: int, visited_rooms: list
    ) -> None:
        await session.execute(
            update(Player).where(Player.id == player_id)
            .values(visited_rooms=visited_rooms)
        )
        await session.commit()
    ```

- [x] Task 4: Create `grant_xp` in `server/core/xp.py` (AC: #6, #9)
  - [x] Add async function to existing `server/core/xp.py`:
    ```python
    async def grant_xp(
        entity_id: str,
        player_entity: Any,
        amount: int,
        source: str,
        detail: str,
        game: Any,
        apply_cha_bonus: bool = True,
    ) -> int:
        """Apply CHA bonus (optional), update stats, persist, send xp_gained message.
        Returns final XP amount."""
        if apply_cha_bonus:
            cha = player_entity.stats.get("charisma", 0)
            cha_multiplier = 1 + cha * settings.XP_CHA_BONUS_PER_POINT
            final_xp = math.floor(amount * cha_multiplier)
        else:
            final_xp = amount
        player_entity.stats["xp"] = player_entity.stats.get("xp", 0) + final_xp
        # Persist
        async with async_session() as session:
            await player_repo.update_stats(session, player_entity.player_db_id, player_entity.stats)
        # Send message
        ws = game.connection_manager.get_websocket(entity_id)
        if ws:
            await ws.send_json({
                "type": "xp_gained",
                "amount": final_xp,
                "source": source,
                "detail": detail,
            })
        return final_xp
    ```
  - [x] Import `async_session` from `server.core.database` and `player_repo` from `server.player`
  - [x] Use `TYPE_CHECKING` guard for Game import if needed; use `Any` type hints for `player_entity` and `game` to avoid circular imports

- [x] Task 5: Wire exploration XP in movement handler (AC: #1, #2)
  - [x] In `server/net/handlers/movement.py:_handle_exit_transition()`, after the room state is sent (line 243) and before building entity_data (line 246):
    1. Load `player_info["visited_rooms"]` (list, default `[]`)
    2. If `target_room_key` not in visited_rooms:
       - Add `target_room_key` to visited_rooms
       - Call `await grant_xp(entity_id, entity, settings.XP_EXPLORATION_REWARD, "exploration", f"Discovered {target_room.name}", game)`
       - Update `player_info["visited_rooms"]` in memory
       - Persist visited_rooms to DB via `player_repo.update_visited_rooms()`
  - [x] Import `grant_xp` from `server.core.xp` and `settings` from `server.core.config`

- [x] Task 6: Wire interaction XP in interact handler (AC: #3, #4)
  - [x] In `server/net/handlers/interact.py:handle_interact()`, after `result = await obj.interact(...)` (line 102):
    1. Check if interaction was first-time: `result.get("status")` is `"looted"` (chest) or `"toggled"` (lever) — NOT `"already_looted"` or `"error"`
    2. Check if this object was already interacted with by this player: use `PlayerObjectState` — but the interact already sets state. A simpler approach: check if result indicates first-time (`"looted"` for chest, but lever always returns `"toggled"`).
    3. **For chests**: Grant XP only when `result["status"] == "looted"` (first time). `"already_looted"` means repeat.
    4. **For levers**: Need to check if this is the first toggle. Use `get_player_object_state()` before interaction — if state is empty, it's first time. OR: track first-interact separately in player_object_state.
    5. Strategy: Before calling `obj.interact()`, check if a per-player interaction record exists via `get_player_object_state()`. If no record exists, this is first interaction → grant XP after successful interact.
    6. Call `await grant_xp(entity_id, entity, settings.XP_INTERACTION_REWARD, "interaction", f"Interacted with {obj_dict.get('type', 'object')}", game)`
  - [x] Import `grant_xp` from `server.core.xp`, `settings` from `server.core.config`, `get_player_object_state` from `server.room.objects.state`, `async_session` from `server.core.database`

- [x] Task 7: Restore visited_rooms on login (AC: #5)
  - [x] In `server/net/handlers/auth.py:handle_login()`, after loading inventory (line 291), load `visited_rooms`:
    ```python
    visited_rooms = player.visited_rooms or []
    ```
  - [x] Store in `player_info`: add `"visited_rooms": visited_rooms` to `game.player_entities[entity_id]` dict (line 294-299)
  - [x] In `_cleanup_player()`, save visited_rooms on disconnect:
    ```python
    visited_rooms = player_info.get("visited_rooms", [])
    if visited_rooms:
        await player_repo.update_visited_rooms(session, entity.player_db_id, visited_rooms)
    ```

- [x] Task 8: Refactor combat XP to use grant_xp (AC: #7)
  - [x] In `server/net/handlers/combat.py:_check_combat_end()`, replace inline XP logic (lines 114-118):
    ```python
    # Old:
    if end_result.get("victory"):
        xp_reward = rewards_per_player.get(eid, {}).get("xp", 0)
        if xp_reward:
            entity.stats["xp"] = entity.stats.get("xp", 0) + xp_reward

    # New:
    if end_result.get("victory"):
        xp_reward = rewards_per_player.get(eid, {}).get("xp", 0)
        if xp_reward:
            await grant_xp(eid, entity, xp_reward, "combat", npc_name, game, apply_cha_bonus=False)
    ```
  - [x] **IMPORTANT**: Combat XP already has CHA bonus applied by `calculate_combat_xp()`. Pass `apply_cha_bonus=False` to avoid double-applying CHA. The `npc_name` for the detail can be sourced from `end_result.get("mob_name", "enemy")`.
  - [x] Import `grant_xp` from `server.core.xp` at the top of combat.py
  - [x] Note: `grant_xp` will also persist stats to DB, so the separate `update_stats` call (line 121-124) for XP is now redundant for the XP value — but the stats persist still covers hp/max_hp sync. Keep the persist call since it writes all stats including the updated XP.

- [x] Task 9: Write tests (AC: #10)
  - [x] Add tests to `tests/test_xp.py` (existing file):
    - `test_grant_xp_applies_cha_bonus`: grant_xp with CHA=6, amount=50 → floor(50 * 1.18) = 59
    - `test_grant_xp_updates_stats`: verify player_entity.stats["xp"] updated
    - `test_grant_xp_sends_message`: verify xp_gained message sent via WebSocket mock
  - [x] Create `tests/test_exploration_xp.py`:
    - `test_first_visit_grants_xp`: Mock room transition, verify xp_gained sent with source="exploration"
    - `test_repeat_visit_no_xp`: Visit same room twice, verify xp_gained NOT sent on second visit
    - `test_visited_rooms_persisted`: Verify visited_rooms saved to DB on cleanup
    - `test_visited_rooms_restored_on_login`: Verify visited_rooms loaded from DB
  - [x] Create `tests/test_interaction_xp.py`:
    - `test_first_chest_interact_grants_xp`: First chest open → xp_gained with source="interaction"
    - `test_repeat_chest_interact_no_xp`: Already-looted chest → no xp_gained
    - `test_first_lever_interact_grants_xp`: First lever toggle → xp_gained
    - `test_repeat_lever_interact_no_xp`: Second lever toggle → no xp_gained

- [x] Task 10: Run `pytest tests/` and fix any failures (AC: #10)

## Dev Notes

### Key Architecture Patterns

- **Config access**: `from server.core.config import settings` — all XP config via `settings.XP_*`
- **PlayerEntity is a dataclass** (`server/player/entity.py:5-15`): `id`, `name`, `x`, `y`, `player_db_id`, `stats` dict, `in_combat` bool. `stats["xp"]` holds current XP.
- **Player DB model** (`server/player/models.py:8-19`): `stats` is JSON column. `visited_rooms` will be a new JSON column (list of room_key strings).
- **Stats whitelist** (`server/player/repo.py:75-79`): `{"hp", "max_hp", "xp", "level", "strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"}`. XP is already whitelisted — no change needed.
- **Repos are module-level async functions**, NOT classes. All take `session: AsyncSession` first. Repos call `session.commit()` internally.
- **`from __future__ import annotations`**: Must be first import in any modified/new module.
- **Circular import prevention**: Use `TYPE_CHECKING` guard for `Game` imports. In `xp.py`, use `Any` for game and entity types to avoid importing `Game` or `PlayerEntity` at runtime.

### Existing Interaction State Tracking

- **Chests** (`server/room/objects/chest.py:28-32`): `get_player_object_state()` checks `{"opened": True}`. First open → `"status": "looted"`. Repeat → `"status": "already_looted"`. This makes first-time detection easy for chests.
- **Levers** (`server/room/objects/lever.py:18-53`): Uses room-scoped state (`get_room_object_state`), NOT player-scoped. Every toggle returns `"status": "toggled"`. For first-interaction tracking, we need to check `get_player_object_state()` for the lever BEFORE the interact call. If no state exists → first time → grant XP + set player state `{"interacted": True}`.

### Exploration XP Integration Point

- Room transitions happen in `_handle_exit_transition()` (`server/net/handlers/movement.py:175-257`).
- After placing entity in new room and sending room_state (line 243), check visited_rooms.
- `player_info` dict (`game.player_entities[entity_id]`) currently has keys: `"entity"`, `"room_key"`, `"db_id"`, `"inventory"`. Add `"visited_rooms"` key (list of room_key strings).
- The room name for the `xp_gained` detail message is available from `target_room.name` (the Room object has a `name` attribute).

### Interaction XP Integration Point

- Interactions happen in `handle_interact()` (`server/net/handlers/interact.py:17-107`).
- After `result = await obj.interact(player_db_id, game)` (line 102), check if first-time.
- For first-time detection strategy:
  - **Chests**: Check `result["status"] == "looted"` (not `"already_looted"`)
  - **Levers**: Check `get_player_object_state()` before interact; if empty → first time. After granting XP, set `{"interacted": True}` via `set_player_object_state()`.
  - **General approach**: Before `obj.interact()`, call `get_player_object_state(session, player_db_id, room_key, target_id)`. If empty dict → first interaction. This works for ALL object types uniformly.

### grant_xp Design Decisions

- `grant_xp` has `apply_cha_bonus: bool = True` param. Exploration/interaction pass `True` (default). Combat passes `False` since `calculate_combat_xp()` already applies CHA. (Note: epics.md specifies `grant_xp(player_entity, amount, source, detail)` — we expand to 7 params adding `entity_id` for WebSocket lookup, `game` for connection access, and `apply_cha_bonus` to avoid double-CHA on combat.)
- All XP sources use `grant_xp` — provides single point for stat update, DB persist, and `xp_gained` message.
- `grant_xp` is `async` because it persists to DB and sends WebSocket messages.
- Returns `int` (final XP after CHA) so callers can use it if needed.

### Player State Lifecycle for visited_rooms

1. **Login** (`auth.py:handle_login`): Load `player.visited_rooms or []` from DB, store in `player_info["visited_rooms"]`
2. **Room transition** (`movement.py:_handle_exit_transition`): Append new room_key, persist to DB
3. **Disconnect/Logout** (`auth.py:_cleanup_player`): Save visited_rooms to DB (belt-and-suspenders — already saved on each transition, but ensures consistency)
4. **Register** (`auth.py:handle_register`): No need to initialize — defaults to `[]` in model

### What NOT to Change

- Do NOT modify effect handlers (damage.py, heal.py, etc.)
- Do NOT implement level-up mechanics — that's Story 11.5
- Do NOT modify the web client — that's Story 11.6
- Do NOT change the `_STATS_WHITELIST` — XP is already whitelisted
- Do NOT add quest XP logic — just placeholder config values
- Do NOT change `calculate_combat_xp` — it's already correct from Story 11.3
- Do NOT double-apply CHA bonus on combat XP

### Previous Story Intelligence

From Story 11.3:
- `server/core/xp.py` exists with `calculate_combat_xp(hit_dice, charisma)`. Add `grant_xp` to this file.
- `settings.XP_CHA_BONUS_PER_POINT = 0.03` already in config. Reuse for CHA bonus in `grant_xp`.
- Combat XP flow: `calculate_combat_xp` → `get_combat_end_result` returns `rewards_per_player` → `_check_combat_end` applies XP per player. This flow is separate from `grant_xp`.
- Tests passing after Story 11.3 (10 new tests in `test_xp.py`).

### Project Structure Notes

- Modified files: `server/core/config.py`, `server/core/xp.py`, `server/player/models.py`, `server/player/repo.py`, `server/net/handlers/movement.py`, `server/net/handlers/interact.py`, `server/net/handlers/auth.py`
- New test files: `tests/test_exploration_xp.py`, `tests/test_interaction_xp.py`
- Modified test file: `tests/test_xp.py` (add grant_xp tests)
- Flat test directory convention — no subdirectories

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Epic 11, Story 11.4, lines 2107-2155]
- [Source: server/core/xp.py:1-24 — existing calculate_combat_xp]
- [Source: server/core/config.py:7-28 — Settings class]
- [Source: server/player/models.py:8-19 — Player DB model]
- [Source: server/player/repo.py:75-79 — _STATS_WHITELIST]
- [Source: server/player/repo.py:82-94 — update_stats]
- [Source: server/player/entity.py:5-15 — PlayerEntity dataclass]
- [Source: server/net/handlers/movement.py:175-257 — _handle_exit_transition]
- [Source: server/net/handlers/interact.py:17-107 — handle_interact]
- [Source: server/net/handlers/auth.py:191-336 — handle_login]
- [Source: server/net/handlers/auth.py:25-103 — _cleanup_player]
- [Source: server/net/handlers/combat.py:49-164 — _check_combat_end]
- [Source: server/room/objects/chest.py:25-63 — ChestObject.interact]
- [Source: server/room/objects/lever.py:18-53 — LeverObject.interact]
- [Source: server/room/objects/state.py:14-54 — get/set_player_object_state]
- [Source: _bmad-output/implementation-artifacts/11-3-configurable-xp-curve-and-combat-rewards.md — previous story]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Added 4 XP config values to `Settings`: `XP_EXPLORATION_REWARD=50`, `XP_INTERACTION_REWARD=25`, `XP_QUEST_REWARD=100` (placeholder), `XP_PARTY_BONUS_PERCENT=10` (placeholder)
- Added `visited_rooms` JSON column to `Player` model with `from __future__ import annotations`
- Added `update_visited_rooms()` to `player/repo.py`
- Created `grant_xp()` in `server/core/xp.py` with `apply_cha_bonus` param — applies CHA bonus, updates stats, persists to DB, sends `xp_gained` WebSocket message
- Wired exploration XP in `_handle_exit_transition()` — first-visit detection via `player_info["visited_rooms"]` list
- Wired interaction XP in `handle_interact()` — first-time detection via `get_player_object_state()` before interact; levers get per-player state `{"interacted": True}` set for tracking
- Restored visited_rooms on login and saved on disconnect in `_cleanup_player()`
- Refactored combat XP in `_check_combat_end()` to use `grant_xp(apply_cha_bonus=False)` — sends `xp_gained` message for combat rewards
- Updated integration tests: combat test now expects `xp_gained` before `combat_end`; chest tests use `_drain_until` helper for message ordering resilience
- Updated room transition tests to patch `grant_xp` to avoid real DB calls
- 12 new tests: 4 grant_xp tests in `test_xp.py`, 4 exploration XP tests in `test_exploration_xp.py`, 4 interaction XP tests in `test_interaction_xp.py`
- 582 total tests passing, 0 failures
- Code review fixes: added `from __future__ import annotations` to repo.py, added spawn room to visited_rooms on login, guarded WebSocket send in grant_xp with try/except

### File List

- server/core/config.py (modified — added 4 XP config values)
- server/core/xp.py (modified — added grant_xp function)
- server/player/models.py (modified — added visited_rooms column, from __future__ import)
- server/player/repo.py (modified — added update_visited_rooms function)
- server/net/handlers/movement.py (modified — exploration XP on room transition)
- server/net/handlers/interact.py (modified — interaction XP on first interact)
- server/net/handlers/auth.py (modified — visited_rooms restore/save)
- server/net/handlers/combat.py (modified — combat XP via grant_xp)
- tests/test_xp.py (modified — added 4 grant_xp tests)
- tests/test_exploration_xp.py (new — 4 exploration XP tests)
- tests/test_interaction_xp.py (new — 4 interaction XP tests)
- tests/test_integration.py (modified — fixed combat and chest test message ordering)
- tests/test_room_transition.py (modified — patched grant_xp for DB-free tests)
