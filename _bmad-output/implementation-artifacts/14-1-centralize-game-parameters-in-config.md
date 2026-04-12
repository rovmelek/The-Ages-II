# Story 14.1: Centralize Game Parameters in Config

Status: done

## Story

As a developer,
I want all game balance parameters defined in a single config source (`Settings` class),
So that changing a game value requires editing one place, and the codebase is consistent with the architecture's JSON-driven configuration principle.

## Acceptance Criteria

1. **Given** the `Settings` class in `server/core/config.py`, **When** Story 14.1 is implemented, **Then** the following settings are added with section comments organizing the file:
   - Player Defaults: `DEFAULT_BASE_HP=100`, `DEFAULT_ATTACK=10`, `DEFAULT_STAT_VALUE=1`
   - Game Structure: `DEFAULT_SPAWN_ROOM="town_square"`, `STAT_CAP=10`, `LEVEL_UP_STAT_CHOICES=3`
   - Combat: `COMBAT_HAND_SIZE=5`, `COMBAT_MIN_DAMAGE=1`
   - NPC: `NPC_DEFAULT_HP_MULTIPLIER=10`, `NPC_ATTACK_DICE_MULTIPLIER=2`
   - Auth: `MIN_USERNAME_LENGTH=3`, `MIN_PASSWORD_LENGTH=6`
   - Trade: `TRADE_COOLDOWN_SECONDS=5`
   - DB: `DB_POOL_SIZE=10`, `DB_MAX_OVERFLOW=20`, `DB_POOL_PRE_PING=True`
   - Migration: `ALEMBIC_DATABASE_URL` auto-derived from `DATABASE_URL` (strips async driver prefix)
   **And** `field_validator` guards exist for: `DEFAULT_BASE_HP >= 1`, `COMBAT_HAND_SIZE >= 1`, `COMBAT_MIN_DAMAGE >= 0`, `STAT_CAP >= 1`, `LEVEL_UP_STAT_CHOICES >= 1`, `DB_POOL_SIZE >= 1`

2. **Given** hardcoded value `100` (base HP) in `auth.py`, `levelup.py`, `movement.py`, `query.py`, `app.py`, **When** Story 14.1 is implemented, **Then** all occurrences reference `settings.DEFAULT_BASE_HP` instead of literal `100`. **And** the same replacement is applied for all other centralized values across their respective files.

3. **Given** `app.py` using hardcoded `60` for mob respawn fallback, **When** Story 14.1 is implemented, **Then** it uses `settings.MOB_RESPAWN_SECONDS` (which already exists in config).

4. **Given** `trade/manager.py` using hardcoded `5` for trade cooldown, **When** Story 14.1 is implemented, **Then** it uses `settings.TRADE_COOLDOWN_SECONDS`.

5. **Given** `_STATS_WHITELIST` in `player/repo.py` excludes `attack`, **When** Story 14.1 is implemented, **Then** a comment explains: "attack excluded -- derived from STR/INT at runtime, not independently persisted".

6. **Given** all existing tests (804+), **When** Story 14.1 is implemented, **Then** all tests pass with assertions unchanged (tests use literal values like `assert hp == 100`, not `settings.*`).

7. **Given** the config file after changes, **When** reviewed, **Then** a comment above player default settings states: "Player defaults: applied at registration only. Changing these does NOT retroactively update existing players in the database."

8. **Given** `test_integration.py`, **When** Story 14.1 begins, **Then** verify it covers the full gameplay loop (register -> login -> move -> fight -> loot -> disconnect -> reconnect -> verify state); expand coverage if gaps exist.

## Tasks / Subtasks

