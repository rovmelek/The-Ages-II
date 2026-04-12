# Story 11.5: XP Level Thresholds & Level-Up Mechanic

Status: done

## Story

As a player,
I want to level up when I accumulate enough XP and choose which stats to improve,
so that I have agency over my character's growth and build.

## Acceptance Criteria

1. **Level threshold formula**: `next_level_xp = level × XP_LEVEL_THRESHOLD_MULTIPLIER` (cumulative, not reset). Level 1→2 at 1000 XP, level 2→3 at 2000 XP, etc. `XP_LEVEL_THRESHOLD_MULTIPLIER` already exists in `server/core/config.py:25` as `1000`.

2. **Threshold detection in grant_xp**: After updating `player_entity.stats["xp"]` in `grant_xp()` (`server/core/xp.py:49`), check if XP >= `level × XP_LEVEL_THRESHOLD_MULTIPLIER`. If so, send `{"type": "level_up_available", "new_level": <current_level+1>, "choose_stats": 3, "current_stats": {...}, "stat_cap": 10}` and set `player_info["pending_level_ups"]` count. Do NOT increment level yet — player must choose stats first.

3. **Non-blocking level-up**: A pending level-up does NOT block gameplay. Player can move, fight, chat, etc. while the choice is pending.

4. **Queued level-ups**: If XP crosses multiple thresholds (e.g., level 1 with 3000 XP), only one `level_up_available` is sent. After the first level-up is completed, if XP still exceeds the next threshold, another `level_up_available` is sent immediately.

5. **level_up action handler**: New WebSocket action `level_up` accepting `{"action": "level_up", "stats": ["strength", "dexterity", "constitution"]}`. Validates:
   - Player has a pending level-up (else error: "No level-up available")
   - Stats list contains only valid stat names from `_VALID_LEVEL_UP_STATS` = `{"strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"}`
   - Duplicates are deduplicated — only unique stats boosted (max 3)
   - Each chosen stat is < 10 (cap). Stats already at 10 are skipped with a warning in the response.

6. **Level-up application**: On valid `level_up` action:
   - Increment each chosen stat by 1 (capped at 10)
   - Increment `level` by 1
   - Recalculate `max_hp = 100 + (new_constitution × settings.CON_HP_PER_POINT)` where `CON_HP_PER_POINT` is 5 (`server/core/config.py:18`)
   - Set `hp = new max_hp` (full heal on level-up)
   - Persist all stats to DB via `player_repo.update_stats()`
   - Send `{"type": "level_up_complete", "level": <new_level>, "stat_changes": {"strength": <new_val>, ...}, "new_max_hp": <val>}`
   - If another level-up is queued (XP still exceeds next threshold), immediately send a new `level_up_available`

7. **Pending level-up tracking**: Store `pending_level_ups: int` in `game.player_entities[entity_id]` dict (in-memory only, not persisted). This tracks how many level-ups are available. Decremented on each `level_up` action, incremented when threshold crossed in `grant_xp`.

8. **Re-check on login**: In `handle_login()` (`server/net/handlers/auth.py:196`), after setting up player stats, check if XP >= `level × XP_LEVEL_THRESHOLD_MULTIPLIER`. If so, calculate pending level-ups count and send `level_up_available` after `room_state`. Store count in `player_info["pending_level_ups"]`.

9. **Handler registration**: Register `level_up` action in `Game._register_handlers()` (`server/app.py:116`) alongside existing handlers.

10. **stats_result includes xp_next**: Update `handle_stats()` (`server/net/handlers/query.py:95`) to include `"xp_next": level × settings.XP_LEVEL_THRESHOLD_MULTIPLIER` in the `stats_result` response.

11. **Tests**: Threshold math, stat choices (valid/invalid/duplicate), cap enforcement (stat at 10 skipped), multi-level queuing, re-check on login, non-blocking behavior, persistence after level-up. `pytest tests/` passes.

## Tasks / Subtasks

