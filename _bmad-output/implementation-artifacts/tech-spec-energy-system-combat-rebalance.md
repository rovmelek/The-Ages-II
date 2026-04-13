---
title: 'Epic 18: Energy System & Combat Rebalance'
slug: 'energy-system-combat-rebalance'
epic: 18
created: '2026-04-12'
status: 'ready-for-dev'
stepsCompleted: [1, 2, 3, 4]
tech_stack:
  - 'Python 3.11+'
  - 'FastAPI + WebSockets'
  - 'SQLAlchemy async + SQLite'
  - 'Pydantic'
  - 'pytest + pytest-asyncio'
files_to_modify:
  - 'server/core/config.py'
  - 'server/core/constants.py'
  - 'server/core/regen.py'
  - 'server/core/effects/restore_energy.py'
  - 'server/core/effects/registry.py'
  - 'server/player/service.py'
  - 'server/player/repo.py'
  - 'server/combat/instance.py'
  - 'server/combat/cards/card_def.py'
  - 'server/combat/cards/models.py'
  - 'server/combat/cards/card_repo.py'
  - 'server/combat/cards/card_hand.py'
  - 'server/combat/service.py'
  - 'server/net/handlers/levelup.py'
  - 'server/net/handlers/inventory.py'
  - 'server/net/handlers/combat.py'
  - 'server/net/outbound_schemas.py'
  - 'server/net/xp_notifications.py'
  - 'server/app.py'
  - 'data/cards/starter_cards.json'
  - 'data/items/base_items.json'
  - 'data/loot/loot_tables.json'
  - 'web-demo/js/game.js'
  - 'web-demo/index.html'
  - 'web-demo/css/style.css'
  - 'alembic/versions/'
code_patterns:
  - 'StrEnum for type constants (ADR-17-1)'
  - 'settings.* for all balance values — never hardcode'
  - 'Effect handler pattern: stateless async function in core/effects/, registered in registry'
  - '_STATS_WHITELIST in player/repo.py — new persisted stats must be added'
  - '@requires_auth decorator on all WebSocket handlers except login/register/reconnect'
  - 'Service layer: handlers thin routing, business logic in service modules'
test_patterns:
  - 'Dual-patch: when repo imported by both handler and service, patch both import paths'
  - 'Use make test (not bare pytest) to avoid collecting BMAD framework tests'
  - 'Test files in flat tests/ directory'
---

# Tech-Spec: Epic 18 — Energy System & Combat Rebalance

**Created:** 2026-04-12

## Overview

### Problem Statement

Energy is currently a transient combat-only resource (starts at 3, regens to full each cycle, never persisted). There is no persistent mana/energy economy — all cards cost the same generic "combat energy" regardless of whether they are physical attacks or magical spells. Additionally, the XP status bar shows confusing total XP values instead of progress within the current level, and the level-up system forces players to spread points across different stats (deduplication prevents stacking).

### Solution

Make energy a persistent player stat (like HP) derived from INT+WIS. Classify cards as physical (free) or magical (costs persistent energy). Replace flat combat energy regen with a formula based on INT+WIS. Add out-of-combat HP and energy regeneration, energy potions as a new consumable, fix XP bar display, and allow level-up point stacking. Design the energy system so it can extend to NPCs in a future epic (NPC card-based combat).

### Scope

**In Scope:**
- Persistent energy/max_energy stats (formula from INT+WIS, persisted to DB via `_STATS_WHITELIST`)
- Card type classification (`card_type` field: physical=free, magical=costs energy)
- Combat energy regen based on INT+WIS formula (replaces flat refill)
- Out-of-combat HP+energy regen (stops immediately on combat entry, resumes on exit)
- Energy potion (new item + `restore_energy` effect type)
- Level-up: allow stacking all 3 points on one attribute (remove deduplication)
- XP bar: show progress within current level instead of total XP
- Architecture doc updates (energy no longer combat-only transient)
- Web demo client updates (energy bar, level-up +/- UI)
- Loot table updates for energy potion drops
- Protocol spec updates (`outbound_schemas.py`, `make check-protocol`)

**Out of Scope:**
- NPC card-based combat (future Epic 19 — NPCs currently use fixed damage formula)
- New card designs or rebalancing card damage/cost values
- Godot client UI (web demo only for now)
- Changes to XP formulas or leveling thresholds
- NPC energy stats (deferred to Epic 19)

## Context for Development

### Codebase Patterns

- Player stats are a flat dict persisted as a JSON blob in SQLite — no schema migration needed for new fields, but `_STATS_WHITELIST` in `player/repo.py` must include new stat keys or they are silently dropped on save
- Energy is currently combat-only transient, initialized in `CombatInstance.add_participant()` via `setdefault("energy", COMBAT_STARTING_ENERGY)`
- Card effects determine physical vs magical via `subtype` field: `"physical"` scales with STR, `"fire"/"ice"/"arcane"` scale with INT, `"heal"` scales with WIS
- Effect handlers are stateless async functions registered in `EffectRegistry` — extend by creating handler file in `core/effects/`, registering in registry, referencing in JSON
- All game balance values must reference `settings.*` from `server/core/config.py` — never hardcode
- Out-of-combat regen uses standalone `server/core/regen.py` module (Scheduler remains focused on NPC lifecycle only)
- `StrEnum` pattern for type constants (ADR-17-1)
- Service layer architecture: handlers are thin routing, business logic in service modules
- `sync_combat_stats()` in `combat/service.py` cherry-picks specific stat keys (`hp`, `max_hp`) from combat back to entity — must add `energy`, `max_energy`
- `clean_player_combat_stats()` in `combat/service.py` actively pops `energy`/`max_energy` from entity stats (combat-only transient cleanup) — must stop popping these
- `PlayerStatsPayload` Pydantic model in `outbound_schemas.py` is the canonical outbound stats schema — all stats responses inherit from it
- Loot tables live in `data/loot/loot_tables.json`, separate from NPC templates in `data/npcs/base_npcs.json`
- `handle_use_item()` in `handlers/inventory.py` persists stats via `player_repo.update_stats()`, then sends `item_used` response — `stats_update` insertion point is after the `item_used` send

### Files to Reference

