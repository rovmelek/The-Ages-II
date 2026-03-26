# Story 7.2: Player Stats Persistence

Status: done

## Story

As a player,
I want my HP and stats to be saved and restored between sessions,
so that damage I take and progress I make persists across logins and server restarts.

## Acceptance Criteria

1. **Given** a first-time player logs in with empty stats in DB,
   **When** the server creates their entity,
   **Then** defaults are applied: hp=100, max_hp=100, attack=10,
   **And** these defaults are saved to the DB.

2. **Given** a player's HP changes during combat (damage taken, heal, shield consumed),
   **When** the complete action resolves (not per individual effect),
   **Then** stats are saved to the DB with only whitelisted keys: hp, max_hp, attack,
   **And** unknown keys are stripped before save.

3. **Given** a player uses a consumable item that modifies both stats and inventory,
   **When** the action completes,
   **Then** both stats and inventory changes are committed in a single DB transaction.

4. **Given** a player disconnects,
   **When** the disconnect handler fires,
   **Then** all player state (stats + inventory + position) is batched into one DB transaction.

5. **Given** combat ends,
   **When** cleanup runs,
   **Then** shield is reset to 0 (NOT persisted — combat-only buffer).

6. **Given** a player logs back in after disconnect or server restart,
   **When** the server loads their entity,
   **Then** stats are restored from DB (hp, max_hp, attack) — not reset to defaults.

7. **Given** `player/repo.py` currently has no `update_stats()` method,
   **When** the story is complete,
   **Then** a stats update method exists and all affected tests pass.

## Tasks / Subtasks

- [ ] Task 1: Add `update_stats()` to player repo (AC: 7)
  - [ ] Create `async def update_stats(session, player_id, stats: dict)` in `server/player/repo.py`
  - [ ] Whitelist keys: `hp`, `max_hp`, `attack` — strip everything else (no `shield`, no combat temps)
  - [ ] Update the `Player.stats` JSON column and commit

- [ ] Task 2: Initialize stats on first login (AC: 1)
  - [ ] In auth.py login handler, if `player.stats` is empty/None, apply defaults: `{hp: 100, max_hp: 100, attack: 10}`
  - [ ] Save defaults to DB immediately via `update_stats()`
  - [ ] For returning players with existing stats, load them as-is

- [ ] Task 3: Restore stats on login (AC: 6)
  - [ ] In auth.py, set `entity.stats = player.stats` (already done at line 82: `stats=player.stats or {}`)
  - [ ] Ensure defaults are applied BEFORE entity creation so the entity always has valid stats

- [ ] Task 4: Persist stats after combat actions (AC: 2, 5)
  - [ ] After `CombatInstance.resolve_action()` completes, sync combat participant stats back to entity
  - [ ] Call `update_stats()` to persist — strip `shield` before save
  - [ ] On combat end: reset shield to 0 in entity stats, then save
  - [ ] Note: combat uses a copy of stats (`dict(entity.stats)`) — changes must flow back

- [ ] Task 5: Persist stats on disconnect (AC: 4)
  - [ ] In `Game.handle_disconnect()` (app.py line 193-199), save stats alongside position
  - [ ] Batch into single DB transaction: position + stats (+ inventory if Story 7.3 is done)

- [ ] Task 6: Persist stats + inventory atomically (AC: 3)
  - [ ] When item usage modifies stats (e.g., healing potion restores HP), save both in one transaction
  - [ ] This can be deferred until Story 7.3 (Inventory Persistence) is implemented — just save stats for now

- [ ] Task 7: Apply XP rewards (Fixes ISS-006) (AC: 2)
  - [ ] In `_check_combat_end()` when `victory=True`, add XP to entity stats: `entity.stats["xp"] = entity.stats.get("xp", 0) + rewards["xp"]`
  - [ ] Add `xp` to the whitelist of persisted keys
  - [ ] Persist updated stats to DB

- [ ] Task 8: Tests (AC: 7)
  - [ ] Unit test `update_stats()` — verify whitelist filtering
  - [ ] Test stats persistence round-trip: set stats → disconnect → login → verify restored
  - [ ] Test combat stats sync: take damage → verify entity stats updated
  - [ ] Run `pytest tests/`

## Dev Notes

### Current Implementation

- **PlayerEntity** (`server/player/entity.py` lines 5-16): dataclass with `stats: dict = field(default_factory=dict)` — plain dict, no schema
- **DB model** (`server/player/models.py` line 14): `stats = Column(JSON)` — stores arbitrary JSON
- **Login** (auth.py line 82): `stats=player.stats or {}` — loads DB stats but falls back to empty
- **Combat** (movement.py lines 130-134): `setdefault` applies defaults to a COPY `dict(entity.stats)`, NOT to the entity itself. Combat stats live in `CombatInstance.participants[idx]` and are never synced back.
- **Repo** (`server/player/repo.py`): Has `update_position()` but NO `update_stats()`
- **Disconnect** (app.py lines 193-199): Only saves position, wrapped in `except Exception: pass`

### Critical Design Decision: Stats Whitelist

Only persist: `hp`, `max_hp`, `attack`, `xp`. Strip everything else (`shield`, combat temps, computed values). Shield is a combat-only buffer that resets to 0 after every combat.

### ISS-006 Integration

This story naturally fixes ISS-006 (victory XP not applied). Task 7 adds XP to entity stats on victory and persists it. Mark ISS-006 as done when this story completes.

### Existing Code to Reuse

- `player_repo.update_position()` — pattern for the new `update_stats()` method
- `server/core/database.py` — `async_session` for DB transactions

### Project Structure Notes

- Modified files: `server/player/repo.py`, `server/net/handlers/auth.py`, `server/net/handlers/combat.py`, `server/app.py` (disconnect handler)
- New test: `tests/test_stats_persistence.py` or add to existing test files

### References

- [Source: server/player/entity.py — lines 5-16]
- [Source: server/player/repo.py — update_position pattern]
- [Source: server/net/handlers/auth.py — line 82, stats loading]
- [Source: server/net/handlers/combat.py — _check_combat_end]
- [Source: server/net/handlers/movement.py — lines 130-134, combat stats copy]
- [Source: ISS-006 — victory XP not applied]
- [Source: architecture.md#Section 9.1 — Player data model]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Completion Notes List
- Task 1: Added `update_stats()` with `_STATS_WHITELIST = {"hp", "max_hp", "attack", "xp"}` to `server/player/repo.py`
- Task 2+3: Modified auth.py login handler to apply default stats `{hp:100, max_hp:100, attack:10, xp:0}` for first-time players and restore saved stats for returning players
- Task 4: Added `_sync_combat_stats()` in combat.py that syncs combat participant stats back to entity and persists to DB after each action
- Task 5: Added `update_stats()` call in `Game.handle_disconnect()` alongside existing `update_position()`
- Task 6: Deferred to Story 7.3 (inventory persistence) — stats-only save works now
- Task 7: Applied XP rewards on combat victory in `_check_combat_end()`, fixing ISS-006. Also resets shield to 0 on combat end.
- Task 8: Created `tests/test_stats_persistence.py` with 6 tests covering whitelist filtering, first-login defaults, returning player restore, disconnect save, and combat stats sync

### File List
- `server/player/repo.py` — Added `update_stats()` with whitelist
- `server/net/handlers/auth.py` — Default stats init + restore on login
- `server/net/handlers/combat.py` — `_sync_combat_stats()`, XP reward application, shield reset on combat end
- `server/app.py` — Stats save on disconnect
- `tests/test_stats_persistence.py` — New test file (6 tests)