- [x] Task 1: Create `get_pending_level_ups` and `send_level_up_available` in `server/core/xp.py` (AC: #2, #4)
  - [x] Add function to detect if player has pending level-ups:
    ```python
    def get_pending_level_ups(stats: dict) -> int:
        """Return how many level-ups are available based on current XP and level."""
        level = stats.get("level", 1)
        xp = stats.get("xp", 0)
        pending = 0
        check_level = level
        while xp >= check_level * settings.XP_LEVEL_THRESHOLD_MULTIPLIER:
            pending += 1
            check_level += 1
        return pending
    ```
  - [x] Add helper to send `level_up_available` message:
    ```python
    async def send_level_up_available(entity_id: str, player_entity: Any, game: Any) -> None:
        """Send level_up_available to the player if they have pending level-ups."""
        stats = player_entity.stats
        new_level = stats.get("level", 1) + 1
        ws = game.connection_manager.get_websocket(entity_id)
        if ws:
            try:
                await ws.send_json({
                    "type": "level_up_available",
                    "new_level": new_level,
                    "choose_stats": 3,
                    "current_stats": {
                        "strength": stats.get("strength", 1),
                        "dexterity": stats.get("dexterity", 1),
                        "constitution": stats.get("constitution", 1),
                        "intelligence": stats.get("intelligence", 1),
                        "wisdom": stats.get("wisdom", 1),
                        "charisma": stats.get("charisma", 1),
                    },
                    "stat_cap": 10,
                })
            except Exception:
                pass
    ```

- [x] Task 2: Modify `grant_xp` to detect threshold crossing (AC: #2, #4, #7)
  - [x] After updating XP in `grant_xp()` (`server/core/xp.py:49`), call `get_pending_level_ups()` and compare to existing `player_info["pending_level_ups"]`.
  - [x] If new pending > 0 and no existing pending (first threshold cross), send `level_up_available` and update `player_info["pending_level_ups"]`.
  - [x] `grant_xp` already has `entity_id` and `game` — look up `player_info` via `game.player_entities.get(entity_id)` internally. No signature change needed.
  - [x] Key logic (after XP update, before return):
    ```python
    # Level-up threshold detection
    player_info = game.player_entities.get(entity_id)
    if player_info is not None:
        new_pending = get_pending_level_ups(player_entity.stats)
        old_pending = player_info.get("pending_level_ups", 0)
        if new_pending > old_pending:
            player_info["pending_level_ups"] = new_pending
            if old_pending == 0:
                await send_level_up_available(entity_id, player_entity, game)
    ```

- [x] Task 3: Create `handle_level_up` handler (AC: #5, #6, #7)
  - [x] Create in `server/net/handlers/levelup.py` (new file):
    ```python
    """Level-up handler for WebSocket clients."""
    from __future__ import annotations
    from typing import TYPE_CHECKING
    from fastapi import WebSocket
    from server.core.config import settings
    from server.core.database import async_session
    from server.core.xp import get_pending_level_ups, send_level_up_available
    from server.player import repo as player_repo
    if TYPE_CHECKING:
        from server.app import Game

    _VALID_LEVEL_UP_STATS = {"strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"}
    _STAT_CAP = 10

    async def handle_level_up(websocket: WebSocket, data: dict, *, game: Game) -> None:
        entity_id = game.connection_manager.get_entity_id(websocket)
        if entity_id is None:
            await websocket.send_json({"type": "error", "detail": "Not logged in"})
            return
        player_info = game.player_entities.get(entity_id)
        if player_info is None:
            await websocket.send_json({"type": "error", "detail": "Not logged in"})
            return
        pending = player_info.get("pending_level_ups", 0)
        if pending <= 0:
            await websocket.send_json({"type": "error", "detail": "No level-up available"})
            return
        chosen_stats = data.get("stats", [])
        if not isinstance(chosen_stats, list):
            await websocket.send_json({"type": "error", "detail": "stats must be a list"})
            return
        # Validate and deduplicate
        unique_stats = list(dict.fromkeys(chosen_stats))[:3]
        for s in unique_stats:
            if s not in _VALID_LEVEL_UP_STATS:
                await websocket.send_json({"type": "error", "detail": f"Invalid stat: {s}"})
                return
        entity = player_info["entity"]
        stats = entity.stats
        stat_changes = {}
        skipped = []
        for s in unique_stats:
            if stats.get(s, 1) >= _STAT_CAP:
                skipped.append(s)
            else:
                stats[s] = stats.get(s, 1) + 1
                stat_changes[s] = stats[s]
        stats["level"] = stats.get("level", 1) + 1
        stats["max_hp"] = 100 + stats.get("constitution", 1) * settings.CON_HP_PER_POINT
        stats["hp"] = stats["max_hp"]
        # Persist
        async with async_session() as session:
            await player_repo.update_stats(session, entity.player_db_id, stats)
        # Decrement pending
        player_info["pending_level_ups"] = pending - 1
        response = {
            "type": "level_up_complete",
            "level": stats["level"],
            "stat_changes": stat_changes,
            "new_max_hp": stats["max_hp"],
        }
        if skipped:
            response["skipped_at_cap"] = skipped
        await websocket.send_json(response)
        # Check for queued level-ups
        remaining = get_pending_level_ups(stats)
        player_info["pending_level_ups"] = remaining
        if remaining > 0:
            await send_level_up_available(entity_id, entity, game)
    ```

- [x] Task 4: Register `level_up` handler in `Game._register_handlers()` (AC: #9)
  - [x] In `server/app.py:116`, add import and registration:
    ```python
    from server.net.handlers.levelup import handle_level_up
    self.router.register("level_up", lambda ws, d: handle_level_up(ws, d, game=self))
    ```

- [x] Task 5: Add level-up re-check on login (AC: #8)
  - [x] In `server/net/handlers/auth.py:handle_login()`, after `entity_entered` broadcast (line 347) — must be AFTER room_state (line 333) so client has context:
    ```python
    pending = get_pending_level_ups(stats)
    if pending > 0:
        player_info_ref = game.player_entities[entity_id]
        player_info_ref["pending_level_ups"] = pending
        await send_level_up_available(entity_id, entity, game)
    ```
  - [x] Import `get_pending_level_ups, send_level_up_available` from `server.core.xp`
  - [x] Initialize `"pending_level_ups": 0` in the `game.player_entities[entity_id]` dict (line 304-310)

- [x] Task 6: Update `handle_stats` to include `xp_next` (AC: #10)
  - [x] In `server/net/handlers/query.py:handle_stats()` (line 110-125), add `xp_next` field:
    ```python
    from server.core.config import settings
    # In the stats dict:
    "xp_next": stats.get("level", 1) * settings.XP_LEVEL_THRESHOLD_MULTIPLIER,
    ```

- [x] Task 7: Write tests (AC: #11)
  - [x] Create `tests/test_level_up.py`:
    - `test_get_pending_level_ups_none`: level=1, xp=500 → 0 pending
    - `test_get_pending_level_ups_one`: level=1, xp=1000 → 1 pending
    - `test_get_pending_level_ups_multiple`: level=1, xp=3500 → 3 pending (thresholds: 1000, 2000, 3000)
    - `test_handle_level_up_valid`: choose 3 stats → level incremented, stats boosted, max_hp recalculated, hp full, `level_up_complete` sent
    - `test_handle_level_up_no_pending`: send `level_up` with 0 pending → error "No level-up available"
    - `test_handle_level_up_invalid_stat`: choose `"mana"` → error "Invalid stat: mana"
    - `test_handle_level_up_duplicate_stats`: `["strength", "strength", "dexterity"]` → only STR+1 and DEX+1 (deduplicated)
    - `test_handle_level_up_stat_at_cap`: stat already at 10 → skipped, included in `skipped_at_cap`
    - `test_handle_level_up_queued`: xp=3500, level=1 → after first level-up, sends new `level_up_available` for next level
    - `test_grant_xp_triggers_level_up`: grant XP that crosses threshold → `level_up_available` sent
    - `test_login_recheck_pending_level_up`: player with xp >= threshold logs in → `level_up_available` sent after room_state
    - `test_stats_result_includes_xp_next`: stats response includes `xp_next` field
    - `test_level_up_persists_stats`: after level-up, stats persisted to DB

- [x] Task 8: Run `pytest tests/` and fix any failures (AC: #11)

## Dev Notes

### Key Architecture Patterns

- **Config access**: `from server.core.config import settings` — `settings.XP_LEVEL_THRESHOLD_MULTIPLIER` is already `1000` (`server/core/config.py:25`), `settings.CON_HP_PER_POINT` is `5` (`server/core/config.py:18`).
- **Handler pattern**: `async def handle_X(ws: WebSocket, data: dict, *, game: Game)` — `game` passed via lambda closure at registration. See existing pattern in `server/app.py:136-185`.
- **New handler file**: Create `server/net/handlers/levelup.py`. Flat handler directory — one file per domain concern. See existing: `auth.py`, `combat.py`, `interact.py`, `query.py`, `movement.py`.
- **Player info dict**: `game.player_entities[entity_id]` has keys `"entity"`, `"room_key"`, `"db_id"`, `"inventory"`, `"visited_rooms"`. Add `"pending_level_ups": int` (default 0). This is in-memory only — not persisted. On login, recalculated from XP vs threshold.
- **Stats whitelist** (`server/player/repo.py:88-92`): `{"hp", "max_hp", "xp", "level", "strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"}`. Already includes `level` — no change needed.
- **`from __future__ import annotations`**: Required as first import in all new/modified modules.
- **Circular import prevention**: Use `TYPE_CHECKING` guard for `Game` imports. Use `Any` for type hints where needed.
- **grant_xp** (`server/core/xp.py:30-65`): Currently takes `entity_id, player_entity, amount, source, detail, game, apply_cha_bonus`. No signature change needed — look up `player_info` via `game.player_entities.get(entity_id)` internally.

### Integration Points

- **grant_xp modification** (`server/core/xp.py:30-65`): After line 49 (`player_entity.stats["xp"] = ...`), add level-up threshold detection. `grant_xp` is called from:
  - `server/net/handlers/combat.py:120` — combat XP (apply_cha_bonus=False)
  - `server/net/handlers/movement.py` — exploration XP
  - `server/net/handlers/interact.py` — interaction XP
  All callers will get automatic level-up detection without code changes.

- **handle_login** (`server/net/handlers/auth.py:196-347`): After player_entities is populated (line 310) and room_state is sent (line 333), check for pending level-ups. The `level_up_available` message should be sent AFTER `room_state` so the client has context.

- **handle_stats** (`server/net/handlers/query.py:95-125`): Add `xp_next` field. Currently returns stats dict without `xp_next`. `settings` import already exists at module level? No — need to add `from server.core.config import settings`.

### max_hp Recalculation

- Formula: `max_hp = 100 + (constitution × settings.CON_HP_PER_POINT)` — `CON_HP_PER_POINT=5` (`server/core/config.py:18`).
- On level-up: recalculate max_hp, set hp = new max_hp (full heal).
- Current defaults: CON=1 → max_hp=105. After CON→2: max_hp=110.

### What NOT to Change

- Do NOT modify the web client — that's Story 11.6
- Do NOT modify combat instance or effect handlers
- Do NOT modify the `_STATS_WHITELIST` — `level` is already there
- Do NOT add new config values — `XP_LEVEL_THRESHOLD_MULTIPLIER` already exists
- Do NOT modify `calculate_combat_xp` — it's unrelated to level-up
- Do NOT persist `pending_level_ups` to DB — it's recalculated on login from XP vs threshold

### Previous Story Intelligence

From Story 11.4:
- `grant_xp` in `server/core/xp.py:30-65` handles XP granting, DB persistence, and `xp_gained` message sending. This is the integration point for level-up detection.
- `game.player_entities[entity_id]` dict currently has: `"entity"`, `"room_key"`, `"db_id"`, `"inventory"`, `"visited_rooms"`.
- All XP sources (combat, exploration, interaction) use `grant_xp` — adding threshold detection here gives universal coverage.
- 582 tests passing after Story 11.4.

### Project Structure Notes

- New file: `server/net/handlers/levelup.py`
- Modified files: `server/core/xp.py`, `server/app.py`, `server/net/handlers/auth.py`, `server/net/handlers/query.py`
- New test file: `tests/test_level_up.py`
- Flat test directory convention — no subdirectories

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Epic 11, Story 11.5, lines 2157-2218]
- [Source: server/core/xp.py:1-65 — grant_xp and calculate_combat_xp]
- [Source: server/core/config.py:7-32 — Settings class with XP_LEVEL_THRESHOLD_MULTIPLIER]
- [Source: server/player/repo.py:88-107 — _STATS_WHITELIST and update_stats]
- [Source: server/player/entity.py:5-16 — PlayerEntity dataclass]
- [Source: server/net/handlers/auth.py:196-347 — handle_login]
- [Source: server/net/handlers/auth.py:304-310 — player_entities dict setup]
- [Source: server/net/handlers/query.py:95-125 — handle_stats]
- [Source: server/app.py:116-185 — _register_handlers]
- [Source: server/net/handlers/combat.py:120 — grant_xp call in _check_combat_end]
- [Source: _bmad-output/implementation-artifacts/11-4-exploration-and-interaction-xp-sources.md — previous story]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Added `get_pending_level_ups()` and `send_level_up_available()` to `server/core/xp.py`
- Modified `grant_xp()` to detect level-up threshold crossing and send `level_up_available` message automatically
- Created `server/net/handlers/levelup.py` with `handle_level_up()` — validates stat choices (dedup, cap, valid names), applies boosts, recalculates max_hp from CON, full heals, persists to DB, sends `level_up_complete`, and handles queued level-ups
- Registered `level_up` action in `Game._register_handlers()`
- Added level-up re-check on login in `handle_login()` — sends `level_up_available` after room_state if player has pending level-ups
- Added `pending_level_ups: 0` to `player_info` dict initialization
- Updated `handle_stats()` to include `xp_next` field in `stats_result`
- Fixed existing `test_xp.py` tests: set `game.player_entities = {}` to avoid MagicMock comparison error from new grant_xp level-up detection
- Fixed `test_query.py::test_stats_excludes_transient`: added `xp_next` to expected keys
- 16 new tests in `tests/test_level_up.py`, 598 total tests passing, 0 failures

### File List

- server/core/xp.py (modified — added get_pending_level_ups, send_level_up_available, level-up detection in grant_xp)
- server/net/handlers/levelup.py (new — handle_level_up handler)
- server/app.py (modified — registered level_up handler)
- server/net/handlers/auth.py (modified — added pending_level_ups to player_info, level-up re-check on login)
- server/net/handlers/query.py (modified — added xp_next to stats_result, added settings import)
- tests/test_level_up.py (new — 16 level-up tests)
- tests/test_xp.py (modified — fixed mock game.player_entities for grant_xp tests)
- tests/test_query.py (modified — added xp_next to expected stats keys)