| File | Purpose |
| ---- | ------- |
| `server/core/config.py` | Settings — add energy/regen config, remove old combat energy settings |
| `server/core/constants.py` | EffectType enum — add RESTORE_ENERGY |
| `server/player/service.py` | `_default_stats()`, `build_stats_payload()`, `_reset_player_stats()` — add energy |
| `server/player/repo.py` | `_STATS_WHITELIST` — add energy/max_energy for DB persistence |
| `server/combat/instance.py` | `add_participant()`, `play_card()`, `_advance_turn()` — persistent energy, card_type check |
| `server/combat/cards/card_def.py` | CardDef dataclass — add `card_type` field |
| `server/combat/cards/models.py` | Card DB model — add `card_type` column |
| `server/combat/cards/card_repo.py` | Card repo — update upsert to include `card_type` column on existing rows |
| `data/cards/starter_cards.json` | Card definitions — add `card_type` to each card |
| `server/core/regen.py` | NEW — out-of-combat HP/energy regen loop (standalone, not in Scheduler) |
| `server/core/effects/registry.py` | Effect registry — register restore_energy handler |
| `server/core/effects/heal.py` | Heal handler — reference pattern for restore_energy |
| `server/net/handlers/levelup.py` | Level-up handler — remove dedup, add energy recalc |
| `data/items/base_items.json` | Item definitions — add energy_potion |
| `web-demo/js/game.js` | Client — XP fix, energy bar, level-up UI redesign |
| `web-demo/index.html` | Client — energy bar HTML |
| `web-demo/css/style.css` | Client — energy bar styling |
| `server/net/outbound_schemas.py` | Add `energy`/`max_energy` to stats payload schema, add `StatsUpdate` outbound schema |
| `server/net/xp_notifications.py` | `send_level_up_available` — update stat_effects descriptions for energy impact |
| `server/combat/service.py` | `sync_combat_stats` — verify energy sync on combat end |
| `server/net/handlers/inventory.py` | `handle_use_item` — send `stats_update` after effect resolution |
| `server/net/handlers/combat.py` | `_broadcast_combat_state` — sends combat state (verify energy fields) |
| `data/npcs/base_npcs.json` | NPC templates — reference loot table keys |
| `data/loot/loot_tables.json` | Loot tables — add energy_potion to 5 tables that include healing_potion (slime_loot, troll_loot, dragon_loot, common_chest, rare_chest) |
| `server/app.py` | Game class — start/stop regen loop lifecycle |
| `_bmad-output/planning-artifacts/architecture.md` | Architecture doc — update energy from transient to persistent |

### Technical Decisions

#### Core Architecture (ADRs)

- **ADR-18-1 (Energy Storage Model)**: Store `energy` and `max_energy` in player stats dict + `_STATS_WHITELIST`, matching the `hp`/`max_hp` pattern. Recalculate `max_energy` on level-up and stat changes. Chosen over computed-only (extra complexity) and separate table (breaks existing pattern).
- **ADR-18-2 (Card Type Classification)**: Add explicit `card_type` field (`"physical"`/`"magical"`) to CardDef and card JSON. Physical cards skip energy cost check. Requires Card DB model column addition + Alembic migration. Chosen over runtime inference (fragile for shields/hybrids) and cost=0 alone (conflates "free" with "physical", blocks future design space).
  - **Classification rubric**: A card is **physical** if ALL of its effects are either (a) damage with subtype `"physical"`, (b) `shield` (defensive gear, not magical barriers), or (c) DoT applied alongside a physical damage effect (e.g., poison coating on a blade — `poison_strike` has both `damage/physical` and `dot`). A card is **magical** if ANY of its effects involve (a) non-physical damage subtypes (`fire`, `ice`, `arcane`), (b) `heal` (magical restoration), (c) `draw` (magical card manipulation), or (d) standalone DoT without a physical damage effect in the same card (e.g., `venom_fang` — pure DoT only, no physical damage component).
  - **Classification**: physical=`slash, heavy_strike, poison_strike, iron_shield, steel_wall` (5 cards); magical=`fire_bolt, ice_shard, arcane_surge, flame_wave, fire_shield, heal_light, greater_heal, fortify, quick_draw, venom_fang` (10 cards).
  - **Rationale for edge cases**: `poison_strike` = physical (has `damage/physical` effect + DoT — physical blade delivers the poison). `venom_fang` = magical (standalone DoT only — no physical damage effect to serve as delivery mechanism; mechanically distinct from `poison_strike`). `iron_shield`/`steel_wall` = physical (armor/gear, not magical barriers). `fire_shield` = magical (has fire damage subtype). `fortify` = magical (contains heal effect). `quick_draw` = magical (card manipulation is a tactical/magical action).
