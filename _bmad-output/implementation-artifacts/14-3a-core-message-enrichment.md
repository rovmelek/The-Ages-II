# Story 14.3a: Core Message Enrichment

Status: done

## Story

As a game client developer,
I want server messages to include all data needed for display (entity IDs, HP values, NPC identifiers),
So that the client is a pure display layer with no need to construct IDs, assume game rules, or guess which NPC died.

## Acceptance Criteria

1. **Given** a successful login via `handle_login`, **When** the server sends `login_success`, **Then** the message includes `entity_id` (e.g., `"player_1"`) as a top-level field, **And** the existing `player_id` field is preserved (additive-only).

2. **Given** a successful registration via `handle_register`, **When** the server sends `login_success`, **Then** the message includes `entity_id` (e.g., `"player_1"`) as a top-level field, **And** the existing `player_id` field is preserved.

3. **Given** a player dies and respawns, **When** the server sends `respawn`, **Then** the message includes `hp` with the player's actual post-respawn HP value, **And** existing fields are preserved.
   > **NOTE**: `respawn` already includes `hp` and `max_hp` (see `server/app.py:329-336`). This AC is pre-satisfied. Verify via test assertion only.

4. **Given** a player completes level-up stat selection, **When** the server sends `level_up_complete`, **Then** the message includes `new_hp` with the player's actual current HP after recalculation, **And** existing fields (`level`, `new_max_hp`, `stat_changes`) are preserved.

5. **Given** a player wins combat against an NPC, **When** the server sends `combat_end` with `victory: true`, **Then** the message includes `defeated_npc_id` with the NPC's entity ID string (e.g., `"npc_slime_1"`), **And** existing fields are preserved. **And** if `instance.npc_id` is `None` (no NPC combat), the field is omitted.

6. **Given** each enriched message type, **When** the corresponding server code path executes, **Then** an existing test (not a new test file) asserts the new field is present and has the correct value (ADR-14-14).

7. **Given** the web client, **When** Story 14.3a is implemented, **Then** the client is updated minimally to use new fields where trivial but does NOT require rewriting client logic.

8. **Given** all emission code paths for each message type, **When** Story 14.3a is implemented, **Then** ALL code paths that emit each message type include the new field (verified by code path audit).

## Tasks / Subtasks