- [x] Task 1: Add new settings to `Settings` class in `server/core/config.py` (AC: #1, #7)
  - [x] 1.1: Add section comments and new settings with default values:
    ```python
    from pydantic import field_validator

    # --- Player Defaults ---
    # Player defaults: applied at registration only. Changing these does NOT
    # retroactively update existing players in the database.
    DEFAULT_BASE_HP: int = 100
    DEFAULT_ATTACK: int = 10
    DEFAULT_STAT_VALUE: int = 1

    # --- Game Structure ---
    DEFAULT_SPAWN_ROOM: str = "town_square"
    STAT_CAP: int = 10
    LEVEL_UP_STAT_CHOICES: int = 3

    # --- Combat ---
    COMBAT_HAND_SIZE: int = 5
    COMBAT_MIN_DAMAGE: int = 1

    # --- NPC ---
    NPC_DEFAULT_HP_MULTIPLIER: int = 10
    NPC_ATTACK_DICE_MULTIPLIER: int = 2

    # --- Auth ---
    MIN_USERNAME_LENGTH: int = 3
    MIN_PASSWORD_LENGTH: int = 6

    # --- Trade ---
    TRADE_COOLDOWN_SECONDS: int = 5

    # --- Database ---
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_PRE_PING: bool = True

    # --- Migration ---
    # Auto-derived: strip async driver for sync Alembic usage
    @property
    def ALEMBIC_DATABASE_URL(self) -> str:
        return self.DATABASE_URL.replace("sqlite+aiosqlite", "sqlite")
    ```
  - [x] 1.2: Add `field_validator` guards:
    ```python
    @field_validator("DEFAULT_BASE_HP")
    @classmethod
    def validate_base_hp(cls, v: int) -> int:
        if v < 1:
            raise ValueError("DEFAULT_BASE_HP must be >= 1")
        return v
    ```
    Same pattern for: `COMBAT_HAND_SIZE >= 1`, `COMBAT_MIN_DAMAGE >= 0`, `STAT_CAP >= 1`, `LEVEL_UP_STAT_CHOICES >= 1`, `DB_POOL_SIZE >= 1`
  - [x] 1.3: Organize existing settings with section comments too (Server, XP, etc.)

- [x] Task 2: Replace hardcoded `100` (base HP) across all files (AC: #2)
  - [x] 2.1: `server/net/handlers/auth.py` — 7 occurrences:
    - Line ~57: `entity.stats.get("max_hp", 100)` -> `entity.stats.get("max_hp", settings.DEFAULT_BASE_HP)`
    - Line ~216: `default_max_hp = 100 + ...` -> `default_max_hp = settings.DEFAULT_BASE_HP + ...`
    - Line ~290: `_DEFAULT_STATS` dict `"hp": 100, "max_hp": 100` -> `settings.DEFAULT_BASE_HP`
    - Line ~298: `stats["max_hp"] = 100 + ...` -> `settings.DEFAULT_BASE_HP + ...`
    - Lines ~380-381: `.get("hp", 100)`, `.get("max_hp", 100)` -> `settings.DEFAULT_BASE_HP`
  - [x] 2.2: `server/net/handlers/levelup.py` — 1 occurrence:
    - Line ~87: `stats["max_hp"] = 100 + ...` -> `settings.DEFAULT_BASE_HP + ...`
  - [x] 2.3: `server/net/handlers/movement.py` — 1 occurrence:
    - Line ~208: `p_stats.setdefault("hp", 100)` -> `settings.DEFAULT_BASE_HP`
  - [x] 2.4: `server/net/handlers/query.py` — 2 occurrences:
    - Lines ~119-120: `.get("hp", 100)`, `.get("max_hp", 100)` -> `settings.DEFAULT_BASE_HP`
  - [x] 2.5: `server/app.py` — 1 occurrence:
    - Line ~272: `entity.stats.get("max_hp", 100)` -> `settings.DEFAULT_BASE_HP`
  - [x] 2.6: Add `from server.core.config import settings` to any file that doesn't already import it

- [x] Task 3: Replace hardcoded `10` (default attack) in player-facing code (AC: #2)
  - [x] 3.1: `server/net/handlers/auth.py` — 3 occurrences:
    - Line ~225: `"attack": 10` -> `settings.DEFAULT_ATTACK`
    - Line ~290: `"attack": 10` in _DEFAULT_STATS -> `settings.DEFAULT_ATTACK`
    - Line ~382: `.get("attack", 10)` -> `settings.DEFAULT_ATTACK`
  - [x] 3.2: `server/net/handlers/movement.py` — 1 occurrence:
    - Line ~210: `p_stats.setdefault("attack", 10)` -> `settings.DEFAULT_ATTACK`
  - [x] 3.3: `server/net/handlers/query.py` — 1 occurrence:
    - Line ~121: `.get("attack", 10)` -> `settings.DEFAULT_ATTACK`
  - **DO NOT change** `combat/instance.py` line ~30 `"attack": 10` (mob fallback default) or line ~351 `.get("attack", 10)` (mob attack fallback) — these are mob defaults, not player defaults. Same for `movement.py` line ~193 `"attack": 10` in mob_stats fallback.

- [x] Task 4: Replace hardcoded `1` (default stat value) (AC: #2)
  - [x] 4.1: `server/net/handlers/auth.py` — 18 occurrences across 3 groups:
    - Registration response (lines ~226-233): 6 literal ability values `"strength": 1, "dexterity": 1, "constitution": 1, "intelligence": 1, "wisdom": 1, "charisma": 1` -> `settings.DEFAULT_STAT_VALUE`
    - `_DEFAULT_STATS` dict (lines ~291-293): 6 literal ability values `"strength": 1, ...` -> `settings.DEFAULT_STAT_VALUE`
    - Login success response (lines ~386-391): 6 `.get("<ability>", 1)` fallbacks -> `settings.DEFAULT_STAT_VALUE`
    - Keep as `1`: `"level": 1` (lines ~226, ~290) and `"xp": 0` (line ~290) — conceptual constants, not stat defaults
    - Keep as `1`: line ~402 `stats.get("level", 1)` in entity_entered broadcast data — level default
  - [x] 4.2: `server/net/handlers/levelup.py`:
    - Line ~77: `stats.get(s, 1)` -> `settings.DEFAULT_STAT_VALUE`
    - Line ~80: `stats.get(s, 1)` -> `settings.DEFAULT_STAT_VALUE`
    - Line ~87: `stats.get("constitution", 1)` -> `settings.DEFAULT_STAT_VALUE`
    - Keep as `1`: line ~84 `stats.get("level", 1)` — level default
  - [x] 4.3: `server/net/handlers/movement.py`:
    - Keep as `1`: line ~337 `entity.stats.get("level", 1)` — level default
  - [x] 4.4: `server/net/handlers/query.py`:
    - Lines ~125-130: 6 `.get("<ability>", 1)` -> `settings.DEFAULT_STAT_VALUE`
    - Keep as `1`: line ~115 `stats.get("level", 1)` — level default
  - [x] 4.5: `server/core/xp.py`:
    - Lines ~102-107: 6 `.get("<ability>", 1)` -> `settings.DEFAULT_STAT_VALUE`
    - Keep as `1`: line ~93 `stats.get("level", 1)` — level default
    - Keep as `1`: line ~80 `stats.get("level", 1)` in `get_pending_level_ups` — level default
    - Keep as `0`: line ~43 `stats.get("charisma", 0)` in `apply_xp` — intentionally `0` (no XP bonus at base), NOT a candidate for `DEFAULT_STAT_VALUE`

- [x] Task 5: Replace hardcoded `"town_square"` (AC: #2)
  - [x] 5.1: `server/net/handlers/auth.py` line ~316: `"town_square"` -> `settings.DEFAULT_SPAWN_ROOM`
  - [x] 5.2: `server/app.py` line ~276: `"town_square"` -> `settings.DEFAULT_SPAWN_ROOM`

- [x] Task 6: Replace hardcoded stat cap and level-up choices (AC: #2)
  - [x] 6.1: `server/net/handlers/levelup.py`:
    - Line ~19: `_STAT_CAP = 10` -> remove constant, use `settings.STAT_CAP`
    - Line ~58: `[:3]` -> `[:settings.LEVEL_UP_STAT_CHOICES]`
  - [x] 6.2: `server/core/xp.py`:
    - Line ~109: `"stat_cap": 10` -> `settings.STAT_CAP`
    - Line ~100: `"choose_stats": 3` -> `settings.LEVEL_UP_STAT_CHOICES`

- [x] Task 7: Replace hardcoded combat hand size and min damage (AC: #2)
  - [x] 7.1: `server/combat/cards/card_hand.py`:
    - Line ~13: `hand_size: int = 5` -> `hand_size: int = settings.COMBAT_HAND_SIZE`
  - [x] 7.2: `server/core/effects/damage.py`:
    - Line ~39: `max(1, ...)` -> `max(settings.COMBAT_MIN_DAMAGE, ...)`
  - [x] 7.3: `server/combat/instance.py`:
    - Line ~368: `max(1, ...)` -> `max(settings.COMBAT_MIN_DAMAGE, ...)`

- [x] Task 8: Replace hardcoded NPC multipliers (AC: #2)
  - [x] 8.1: `server/room/objects/npc.py`:
    - Line ~74: `tmpl.get("hp_multiplier", 10)` -> `tmpl.get("hp_multiplier", settings.NPC_DEFAULT_HP_MULTIPLIER)`
    - Line ~79: `hit_dice * 2` -> `hit_dice * settings.NPC_ATTACK_DICE_MULTIPLIER`

- [x] Task 9: Replace hardcoded auth validation lengths (AC: #2)
  - [x] 9.1: `server/net/handlers/auth.py`:
    - Line ~194: `len(username) < 3` -> `len(username) < settings.MIN_USERNAME_LENGTH`
    - Line ~199: `len(password) < 6` -> `len(password) < settings.MIN_PASSWORD_LENGTH`

- [x] Task 10: Replace hardcoded trade cooldown and mob respawn fallback (AC: #3, #4)
  - [x] 10.1: `server/trade/manager.py`:
    - Line ~64: `time.time() + 5` -> `time.time() + settings.TRADE_COOLDOWN_SECONDS`
    - (settings import already exists at line 9 — no new import needed)
  - [x] 10.2: `server/app.py`:
    - Line ~258: `.get("respawn_seconds", 60)` -> `.get("respawn_seconds", settings.MOB_RESPAWN_SECONDS)`

- [x] Task 11: Add attack whitelist comment (AC: #5)
  - [x] 11.1: `server/player/repo.py`: add comment above `_STATS_WHITELIST` explaining attack exclusion:
    ```python
    # attack excluded -- derived from STR/INT at runtime, not independently persisted
    ```

- [x] Task 12: Verify integration test coverage (AC: #8)
  - [x] 12.1: Read `tests/test_integration.py` and verify it covers: register -> login -> move -> fight -> loot -> disconnect -> reconnect -> verify state
  - [x] 12.2: If gaps exist, add missing coverage (but do NOT change assertion values)

- [x] Task 13: Run `make test` and verify all 804+ tests pass (AC: #6)
  - [x] 13.1: No test assertion values should change — only production code references change
  - [x] 13.2: If any test directly constructs `Settings()` or patches config values, verify no breakage

## Dev Notes

### Key Principle: Import Pattern
All files that need `settings` should use:
```python
from server.core.config import settings
```
This import is already present in most handler files. Check before adding duplicates.

### What NOT to Change
- **Test assertion values**: Tests assert `hp == 100`, `attack == 10`, etc. These stay as literal values. Only production code references change.
- **`"level": 1` and `"xp": 0` defaults**: These are conceptual constants (level always starts at 1, XP at 0), not game balance parameters. Keep as literals.
- **Default mob stats `hp=50, max_hp=50, attack=10`**: These are per-mob defaults in `CombatInstance.__init__` (line ~30) and `movement.py` (line ~193). They are NPC fallback values, not player defaults. Leave all three values alone. Similarly, `combat/instance.py` line ~351 `.get("attack", 10)` is a mob attack fallback — leave as-is.
- **Fallback basic attack card damage `10` in movement.py line ~188**: This is a safety fallback for when no cards are loaded, not a game balance parameter. Leave as-is.
- **`.get("charisma", 0)` in xp.py line ~43**: Uses `0` intentionally (no XP bonus at base), NOT `1`. Do not replace with `DEFAULT_STAT_VALUE`.
- **`.get("strength/dexterity/intelligence", 0)` in damage.py and combat/instance.py**: Stat lookups in effect/mob-attack code use `0` as default (no bonus), NOT `1`. Do not replace.
- **`.get("wisdom", 0)` in heal.py line ~17**: Same pattern — stat lookup for heal bonus uses `0` default. Do not replace.
- **`_RARE_CHECK_INTERVAL = 60` in scheduler.py line ~24**: System timer for rare spawn check frequency, not a game balance parameter. Excluded from centralization — this is an internal scheduling interval, not player-facing balance.

### Existing `settings` Import Status
Files that already import `settings`:
- `server/core/config.py` (defines it)
- `server/net/handlers/auth.py` (uses `CON_HP_PER_POINT`)
- `server/net/handlers/levelup.py` (uses `CON_HP_PER_POINT`)
- `server/net/handlers/movement.py` (uses `COMBAT_STARTING_ENERGY`, `COMBAT_ENERGY_REGEN`)
- `server/net/handlers/query.py` (uses XP config values)
- `server/core/xp.py` (uses XP config values)
- `server/app.py` (uses `MOB_RESPAWN_SECONDS`, `DATABASE_URL`)
- `server/combat/instance.py` — NOTE: uses **local/lazy imports** inside methods (`add_participant`, `_advance_turn`, `_mob_attack_target`), NOT a top-level import. Follow the existing pattern when adding new `settings` references in this file.
- `server/core/effects/damage.py` (uses stat scaling)
- `server/trade/manager.py` (uses trade timeouts)

Files that will NEED the import added:
- `server/combat/cards/card_hand.py` (for `COMBAT_HAND_SIZE`)
- `server/room/objects/npc.py` (for NPC multipliers)

### Forward-Looking Settings (No Current Hardcoded Values)
- `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_PRE_PING`: Added to config for Story 14.7 (PostgreSQL readiness). `database.py` currently has NO pool config — `create_async_engine` uses defaults. These settings are consumed in 14.7, not 14.1.
- `ALEMBIC_DATABASE_URL`: Also for Story 14.7 — derived property, no current usage.

### Architecture Compliance
- ADR-14-6: Use section comments in flat `BaseSettings` — no nested models
- ADR-14-19: Validators for 6 critical settings only (not every setting)
- `ALEMBIC_DATABASE_URL` as `@property` — derived, not a separate env var
- Pydantic v2 `field_validator` API (not v1 `@validator`)

### Previous Story Pattern (13.1)
Story 13.1 established the pattern for large-scale refactors:
- Pure mechanical replacement across many files
- Zero assertion value changes in tests
- `make test` as the verification gate
- ~804 tests must all pass

### Project Structure Notes
- All server code under `server/` with domain-driven subdirectories
- Config module at `server/core/config.py` — singleton `settings = Settings()` at module level
- No circular import risk: `config.py` has no internal imports

### References
- [Source: _bmad-output/planning-artifacts/epics.md#Story 14.1]
- [Source: _bmad-output/planning-artifacts/architecture.md#Section 3.1]
- [Source: _bmad-output/project-context.md#Critical Implementation Rules]
- [Source: server/core/config.py] — current Settings class
- [Source: _bmad-output/implementation-artifacts/13-1-transaction-context-manager-and-repo-refactor.md] — previous story patterns

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Debug Log References

### Completion Notes List
- Added 16 new settings to `Settings` class organized by section (Player Defaults, Game Structure, Combat, NPC, Auth, Trade, Database, Migration)
- Added 6 `field_validator` guards for critical settings
- Replaced hardcoded `100` (base HP) across 5 files (12 occurrences)
- Replaced hardcoded `10` (default attack) in 3 files (5 player-facing occurrences); left mob defaults unchanged
- Replaced hardcoded `1` (default stat value) across 4 files (~30 occurrences); preserved `"level": 1` and `"xp": 0` as conceptual constants
- Replaced hardcoded `"town_square"` in 2 files (2 occurrences)
- Replaced `_STAT_CAP = 10` and `[:3]` in levelup.py with settings references
- Replaced `"stat_cap": 10` and `"choose_stats": 3` in xp.py
- Replaced hardcoded hand size `5` in card_hand.py
- Replaced hardcoded min damage `1` in damage.py and instance.py
- Replaced NPC hp_multiplier fallback `10` and attack dice multiplier `2` in npc.py
- Replaced auth validation lengths `3` and `6` in auth.py
- Replaced trade cooldown `5` in trade/manager.py
- Replaced mob respawn fallback `60` in app.py with `settings.MOB_RESPAWN_SECONDS`
- Added attack exclusion comment to `_STATS_WHITELIST` in player/repo.py
- Added `from server.core.config import settings` to card_hand.py and npc.py
- All 804 tests pass — zero assertion value changes

### File List
- server/core/config.py (modified — added 16 settings, 6 validators, section organization)
- server/net/handlers/auth.py (modified — replaced HP, attack, stat, spawn room, auth length hardcodes)
- server/net/handlers/levelup.py (modified — replaced stat cap, level-up choices, stat value, base HP)
- server/net/handlers/movement.py (modified — replaced HP and attack defaults)
- server/net/handlers/query.py (modified — replaced HP, attack, stat value defaults)
- server/app.py (modified — replaced HP default, spawn room, mob respawn fallback)
- server/core/xp.py (modified — replaced stat cap, level-up choices, stat values)
- server/combat/cards/card_hand.py (modified — replaced hand size default, added settings import)
- server/core/effects/damage.py (modified — replaced min damage)
- server/combat/instance.py (modified — replaced min damage in mob attack)
- server/room/objects/npc.py (modified — replaced HP multiplier and attack dice multiplier, added settings import)
- server/trade/manager.py (modified — replaced trade cooldown)
- server/player/repo.py (modified — added attack exclusion comment)