- **ADR-18-3 (Out-of-Combat Regen Architecture)**: Standalone `server/core/regen.py` module with `start_regen_loop(game)` / `stop_regen_loop()` async functions. Skip players in combat (`entity.in_combat`). Skip players at full HP+energy. Persist to DB periodically (not every tick). Keeps Scheduler focused on NPC lifecycle (single-responsibility). Regen stops immediately on combat entry, resumes on exit — no cooldown delay. Chosen over per-player timers (lifecycle bugs) and event-driven (AFK players wouldn't heal).
- **ADR-18-6 (Existing Player Migration)**: Lazy migration via `_resolve_stats()` — add energy/max_energy to `_default_stats()`. Existing pattern already merges defaults under DB values on login. No Alembic data migration needed for player stats. **Critical:** In `_resolve_stats()`, in the `else` branch (returning player), add: `if "max_energy" not in db_stats: recalculate max_energy from actual stats["intelligence"] and stats["wisdom"] using the formula, set energy = max_energy`. Without this, existing players with leveled-up INT/WIS get wrong max_energy from defaults (25 instead of their actual value). **Known limitation:** Once `max_energy` is in DB, this recalc never fires again. If a future feature modifies INT/WIS without recalculating `max_energy`, the value becomes stale. Same latent risk exists for `max_hp`/CON. Both derived stats are only recalculated on level-up (ADR-18-9). Any future stat-modifying feature must handle this — not an Epic 18 concern.
- **ADR-18-7 (Card Model Migration)**: Alembic migration adds `card_type` column with `server_default=text("'physical'")` for cross-database compatibility (SQLite + PostgreSQL). JSON update + server restart populates values via `load_cards_from_json()`. **Verify**: `load_cards_from_json()` uses a manual get-then-update pattern (NOT SQL-level `on_conflict_do_update`). Task 8b adds `existing.card_type = data.get("card_type", "physical")` to the attribute assignment block. Without this, existing card rows keep `card_type = "physical"` (the server_default).
- **ADR-18-10 (Physical Card Cost)**: Set `cost: 0` in JSON for physical cards. `card_type` field carries the semantic classification. Server checks `card_type` to skip energy deduction; cost=0 provides defense in depth.
- **ADR-18-14 (Config Removal)**: Remove `COMBAT_STARTING_ENERGY` and `COMBAT_ENERGY_REGEN` immediately. Fix all references in the same implementation. No deprecation — solo project, dead config is confusing.
- **Energy system designed for future NPC extension** (Epic 19): same formulas, same card_type field will apply when NPCs gain card decks.

#### Formulas & Rates

- **ADR-18-4 (Max Energy Formula)**: `max_energy = DEFAULT_BASE_ENERGY + INT * INT_ENERGY_PER_POINT + WIS * WIS_ENERGY_PER_POINT` (defaults: BASE=20, INT_PER=3, WIS_PER=2). Weighted linear, mirrors `max_hp = BASE + CON * PER_POINT` pattern. INT weighted higher (raw magical power = larger pool).
- **ADR-18-5 (Combat Energy Regen)**: `floor(BASE_COMBAT_ENERGY_REGEN + (INT + WIS) * COMBAT_ENERGY_REGEN_FACTOR)` (defaults: BASE=2, FACTOR=0.5). Matches old default of 3 regen at starting stats. Both INT and WIS contribute to regen.
- **ADR-18-8 (Regen Rates)**: Out-of-combat regen: HP +3/tick, Energy +2/tick, every 10 seconds (`REGEN_INTERVAL_SECONDS=10`, `REGEN_HP_PER_TICK=3`, `REGEN_ENERGY_PER_TICK=2`). Persist to DB every 6th tick (60s) via tick counter (`REGEN_PERSIST_INTERVAL=6`). Balances recovery speed against potion value.
- **ADR-18-9 (Level-Up Energy Recalc)**: Mirror `max_hp` pattern exactly — recalculate `max_energy` from INT+WIS on level-up, then set `energy = max_energy` (full restore). Applies alongside existing full HP heal.
- **ADR-18-12 (Energy Potion Scaling)**: No stat scaling — flat 25 energy restored. Potions are physical items with fixed potency, unlike card-based heals which scale with WIS. Note: the restore value (25) lives in item JSON data (`data/items/base_items.json`), not in `config.py`. This follows the established pattern — item-specific values in data files, game-wide balance in config. Per-item values are rebalanceable by editing JSON without code changes.
- **ADR-18-13 (Regen During Disconnect Grace)**: Continue regen during the 120s disconnect grace period. Entity stays in memory anyway; regen stops naturally on session cleanup.
- **Stat effects config references**: `send_level_up_available` stat_effects descriptions must use `settings.INT_ENERGY_PER_POINT` and `settings.WIS_ENERGY_PER_POINT` (e.g., `f"+{settings.INT_ENERGY_PER_POINT} max energy per point"`) — not hardcoded numbers.

#### Combat Integration

- **Combat energy sync**: Energy flows through the same combat entry/exit sync as HP — `add_participant()` copies current energy from entity stats (no more `setdefault`), combat exit writes modified energy back. Note: `initiate_combat()` in `combat/service.py` uses `setdefault("shield", 0)` for the stats map — this is correct because shield is combat-only transient and may not exist in entity stats. Do NOT add a setdefault for energy here — energy is now always present in entity stats from `_resolve_stats()`. **Investigation findings** (4 functions must change in `server/combat/service.py`): (1) In `sync_combat_stats()`: add `"energy", "max_energy"` to the cherry-pick loop alongside `"hp", "max_hp"`. (2) In `clean_player_combat_stats()`: **remove** the `entity.stats.pop("energy", None)` and `entity.stats.pop("max_energy", None)` lines — energy is now persistent. **Keep** `entity.stats.pop("shield", None)` — shield remains combat-only transient. Add `"energy", "max_energy"` to the stat sync loop alongside `"hp", "max_hp"`. (3) In `cleanup_participant()`: add `"energy", "max_energy"` to the stat sync loop. (4) In `handle_flee_outcome()`: before calling `instance.remove_participant()` (which pops participant_stats), sync `"energy", "max_energy"` from `instance.participant_stats[entity_id]` back to `entity.stats`. Without this, fled players lose all energy changes from combat.
- **Combat energy regen display**: Include computed `energy_regen` value per participant in `get_state()`. Client displays "+N/cycle" next to energy bar during combat. Should-have priority.
- **DRY energy regen formula**: Extract `compute_energy_regen(stats: dict) -> int` as a module-level function in `server/combat/instance.py`, used by both `_advance_turn()` (actual regen) and `get_state()` (display value). Note: out-of-combat regen in `regen.py` uses flat `REGEN_ENERGY_PER_TICK` — different formula, no shared code needed.
- **Defensive energy floor**: Energy deduction in `play_card()` uses `max(0, stats["energy"] - card_cost)` to prevent negative energy.
- **Respawn energy reset**: `_reset_player_stats()` resets `energy` to `max_energy` alongside existing HP reset. Also pop `active_effects` (pre-existing issue: DoTs could persist through respawn if not cleared — fixing while we're modifying this function). **Flow ordering on death**: `clean_player_combat_stats()` runs first, then `_reset_player_stats()` runs. **Current behavior** (pre-Epic 18): `clean_player_combat_stats()` pops energy/max_energy then syncs hp/max_hp. **After Epic 18 fix** (Task 12): it syncs energy/max_energy (no more pop), then `_reset_player_stats()` overrides with full HP and full energy. The sync-then-reset ordering means the reset always wins — the player gets a fresh start regardless of combat-end state.
- **Regen persist batching**: Regen persist step must use a single `game.transaction()` for all player stat updates in the batch, not individual transactions per player. Matches existing batch pattern in `_run_rare_spawn_checks`.
- **Regen loop error isolation**: Wrap each player's `stats_update` send and stat modification in try/except. One bad connection must not stop regen for all players. Follows EventBus error-isolation pattern (`emit()` wraps each subscriber in try/except).
- **Regen loop in-place mutation**: The regen loop MUST modify `entity.stats` dict in-place (direct dict assignment, e.g., `entity.stats["hp"] += N`). Do NOT copy the dict or use a snapshot — `entity.stats` is a shared mutable object used by combat and other systems. In-place mutation ensures no stale data. The synchronous dict assignment (no `await` between read and write) prevents race conditions under asyncio cooperative scheduling.
- **Regen loop WebSocket check**: Before sending `stats_update`, check if the player has an active WebSocket via `connection_manager.get_websocket(entity_id)`. Skip the send (but still apply the stat mutation) if WebSocket is None. Use `connection_manager.send_to_player_seq()` for the send — consistent with other server-pushed messages (e.g., `xp_gained`). This avoids ~12 suppressed exceptions per disconnected player during the 120s grace period.
- **Loot table update**: Add `energy_potion` to NPC loot tables that currently drop `healing_potion`.

#### Client Display Rules (Web Demo — POC Only, No Game Logic)

- **Energy bar placement**: Below HP bar, above XP bar. Same width/structure as HP bar, blue/purple color scheme. In combat overlay, show energy for local player only; other participants show HP only.
- **Card type display**: Include `card_type` in `CardDef.to_dict()`. Client color-codes card cost: gray/white for physical (free), blue/purple for magical (energy cost).
- **Unaffordable card display**: Client reads `card.cost` and `card.card_type` from server-provided card data to visually dim unaffordable magical cards. **Display hint only** — server remains authoritative and rejects invalid plays. No game formulas client-side.
- **Level-up UI total impact**: Client displays server-provided `stat_effects` descriptions per stat. For multi-point allocation, client appends "×N" to the server description. Client does NOT compute actual stat effects — server descriptions are authoritative.
- **Level-up UI server authority**: Client reads `choose_stats` and `stat_cap` from `level_up_available` message to constrain +/- controls. Server validates all submissions independently. No game formulas client-side.
- **Regen visual feedback**: Pulse animation on HP/energy bars when `stats_update` changes values — reuse XP flash animation pattern.

#### Protocol & Messages

- **ADR-18-11 (Regen Client Notification)**: Regen loop pushes `stats_update` to each player after each regen tick. Skips players at full HP+energy. Chosen over polling (wasteful) and client-side prediction (drift risk).
- **ADR-18-15 (`stats_update` Scope)**: Defined broadly — used for regen ticks, out-of-combat item use, and any future out-of-combat stat change. Shape: `{"type": "stats_update", "hp": N, "max_hp": N, "energy": N, "max_energy": N}`.
- **Protocol: `StatsUpdate` schema**: Add `StatsUpdate` Pydantic model to `outbound_schemas.py` with fields: `type: str = "stats_update"`, `hp: int`, `max_hp: int`, `energy: int`, `max_energy: int`. Follow the existing codebase pattern (`str` with default, not `Literal`). Run `make check-protocol` to verify.
- **Out-of-combat item `stats_update`**: `handle_use_item()` (in `server/net/handlers/inventory.py`, after the `item_used` response send) must send `stats_update` when the item has stat-affecting effects. Guard: check if any effect result has `type` in `(EffectType.HEAL, EffectType.RESTORE_ENERGY)` before sending. This is precise — only sends when HP or energy actually changed. `shield` effects are combat-only and won't trigger outside combat.
- **`respawn` message update**: Add `energy` and `max_energy` fields (parity with `hp`/`max_hp`).
- **`level_up_complete` message update**: Add `new_max_energy`, `new_energy` fields (parity with `new_max_hp`/`new_hp`), and `stat_increases: {stat: points_applied}` for celebration messages with stacking. **Keep** existing `stat_changes: {stat: new_absolute_value}` — the client uses it to update stat displays. The two fields serve different purposes: `stat_changes` = absolute values for state update, `stat_increases` = deltas for display messages (e.g., "STR+3").
- **Stat effects energy descriptions**: Update `send_level_up_available` stat_effects: `"intelligence": "+N magic dmg, +N max energy per point"`, `"wisdom": "+N healing, +N max energy per point"` (using settings values).

### Do NOT Change (Scope Guard)

- **`_mob_attack_target()`** — NPC attacks remain fixed damage formula. NPC card-based combat is deferred to Epic 19.
- **`CombatInstance.use_item()` energy handling** — items remain free in combat (no energy cost). Only `play_card()` checks energy.
- **`NpcEntity`** — do NOT add energy/max_energy to NPCs. Deferred to Epic 19.
- **Card damage values or costs** — do NOT rebalance existing card stats. Only change: physical cards get `cost: 0` and `card_type: "physical"`. Magical cards keep existing costs and get `card_type: "magical"`.
- **`server/room/npc.py`** — NPC entity, template loading, and `_derive_stats_from_hit_dice()` are unchanged. Do NOT add energy to NPC stats derivation.
- **XP formulas or leveling thresholds** — no changes to `XP_LEVEL_THRESHOLD_MULTIPLIER` or XP curve.
- **Chat system** — no modifications to chat, markdown support, or `CHAT_FORMAT`.

### Protocol Change Summary

| Message | Change | Fields |
|---------|--------|--------|
| `stats_update` | **New outbound** | `type`, `hp`, `max_hp`, `energy`, `max_energy` |
| `login_success.stats` | **Modified** — add fields | `energy`, `max_energy` |
| `stats_result.stats` | **Modified** — inherits from `PlayerStatsPayload` | `energy`, `max_energy` (automatic via inheritance) |
| `combat_turn.participants[]` | **Modified** — add field + semantic change | `energy_regen` (new). Existing `energy`/`max_energy` fields change meaning: previously transient (reset each combat), now persistent (carried across combats). Wire format unchanged. |
| `combat_start.participants[]` | **Modified** — same as combat_turn | Same `get_state()` output — inherits `energy_regen` field and semantic change. |
| `combat_update.participants[]` | **Modified** — same as combat_turn | Same `get_state()` output — inherits `energy_regen` field and semantic change. |
| `level_up_complete` | **Modified** — add fields | `new_max_energy`, `new_energy`, `stat_increases: {stat: points_applied}` |
| `respawn` | **Modified** — add fields | `energy`, `max_energy` |
| `level_up_available.stat_effects` | **Modified** — updated content | INT/WIS descriptions include energy impact |
| `item_used.effect_results` | **New effect result type** | `restore_energy`: `{type, value, target_energy}` |
| `combat_turn.hands[]` card shape | **Modified** — add field | `card_type` added via `CardDef.to_dict()` |

## Implementation Plan

### Tasks

#### Phase 1: Foundation (Config, Constants, Player Stats)

- [ ] Task 1: Add energy config settings and remove old combat energy settings
  - File: `server/core/config.py`
  - Action: Add `DEFAULT_BASE_ENERGY=20`, `INT_ENERGY_PER_POINT=3`, `WIS_ENERGY_PER_POINT=2`, `BASE_COMBAT_ENERGY_REGEN=2`, `COMBAT_ENERGY_REGEN_FACTOR=0.5`, `REGEN_INTERVAL_SECONDS=10`, `REGEN_HP_PER_TICK=3`, `REGEN_ENERGY_PER_TICK=2`, `REGEN_PERSIST_INTERVAL=6`. Remove `COMBAT_STARTING_ENERGY` and `COMBAT_ENERGY_REGEN`. Add validators for new settings where appropriate.
  - Notes: ADR-18-14 — remove immediately, fix all references.

- [ ] Task 2: Add `RESTORE_ENERGY` to EffectType enum
  - File: `server/core/constants.py`
  - Action: Add `RESTORE_ENERGY = "restore_energy"` to `EffectType` StrEnum.

- [ ] Task 3: Add energy/max_energy to player stats whitelist
  - File: `server/player/repo.py`
  - Action: Add `"energy"`, `"max_energy"` to `_STATS_WHITELIST` set. Update the comment above the set to explain: `attack` is excluded (always DEFAULT_ATTACK, never modified); `energy`/`max_energy` are included (consumable resource like HP, must persist across sessions); `shield`/`active_effects` remain excluded (combat-only transient).

- [ ] Task 4: Add energy to player default stats, resolve_stats, build_stats_payload, and respawn
  - File: `server/player/service.py`
  - Action:
    - `_default_stats()`: Add `"energy": settings.DEFAULT_BASE_ENERGY` and `"max_energy": settings.DEFAULT_BASE_ENERGY` as fallback defaults (value 20). These are ONLY used as merge bases for `{**_default_stats(), **db_stats}` in the returning-player path — for new players and migration, `_resolve_stats()` immediately overwrites them with the actual derived values computed from INT+WIS. This matches how `hp`/`max_hp` use `DEFAULT_BASE_HP` as defaults but get overwritten by the CON-based formula. Add a code comment: `# energy/max_energy: fallback defaults only — _resolve_stats() derives actual values from INT+WIS`.
    - `_resolve_stats()`: In `if not db_stats` (first-time) branch, compute `max_energy` from INT+WIS formula (same location where `max_hp` is computed from CON), set `energy = max_energy`. In `else` (returning player) branch, add: `if "max_energy" not in db_stats: recalculate max_energy from actual stats["intelligence"] and stats["wisdom"] using the formula, set energy = max_energy` (ADR-18-6). This keeps `max_hp` and `max_energy` initialization symmetric — both derived in `_resolve_stats()`, not in `_default_stats()`.
    - `build_stats_payload()`: Add `"energy": stats.get("energy", settings.DEFAULT_BASE_ENERGY)` and `"max_energy": stats.get("max_energy", settings.DEFAULT_BASE_ENERGY)` fields. Use `DEFAULT_BASE_ENERGY` (20) as fallback, matching the `hp`/`DEFAULT_BASE_HP` pattern.
    - `_reset_player_stats()`: Add `entity.stats["energy"] = entity.stats.get("max_energy", settings.DEFAULT_BASE_ENERGY)`. Also add `entity.stats.pop("active_effects", None)` to clear DoTs on respawn (pre-existing bug fix).
  - Notes: This is the foundation — all other tasks depend on energy being in the stats dict.

- [ ] Task 5: Add energy/max_energy to outbound stats schemas
  - File: `server/net/outbound_schemas.py`
  - Action: Update the file docstring count (currently says "38" but actual count is 40; after adding `StatsUpdateMessage` it'll be 41). Add `energy: int` and `max_energy: int` fields to `PlayerStatsPayload`. Add new `StatsUpdateMessage` Pydantic model with `type: str = "stats_update"`, `hp: int`, `max_hp: int`, `energy: int`, `max_energy: int`. Add `energy` and `max_energy` to respawn-related schemas. Add `new_max_energy: int | None`, `new_energy: int | None`, `stat_increases: dict[str, int] | None` to level_up_complete schema. **Cross-ref**: `stat_increases` shape must match Task 24's implementation — `dict[str, int]` mapping stat name → points actually applied (e.g., `{"strength": 3}`). Add `energy_regen: int` to `CombatParticipantPayload`. Add `card_type: str` to `CardPayload` (confirmed: `CardPayload` exists as a Pydantic model in `outbound_schemas.py` and currently lacks `card_type`). Cross-ref Task 8 which adds `card_type` to `CardDef.to_dict()` — both must match.

- [ ] Task 6: Update stat_effects descriptions for energy impact
  - File: `server/net/xp_notifications.py`
  - Action: Update `send_level_up_available()` stat_effects dict. The function already defines `ssf = settings.STAT_SCALING_FACTOR`. Update: `"intelligence": f"+{ssf:g} magic dmg, +{settings.INT_ENERGY_PER_POINT} max energy per point"`, `"wisdom": f"+{ssf:g} healing, +{settings.WIS_ENERGY_PER_POINT} max energy per point"`. All values from settings, not hardcoded.

- [ ] Task 7: Fix all tests broken by foundation changes
  - Files: `tests/test_login.py`, `tests/test_outbound_schemas.py`, `tests/test_stats_persistence.py`, `tests/test_combat_effects.py`, `tests/test_stat_combat.py`
  - Action: Update `_make_player_stats()` helpers to include `energy`/`max_energy`. Update schema assertions for new fields. Update login response assertions. Verify `make test` passes.

#### Phase 2: Card Type System

- [ ] Task 8: Add card_type to CardDef and Card model
  - Files: `server/combat/cards/card_def.py`, `server/combat/cards/models.py`
  - Action: Add `card_type: str = "physical"` field to `CardDef` dataclass. Update `from_db()` and `to_dict()` to include `card_type`. Add `card_type: Mapped[str] = mapped_column(String(30), server_default=text("'physical'"))` to Card model.

- [ ] Task 8b: Update card repo upsert to include card_type
  - File: `server/combat/cards/card_repo.py`
  - Action: In `load_cards_from_json()`, add `existing.card_type = data.get("card_type", "physical")` to the attribute assignment block where existing card rows are updated. The function uses a manual `get_by_key()` + attribute assignment pattern (NOT SQL-level `on_conflict_do_update`). Without this line, existing rows keep `card_type = "physical"` (the server_default) and magical cards won't be classified correctly.

- [ ] Task 9: Create Alembic migration for card_type column
  - File: `alembic/versions/` (new migration file)
  - Action: `alembic revision --autogenerate -m "add card_type to cards"`. Verify migration uses `server_default=text("'physical'")` for cross-DB compatibility. Run `make db-migrate`.

- [ ] Task 10: Update card JSON data with card_type and costs
  - File: `data/cards/starter_cards.json`
  - Action: Add `"card_type": "physical"` and set `"cost": 0` for: `slash`, `heavy_strike`, `poison_strike`, `iron_shield`, `steel_wall` (5 cards). Add `"card_type": "magical"` for: `fire_bolt`, `ice_shard`, `arcane_surge`, `flame_wave`, `fire_shield`, `heal_light`, `greater_heal`, `fortify`, `quick_draw`, `venom_fang` (10 cards, keep existing costs). See ADR-18-2 classification rubric for rationale.

- [ ] Task 11: Update combat instance for card_type energy check
  - File: `server/combat/instance.py`
  - Action:
    - `add_participant()`: Remove `setdefault("energy", ...)` and `setdefault("max_energy", ...)` — energy now comes from player stats.
    - `play_card()`: Change energy check to only apply for non-physical cards. **Sequencing**: the card_type check must happen BEFORE `hand.play_card(card_key)` (which removes the card from hand). **Required**: add `get_card_def(card_key) -> CardDef` method to `CardHand` in `server/combat/cards/card_hand.py` (follows the `get_card_cost()` pattern — lookup without removal). `get_card_cost()` can be kept for backward compatibility or removed in favor of `get_card_def().cost` — developer's choice, both are equivalent. The `play_card()` pseudocode below uses `get_card_def()` to replace the `get_card_cost()` call. Pseudocode: `card_def = hand.get_card_def(card_key); if card_def.card_type != "physical": card_cost = card_def.cost; if stats.get("energy", 0) < card_cost: raise ValueError("Not enough energy")`. Then `played = hand.play_card(card_key)` and `if card_def.card_type != "physical": stats["energy"] = max(0, stats["energy"] - card_cost)`.
    - `_advance_turn()`: Replace flat regen with formula: extract `compute_energy_regen(stats)` module-level function, use `floor(settings.BASE_COMBAT_ENERGY_REGEN + (stats.get("intelligence", 0) + stats.get("wisdom", 0)) * settings.COMBAT_ENERGY_REGEN_FACTOR)`, cap at `max_energy`.
    - `get_state()`: Add `energy_regen` per participant using `compute_energy_regen()`.
  - Notes: Remove references to `COMBAT_STARTING_ENERGY` and `COMBAT_ENERGY_REGEN`.

- [ ] Task 12: Update combat service for energy sync
  - File: `server/combat/service.py`
  - Action:
    - `sync_combat_stats()`: Add `"energy", "max_energy"` to the cherry-pick loop.
    - `clean_player_combat_stats()`: Remove `entity.stats.pop("energy", None)` and `entity.stats.pop("max_energy", None)`. Add `"energy", "max_energy"` to the stat sync loop.
    - `cleanup_participant()`: Add `"energy", "max_energy"` to the stat sync loop.
    - `handle_flee_outcome()`: Before `instance.remove_participant()` (which pops participant_stats), sync `"hp", "max_hp", "energy", "max_energy"` from `instance.participant_stats[entity_id]` to `entity.stats`. **Pre-existing bug**: the current code never syncs HP back on flee either — fled players lose ALL combat stat changes (HP damage, heals, etc.). Fix HP and energy sync together. Create ISS-033 doc before implementing (see Notes section).

- [ ] Task 13: Fix all tests broken by card type and combat changes
  - Files: `tests/test_combat.py`, `tests/test_combat_resolution.py`, `tests/test_sample_data.py`
  - Action: Update energy init tests (energy now from stats, not COMBAT_STARTING_ENERGY). Update energy deduct tests to use non-physical cards. Update regen formula tests. Update card data assertions for card_type field. Verify `make test` passes.

#### Phase 3: Energy Potion & Restore Energy Effect

- [ ] Task 14: Create restore_energy effect handler
  - File: `server/core/effects/restore_energy.py` (NEW)
  - Action: Create handler following `heal.py` pattern. Flat restore (no stat scaling per ADR-18-12): `target["energy"] = min(target.get("energy", 0) + effect.get("value", 0), target.get("max_energy", 0))`. Return `{"type": EffectType.RESTORE_ENERGY, "value": actual, "target_energy": target["energy"]}`.

- [ ] Task 15: Register restore_energy in effect registry
  - File: `server/core/effects/registry.py`
  - Action: Import `handle_restore_energy`, register `EffectType.RESTORE_ENERGY` handler in `create_default_registry()`.

- [ ] Task 16: Add restore_energy to self-targeting in combat
  - File: `server/combat/instance.py`
  - Action: Add `EffectType.RESTORE_ENERGY` to self-targeting group in `_resolve_effect_targets()` alongside `HEAL`, `SHIELD`, `DRAW`. Note: this only affects in-combat item use. Out-of-combat item use in `handle_use_item()` already passes `player_stats` as both source and target (self-targeting by construction) and does NOT go through `_resolve_effect_targets()`. Both paths work correctly for `restore_energy`.

- [ ] Task 17: Add energy potion item and update loot tables
  - Files: `data/items/base_items.json`, `data/loot/loot_tables.json`
  - Action: Add `energy_potion` item: `{"item_key": "energy_potion", "name": "Energy Potion", "category": "consumable", "stackable": true, "charges": 3, "effects": [{"type": "restore_energy", "value": 25}], "usable_in_combat": true, "usable_outside_combat": true, "description": "Restores 25 energy. 3 uses."}`. Add `energy_potion` entries to loot tables, mirroring `healing_potion` quantities in each table: `slime_loot` (qty 1), `troll_loot` (qty 1), `dragon_loot` (qty 2), `common_chest` (qty 1), `rare_chest` (qty 3).

- [ ] Task 18: Add stats_update after out-of-combat item use
  - File: `server/net/handlers/inventory.py`
  - Action: In `handle_use_item()`, after the `item_used` response send, check if any effect result has `type` in `(EffectType.HEAL, EffectType.RESTORE_ENERGY)`. If so, send `{"type": "stats_update", "hp": entity.stats["hp"], "max_hp": entity.stats["max_hp"], "energy": entity.stats.get("energy", 0), "max_energy": entity.stats.get("max_energy", 0)}` to the player. This matches the precise guard in the Protocol & Messages section.

- [ ] Task 19: Add energy/max_energy to respawn message
  - File: `server/player/service.py`
  - Action: In `respawn_player()`, add `"energy": entity.stats.get("energy", 0)` and `"max_energy": entity.stats.get("max_energy", 0)` to the respawn response dict.

- [ ] Task 20: Fix tests for effects, items, and loot
  - Files: `tests/test_effects.py`, `tests/test_item_usage.py`, `tests/test_loot.py`
  - Action: Add `test_restore_energy_effect` tests (happy path, cap at max, zero energy). Update loot table assertion counts. Add energy potion usage tests. Verify `make test` passes.

#### Phase 4: Out-of-Combat Regen

- [ ] Task 21: Create regen loop module
  - File: `server/core/regen.py` (NEW)
  - Action: Create `start_regen_loop(game)` and `stop_regen_loop()` async functions. Background loop: every `REGEN_INTERVAL_SECONDS`, iterate `game.player_manager.all_sessions()`. Skip if `entity.in_combat` or (HP == max_hp AND energy == max_energy). Add `REGEN_HP_PER_TICK` to HP (cap at max_hp), `REGEN_ENERGY_PER_TICK` to energy (cap at max_energy). Send `stats_update` message to player. Every `REGEN_PERSIST_INTERVAL` ticks, batch-persist all modified player stats in a single `game.transaction()`. Wrap each player's tick in try/except for error isolation.

- [ ] Task 22: Wire regen loop into Game lifecycle
  - File: `server/app.py`
  - Action: Import `start_regen_loop`, `stop_regen_loop` from `server.core.regen`. Call `await start_regen_loop(self)` after `self.scheduler.start(self)` in `startup()`. Call `await stop_regen_loop()` after `self.scheduler.stop()` in `shutdown()`.

- [ ] Task 23: Add regen loop tests
  - File: `tests/test_regen.py` (NEW)
  - Action: Test regen ticks HP and energy. Test skips in-combat players. Test skips full HP+energy players. Test persist fires every Nth tick. Test error isolation (bad WebSocket doesn't crash loop). Test regen stops on `stop_regen_loop()`.

#### Phase 5: Level-Up Stacking

- [ ] Task 24: Remove dedup and add energy recalc in level-up handler
  - File: `server/net/handlers/levelup.py`
  - Action: Replace `unique_stats = list(dict.fromkeys(chosen_stats))[:settings.LEVEL_UP_STAT_CHOICES]` with `chosen = chosen_stats[:settings.LEVEL_UP_STAT_CHOICES]`. Update variable name through rest of function. Keep empty-check (`if not chosen`). Add `stat_increases` tracking dict in the application loop. After level increment: add `max_energy` recalc from INT+WIS, set `energy = max_energy`. Add `stat_increases` and `new_max_energy`/`new_energy` to response dict.

- [ ] Task 25: Fix level-up tests
  - File: `tests/test_level_up.py`
  - Action: Rewrite dedup test → stacking test (e.g., `["strength", "strength", "strength"]` → STR+3). Add test for stacking respects cap (STR=9, send 3x → only +1 applied, 2 skipped). Add test for `stat_increases` in response. Add test for `max_energy`/`energy` recalc on level-up. Verify `make test` passes.

#### Phase 6: XP Bar Fix

- [ ] Task 26: Fix XP bar display text
  - File: `web-demo/js/game.js`
  - Action: In `updateStatsPanel()`, change `$xpText.textContent = \`${currentXp}/${xpNext}\`` to `$xpText.textContent = \`${xpInLevel} / ${xpNeeded}\``. Variables `xpInLevel` and `xpNeeded` are already computed.

#### Phase 7: Web Demo Client

- [ ] Task 27: Add energy bar to HUD
  - Files: `web-demo/index.html`, `web-demo/css/style.css`, `web-demo/js/game.js`
  - Action: Add energy bar HTML below HP bar, above XP bar (mirror HP bar structure). Add blue/purple CSS styling. In `updateStatsPanel()`, add energy bar update reading `stats.energy` / `stats.max_energy`. Add pulse animation on `stats_update` (reuse XP flash pattern). Add `handleStatsUpdate()` message handler for `stats_update` messages.

- [ ] Task 28: Add energy display in combat UI
  - File: `web-demo/js/game.js`
  - Action: Show energy bar for local player in combat overlay reading from combat participant data. Display "+N/cycle" using `energy_regen` from combat state. Dim/gray unaffordable magical cards by reading `card.card_type` and comparing `card.cost > currentEnergy`.

- [ ] Task 29: Redesign level-up modal with +/- controls
  - File: `web-demo/js/game.js`
  - Action: Replace `toggleLevelUpStat()` toggle buttons with +/- stepper controls. Track `levelUpAllocations` as `{stat: count}` object. Total across all stats capped at `choose_stats`. Per-stat capped at `stat_cap - current_value`. Display server `stat_effects` description with "×N" suffix for multi-point. On confirm, send flat array with repeats.
  - Notes: Client reads `choose_stats`, `stat_cap`, `stat_effects` from server `level_up_available` message. No game logic.

- [ ] Task 30: Update level-up complete handler
  - File: `web-demo/js/game.js`
  - Action: In `handleLevelUpComplete()`, update `stats.energy` and `stats.max_energy` from response. Update celebration message to use `stat_increases` for correct "+N" per stat (not hardcoded "+1").

#### Phase 8: Protocol & Documentation

- [ ] Task 31: Bump protocol version, run protocol check, update architecture docs
  - Files: `server/core/constants.py`, `_bmad-output/planning-artifacts/architecture.md`
  - Action: Bump `PROTOCOL_VERSION` from `"1.0"` to `"1.1"` in `server/core/constants.py` (new messages + modified message shapes = minor version bump). Run `make check-protocol`. Update architecture doc: Section 9.1 — energy is now persistent (remove from "combat-only transient" list). Add energy formula, regen system, card_type to relevant sections. Update project-context.md if needed.

- [ ] Task 32: Final test pass
  - Action: Run `make test`. Verify all tests pass (old + new). Check test count has increased. Run `make check-protocol` to verify protocol spec consistency.

### Acceptance Criteria

#### Persistent Energy

- [ ] AC 1: Given a new player registers, when they log in, then their stats include `energy` and `max_energy` computed from `DEFAULT_BASE_ENERGY + INT * INT_ENERGY_PER_POINT + WIS * WIS_ENERGY_PER_POINT`.
- [ ] AC 2: Given an existing player (pre-Epic 18) logs in with no energy in DB, when `_resolve_stats()` runs, then `max_energy` is recalculated from their actual INT and WIS values (not defaults), and `energy` is set to `max_energy`.
- [ ] AC 3: Given a player's energy/max_energy are modified, when they disconnect and reconnect, then the values are preserved (survive DB round-trip via `_STATS_WHITELIST`).

#### Card Type & Energy Cost

- [ ] AC 4: Given a player plays a physical card (`card_type: "physical"`), when the card resolves, then no energy is deducted.
- [ ] AC 5: Given a player plays a magical card (`card_type: "magical"`) with sufficient energy, when the card resolves, then energy is deducted by the card's cost.
- [ ] AC 6: Given a player plays a magical card with insufficient energy, when they attempt to play it, then the server returns "Not enough energy" error.
- [ ] AC 6b: Given a `CardHand` with cards, when `get_card_def(card_key)` is called, then the `CardDef` is returned without removing the card from the hand (lookup only, no side effects).
- [ ] AC 7: Given all 15 starter cards, when their data is loaded, then 5 are `card_type: "physical"` with `cost: 0` (`slash`, `heavy_strike`, `poison_strike`, `iron_shield`, `steel_wall`) and 10 are `card_type: "magical"` with original costs (`venom_fang` is magical — standalone DoT without physical damage component).

#### Combat Energy Regen

- [ ] AC 8: Given a combat cycle completes, when energy regenerates, then each alive participant gains `floor(BASE_COMBAT_ENERGY_REGEN + (INT + WIS) * COMBAT_ENERGY_REGEN_FACTOR)` energy, capped at `max_energy`.
- [ ] AC 9: Given combat state is requested, when `get_state()` returns, then each participant includes `energy_regen` value.

#### Combat Sync

- [ ] AC 10: Given a player is in combat and energy changes, when combat ends, then the modified energy value is synced back to the player entity (not popped as transient).
- [ ] AC 10b: Given a player flees combat with modified energy, when `handle_flee_outcome()` runs, then energy is synced from combat participant stats to entity stats before the participant is removed. Energy value is preserved after flee.
- [ ] AC 11: Given a player dies in combat and respawns, when `_reset_player_stats()` runs, then energy is reset to max_energy alongside HP, and `active_effects` are cleared.

#### Out-of-Combat Regen

- [ ] AC 12: Given a player is not in combat and has HP < max_hp or energy < max_energy, when the regen loop ticks, then HP increases by `REGEN_HP_PER_TICK` and energy by `REGEN_ENERGY_PER_TICK` (capped at max).
- [ ] AC 13: Given a player is in combat, when the regen loop ticks, then they are skipped (no regen applied).
- [ ] AC 14: Given a player is at full HP and full energy, when the regen loop ticks, then they are skipped (no message sent).
- [ ] AC 15: Given the regen loop ticks, when stats change, then a `stats_update` message is sent to the player with current HP/max_hp/energy/max_energy.
- [ ] AC 16: Given one player's WebSocket fails during regen, when the regen loop continues, then other players still receive their regen (error isolation).
- [ ] AC 16b: Given the server starts up, when `Game.startup()` completes, then the regen loop is running (started after scheduler). Given the server shuts down, when `Game.shutdown()` runs, then the regen loop is stopped cleanly.

#### Energy Potion

- [ ] AC 17: Given a player has an energy potion and low energy, when they use it outside combat, then energy is restored by 25 (capped at max_energy), a `stats_update` message is sent immediately, and one charge is consumed.
- [ ] AC 18: Given a player uses an energy potion in combat, when the item resolves, then energy is restored and the action costs their turn (same as healing potion).
- [ ] AC 19: Given energy potions are added to loot tables, when loot is generated from a table that includes `healing_potion`, then `energy_potion` also appears in the loot results.

#### Level-Up Stacking

- [ ] AC 20: Given a player levels up and sends `["strength", "strength", "strength"]`, when the server processes it, then STR increases by 3 (not deduped to 1).
- [ ] AC 21: Given a player sends `["strength", "strength", "strength"]` and STR is at 9, when processed, then STR increases by 1 (to cap 10) and 2 points are skipped (reported in `skipped_at_cap`).
- [ ] AC 22: Given a level-up completes, when the response is sent, then it includes `stat_increases` showing only **applied** points (e.g., `{"strength": 1}` if STR was at 9 and only 1 of 3 applied), `new_max_energy`, and `new_energy`. `skipped_at_cap` may contain repeated stat names (e.g., `["strength", "strength"]` for 2 skipped attempts).
- [ ] AC 23: Given a player puts points into INT or WIS, when level-up completes, then `max_energy` is recalculated and `energy` is set to new `max_energy`.

#### XP Bar

- [ ] AC 24: Given a level 2 player with 1500 XP, when the XP bar renders, then it displays "500 / 1000" (progress within level) not "1500/2000" (total).

#### Client Display (Web Demo)

- [ ] AC 25: Given a player is logged in, when the HUD renders, then an energy bar is visible below HP bar with blue/purple color showing current/max energy.
- [ ] AC 26: Given a player is in combat, when cards render, then physical cards show cost in gray/white and magical cards in blue/purple. Unaffordable magical cards are visually dimmed.
- [ ] AC 27: Given the level-up modal opens, when a player allocates points, then +/- controls allow stacking multiple points on one stat, total capped at `choose_stats` from server.

#### Protocol

- [ ] AC 28: Given the implementation is complete, when `make check-protocol` runs, then it passes with no errors.

## Additional Context

### Dependencies

None — builds on existing combat, stats, and effect systems.

### Test Files Impacted

**Will definitely need updates:**

| File | Reason |
|------|--------|
| `tests/test_combat.py` | 7 energy tests: init, state, deduct, not-enough, regen, pass-no-cost, item-no-cost |
| `tests/test_effects.py` | New `restore_energy` effect handler tests needed |
| `tests/test_item_usage.py` | `_make_player_stats()` helper lacks energy; energy_potion tests needed |
| `tests/test_loot.py` | 5 loot table tests assert exact item counts — adding energy_potion breaks assertions |
| `tests/test_level_up.py` | Dedup behavior tests must become stacking tests; energy recalc on level-up |
| `tests/test_outbound_schemas.py` | `PlayerStatsPayload` gains energy/max_energy fields |

**Likely need updates:**

| File | Reason |
|------|--------|
| `tests/test_combat_effects.py` | `_make_player_stats()` helper lacks energy |
| `tests/test_stat_combat.py` | `_make_player_stats()` helper lacks energy |
| `tests/test_combat_resolution.py` | Combat end/resolution — energy sync changes |
| `tests/test_login.py` | Login response stats payload gains energy fields |
| `tests/test_sample_data.py` | Validates data files — new item/loot entries |
| `tests/test_stats_persistence.py` | Energy must survive save/load round-trip |

### Testing Strategy

**Unit Tests (new):**
- `test_restore_energy_effect` — happy path, cap at max, zero energy start
- `test_compute_energy_regen` — formula with various INT/WIS values
- `test_get_card_def` — lookup returns CardDef without removing from hand, raises ValueError for missing card
- `test_card_type_energy_check` — physical free, magical deducts, not enough energy
- `test_level_up_stacking` — 3 points same stat, mixed, cap behavior
- `test_level_up_energy_recalc` — max_energy updated, energy reset to max
- `test_regen_loop` — tick applies regen, skips combat, skips full, error isolation, persist batching
- `test_stats_update_message` — sent on regen tick, sent on item use
- `test_energy_persistence` — save/load round-trip via whitelist

**Existing test updates:**
- Update `_make_player_stats()` helpers in test_combat_effects, test_stat_combat, test_item_usage to include energy/max_energy
- Update test_combat.py energy tests for persistent energy (no setdefault), formula regen, card_type-conditional cost
- Update test_loot.py assertions for energy_potion in loot tables (both item counts AND verify `energy_potion` appears alongside `healing_potion` in the same loot tables)
- Update test_outbound_schemas.py for PlayerStatsPayload energy fields
- Update test_level_up.py — replace dedup test with stacking test, add stat_increases assertion
- Update test_login.py — login response includes energy stats
- Update test_combat_resolution.py — energy synced on combat end (not popped)

**Integration/manual testing:**
- Start server, login → verify energy bar visible with correct max
- Enter combat → play physical card (free) → play magical card (energy deducted) → verify dimmed cards when low energy
- Wait out of combat → observe HP and energy bars filling (regen)
- Use energy potion out of combat → energy bar updates immediately
- Use energy potion in combat → energy restored, turn consumed
- Level up → put all 3 points in STR → verify STR+3 and celebration message
- Level up with INT points → verify max_energy increases and energy resets to new max
- XP bar → verify shows progress within level
- Run `make test` — all tests pass
- Run `make check-protocol` — passes

### Notes

- Energy is rarely a constraint at level 1 with low-cost cards (25 max energy, cards cost 1-3). This is acceptable as an onboarding ramp — the constraint becomes real with harder mobs and sustained casting. Flag for future balance pass if playtesting shows energy is never limiting.
- **Balance observations from first principles analysis**: (1) Physical builds have no resource management decisions — always play strongest card. Heavy_strike at cost 0 with 25 base damage may be overpowered compared to magical equivalents that cost energy. (2) INT is double-loaded for casters (more damage + bigger energy pool), while physical stats have clearer tradeoffs (STR=damage vs CON=survivability). (3) Energy potion with `charges: 3` and `value: 25` provides 75 total energy restoration — three full refills at starting max_energy (25). This trivializes energy for casters at low levels while being useless for physical builds. These are all acceptable for MVP — the settings-based formulas and data-driven item values allow rebalancing without code changes. Flag for playtesting.
- Any future feature that modifies INT or WIS at runtime (e.g., buff/debuff effects, stat-boosting items) must also recalculate `max_energy`. Same limitation exists for CON→`max_hp`. This is an existing architectural pattern — not an Epic 18 change.
- **Pre-existing bugs discovered during Epic 18 investigation** (require ISS docs per CLAUDE.md before fixing):
  - **ISS-033**: `handle_flee_outcome()` never syncs HP/stats back to entity before `remove_participant()` pops combat stats. Fled players lose all combat stat changes (HP damage, heals). Fixed in Task 12 alongside energy sync. Create ISS doc before implementing Task 12.
  - **ISS-034**: `_reset_player_stats()` does not clear `active_effects` (DoTs). Dying players could carry DoTs through respawn into next combat. Fixed in Task 4. Create ISS doc before implementing Task 4.
