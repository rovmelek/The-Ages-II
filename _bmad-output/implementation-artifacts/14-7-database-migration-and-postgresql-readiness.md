# Story 14.7: Database Migration & PostgreSQL Readiness

Status: done

## Story

As a developer,
I want Alembic schema migrations, connection pooling config, and timezone-correct datetimes,
So that the database layer supports schema evolution and is ready for a future PostgreSQL swap.

## Acceptance Criteria

1. **Given** the project has no Alembic setup, **When** Story 14.7 is implemented, **Then** `alembic/` directory, `alembic.ini`, and `alembic/env.py` exist configured for sync Alembic using `settings.ALEMBIC_DATABASE_URL`, **And** an auto-generated initial migration represents the current schema, **And** running `alembic upgrade head` on a fresh database produces a schema identical to `create_all`, **And** a migration roundtrip test verifies this equivalence.

2. **Given** `Base.metadata.create_all` in `server/core/database.py` (line 23), **When** Story 14.7 is implemented, **Then** `create_all` is preserved alongside Alembic (not removed) per ADR-14-21.

3. **Given** `Makefile` with existing `test`, `test-verbose`, `server`, `install` targets, **When** Story 14.7 is implemented, **Then** a `make db-migrate` target exists that runs `alembic upgrade head` using `.venv/bin/alembic`.

4. **Given** `create_async_engine` in `server/core/database.py` (line 10) with no pool config, **When** Story 14.7 is implemented, **Then** pool settings (`pool_size`, `max_overflow`, `pool_pre_ping`) from `settings` are applied conditionally — only when the URL does NOT contain `sqlite` (SQLite uses `StaticPool`/single-connection and ignores these params).

5. **Given** `SpawnCheckpoint` in `server/room/spawn_models.py` (lines 16-17) with `DateTime` columns (no `timezone=True`), and `datetime.now(UTC).replace(tzinfo=None)` usage in `server/core/scheduler.py` (lines 123, 207), **When** Story 14.7 is implemented, **Then** all datetime usage is timezone-aware (`datetime.now(UTC)` without `.replace(tzinfo=None)`), **And** `SpawnCheckpoint` columns use `DateTime(timezone=True)`, **And** the initial Alembic migration includes this column type.