- [x] Task 1: Add `entity_id` to `login_success` in `handle_register` (AC: #2)
  - [x] 1.1: In `server/net/handlers/auth.py` line 217-236, add `"entity_id": f"player_{player.id}"` to the `login_success` dict (after `"player_id": player.id`).

- [x] Task 2: Add `entity_id` to `login_success` in `handle_login` (AC: #1)
  - [x] 2.1: In `server/net/handlers/auth.py` line 376-395, add `"entity_id": entity_id` to the `login_success` dict (after `"player_id": player.id`). The variable `entity_id` is already constructed at line 276 as `f"player_{player.id}"`.

- [x] Task 3: Add `new_hp` to `level_up_complete` (AC: #4)
  - [x] 3.1: In `server/net/handlers/levelup.py` line 94-99, add `"new_hp": stats["hp"]` to the response dict. At this point `stats["hp"]` has been set to `stats["max_hp"]` on line 87 (full heal on level-up).

- [x] Task 4: Add `defeated_npc_id` to `combat_end` on victory (AC: #5)
  - [x] 4.1: In `server/net/handlers/combat.py`, inside the per-player loop (line 84), after constructing `player_end_result` (line 144), add the field conditionally:
    ```python
    if end_result.get("victory") and instance.npc_id:
        player_end_result["defeated_npc_id"] = instance.npc_id
    ```
    Place this before the `await ws.send_json(...)` at line 151.

- [x] Task 5: Verify `respawn` already includes `hp` (AC: #3)
  - [x] 5.1: Confirm `server/app.py:329-336` already sends `hp` and `max_hp`. No server code change needed.

- [x] Task 6: Add test assertions for `entity_id` in `login_success` (AC: #6)
  - [x] 6.1: In `tests/test_auth.py`, in `test_register_success` (line 81): add `assert resp["entity_id"] == f"player_{resp['player_id']}"`.
  - [x] 6.2: In `tests/test_auth.py`, in `test_register_login_success_includes_stats` (line 167): add `assert "entity_id" in resp` and `assert resp["entity_id"] == f"player_{resp['player_id']}"`.
  - [x] 6.3: In `tests/test_auth.py`, in `test_login_success_includes_stats` (line 188): add `assert resp["entity_id"] == f"player_{resp['player_id']}"`.

- [x] Task 7: Add test assertion for `new_hp` in `level_up_complete` (AC: #6)
  - [x] 7.1: In `tests/test_level_up.py`, in `test_handle_level_up_valid` (line 120): after line 144 (`assert msg["new_max_hp"] == 110`), add `assert msg["new_hp"] == 110` (equals max_hp due to full heal).

- [x] Task 8: Add test assertion for `defeated_npc_id` in `combat_end` (AC: #6)
  - [x] 8.1: In `tests/test_party_combat.py`, in `test_check_combat_end_per_player_loot` (line 623): this test passes `npc_id="npc_1"` to `start_combat()` (line 637), so `instance.npc_id` is set. After `_check_combat_end` call, retrieve the websocket mock via `game.connection_manager.get_websocket("player_1")` and inspect `ws.send_json.call_args_list` to find the `combat_end` message. Assert it includes `"defeated_npc_id": "npc_1"`.
  - [x] 8.2: **Do NOT use** `test_check_combat_end_applies_party_bonus` (line 533) or `test_check_combat_end_solo_no_bonus` (line 682) — those tests don't pass `npc_id` to `start_combat()`, so `instance.npc_id` is `None` and `defeated_npc_id` would be absent.

- [x] Task 9: Add test assertion for `hp` in `respawn` (AC: #3, #6)
  - [x] 9.1: Added `test_respawn_player_sends_hp` to `tests/test_game.py` — calls real `game.respawn_player()`, captures WebSocket message, asserts `hp == 100` and `max_hp == 100`.

- [x] Task 10: Minimal web client updates (AC: #7)
  - [x] 10.1: In `web-demo/js/game.js`, `handleLoginSuccess` (line 515): replace `const entityId = \`player_${data.player_id}\`` with `const entityId = data.entity_id || \`player_${data.player_id}\`` (use server value with fallback).
  - [x] 10.2: In `handleRespawn` (line 645-658): replace `gameState.player.stats.hp = gameState.player.stats.max_hp` with `gameState.player.stats.hp = data.hp` (use server-authoritative value).
  - [x] 10.3: In `handleLevelUpComplete` (line 1670): replace `stats.hp = data.new_max_hp` with `stats.hp = data.new_hp || data.new_max_hp` (use server value with fallback).
  - [x] 10.4: In `handleCombatEnd` (line 1160): in the victory NPC-marking block (lines 1171-1179), add an early branch: if `data.defeated_npc_id` is present, find the NPC by ID directly (`gameState.room.npcs.find(n => n.id === data.defeated_npc_id)`) instead of using the proximity heuristic. Keep proximity as fallback.

- [x] Task 11: Run `make test` and verify all tests pass (AC: #6)

## Dev Notes

### Architecture Compliance
- **ADR-14-14**: Tests as message contract — add assertions to existing test functions, NOT new test files.
- **Additive-only changes**: All existing fields preserved. New fields added alongside, never replacing.
- **Cross-cutting rule**: Test assertions use literal values (e.g., `assert msg["new_hp"] == 110`), not `settings.*` references.

### Key Implementation Details

**`login_success` has 2 emission paths:**
1. `handle_register` (`auth.py:217-236`) — `player.id` available but `entity_id` variable not yet constructed. Use `f"player_{player.id}"` inline.
2. `handle_login` (`auth.py:376-395`) — `entity_id` already exists as a local variable (line 276).

**`respawn` already has `hp`:** The `Game.respawn_player()` method at `server/app.py:329-336` already sends `hp` and `max_hp`. No code change needed — only a test assertion to formally verify. HP is set to `max_hp` at line 280.

**`level_up_complete` new_hp:** After level-up, `stats["hp"] = stats["max_hp"]` (line 87 of `levelup.py`). The `new_hp` value will always equal `new_max_hp` currently, but sending it explicitly decouples the client from this game rule.

**`combat_end` defeated_npc_id:** `instance.npc_id` (from `CombatInstance`, `server/combat/instance.py:31`) is the NPC entity ID string. It can be `None` for PvP or non-NPC combat. Only include `defeated_npc_id` when both `victory` is true AND `npc_id` is not None. The field goes into `player_end_result` dict before `ws.send_json` at line 151.

**`combat_end` uses `victory: True/False`** (boolean), NOT `result: "victory"`. The check is `end_result.get("victory")`.

### What NOT to Change
- Existing message field names or values
- Combat loot distribution logic
- Respawn flow or HP calculation logic
- Level-up stat selection or persistence logic
- Any test assertion values for existing fields
- Client-side logic beyond minimal field adoption

### Web Client Guidance
All client changes are defensive (use new field with fallback to old behavior):
- `data.entity_id || \`player_${data.player_id}\`` — graceful degradation
- `data.hp` instead of `stats.max_hp` — use server-authoritative value
- `data.new_hp || data.new_max_hp` — fallback for backwards compat
- `data.defeated_npc_id` with proximity fallback — NPC marking improvement

### Testing Strategy
Add assertions to these existing tests (ADR-14-14):
| Message | Test File | Test Function | New Assertion |
|---------|-----------|---------------|---------------|
| `login_success` (register) | `tests/test_auth.py` | `test_register_success` (line 81) | `entity_id == f"player_{player_id}"` |
| `login_success` (register) | `tests/test_auth.py` | `test_register_login_success_includes_stats` (line 167) | `entity_id` present |
| `login_success` (login) | `tests/test_auth.py` | `test_login_success_includes_stats` (line 188) | `entity_id == f"player_{player_id}"` |
| `level_up_complete` | `tests/test_level_up.py` | `test_handle_level_up_valid` (line 120) | `new_hp == 110` |
| `combat_end` (victory) | `tests/test_party_combat.py` | `test_check_combat_end_per_player_loot` (line 623) | `defeated_npc_id == "npc_1"` |
| `respawn` | Existing test TBD | Assert `hp` field present in respawn message | `hp == max_hp` |

### Previous Story Intelligence (14.2)
- Pure mechanical changes across files — same pattern here
- Zero test assertion changes for existing values
- `make test` as verification gate
- All tests must pass (currently 804)
- ADR-14-14 pattern: tests serve as message contracts

### Project Structure Notes
- Modified server files: `server/net/handlers/auth.py`, `server/net/handlers/levelup.py`, `server/net/handlers/combat.py`
- No changes to `server/app.py` (respawn already has `hp`)
- Modified test files: `tests/test_auth.py`, `tests/test_level_up.py`, `tests/test_party_combat.py`
- Modified client file: `web-demo/js/game.js`
- No new files created, no files deleted

### References
- [Source: _bmad-output/planning-artifacts/epics.md#Story 14.3a] — AC and FRs
- [Source: _bmad-output/planning-artifacts/epics.md#ADR-14-14] — tests as message contract
- [Source: server/net/handlers/auth.py:217-236] — register login_success emission
- [Source: server/net/handlers/auth.py:376-395] — login login_success emission
- [Source: server/app.py:329-336] — respawn message (already has hp)
- [Source: server/net/handlers/levelup.py:94-102] — level_up_complete emission
- [Source: server/net/handlers/combat.py:141-151] — combat_end emission
- [Source: server/combat/instance.py:31] — instance.npc_id
- [Source: web-demo/js/game.js:515] — client entity_id construction
- [Source: _bmad-output/implementation-artifacts/14-2-data-driven-loot-tables.md] — previous story patterns

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List
- Added `entity_id` field to `login_success` in both `handle_register` and `handle_login` (additive-only, `player_id` preserved)
- Added `new_hp` field to `level_up_complete` response (equals `max_hp` after full heal on level-up)
- Added `defeated_npc_id` field to `combat_end` on victory when `instance.npc_id` is set (omitted for non-NPC combat)
- Confirmed `respawn` message already includes `hp` and `max_hp` — no server change needed
- Added `entity_id` assertions to 3 existing auth tests (`test_register_success`, `test_register_login_success_includes_stats`, `test_login_success_includes_stats`)
- Added `new_hp == 110` assertion to `test_handle_level_up_valid`
- Added `defeated_npc_id == "npc_1"` assertion to `test_check_combat_end_per_player_loot`
- Added `test_respawn_player_sends_hp` to `test_game.py` asserting respawn message includes `hp` and `max_hp`
- Updated web client: `handleLoginSuccess` uses `data.entity_id`, `handleRespawn` uses `data.hp`, `handleLevelUpComplete` uses `data.new_hp`, `handleCombatEnd` uses `data.defeated_npc_id` with proximity fallback
- All 805 tests pass (804 existing + 1 new), zero assertion changes to existing values

### File List
- server/net/handlers/auth.py (modified — added `entity_id` to both `login_success` emissions)
- server/net/handlers/levelup.py (modified — added `new_hp` to `level_up_complete`)
- server/net/handlers/combat.py (modified — added `defeated_npc_id` to `combat_end` on victory)
- tests/test_auth.py (modified — added `entity_id` assertions to 3 tests)
- tests/test_level_up.py (modified — added `new_hp` assertion)
- tests/test_party_combat.py (modified — added `defeated_npc_id` assertion)
- tests/test_game.py (modified — added `test_respawn_player_sends_hp`)
- web-demo/js/game.js (modified — updated 4 message handlers to use new fields)