6. **Given** the decomposed combat helpers in `server/net/handlers/combat.py`, **When** Story 14.7 is implemented, **Then** per-participant transactions in `_check_combat_end` (lines 193-218) are consolidated — currently each participant may trigger up to 3 separate `game.transaction()` calls: one in `grant_xp` (xp.py:50), one in `_distribute_combat_loot` (combat.py:87), and one for stats persist (combat.py:214). These should be merged to 1 transaction per participant. **And** per-participant isolation is preserved (participant A's failure does not roll back participant B).

7. **Given** all existing tests, **When** Story 14.7 is implemented, **Then** all tests pass via `make test`.

## Tasks / Subtasks

### Part A: Alembic Scaffold (AC: #1, #2, #3)

- [x] Task 1: Install Alembic and create scaffold
  - [x] 1.1: Add `alembic` to project dependencies in `pyproject.toml` (under `[project.dependencies]`). Run `.venv/bin/pip install -e ".[dev]"` to install.
  - [x] 1.2: Run `.venv/bin/alembic init alembic` to create the `alembic/` directory, `alembic.ini`, and `alembic/env.py`.
  - [x] 1.3: Edit `alembic.ini`: set `sqlalchemy.url` to empty string (will be overridden by `env.py`).
  - [x] 1.4: Edit `alembic/env.py`:
    - Import `settings` from `server.core.config` and `Base` from `server.core.database`.
    - Import all model modules so `Base.metadata` discovers them (same imports as `init_db()` in `database.py` lines 16-20: `server.combat.cards.models`, `server.items.models`, `server.player.models`, `server.room.models`, `server.room.spawn_models`).
    - Set `target_metadata = Base.metadata`.
    - In `run_migrations_offline()`, set `url = settings.ALEMBIC_DATABASE_URL`.
    - In `run_migrations_online()`, create engine with `create_engine(settings.ALEMBIC_DATABASE_URL)` (sync, not async).

- [x] Task 2: Generate initial migration
  - [x] 2.1: Delete `data/game.db` if it exists (fresh start for migration generation).
  - [x] 2.2: Run `.venv/bin/alembic revision --autogenerate -m "initial schema"` to auto-generate the initial migration.
  - [x] 2.3: Review the generated migration file — it should create all 7 tables: `players`, `cards`, `items`, `rooms`, `room_states`, `player_object_states`, `spawn_checkpoints` with correct column types.
  - [x] 2.4: Verify the migration includes `DateTime(timezone=True)` for `SpawnCheckpoint` columns (after Part C changes).

- [x] Task 3: Add Makefile target
  - [x] 3.1: Add `db-migrate` target to `Makefile`: `.venv/bin/alembic upgrade head`. Add it to the `.PHONY` line.

### Part B: Connection Pool Config (AC: #4)

- [x] Task 4: Conditional pool settings in `database.py`
  - [x] 4.1: In `server/core/database.py` (line 10), modify the `create_async_engine` call. Check if `"sqlite"` is in `settings.DATABASE_URL`. If NOT sqlite, add `pool_size=settings.DB_POOL_SIZE`, `max_overflow=settings.DB_MAX_OVERFLOW`, `pool_pre_ping=settings.DB_POOL_PRE_PING`. If sqlite, do not pass pool params (SQLite + aiosqlite uses `StaticPool` internally).
  - [x] 4.2: The `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_PRE_PING` settings already exist in `server/core/config.py` (lines 80-82) — no config changes needed.
  - [x] 4.3: Update the `ALEMBIC_DATABASE_URL` property in `server/core/config.py` (lines 85-88) to handle PostgreSQL async drivers in addition to SQLite. Currently it only replaces `sqlite+aiosqlite` → `sqlite`. Add handling for `postgresql+asyncpg` → `postgresql` (the default psycopg2 driver). This makes the property actually PostgreSQL-ready.

### Part C: Timezone-Aware Datetimes (AC: #5)

- [x] Task 5: Update `SpawnCheckpoint` model
  - [x] 5.1: In `server/room/spawn_models.py` (lines 16-17), change `DateTime` to `DateTime(timezone=True)` for both `last_check_at` and `next_check_at` columns.

- [x] Task 6: Remove `.replace(tzinfo=None)` from scheduler
  - [x] 6.1: In `server/core/scheduler.py` line 123, change `datetime.now(UTC).replace(tzinfo=None)` to `datetime.now(UTC)`.
  - [x] 6.2: In `server/core/scheduler.py` line 207, change `datetime.now(UTC).replace(tzinfo=None)` to `datetime.now(UTC)`.
  - [x] 6.3: Review `_run_rare_spawn_checks` and `_recover_checkpoints` — the comparison `cp.next_check_at <= now` (line 213) must work with timezone-aware datetimes. Added `_ensure_aware()` helper to normalize naive SQLite datetimes to UTC-aware before comparison.

### Part D: Transaction Consolidation (AC: #6)

- [x] Task 7: Consolidate per-participant transactions in `_check_combat_end`
  - [x] 7.1: In `server/net/handlers/combat.py`, modify the per-participant loop (lines 193-218). Currently, for a victorious participant, up to 3 `game.transaction()` calls occur:
    - `_award_combat_xp` → `grant_xp` (xp.py:50) — persists stats with XP
    - `_distribute_combat_loot` (combat.py:87) — persists inventory with loot
    - Stats persist (combat.py:214) — persists stats again
  - [x] 7.2: Refactor approach: Pass a `session` parameter through `grant_xp` and `_distribute_combat_loot` so they can participate in a single transaction opened in `_check_combat_end`. Add an optional `session` parameter to both functions — when provided, use it instead of opening a new transaction.
  - [x] 7.3: In `_check_combat_end`, open one `game.transaction()` per participant that covers XP grant + loot distribution + stats persist. Each participant gets its own `try/except` wrapping its transaction so one participant's failure doesn't affect others.
  - [x] 7.4: `grant_xp` in `server/core/xp.py` (line 29) is also called from `server/net/handlers/interact.py` and `server/net/handlers/movement.py` (exploration XP). Those callers pass no session, so `grant_xp` must remain backward-compatible — open its own transaction when no session is provided.
  - [x] 7.5: `_distribute_combat_loot` is only called from `_check_combat_end`, so it can be changed more freely — but keep the optional session pattern for consistency.
  - [x] 7.6: `_sync_combat_stats` (combat.py:19-35) also opens a transaction per participant on every turn. This is called from `_broadcast_combat_state` on every combat action — leave this unchanged (it's per-turn, not per-combat-end, and consolidating it would require threading sessions through the combat action handlers).

### Part E: Migration Roundtrip Test (AC: #1, #7)

- [x] Task 8: Write migration equivalence test
  - [x] 8.1: Create `tests/test_migration.py`. The test should:
    - Create two temporary SQLite databases (using `tempfile`).
    - Database A: apply `Base.metadata.create_all` (sync engine).
    - Database B: run `alembic upgrade head` programmatically (using `alembic.command.upgrade` with `alembic.config.Config`).
    - Compare the schemas of both databases (table names, column names, column types, nullable flags, constraints).
    - Assert they are equivalent.
  - [x] 8.2: Use `sqlalchemy.inspect(engine).get_table_names()` and `get_columns(table_name)` for schema comparison.
  - [x] 8.3: Run `make test` and confirm all tests pass.

### Part F: Verification (AC: #7)

- [x] Task 9: Run full test suite
  - [x] 9.1: Run `make test`. All previously-passing tests must still pass.
  - [x] 9.2: Updated `tests/test_spawn.py` (5 occurrences) and `tests/test_events.py` (1 occurrence) to use timezone-aware datetimes. Added `_ensure_aware()` helper to scheduler for SQLite naive-datetime compatibility.
  - [x] 9.3: Delete `data/game.db` before final verification to ensure clean state.

## Dev Notes

### Architecture Compliance

- **ADR-14-5**: Sync Alembic with auto-derived `ALEMBIC_DATABASE_URL` (`settings.ALEMBIC_DATABASE_URL` property already exists in config.py:86-88, converts `sqlite+aiosqlite` → `sqlite`).
- **ADR-14-9**: Merge per-participant transactions (3→1), preserve per-participant isolation. Don't merge across participants.
- **ADR-14-11**: Pool settings conditional on driver — only apply when URL is not SQLite.
- **ADR-14-12**: UTC-aware datetimes — stop stripping tzinfo.
- **ADR-14-18**: Auto-generate initial migration; delete dev DBs for fresh start.
- **ADR-14-21**: Keep `create_all` alongside Alembic — do NOT remove it from `database.py`.

### Key Files to Modify

**Production files:**
| File | Changes |
|------|---------|
| `server/core/database.py` | Conditional pool settings on `create_async_engine` |
| `server/room/spawn_models.py` | `DateTime(timezone=True)` on checkpoint columns |
| `server/core/scheduler.py` | Remove `.replace(tzinfo=None)` (2 locations) |
| `server/core/xp.py` | Add optional `session` param to `grant_xp` |
| `server/core/config.py` | Update `ALEMBIC_DATABASE_URL` property to handle PostgreSQL async drivers |
| `server/net/handlers/combat.py` | Consolidate per-participant transactions in `_check_combat_end`; optional `session` param on `_distribute_combat_loot` |

**New files:**
| File | Purpose |
|------|---------|
| `alembic.ini` | Alembic config (project root) |
| `alembic/env.py` | Migration environment (imports models, uses `settings.ALEMBIC_DATABASE_URL`) |
| `alembic/versions/<hash>_initial_schema.py` | Auto-generated initial migration |
| `tests/test_migration.py` | Roundtrip test: `create_all` vs `alembic upgrade head` schema equivalence |

**Modified config files:**
| File | Changes |
|------|---------|
| `pyproject.toml` | Add `alembic` dependency |
| `Makefile` | Add `db-migrate` target |

### Transaction Consolidation Detail

**Current state** (per participant in `_check_combat_end`):
```
Transaction 1: grant_xp → update_stats (XP)        [xp.py:50]
Transaction 2: _distribute_combat_loot → get_by_id + update_inventory  [combat.py:87]
Transaction 3: update_stats (final combat stats)     [combat.py:214]
```

**Target state** (per participant):
```
Transaction 1: update_stats (XP + final stats) + get_by_id + update_inventory (loot)
```

Key constraint: `grant_xp` also sends WebSocket messages (`xp_gained`, `level_up_available`). These should remain outside the transaction — messages are best-effort and shouldn't block DB commits.

### What NOT to Change

- `_sync_combat_stats` (combat.py:19-35) — called per-turn from `_broadcast_combat_state`, not part of combat-end consolidation
- `handle_use_item_combat` (combat.py:310) — its transaction is for item consumption during combat, separate concern
- `Base.metadata.create_all` in `database.py` — preserve per ADR-14-21
- `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_PRE_PING` in `config.py` — already exist, no changes needed

### Previous Story Intelligence (14.6)

- Lock additions were transparent to existing tests — similarly, transaction consolidation should not change observable behavior
- Test setup pattern: `game.transaction = MagicMock(return_value=mock_ctx)` for unit tests
- 781 passed in 14.6, with 8 pre-existing failures and 2 collection errors (`test_chest`, `test_loot` — `server.items.loot` deleted in 14.2)
- `PlayerSession` dataclass is the standard way to access player info (`.entity`, `.db_id`, `.inventory`, `.room_key`)

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 14.7] — AC, FR113, FR115, FR116, FR117
- [Source: server/core/database.py:10-23] — `create_async_engine` (no pool config), `init_db` with `create_all`
- [Source: server/core/config.py:78-88] — `DATABASE_URL`, `DB_POOL_*` settings, `ALEMBIC_DATABASE_URL` property
- [Source: server/room/spawn_models.py:16-17] — `DateTime` columns without `timezone=True`
- [Source: server/core/scheduler.py:123,207] — `datetime.now(UTC).replace(tzinfo=None)`
- [Source: server/net/handlers/combat.py:193-218] — per-participant loop with 3 transactions
- [Source: server/core/xp.py:29-74] — `grant_xp` with its own `game.transaction()` at line 50
- [Source: _bmad-output/implementation-artifacts/14-6-concurrency-safety.md] — previous story learnings

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Added `alembic>=1.13.0` to `pyproject.toml` dependencies; ran `alembic init alembic`
- Configured `alembic/env.py` with model imports, `settings.ALEMBIC_DATABASE_URL`, `_get_url()` helper for config override support
- Set `alembic.ini` `sqlalchemy.url` to empty (env.py provides URL)
- Auto-generated initial migration `bf6901ef8aa9_initial_schema.py` covering all 7 tables with `DateTime(timezone=True)` on `spawn_checkpoints`
- Added `make db-migrate` target to Makefile
- Conditional pool settings in `database.py`: `pool_size`, `max_overflow`, `pool_pre_ping` applied only for non-SQLite URLs
- Updated `ALEMBIC_DATABASE_URL` property to handle both `sqlite+aiosqlite` → `sqlite` and `postgresql+asyncpg` → `postgresql`
- Changed `SpawnCheckpoint` columns to `DateTime(timezone=True)`
- Removed `.replace(tzinfo=None)` from `scheduler.py` (2 locations); added `_ensure_aware()` helper for SQLite compatibility (SQLite returns naive datetimes even with `timezone=True`)
- Updated `tests/test_spawn.py` (5 occurrences) and `tests/test_events.py` (1 occurrence) to use timezone-aware datetimes
- Added optional `session` parameter to `grant_xp()` in `xp.py` — backward-compatible (opens own transaction when no session provided)
- Added optional `session` parameter to `_distribute_combat_loot()` and `_award_combat_xp()` in `combat.py`
- Consolidated per-participant transactions in `_check_combat_end`: 3 transactions → 1 per participant with try/except for per-participant isolation
- Created `tests/test_migration.py` with roundtrip schema equivalence test
- 782 passed, 8 pre-existing failures, 2 collection errors (unchanged from 14.6)

### File List

- pyproject.toml (modified — added `alembic>=1.13.0` dependency)
- alembic.ini (new — Alembic config with empty sqlalchemy.url)
- alembic/env.py (new — migration env with model imports, `_get_url()` helper)
- alembic/versions/bf6901ef8aa9_initial_schema.py (new — auto-generated initial migration)
- alembic/script.py.mako (new — Alembic template, auto-generated)
- alembic/README (new — Alembic readme, auto-generated)
- Makefile (modified — added `db-migrate` target)
- server/core/database.py (modified — conditional pool settings on `create_async_engine`)
- server/core/config.py (modified — `ALEMBIC_DATABASE_URL` handles PostgreSQL async drivers)
- server/room/spawn_models.py (modified — `DateTime(timezone=True)` on checkpoint columns)
- server/core/scheduler.py (modified — removed `.replace(tzinfo=None)`, added `_ensure_aware()` helper)
- server/core/xp.py (modified — optional `session` param on `grant_xp`)
- server/net/handlers/combat.py (modified — optional `session` params, consolidated per-participant transactions in `_check_combat_end`)
- tests/test_spawn.py (modified — timezone-aware datetimes)
- tests/test_events.py (modified — timezone-aware datetimes)
- tests/test_migration.py (new — migration roundtrip schema equivalence test)
