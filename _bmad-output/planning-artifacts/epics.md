---
stepsCompleted: ["step-01-validate-prerequisites", "step-02-design-epics", "step-03-create-stories", "step-04-final-validation", "step-01-epic10-prerequisites", "step-02-epic10-design", "step-03-epic10-stories", "step-04-epic10-validation", "step-01-epic11-prerequisites", "step-02-epic11-design", "step-03-epic11-stories", "step-04-epic11-validation", "step-01-epic12-prerequisites", "step-02-epic12-design", "step-03-epic12-stories", "step-04-epic12-validation", "step-01-epic14-prerequisites", "step-02-epic14-design", "step-03-epic14-stories", "step-04-epic14-validation"]
inputDocuments:
  - "THE_AGES_SERVER_PLAN.md"
  - "_bmad-output/planning-artifacts/architecture.md"
  - "_bmad-output/planning-artifacts/execution-plan.md"
  - "_bmad-output/implementation-artifacts/tech-spec-web-test-client.md"
  - "CLAUDE.md"
  - "_bmad-output/implementation-artifacts/sprint-status.yaml"
  - "Deep code analysis (Epic 14 source) — web client logic leaks, hardcoded parameters, modularity violations, DB/infrastructure gaps"
---

# The-Ages-II - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for The-Ages-II, decomposing the requirements from the Architecture specification and original server plan into implementable stories.

## Requirements Inventory

### Functional Requirements

FR1: Project scaffolding with domain-driven directory structure (core/, net/, player/, room/, combat/, items/, web/)
FR2: FastAPI application with WebSocket endpoint and health check
FR3: SQLAlchemy async database initialization with SQLite via aiosqlite
FR4: Player model with credentials, stats, inventory, card collection, current position
FR5: Room model with tile grid (up to 100x100), exits, objects, spawn points, and schema_version
FR6: RoomState model for runtime mob states and shared interactive object states
FR7: PlayerObjectState model for per-player object state (e.g., opened chests)
FR8: Card model with multi-effect chain (list of effects with type, subtype, value)
FR9: SpawnCheckpoint model for persisting NPC spawn check timestamps across server restarts
FR10: Player persistence repo (CRUD, position updates, inventory updates)
FR11: Room persistence repo (CRUD, room state, JSON loading via RoomProvider interface)
FR12: Card persistence repo (load card definitions from JSON)
FR13: Tile type system (floor, wall, exit, mob_spawn, water) with walkability rules
FR14: Room instance with 100x100 tile grid, entity management, and movement validation
FR15: 4-directional movement with wall collision and boundary checking
FR16: Exit tile detection triggering room transitions between zones
FR17: Room object system: static objects (trees, rocks — blocking/decoration)
FR18: Room object system: interactive objects with state_scope (room-shared or per-player)
FR19: Chest interaction with permanent one-time loot per player
FR20: Lever/interactive object system with room-shared state changes
FR21: NPC system with behavior_type field (prototype: hostile only; future: merchant, quest_giver)
FR22: Three-tier NPC spawn system (persistent, timed respawn, rare with chance roll)
FR23: Spawn check timestamp persistence surviving server restarts
FR24: Global announcement broadcast when rare/epic NPC spawns
FR25: WebSocket connection management (connect, disconnect, player entity ID mapping)
FR26: JSON message routing by 'action' field to domain-specific handler modules
FR27: Player registration with username/password validation and bcrypt hashing
FR28: Player login with credential verification, entity creation, room placement
FR29: Room state broadcast on player entry (full 100x100 tile grid + all entities + objects)
FR30: Entity movement broadcasting to all players in room
FR31: Entity enter/leave notifications to room players
FR32: Room chat and whisper messaging
FR33: Turn-based card combat: one action per turn (play card OR use item OR pass)
FR34: Card hand management (deck/hand/discard cycling, hand size 5, draw on play)
FR35: Multi-effect card resolution via shared effect registry
FR36: Combat turn advancement with mob attack on pass and end-of-cycle
FR37: Shield absorption before HP damage
FR38: Victory condition (mob HP <= 0) with XP/loot rewards
FR39: Defeat condition (all player HPs <= 0)
FR40: Flee action (exit combat, combat continues for remaining participants)
FR41: Mob respawn scheduling after combat ends
FR42: Shared effect registry used by both cards and items (damage, heal, shield, dot, draw)
FR43: Item definitions with category (consumable, material), charges, stackable flag
FR44: Player inventory with unlimited stacking
FR45: Consumable items usable during combat turns (as the one action)
FR46: Consumable items usable outside combat (e.g., healing potions between fights)
FR47: Item effect resolution via same shared effect registry as cards
FR48: Game class as central orchestrator owning all managers and services
FR49: Server startup sequence: init DB, load rooms, spawn NPCs, load cards/items, register handlers
FR50: Player disconnect handling: save position, remove from room, notify other players
FR51: Spawn point resolution — new players placed at room's configured player spawn point, not default (0,0) which may be a wall tile; spawn point must be validated as walkable after static objects are applied, with fallback to first walkable floor tile; change default room from "test_room" to "town_square" and call get_player_spawn() for first-time players (detect via current_room_id is None); save current_room_id to DB after first placement to avoid re-detecting first-time on subsequent logins
FR52: Player stats persistence — hp, max_hp, and attack are persisted to database on every HP change (save once after the complete action resolves, not after each individual effect within an action) and restored on login; shield resets to 0 on combat end and is NOT persisted (combat-only buffer); defaults (hp=100, max_hp=100, attack=10) applied only on first login when stats are empty; only whitelisted keys (hp, max_hp, attack) are persisted — unknown keys stripped before save to prevent injection; when an action modifies both stats and inventory (e.g., using a consumable), both changes must be committed in a single DB transaction; on disconnect, batch all player-state saves (stats + inventory + position) into one transaction
FR53: Death/respawn mechanic — defeated players respawn at town_square spawn point with full HP (deliberate design choice: town is safe zone, walking back is the time cost); no death penalty for prototype (no XP/item/gold loss); synchronous cleanup sequence: combat removal → in_combat flag clear → set stats to respawn values → save all state to DB (stats + position + room_key = town_square) → THEN in-memory room transfer and broadcast (DB save before transfer ensures crash recovery places player correctly); respawn logic encapsulated as game.respawn_player(entity_id) method on Game class, not in combat handler directly; no immediate re-encounter with respawning mobs; unclean disconnect during combat is treated as flee (player removed from combat, combat continues for others)
FR54: Inventory persistence — player inventory saved to database on every mutation (pickup, use, trade, loot, and disconnect) and restored on login, not recreated empty on each login; items retained on death (no item loss for prototype); Inventory class needs to_dict/from_dict methods for DB round-tripping — from_dict takes an item lookup callable (str) -> ItemDef to hydrate runtime objects without coupling Inventory to Game; chest loot granting must use upsert pattern to prevent duplication under concurrent access
FR55: Duplicate login protection — server kicks existing session when same account logs in concurrently; for prototype, kick immediately (deferred kick until current message handler completes is a production optimization); kick cleanup order: remove entity from room → remove from connection_manager immediately (do not wait for disconnect event) → close WebSocket → proceed with new login; old session's state is saved before kick; any active combat is forfeited (player removed from combat instance)
FR56: NPC death state broadcast — after combat victory, server rebroadcasts room_state to all players in the room so all clients see the NPC as dead (using existing room_state format ensures consistent state); also fix pre-existing bug: NPC is_alive is currently set False at encounter time (movement.py:101), not at victory — must change to set is_alive=False only on combat victory and use an in_combat flag at encounter instead; add in_combat: bool field to NpcEntity dataclass; to_dict() must NOT expose in_combat (server-internal); encounter check must verify both is_alive and not in_combat; NPC in_combat flag is purely in-memory, not persisted to DB — server restart resets all NPCs to available state; note: targeted npc_update message is the production optimization path but room_state rebroadcast is sufficient for prototype
FR57: Card cost enforcement — implement mana/energy resource system so card cost field has mechanical meaning, or remove cost field
FR58: Vertical room exits — support stairs/ladders with new tile types (STAIRS_UP, STAIRS_DOWN); requires direction disambiguation since movement "up"/"down" means north/south on grid while vertical exit "up"/"down" means ascend/descend — consider "ascend"/"descend" exit directions or interact-based triggering
FR59: Admin authentication (shared secret) — REST endpoints protected by ADMIN_SECRET env var
FR60: Admin-triggered graceful shutdown — POST /admin/shutdown saves all state, notifies clients, exits
FR61: Admin-triggered server restart — POST /admin/restart with process re-execution
FR62: Player logout — server action `logout` that saves state, removes from room, notifies others, closes WebSocket
FR63: Player logout — web client `/logout` command and logout button returning to login screen
FR64: Interactive objects (chests, levers) are non-walkable — players interact from adjacent tiles
FR65: Directional interaction — `/interact <direction>` command resolves to adjacent interactive object and sends `interact` action
FR66: Slash command parser — client-side parser translating `/command args` into server actions via chat input
FR67: Slash commands: `/logout`, `/whisper @name message`, `/interact <direction>`, `/inventory`, `/use <item>`, `/look`, `/who`, `/stats`, `/help`, `/flee`, `/pass`
FR68: Server action `look` — returns objects, NPCs, and players on current tile and adjacent tiles
FR69: Server action `who` — returns list of players in current room
FR70: Server action `stats` — returns current player stats (HP, max_hp, attack, XP)
FR71: Server action `help` — returns list of available actions/commands
FR72: Proximity notification — server notifies player when they move adjacent to an interactive object
FR73: Player stats HUD — always-visible HP bar, XP display, attack stat in web client
FR74: Mob loot drops — combat victory generates loot from NPC's `loot_table`, adds to player inventory, included in `combat_end` message
FR75: Mob loot tables — add loot table entries for all NPC types (goblin_loot, slime_loot, bat_loot, troll_loot, dragon_loot)
FR76: Increased NPC spawn density — add more slime/mob spawn points in larger rooms (town_square, dark_cave)
FR77: XP level thresholds — define XP required per level with scaling curve
FR78: Level-up mechanic — when XP exceeds threshold, player chooses up to 3 of 6 D&D-style stats to boost +1 (cap 10), max_hp recalculated from CON
FR79: Level-up notification — server sends `level_up` message to player with new level and stat changes
FR80: Level display — player level shown in stats HUD and included in entity data visible to other players
FR81: `/stats` updated to include level and XP-to-next-level
FR88: D&D-style stat system — STR, DEX, CON, INT, WIS, CHA for PC (default 1) and NPC (derived from hit_dice); persisted to DB
FR89: Stat-to-combat mapping — STR→physical damage bonus, DEX→flat damage reduction (min 1 dmg), CON→max_hp scaling (100+CON×5), INT→magical damage bonus (fire/ice/arcane), WIS→heal bonus; formula: floor(stat × 1.0)
FR90: NPC hit_dice system — all NPC abilities = hit_dice value, max_hp = hit_dice × hp_multiplier; replaces flat hp/attack stats in NPC data
FR91: Configurable XP curve — XP_CURVE_TYPE (quadratic/linear), XP_CURVE_MULTIPLIER (default 25), combat XP = f(hit_dice); CHA XP bonus via XP_CHA_BONUS_PER_POINT (default 0.03)
FR92: Multiple XP sources — combat victory (hit_dice-based), exploration (first room visit), object interaction (first-time chest/lever); hooks for quest completion and party bonus
FR93: Stats persistence — all 6 ability scores + level persisted to DB; stats whitelist expanded from {hp, max_hp, attack, xp} to include strength, dexterity, constitution, intelligence, wisdom, charisma, level
FR82: Trade system — mutual exchange model; `/trade @player` sends trade session request to target; target must `/trade accept` to enter negotiation or `/trade reject` to decline (request times out at 30s if ignored); once in session, both players place items via `/trade offer item_name quantity` (accepts item keys and display names, case-insensitive, consistent with `/use` ISS-010); supports multi-item syntax: `/trade offer item1 qty1 item2 qty2`; each player can offer multiple items — `/trade offer` adds to or updates the player's offer list; `MAX_TRADE_ITEMS` config (default 10) — reject offer if total unique items exceeds limit; `/trade remove item_name` removes an item from the offer; `/trade offer` validates player currently has sufficient quantity (rejected if insufficient, final validation still at execution); `/trade ready` signals confirmation; trade executes atomically when both players ready; `/trade cancel` aborts at any point; adding/removing an offer resets both players' ready state (prevents bait-and-switch); state machine: `idle → request_pending → negotiating → one_ready → both_ready → executing → complete`; `ItemDef` gains a `tradeable: bool = True` field — non-tradeable items blocked from offers; one active trade session per player — auto-reject new `/trade @player` if either player already in a session; `TradeManager` must use async lock when assigning trades to prevent race conditions; configurable trade session timeout (`TRADE_SESSION_TIMEOUT_SECONDS`, default 60) — resets on any trade activity (offer/remove/ready), auto-cancel on inactivity; cooldown after cancel/reject/timeout (e.g., 5s) before player can initiate new trade; distinct message types (`trade_request`, `trade_update`, `trade_result`) for client rendering; `trade_request` message must include sender name; `trade_update` shows current offers from both sides; `/trade` uses subcommand pattern — handler parses first arg as subcommand (`@player`, `accept`, `reject`, `offer`, `remove`, `ready`, `cancel`, or no subcommand for status); `/trade` (no subcommand while in session) shows current offers from both sides and ready state; add name → entity_id index to ConnectionManager for player name resolution (shared by trade and party systems); disconnect cleanup order: cancel trades → remove from combat → handle party departure → save state → remove from room → notify
FR83: Trade validation — both players must be in same room, online, not in combat; trade requires same-room regardless of party status — party membership has no effect on trade eligibility; items validated before transfer (sufficient quantity, item exists, `tradeable` flag checked); atomic two-player inventory swap in a single DB transaction to prevent duplication or loss; trade is immediately cancelled if either player disconnects, changes room, or enters combat; accept/execute requires both players connected with live entities; no item escrow — quantities validated from live inventory at execution time; self-trades rejected (same `player_db_id`); duplicate login kick cancels all pending trades for that `player_db_id`; trade fails entirely if any offered quantity exceeds current inventory at execution time — no partial trades
FR84: Party system — `/party invite @player`, `/party accept`, `/party leave`, `/party disband`, `/party kick @player` (leader only), `/party` (no subcommand) shows current party members, leader, and member online/room status; `/party` uses subcommand pattern — handler parses first arg as subcommand; party leader is the player who created the party; leader succession: on leader disconnect, leadership passes to longest-standing member; party dissolved when last member leaves/disconnects; party invites allowed during combat but party combat (FR86) only applies to encounters starting after party formation; `/party leave` allowed during combat but does not affect current combat instance — player remains in combat, XP calculated based on combat participants at victory not current party state; `/party kick` and `/party disband` blocked while any party members share an active combat instance; one pending invite per inviter at a time — sending new invite cancels previous; cooldown before re-inviting same player (also applies after kick); `MAX_PARTY_SIZE` config (default 4) — invite rejected when party is full; invite target must be online (error: "Player not found" / "Player is not online"); invite rejected if target is already in a party (must `/party leave` first); no same-room requirement for invite; trades and parties are ephemeral (in-memory only) — all dissolved on server restart/shutdown with player notification; distinct message types (`party_invite`, `party_update`) for client rendering; disconnect cleanup order same as FR82
FR85: Party chat — `/party message` translates to dedicated `party_chat` action (not overloading existing `chat` action); server validates sender is in a party and routes only to party members; sender name set server-side (no client impersonation); sends to party members only, regardless of room; `MAX_CHAT_MESSAGE_LENGTH` (default 500) applied to party chat messages; distinct message type (`party_chat`) for client rendering
FR86: Party combat — party members in same room enter combat together when any member encounters a mob; only the moving player's party joins — other parties/players on same tile unaffected; mob marked `in_combat` prevents duplicate encounters; only non-`in_combat` same-room party members join new encounter; mob HP scales with party size at encounter time (e.g., HP × party_size) to maintain challenge; `XP_PARTY_BONUS_PERCENT` (default 10) applied to combat XP only when 2+ party members are in the combat instance at victory; turn order: round-robin in party join order, mob attacks one random party member at end of cycle (random target for prototype; future: threat/aggro system); death during party combat: dead member removed from combat instance (like flee), no XP awarded, mob HP does not rescale down, party membership persists across respawn; remaining members notified when a party member flees combat; HIGHEST-RISK STORY: must audit and extend `CombatInstance` for multi-player support — verify players is a list, turn cycling handles N players, victory/defeat conditions work with N players
FR87: World map — `/map` shows discovered rooms and connections; reuses existing `visited_rooms` field on Player model — no new DB schema needed; server reads `visited_rooms` and cross-references room exit data to build connections; server sends `map_data` message with only discovered rooms — undiscovered rooms omitted entirely from response (client cannot infer total count or names); format: `{rooms: [{room_key, name}], connections: [{from_room, to_room, direction}]}`; connections to undiscovered rooms show destination as `???` (preserves exploration mystery while revealing exit exists); connections derived from room exit data at render time — no separate connection storage; web client renders as text-based node list in dedicated panel
FR94: Server `xp_gained` message must include `new_total_xp` (absolute value), not just `amount` (delta) — prevents client-side XP accumulation drift on missed messages
FR95: Server `login_success` message must include `entity_id` — client should not construct `player_{id}` format internally
FR96: Server `respawn` message must include new `hp` value — client should not assume `hp = max_hp` game rule
FR97: Server `level_up_complete` message must include `new_hp` — client should not assume full heal on level-up
FR98: Server `combat_end` message must include defeated NPC `entity_id` — client should not use proximity heuristic to guess which NPC died
FR99: Server `stats` and `level_up_available` messages must include `xp_for_next_level` and `xp_for_current_level` — client should not compute XP curve formula
FR100: Server `level_up_available` message must include stat effect descriptions derived from config values — client should not hardcode `+5 HP per CON`, `+3% XP per CHA` etc.
FR101: Default player stats centralized in config: `DEFAULT_BASE_HP=100`, `DEFAULT_ATTACK=10`, `DEFAULT_STAT_VALUE=1` — replacing 5+ hardcoded occurrences across auth.py, levelup.py, movement.py, query.py
FR102: Game structure parameters centralized in config: `DEFAULT_SPAWN_ROOM="town_square"`, `STAT_CAP=10`, `LEVEL_UP_STAT_CHOICES=3` — each currently hardcoded in 2+ files
FR103: Combat parameters centralized in config: `COMBAT_HAND_SIZE=5`, `COMBAT_MIN_DAMAGE=1` — currently hardcoded in card_hand.py and damage.py/instance.py
FR104: NPC derivation parameters centralized in config: `NPC_DEFAULT_HP_MULTIPLIER=10`, `NPC_ATTACK_DICE_MULTIPLIER=2` — currently hardcoded in npc.py
FR105: Auth validation parameters centralized in config: `MIN_USERNAME_LENGTH=3`, `MIN_PASSWORD_LENGTH=6` — currently hardcoded in auth.py
FR106: Loot tables moved from hardcoded Python dict (server/items/loot.py) to JSON data file (data/loot/) — consistent with cards, items, NPCs data-driven pattern per architecture Section 2.4
FR107: Fix app.py:259 mob respawn fallback to use `settings.MOB_RESPAWN_SECONDS` instead of hardcoded `60`; fix trade cooldown to use config `TRADE_COOLDOWN_SECONDS=5` instead of hardcoded value in trade/manager.py:64
FR108: Replace untyped `player_entities: dict[str, dict]` with a `PlayerSession` dataclass (fields: entity, room_key, db_id, inventory, visited_rooms, pending_level_ups) — two-phase migration with `__getitem__` compat bridge, then call-site migration; eliminates fragile string-key access across all handlers
FR109: Add read-only public accessors (`MappingProxyType`) to `RoomInstance` for `_entities`, `_npcs`, `_interactive_objects` — eliminate cross-module private attribute access from handlers and room objects
FR110: Store `room_key` on `InteractiveObject` at creation time — eliminate the `_get_room_key()` anti-pattern where chest.py and lever.py do linear scan of `game.room_manager._rooms`; no `interact()` signature change needed
FR111: Decompose `_check_combat_end` (133 lines) into testable module-level helper functions within `combat.py` — separates XP calc, loot gen, defeat handling, cleanup into independently testable units; bonus objective: decompose `game.respawn_player()` similarly within `app.py`
FR112: Remove `_NPC_TEMPLATES` module-global import from `scheduler.py` — expose as `game.npc_templates` attribute on the composition root, following existing access pattern
FR113: Set up Alembic for schema migrations — replace `Base.metadata.create_all` auto-create with versioned migration scripts for production readiness
FR114: Add `asyncio.Lock` to trade execution (`_execute_trade` TOCTOU race between validation and DB write) and NPC encounter initiation (`_handle_mob_encounter` TOCTOU race between `in_combat` check and set)
FR115: Add PostgreSQL-compatible connection pooling config to `create_async_engine` — `pool_size`, `max_overflow`, `pool_pre_ping` (conditional on whether driver is asyncpg vs aiosqlite)
FR116: Fix `SpawnCheckpoint` DateTime handling — use timezone-aware datetimes consistently instead of `datetime.now(UTC).replace(tzinfo=None)` for PostgreSQL compatibility
FR117: Consolidate transaction granularity in `_check_combat_end` — currently opens 3-4 separate transactions per participant in a loop; should be one transaction per combat resolution
FR118: Make effect targeting data-driven — add `"target": "self"|"enemy"` field on card/item effects instead of hardcoded if/else in `CombatInstance.resolve_card_effects()`

### NonFunctional Requirements

NFR1: Python 3.11+ required
NFR2: Max 30 players per room
NFR3: Mob respawn timer configurable (default 60s)
NFR4: Combat turn timeout configurable (default 30s)
NFR5: bcrypt password hashing for security
NFR6: Pydantic message validation for all client-server communication
NFR7: Room JSON schema versioned (schema_version field) for future migration support
NFR8: Room entry payload optimized (~50KB for 100x100 grid with integer tile type IDs)
NFR9: All game balance parameters must be configurable via environment variables (Pydantic BaseSettings pattern) — no game-affecting numeric constants hardcoded in Python source
NFR10: Server messages must be self-contained — client should never need to compute, derive, or accumulate game state from deltas; enables engine-agnostic client replacement
NFR11: No module should access private (`_`-prefixed) attributes of another module — all cross-module access through public APIs
NFR12: Database layer must be compatible with PostgreSQL swap via `DATABASE_URL` env var without code changes beyond driver dependency
NFR13: All concurrent state mutations must be protected by `asyncio.Lock` to prevent TOCTOU races at `await` yield points

### Additional Requirements

- Domain-driven directory structure separating concerns (core, net, player, room, combat, items, web)
- RoomProvider interface pattern: JsonRoomProvider now, DbRoomProvider for future editor
- Cards use effects list (not single effect) from day one to support future skill tree upgrades
- NPC behavior_type field supports future expansion (merchant, quest_giver) without architectural changes
- Scheduler service for periodic tasks (spawn checks, respawn timers) as core service
- Event bus for global announcements and cross-system triggers as core service
- Effect registry as shared core service extensible by adding new handler files
- Item categories unified in single inventory system (consumables and materials together)
- Loot table system for chests, reusable for future combat rewards
- Architecture Section 2.4 mandates JSON-driven configuration: "JSON defines what (data, values, configurations)" — loot tables in Python code violate this
- Architecture Section 3.1 specifies handlers should be "thin, delegate to domain logic" — `_check_combat_end` (133 lines) and `handle_login` (158 lines) violate this
- Architecture's `RoomProvider` interface pattern demonstrates expected abstraction quality — other cross-module boundaries should follow similar patterns
- Architecture documents `game.session_factory()` as the single DB access pattern — Alembic must integrate with this, not bypass it

### UX Design Requirements

Web demo client (`web-demo/`) implemented as a proof-of-concept test tool. Vanilla HTML/CSS/JS served by FastAPI StaticFiles mount. Covers: auth, tile viewport, movement, chat, combat with cards, inventory, object interaction, stats display, server message log. Production client planned in Godot. Tech spec: `_bmad-output/implementation-artifacts/tech-spec-web-test-client.md`.

### FR Coverage Map

| FR | Epic | Description |
|----|------|-------------|
| FR1 | Epic 1 | Domain-driven directory structure |
| FR2 | Epic 1 | FastAPI app with WebSocket + health check |
| FR3 | Epic 1 | Async database initialization |
| FR4 | Epic 1 | Player model |
| FR5 | Epic 1 | Room model (100x100, schema_version) |
| FR6 | Epic 1 | RoomState model |
| FR7 | Epic 1 | PlayerObjectState model |
| FR8 | Epic 1 | Card model with multi-effect chain |
| FR9 | Epic 1 | SpawnCheckpoint model |
| FR10 | Epic 1 | Player persistence repo |
| FR11 | Epic 1 | Room persistence repo + RoomProvider |
| FR12 | Epic 1 | Card persistence repo |
| FR13 | Epic 1 | Tile type system |
| FR14 | Epic 1 | Room instance (grid, entities) |
| FR15 | Epic 2 | 4-directional movement |
| FR16 | Epic 2 | Exit tile room transitions |
| FR17 | Epic 2 | Static room objects (blocking/decoration) |
| FR18 | Epic 3 | Interactive objects with state_scope |
| FR19 | Epic 3 | Chest interaction (permanent one-time loot) |
| FR20 | Epic 3 | Lever/interactive shared state |
| FR21 | Epic 3 | NPC system with behavior_type |
| FR22 | Epic 3 | Three-tier NPC spawn system |
| FR23 | Epic 3 | Spawn checkpoint persistence |
| FR24 | Epic 3 | Global rare spawn announcements |
| FR25 | Epic 1 | WebSocket connection management |
| FR26 | Epic 1 | Message routing by action field |
| FR27 | Epic 1 | Player registration |
| FR28 | Epic 1 | Player login + room placement |
| FR29 | Epic 1 | Room state broadcast on entry |
| FR30 | Epic 2 | Movement broadcasting |
| FR31 | Epic 1 | Entity enter/leave notifications |
| FR32 | Epic 2 | Room chat and whispers |
| FR33 | Epic 4 | Turn-based combat (one action per turn) |
| FR34 | Epic 4 | Card hand management |
| FR35 | Epic 4 | Multi-effect card resolution |
| FR36 | Epic 4 | Turn advancement + mob attacks |
| FR37 | Epic 4 | Shield absorption |
| FR38 | Epic 4 | Victory condition + rewards |
| FR39 | Epic 4 | Defeat condition |
| FR40 | Epic 4 | Flee action |
| FR41 | Epic 3 | Mob respawn scheduling |
| FR42 | Epic 4 | Shared effect registry |
| FR43 | Epic 5 | Item definitions (consumable, material) |
| FR44 | Epic 5 | Unlimited stacking inventory |
| FR45 | Epic 5 | Items usable in combat |
| FR46 | Epic 5 | Items usable outside combat |
| FR47 | Epic 5 | Item effects via shared registry |
| FR48 | Epic 1 | Game orchestrator class |
| FR49 | Epic 1 | Server startup sequence |
| FR50 | Epic 1 | Disconnect handling |
| FR51 | Epic 7 | Spawn point resolution |
| FR52 | Epic 7 | Player stats persistence |
| FR53 | Epic 7 | Death/respawn mechanic |
| FR54 | Epic 7 | Inventory persistence |
| FR55 | Epic 7 | Duplicate login protection |
| FR56 | Epic 7 | NPC death state broadcast |
| FR57 | Epic 8 | Card cost enforcement |
| FR58 | Epic 8 | Vertical room exits |
| FR59 | Epic 9 | Admin authentication (shared secret) |
| FR60 | Epic 9 | Admin-triggered graceful shutdown |
| FR61 | Epic 9 | Admin-triggered server restart |
| FR62 | Epic 10 | Player logout server action |
| FR63 | Epic 10 | Player logout client UI + command |
| FR64 | Epic 10 | Non-walkable interactive objects |
| FR65 | Epic 10 | Directional `/interact <direction>` command |
| FR66 | Epic 10 | Slash command parser (client-side) |
| FR67 | Epic 10 | Slash commands full list |
| FR68 | Epic 10 | Server action `look` |
| FR69 | Epic 10 | Server action `who` |
| FR70 | Epic 10 | Server action `stats` |
| FR71 | Epic 10 | Server action `help` |
| FR72 | Epic 10 | Proximity notification for interactive objects |
| FR73 | Epic 10 | Player stats HUD |
| FR74 | Epic 10 | Mob loot drops on combat victory |
| FR75 | Epic 10 | Loot table entries for all NPC types |
| FR76 | Epic 10 | Increased NPC spawn density |
| FR77 | Epic 11 | XP level thresholds (configurable linear scaling) |
| FR78 | Epic 11 | Level-up mechanic (choose 3 stats, D&D-style) |
| FR79 | Epic 11 | Level-up notification |
| FR80 | Epic 11 | Level display in HUD and entity data |
| FR81 | Epic 11 | `/stats` includes level, XP-to-next, and all 6 abilities |
| FR88 | Epic 11 | D&D-style stat system (STR/DEX/CON/INT/WIS/CHA) for PC and NPC |
| FR89 | Epic 11 | Stat-to-combat mapping (damage, reduction, HP, heal bonuses) |
| FR90 | Epic 11 | NPC hit_dice system (all abilities from hit_dice) |
| FR91 | Epic 11 | Configurable XP curve (quadratic/linear, CHA bonus) |
| FR92 | Epic 11 | Multiple XP sources (combat, exploration, interaction, hooks) |
| FR93 | Epic 11 | Stats persistence (6 abilities + level to DB) |
| FR82 | Epic 12 (Story 12.1) | Trade system (mutual exchange, tradeable flag, state machine) |
| FR83 | Epic 12 (Story 12.2) | Trade validation (atomic swap, disconnect cancellation, no escrow) |
| FR84 | Epic 12 (Stories 12.3, 12.4) | Party system — infrastructure (12.3) + commands (12.4) |
| FR85 | Epic 12 (Story 12.5) | Party chat |
| FR86 | Epic 12 (Stories 12.6, 12.7) | Party combat — engine extension (12.6) + integration (12.7) |
| FR87 | Epic 12 (Story 12.8) | World map with room discovery |
| FR94 | Epic 14 (Story 14.3b) | xp_gained includes new_total_xp |
| FR95 | Epic 14 (Story 14.3a) | login_success includes entity_id |
| FR96 | Epic 14 (Story 14.3a) | respawn includes new hp |
| FR97 | Epic 14 (Story 14.3a) | level_up_complete includes new_hp |
| FR98 | Epic 14 (Story 14.3a) | combat_end includes defeated NPC entity_id |
| FR99 | Epic 14 (Story 14.3b) | stats/level_up include XP thresholds |
| FR100 | Epic 14 (Story 14.3b) | level_up includes stat effect descriptions from config |
| FR101 | Epic 14 (Story 14.1) | DEFAULT_BASE_HP, DEFAULT_ATTACK, DEFAULT_STAT_VALUE in config |
| FR102 | Epic 14 (Story 14.1) | DEFAULT_SPAWN_ROOM, STAT_CAP, LEVEL_UP_STAT_CHOICES in config |
| FR103 | Epic 14 (Story 14.1) | COMBAT_HAND_SIZE, COMBAT_MIN_DAMAGE in config |
| FR104 | Epic 14 (Story 14.1) | NPC_DEFAULT_HP_MULTIPLIER, NPC_ATTACK_DICE_MULTIPLIER in config |
| FR105 | Epic 14 (Story 14.1) | MIN_USERNAME_LENGTH, MIN_PASSWORD_LENGTH in config |
| FR106 | Epic 14 (Story 14.2) | Loot tables to JSON data files |
| FR107 | Epic 14 (Story 14.1) | Fix hardcoded respawn 60s + trade cooldown 5s to use config |
| FR108 | Epic 14 (Story 14.4a) | PlayerSession dataclass (two-phase migration) |
| FR109 | Epic 14 (Story 14.4b) | Read-only public accessors on RoomInstance |
| FR110 | Epic 14 (Story 14.4b) | room_key stored on InteractiveObject at creation |
| FR111 | Epic 14 (Story 14.5) | Decompose _check_combat_end into testable helpers |
| FR112 | Epic 14 (Story 14.5) | game.npc_templates replaces _NPC_TEMPLATES import |
| FR113 | Epic 14 (Story 14.7) | Alembic scaffold + initial migration |
| FR114 | Epic 14 (Story 14.6) | asyncio.Lock for trade + NPC encounter races |
| FR115 | Epic 14 (Story 14.7) | PostgreSQL connection pooling config |
| FR116 | Epic 14 (Story 14.7) | Timezone-aware datetimes |
| FR117 | Epic 14 (Story 14.7) | Transaction consolidation in combat resolution |
| FR118 | Backlog | Data-driven effect targeting (deferred from Epic 14) |

## Epic List

### Epic 1: Player Registration & World Entry
Players can register an account, login via WebSocket, and enter a room — seeing the full tile map, other players, and objects. This epic delivers the foundational systems: project scaffolding, database models, persistence layer, networking, authentication, and room loading.
**FRs covered:** FR1, FR2, FR3, FR4, FR5, FR6, FR7, FR8, FR9, FR10, FR11, FR12, FR13, FR14, FR25, FR26, FR27, FR28, FR29, FR31, FR48, FR49, FR50

### Epic 2: Movement & Room Exploration
Players can move around the tile grid, encounter obstacles (walls, static objects like rocks and trees), transition between rooms via exit tiles, see other players moving, and chat with them.
**FRs covered:** FR15, FR16, FR17, FR30, FR32

### Epic 3: Room Objects & NPC Spawning
The world becomes alive — players encounter interactive objects (chests with permanent one-time loot, levers that change room state), hostile NPCs spawn on configurable timers, and rare/epic NPC spawns trigger global announcements to all connected players.
**FRs covered:** FR18, FR19, FR20, FR21, FR22, FR23, FR24, FR41

### Epic 4: Turn-Based Card Combat
When a player encounters a hostile mob, turn-based card combat begins. Players draw cards, play them to deal damage/heal/shield via a multi-effect system, pass turns, or flee. Combat resolves with victory (rewards) or defeat. The shared effect registry is established as a core service.
**FRs covered:** FR33, FR34, FR35, FR36, FR37, FR38, FR39, FR40, FR42

### Epic 5: Items & Inventory
Players can collect items from chests, manage an inventory with unlimited stacking, and use consumable items both during combat (as their one action per turn, alternative to playing a card) and outside combat (healing between fights). Items share the same effect registry as cards.
**FRs covered:** FR43, FR44, FR45, FR46, FR47

### Epic 6: Integration, Sample Data & Testing
The complete prototype gameplay loop works end-to-end with sample content — two rooms (Town Square, Dark Cave), a 15-card base set, consumable items, hostile NPCs. Comprehensive test suite covers all systems. Full gameplay loop verified: Register → Login → Explore → Interact → Combat → Collect → Transition.

### Epic 7: Server Hardening
Players experience a reliable, persistent game world — spawning at valid positions, keeping their stats and inventory across sessions, recovering from defeat, seeing accurate NPC states, and being protected from concurrent login abuse.
**FRs covered:** FR51, FR52, FR53, FR54, FR55, FR56
**Dependencies:** Only FR52 → FR53 is a hard dependency (death/respawn needs persisted stats). All other stories are logically independent but FR51, FR52, FR54, FR55 all modify auth.py, so sequencing avoids merge conflicts. Recommended order (score-optimized): FR51 (quick win, player impact) → FR52 (highest priority, blocks FR53) → FR54 (high risk persistence) → FR53 (needs FR52) → FR55 (robustness) → FR56 (low-impact visual fix).
**Cross-cutting AC:** Each story must update existing tests to reflect new behavior and leave the full test suite green. Known test impacts: test_login.py:215 (spawn position), test_integration.py:165 (empty inventory).

### Epic 8: World Expansion
The game world grows with new mechanics — vertical room exits (stairs/ladders), and a mana/energy resource system that gives card costs mechanical meaning. Note: FR57 and FR58 are independent features grouped by implementation phase (both require design decisions before implementation), not by user journey.
**FRs covered:** FR57, FR58

### Epic 9: Server Administration
Server operators can manage the game server without SSH process management — triggering graceful shutdown or restart via authenticated admin commands, with proper player state preservation and client notification.
**FRs covered:** FR59, FR60, FR61

### Epic 10: Gameplay Polish & Interaction
Players experience a polished, discoverable game world — interacting with objects via commands or proximity, managing inventory and using items through multiple access methods, receiving loot from defeated mobs, and seeing their stats at a glance. A unified slash command system provides engine-agnostic access to all game mechanics.
**FRs covered:** FR62, FR63, FR64, FR65, FR66, FR67, FR68, FR69, FR70, FR71, FR72, FR73, FR74, FR75, FR76
**Dependencies:** Builds on Epics 1-9 (all complete). Standalone.

### Epic 11: Experience & Stat System
Players have meaningful character stats (STR, DEX, CON, INT, WIS, CHA) that affect card combat outcomes. NPCs use a hit_dice system for simplified stat derivation. Players gain XP from combat, exploration, and object interaction, with hooks ready for future quest and party XP. A configurable XP curve (quadratic default) drives leveling, where players choose which stats to boost — creating meaningful progression with player agency.
**FRs covered:** FR77, FR78, FR79, FR80, FR81, FR88, FR89, FR90, FR91, FR92, FR93
**Dependencies:** Builds on Epics 1-10 (all complete). Standalone. Internal dependency chain: 11.1 (stats) → 11.2 (combat wiring) → 11.3 (XP curve + combat rewards) → 11.4 (exploration/interaction XP) → 11.5 (leveling) → 11.6 (notification/UI).

### Epic 12: Social Systems
Players can trade items with each other, form parties for cooperative combat, and navigate the world using a discovered map — transforming the game from a solo experience into a social one. Trade is a mutual exchange model with session consent, multi-item offers, bait-and-switch prevention, and atomic DB swaps. Party system tracks leader/members with invite/accept/leave/disband/kick commands, leader succession, and combat integration.
**FRs covered:** FR82, FR83, FR84, FR85, FR86, FR87
**Dependencies:** Builds on Epics 10-11. Standalone. Internal dependency chain: 12-1 (trade system) → 12-2 (trade validation); 12-3 (party infra) → 12-4 (party commands) → 12-5 (party chat) → 12-6 (party combat); 12-7 (world map) is independent.
**Architecture Decisions:**
- ADR-1: Trade state in-memory only (60s sessions; DB atomicity handles crashes)
- ADR-2: Party state in-memory only (reform cost 3s < persistence complexity)
- ADR-3: New `server/trade/` and `server/party/` packages (matches domain-driven structure alongside `combat/`, `items/`)
- ADR-4: Name → entity_id index added to `ConnectionManager` (already owns "who is online" data)
- ADR-5: Extend `CombatInstance` for multi-player, don't rewrite (audit first in Story 12-6; preserve 600+ tests)
- ADR-6: Map data computed on request, no caching (trivial O(rooms × exits) cost)

### Epic 14: Codebase Structure & Infrastructure Hardening
The game server becomes production-ready for engine-agnostic client development and future PostgreSQL deployment. Game balance parameters are fully configurable, server messages are self-contained (enabling Godot client without replicating game logic), module boundaries are clean, and database infrastructure supports schema migrations and concurrent operations safely.
**FRs covered:** FR94, FR95, FR96, FR97, FR98, FR99, FR100, FR101, FR102, FR103, FR104, FR105, FR106, FR107, FR108, FR109, FR110, FR111, FR112, FR113, FR114, FR115, FR116, FR117
**NFRs addressed:** NFR9, NFR10, NFR11, NFR12, NFR13
**Backlog (deferred):** FR118 (data-driven effect targeting — implement when needed)
**Dependencies:** Epic 13 must complete before Epic 14 begins.
**Decision gate:** After Phase 1, evaluate: continue cleanup or pivot to content/Godot?

**Execution order:**
```
Phase 1 (Now):   14.1 → 14.3a → 14.3b     14.2 (anytime, independent)
Phase 2 (Soon):  14.4b → 14.4a → 14.5
Phase 3 (Later): 14.6, 14.7 (14.7 depends on 14.5)
```

**Dependency graph:**
```
14.1 ──→ 14.3a (messages reference config values)
14.1 ──→ 14.3b (stat descriptions from config)
14.4a ─→ 14.5 ─→ 14.7 (decomposition → transaction consolidation)
14.2, 14.4b, 14.6 — independently implementable
```

**Cross-cutting rules:**
- Refactoring stories (14.4a, 14.4b, 14.5): all existing tests pass, no assertion changes, no new behavior
- Message enrichment stories (14.3a, 14.3b): additive-only changes (new fields, old fields preserved); server tests assert new fields
- Test assertions use literal values (e.g., `assert hp == 100`), not `settings.*` references
- Config values are for new characters only — not retroactive to existing DB records

**Stories:**

| Story | Title | FRs | Urgency |
|-------|-------|-----|---------|
| 14.1 | Centralize Game Parameters in Config | FR101-FR105, FR107 | Now |
| 14.2 | Data-Driven Loot Tables | FR106 | Now |
| 14.3a | Core Message Enrichment | FR95, FR96, FR97, FR98 | Now |
| 14.3b | XP & Stats Display Enrichment | FR94, FR99, FR100 | Now |
| 14.4b | Room Accessors & Interact Signature | FR109, FR110 | Soon |
| 14.4a | PlayerSession Dataclass | FR108 | Soon |
| 14.5 | Decompose Handler Business Logic | FR111, FR112 | Soon |
| 14.6 | Concurrency Safety | FR114 | Later |
| 14.7 | Database Migration & PostgreSQL Readiness | FR113, FR115, FR116, FR117 | Later |

**Architecture Decisions (ADR-14-1 through ADR-14-21):**
- ADR-14-1: PlayerSession two-phase migration with `__getitem__` compat bridge, both phases in 14.4a
- ADR-14-2: Loot table loader in `item_repo.py` alongside `load_items()`
- ADR-14-3: `MappingProxyType` for read-only room accessors
- ADR-14-4: Decompose into module-level helpers within `combat.py` (not service extraction)
- ADR-14-5: Sync Alembic with auto-derived `ALEMBIC_DATABASE_URL`
- ADR-14-6: Section comments in flat `BaseSettings` (sufficient at current scale)
- ADR-14-7: Trade locks on `TradeManager`, NPC lock on `NpcEntity` dataclass field
- ADR-14-8: `game.npc_templates` attribute replaces `_NPC_TEMPLATES` import
- ADR-14-9: Merge per-participant transactions (3→1), preserve per-participant isolation
- ADR-14-10: Per-effect `"target"` with smart defaults (FR118, deferred to backlog)
- ADR-14-11: DB pool settings in config (`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_PRE_PING`), conditional on driver
- ADR-14-12: UTC-aware datetimes throughout; Alembic initial migration includes timezone column change
- ADR-14-13: `room_key` stored on `InteractiveObject` at creation (no `interact()` signature change)
- ADR-14-14: Tests as message contract (no separate schema doc; Pydantic response models as future epic)
- ADR-14-15: Direct 1:1 loot table JSON translation (no weighted drops in this story)
- ADR-14-16: Both PlayerSession migration phases within single Story 14.4a
- ADR-14-17: NFR verification via curated grep checklist + CLAUDE.md convention update
- ADR-14-18: Auto-generate initial Alembic migration; delete dev DBs; `make db-migrate` target
- ADR-14-19: Pydantic `field_validator` for 6 critical settings only (BASE_HP≥1, HAND_SIZE≥1, MIN_DAMAGE≥0, STAT_CAP≥1, STAT_CHOICES≥1, POOL_SIZE≥1)
- ADR-14-20: Party module globals (`_pending_invites` etc.) deferred — within-module, not cross-module
- ADR-14-21: Keep `create_all` alongside Alembic (don't force transition in scaffolding story)

**Per-story design decisions:**

**14.1 — Centralize Game Parameters in Config**
- Settings organized with section comments (ADR-14-6)
- Add `ALEMBIC_DATABASE_URL` auto-derived sync URL
- `field_validator` for 6 critical settings (ADR-14-19)
- Document: "config = new character defaults only, not retroactive"
- Add comment to `_STATS_WHITELIST` explaining `attack` exclusion
- Check `test_integration.py` coverage as prerequisite; expand if gaps
- Update CLAUDE.md with config convention

**14.2 — Data-Driven Loot Tables**
- Direct 1:1 JSON translation to `data/loot/loot_tables.json` (ADR-14-15)
- Loader function in `item_repo.py` (ADR-14-2)
- Subtasks: JSON schema → loader → `Game.startup()` hook → call site updates → delete `loot.py` constant
- Runtime data on `game.loot_tables`

**14.3a — Core Message Enrichment**
- FR95: `entity_id` in `login_success`
- FR96: `hp` in `respawn`
- FR97: `new_hp` in `level_up_complete`
- FR98: `defeated_npc_id` in `combat_end`
- Additive-only changes; code path audit per emission site
- Add assertions to existing tests (not new test files) (ADR-14-14)
- Minimal web client updates (don't rewrite client logic)

**14.3b — XP & Stats Display Enrichment**
- FR94: `new_total_xp` in `xp_gained`
- FR99: `xp_for_next_level`, `xp_for_current_level` in stats
- FR100: stat effect descriptions from config in `level_up_available`
- Same additive-only and test rules as 14.3a

**14.4b — Room Accessors & Interact Signature**
- Read-only public accessors via `MappingProxyType` (ADR-14-3)
- `room_key` stored on object at creation time (ADR-14-13); delete `_get_room_key()` from chest/lever
- Pure refactor — all existing tests pass

**14.4a — PlayerSession Dataclass**
- Two-phase migration within single story (ADR-14-1, ADR-14-16)
- Pre-implementation grep for dict-specific patterns (`**`, `.copy()`, `isinstance`, `dict()`, serialization)
- Phase 2 scope conditional on grep results
- Pure refactor — all existing tests pass

**14.5 — Decompose Handler Business Logic**
- `_check_combat_end` → 4 helpers: `_award_combat_xp`, `_distribute_combat_loot`, `_handle_player_defeat`, `_cleanup_combat_state` (suggested, non-binding)
- `game.npc_templates` attribute replaces `_NPC_TEMPLATES` import (ADR-14-8)
- Bonus objective: decompose `game.respawn_player()` → `_reset_player_stats`, `_transfer_to_spawn`, `_broadcast_respawn` (droppable if story gets complex)
- Pure refactor — all existing tests pass

**14.6 — Concurrency Safety**
- Per-NPC lock via `_lock: asyncio.Lock` field on `NpcEntity` dataclass (ADR-14-7)
- Per-trade lock dict on `TradeManager` keyed by sorted player IDs (ADR-14-7)
- Short critical sections (protect check-and-set only)
- Document `asyncio.gather` concurrent test pattern

**14.7 — Database Migration & PostgreSQL Readiness**
- Sync Alembic with derived URL (ADR-14-5); auto-generate initial migration (ADR-14-18)
- Keep `create_all` alongside Alembic (ADR-14-21); delete dev DBs for fresh start
- Pool settings conditional on driver (ADR-14-11)
- UTC-aware datetimes on `SpawnCheckpoint` (ADR-14-12)
- Per-participant loot transaction isolation intentional (ADR-14-9); stat saves consolidated
- Migration roundtrip test: verify `alembic upgrade head` matches `create_all` schema
- `make db-migrate` Makefile target
- ADR-14-5 future debt noted: sync Alembic creates two connection paths in PostgreSQL production

**Epic 14 — Definition of Done:**
- All stories in shipped phases complete
- All 800+ existing tests pass
- `test_integration.py` covers full gameplay loop (register → login → move → fight → loot → disconnect → reconnect → verify state)
- NFR verification scan passes (grep for hardcoded game values, `"town_square"`, cross-module `_` access)
- Note: `party.py` module globals are known debt — within-module, tracked for future cleanup
- E2E smoke test: full gameplay loop verified end-to-end after all refactoring
- CLAUDE.md updated with new conventions (config for game values, no cross-module `_` access, server messages self-contained)

### Epic 15: Server Architecture Refinement
The server's internal structure is tightened — player session lifecycle gets a dedicated manager, handler boilerplate is eliminated via middleware, cross-module dependencies flow in the correct direction, and remaining domain model gaps are closed. Pure refactoring epic: zero gameplay behavior changes, all existing tests pass unchanged.
**No new FRs** — internal refactoring driven by codebase review findings, not new functionality.
**Dependencies:** Epic 14 complete.
**Findings source:** Adversarial codebase review (2026-04-11), findings C/D/E/I/J/K/L/O/Q/R/U/W/X.
**Deferred findings:** (A) `xp.py` mixing business logic with WebSocket sending — acknowledged trade-off; centralizing notification prevents forgotten sends, refactoring requires callback/event pattern design. (V) untyped stats dicts — requires TypedDict/dataclass design; scope for a future epic. (G) `TradeManager.set_connection_manager()` setter injection — low impact, defer unless touched by another story.

**Execution order:**
```
Phase 1 (Core):  15.1 → 15.2 → 15.3
Phase 2 (Clean): 15.4, 15.5a, 15.5b, 15.6, 15.7 (all independent)
```

**Dependency graph:**
```
15.1 (PlayerManager) ──→ 15.2 (_cleanup_player relocation — depends on PlayerManager)
                         15.2 ──→ 15.3 (auth middleware — 15.3 AC for handle_logout assumes cleanup_session exists)
15.4, 15.5a, 15.5b, 15.6, 15.7 — independently implementable
```

**Note on 15.2 → 15.4 ordering:** Story 15.2 moves `_cleanup_player` (which calls `cleanup_pending_invites` from party handler). If 15.4 is done first, the relocated cleanup calls `game.party_manager.cleanup_invites()`. If 15.2 is done first, the deferred import moves from `auth.py` to `PlayerManager` and is cleaned up when 15.4 lands. Either order works.

**Stories:**

| Story | Title | Findings | Phase |
|-------|-------|----------|-------|
| 15.1 | Player Session Manager | I, W | Core |
| 15.2 | Relocate Player Cleanup to Game Layer | U | Core |
| 15.3 | Handler Auth Middleware | D | Core |
| 15.4 | Party Invite State → PartyManager | E | Clean |
| 15.5a | Extract Effect Targeting | Q | Clean |
| 15.5b | NpcEntity & Dataclass Relocation | C, X | Clean |
| 15.6 | EventBus Resilience & Config Gaps | R, O, L | Clean |
| 15.7 | Data Layer Consistency | J, K | Clean |

---

## Epic 14: Codebase Structure & Infrastructure Hardening

The game server becomes production-ready for engine-agnostic client development and future PostgreSQL deployment. Game balance parameters are fully configurable, server messages are self-contained (enabling Godot client without replicating game logic), module boundaries are clean, and database infrastructure supports schema migrations and concurrent operations safely.

### Story 14.1: Centralize Game Parameters in Config

As a developer,
I want all game balance parameters defined in a single config source (`Settings` class),
So that changing a game value requires editing one place, and the codebase is consistent with the architecture's JSON-driven configuration principle.

**Acceptance Criteria:**

**Given** the `Settings` class in `server/core/config.py`
**When** Story 14.1 is implemented
**Then** the following settings are added with section comments organizing the file:
- Player Defaults: `DEFAULT_BASE_HP=100`, `DEFAULT_ATTACK=10`, `DEFAULT_STAT_VALUE=1`
- Game Structure: `DEFAULT_SPAWN_ROOM="town_square"`, `STAT_CAP=10`, `LEVEL_UP_STAT_CHOICES=3`
- Combat: `COMBAT_HAND_SIZE=5`, `COMBAT_MIN_DAMAGE=1`
- NPC: `NPC_DEFAULT_HP_MULTIPLIER=10`, `NPC_ATTACK_DICE_MULTIPLIER=2`
- Auth: `MIN_USERNAME_LENGTH=3`, `MIN_PASSWORD_LENGTH=6`
- Trade: `TRADE_COOLDOWN_SECONDS=5`
- DB: `DB_POOL_SIZE=10`, `DB_MAX_OVERFLOW=20`, `DB_POOL_PRE_PING=True`
- Migration: `ALEMBIC_DATABASE_URL` auto-derived from `DATABASE_URL` (strips async driver prefix)
**And** `field_validator` guards exist for: `DEFAULT_BASE_HP >= 1`, `COMBAT_HAND_SIZE >= 1`, `COMBAT_MIN_DAMAGE >= 0`, `STAT_CAP >= 1`, `LEVEL_UP_STAT_CHOICES >= 1`, `DB_POOL_SIZE >= 1`

**Given** hardcoded value `100` (base HP) in `auth.py`, `levelup.py`, `movement.py`, `query.py`
**When** Story 14.1 is implemented
**Then** all occurrences reference `settings.DEFAULT_BASE_HP` instead of literal `100`
**And** the same replacement is applied for all other centralized values across their respective files

**Given** `app.py:259` using hardcoded `60` for mob respawn fallback
**When** Story 14.1 is implemented
**Then** it uses `settings.MOB_RESPAWN_SECONDS` (which already exists in config)

**Given** `trade/manager.py:64` using hardcoded `5` for trade cooldown
**When** Story 14.1 is implemented
**Then** it uses `settings.TRADE_COOLDOWN_SECONDS`

**Given** `_STATS_WHITELIST` in `player/repo.py` excludes `attack`
**When** Story 14.1 is implemented
**Then** a comment explains: "attack excluded — derived from STR/INT at runtime, not independently persisted"

**Given** all existing tests (800+)
**When** Story 14.1 is implemented
**Then** all tests pass with assertions unchanged (tests use literal values like `assert hp == 100`, not `settings.*`)

**Given** `test_integration.py`
**When** Story 14.1 begins
**Then** verify it covers the full gameplay loop (register → login → move → fight → loot → disconnect → reconnect → verify state); expand coverage if gaps exist

**Given** the config file after changes
**When** reviewed
**Then** a comment above player default settings states: "Player defaults: applied at registration only. Changing these does NOT retroactively update existing players in the database."

**Implementation notes:**
- ADR-14-6: Section comments in flat `BaseSettings` (no nested models)
- ADR-14-19: Validators for 6 critical settings only
- ~10-12 production files modified, 0 test assertion changes
- Update CLAUDE.md: "Game balance values must reference `settings.*`"

### Story 14.2: Data-Driven Loot Tables

As a developer,
I want loot tables defined in JSON data files instead of hardcoded Python dicts,
So that game content follows the architecture's JSON-driven configuration principle and loot can be modified without code changes.

**Acceptance Criteria:**

**Given** the hardcoded `LOOT_TABLES` dict in `server/items/loot.py`
**When** Story 14.2 is implemented
**Then** a `data/loot/loot_tables.json` file contains the same data in direct 1:1 JSON translation (list of `{item_key, quantity}` per table key)

**Given** the `item_repo.py` module
**When** Story 14.2 is implemented
**Then** a `load_loot_tables(data_dir: Path) -> dict` function loads and returns the JSON loot tables

**Given** `Game.startup()` initialization sequence
**When** Story 14.2 is implemented
**Then** loot tables are loaded after items (loot references item keys) and stored as `game.loot_tables`

**Given** all call sites that import or reference `LOOT_TABLES` from `server/items/loot.py`
**When** Story 14.2 is implemented
**Then** they reference `game.loot_tables` instead
**And** the `LOOT_TABLES` constant and `loot.py` module are deleted

**Given** all existing tests
**When** Story 14.2 is implemented
**Then** all tests pass; test fixtures that reference loot tables are updated to use the new data source

**Implementation notes:**
- ADR-14-2: Loader in `item_repo.py` (not a new repo file)
- ADR-14-15: Direct 1:1 JSON translation (no weighted drops)
- ~2-3 production files + 1 new JSON, 2-3 test files updated
- Small, self-contained, independently shippable

### Story 14.3a: Core Message Enrichment

As a game client developer,
I want server messages to include all data needed for display (entity IDs, HP values, NPC identifiers),
So that the client is a pure display layer with no need to construct IDs, assume game rules, or guess which NPC died.

**Acceptance Criteria:**

**Given** a successful login
**When** the server sends `login_success`
**Then** the message includes `entity_id` (e.g., `"player_1"`) as a field
**And** the existing `player_id` field is preserved (additive-only)

**Given** a player dies and respawns
**When** the server sends `respawn`
**Then** the message includes `hp` with the player's actual post-respawn HP value
**And** existing fields are preserved

**Given** a player completes level-up stat selection
**When** the server sends `level_up_complete`
**Then** the message includes `new_hp` with the player's actual current HP after recalculation
**And** existing fields (`level`, `new_max_hp`, `stat_changes`) are preserved

**Given** a player wins combat against an NPC
**When** the server sends `combat_end` with `result: "victory"`
**Then** the message includes `defeated_npc_id` with the NPC's entity ID string
**And** existing fields are preserved

**Given** each enriched message type
**When** the corresponding server code path executes
**Then** an existing test (not a new test file) asserts the new field is present and has the correct value

**Given** the web client
**When** Story 14.3a is implemented
**Then** the client is updated minimally to not break — uses new fields where trivial but does NOT require rewriting client logic

**Given** all emission code paths for each message type
**When** Story 14.3a is implemented
**Then** ALL code paths that emit each message type include the new field (verified by code path audit)

**Implementation notes:**
- ADR-14-14: Tests as message contract (add assertions to existing tests)
- 4 server files modified, 4-6 existing tests gain new assertions
- Minimal web client updates (don't rewrite proximity heuristic or respawn logic)
- Depends on 14.1 (no config references in this story, but must be sequenced after)

### Story 14.3b: XP & Stats Display Enrichment

As a game client developer,
I want server messages to include absolute XP totals, level thresholds, and stat effect descriptions,
So that the client displays XP progress and stat information without hardcoding the XP formula or stat bonus values.

**Acceptance Criteria:**

**Given** a player gains XP (combat, exploration, or interaction)
**When** the server sends `xp_gained`
**Then** the message includes `new_total_xp` (absolute XP total after gain)
**And** the existing `amount` field is preserved (additive-only)

**Given** a player requests stats or the server sends stat-related messages
**When** the server sends `stats_result` or `level_up_available`
**Then** the message includes `xp_for_next_level` and `xp_for_current_level` computed from the XP curve config

**Given** a player receives `level_up_available`
**When** the server sends the message
**Then** it includes `stat_effects` — a dict mapping each stat name to its effect description derived from config values (e.g., `{"constitution": "+5 max HP per point"}` using `settings.CON_HP_PER_POINT`)

**Given** each enriched message type
**When** the corresponding server code path executes
**Then** an existing test asserts the new fields are present with correct values

**Given** the web client
**When** Story 14.3b is implemented
**Then** the client is updated minimally — uses `new_total_xp` if trivial, but does NOT require rewriting the XP bar formula or stat description rendering

**Implementation notes:**
- Depends on 14.1 (stat descriptions reference config values like `CON_HP_PER_POINT`)
- 2-3 server files modified (`core/xp.py`, `handlers/query.py`)
- Same additive-only and test rules as 14.3a

### Story 14.4b: Room Accessors & Interact Signature

As a developer,
I want clean public APIs on `RoomInstance` and room objects knowing their own room,
So that no module accesses another module's private attributes, and interactive objects don't scan all rooms to find themselves.

**Acceptance Criteria:**

**Given** `RoomInstance` with private attributes `_entities`, `_npcs`, `_interactive_objects`
**When** Story 14.4b is implemented
**Then** read-only public properties `entities`, `npcs`, `interactive_objects` exist returning `MappingProxyType` views
**And** all handler code that accessed `room._entities`, `room._npcs`, `room._interactive_objects` uses the public properties instead

**Given** `InteractiveObject` base class and its subclasses (`ChestObject`, `LeverObject`)
**When** Story 14.4b is implemented
**Then** each object stores `self.room_key` set at creation time (passed by `RoomInstance` during object construction)
**And** `_get_room_key()` methods are deleted from `ChestObject` and `LeverObject`
**And** code that called `_get_room_key()` uses `self.room_key` instead

**Given** handlers in `movement.py` and `query.py` that access `room._interactive_objects` or `room._npcs`
**When** Story 14.4b is implemented
**Then** they use `room.interactive_objects` and `room.npcs` (public read-only accessors)

**Given** all existing tests
**When** Story 14.4b is implemented
**Then** all tests pass without assertion changes (pure refactor)

**Implementation notes:**
- ADR-14-3: `MappingProxyType` for zero-copy read-only enforcement
- ADR-14-13: `room_key` stored on object at creation (no `interact()` signature change)
- ~5-6 production files modified, 3-4 test files
- Independent — no dependencies on other Phase 2 stories

### Story 14.4a: PlayerSession Dataclass

As a developer,
I want `game.player_entities` to use a typed `PlayerSession` dataclass instead of untyped dicts,
So that IDE autocompletion works, typos in field names are caught at development time, and the most-accessed data structure in the codebase is type-safe.

**Acceptance Criteria:**

**Given** the need for a typed player session
**When** Story 14.4a is implemented
**Then** a `PlayerSession` dataclass exists with typed fields: `entity` (PlayerEntity), `room_key` (str), `db_id` (int), `inventory` (Inventory), `visited_rooms` (set[str]), `pending_level_ups` (int)
**And** `game.player_entities` is typed as `dict[str, PlayerSession]`

**Given** the two-phase migration approach
**When** Phase 1 is implemented
**Then** `PlayerSession` implements `__getitem__` mapping string keys to attributes
**And** all existing code (`player_info["entity"]`, `player_info["room_key"]`, etc.) continues to work unchanged
**And** all existing tests pass without modification

**Given** pre-implementation grep results for dict-specific patterns
**When** the grep is run before Phase 2
**Then** patterns checked include: `**player_info` (spread), `.copy()`, `isinstance(*, dict)`, `dict(player_info)`, `json.dumps` (serialization)
**And** Phase 2 scope is adjusted based on findings (implement full `Mapping` protocol if spread/copy patterns exist, or fix call sites)

**Given** Phase 2 migration
**When** all call sites are migrated to attribute access (`player_info.entity`, `player_info.room_key`)
**Then** `__getitem__` is removed from `PlayerSession`
**And** all tests pass (mock patterns updated to construct `PlayerSession(...)` instances)

**Given** all existing tests
**When** Story 14.4a is fully implemented (both phases)
**Then** all tests pass without assertion value changes (pure refactor — expected values unchanged, only mock construction patterns updated)

**Implementation notes:**
- ADR-14-1: Two-phase `__getitem__` compat bridge
- ADR-14-16: Both phases within single story (migration is mechanical)
- ~15-20 production files, ~15-20 test files (mock pattern updates)
- Largest story in the epic — budget accordingly

### Story 14.5: Decompose Handler Business Logic

As a developer,
I want thick handler functions broken into independently testable helpers,
So that combat resolution logic, NPC template access, and respawn orchestration are readable, testable, and maintainable.

**Acceptance Criteria:**

**Given** `_check_combat_end` in `server/net/handlers/combat.py` (133 lines)
**When** Story 14.5 is implemented
**Then** it is decomposed into module-level helper functions within `combat.py` (suggested: `_award_combat_xp`, `_distribute_combat_loot`, `_handle_player_defeat`, `_cleanup_combat_state`)
**And** each helper receives `game` as a parameter and handles one responsibility
**And** `_check_combat_end` becomes a thin orchestrator calling the helpers

**Given** `scheduler.py` importing `_NPC_TEMPLATES` from `server.room.objects.npc`
**When** Story 14.5 is implemented
**Then** `Game` exposes `self.npc_templates` as a public attribute (set during startup)
**And** `scheduler.py` accesses `self.game.npc_templates` instead of the module-level import
**And** the cross-module `_NPC_TEMPLATES` import is removed

**Given** `game.respawn_player()` in `app.py` (~80 lines) — bonus objective
**When** time permits within Story 14.5
**Then** it is decomposed into helpers within `app.py` (suggested: `_reset_player_stats`, `_transfer_to_spawn`, `_broadcast_respawn`)
**And** if the story is already complex, this decomposition is deferred

**Given** all existing tests
**When** Story 14.5 is implemented
**Then** all tests pass without assertion changes (pure refactor)

**Implementation notes:**
- ADR-14-4: Module-level functions in `combat.py` (no new files, no service class)
- ADR-14-8: `game.npc_templates` attribute (follows existing composition root pattern)
- `respawn_player` decomposition is explicitly droppable
- Depends on 14.4a (helpers use `PlayerSession` type)

### Story 14.6: Concurrency Safety

As a developer,
I want trade execution and NPC encounter initiation protected by async locks,
So that concurrent WebSocket coroutines cannot cause TOCTOU race conditions at `await` yield points.

**Acceptance Criteria:**

**Given** `NpcEntity` dataclass
**When** Story 14.6 is implemented
**Then** it has a `_lock: asyncio.Lock` field (created via `field(default_factory=asyncio.Lock, repr=False, compare=False)`)
**And** the NPC encounter handler acquires `npc._lock` before checking `in_combat` and releases after setting it
**And** the critical section is short (protects only the check-and-set, not the full encounter setup)

**Given** `TradeManager`
**When** Story 14.6 is implemented
**Then** it has a `_trade_locks: dict[tuple, asyncio.Lock]` keyed by sorted player ID pairs
**And** `_execute_trade` acquires the lock before inventory validation and releases after the DB write
**And** the critical section is short (protects validation-through-write, not the full trade session)

**Given** two coroutines simultaneously moving onto the same NPC
**When** both attempt to initiate combat
**Then** only one enters combat; the other receives an appropriate response (NPC already in combat)

**Given** two coroutines simultaneously executing a trade
**When** both race through validation and DB write
**Then** the lock serializes access — one completes first, the second sees updated inventory

**Given** the `asyncio.gather` test pattern
**When** concurrency tests are written
**Then** at least 2 tests use `asyncio.gather` to verify lock behavior (one for NPC encounter, one for trade)

**Implementation notes:**
- ADR-14-7: NPC lock on dataclass, trade lock dict on TradeManager
- Short critical sections only — don't lock entire encounter/trade flows
- Independent — no dependencies on other stories
- New test pattern for this codebase; document for future reference

### Story 14.7: Database Migration & PostgreSQL Readiness

As a developer,
I want Alembic schema migrations, connection pooling config, and timezone-correct datetimes,
So that the database layer supports schema evolution and is ready for a future PostgreSQL swap.

**Acceptance Criteria:**

**Given** the project has no Alembic setup
**When** Story 14.7 is implemented
**Then** `alembic/` directory, `alembic.ini`, and `env.py` exist configured for sync Alembic using `settings.ALEMBIC_DATABASE_URL`
**And** an auto-generated initial migration represents the current schema
**And** running `alembic upgrade head` on a fresh database produces a schema identical to `create_all`
**And** a migration roundtrip test verifies this equivalence

**Given** `Base.metadata.create_all` in `database.py`
**When** Story 14.7 is implemented
**Then** `create_all` is preserved alongside Alembic (not removed)

**Given** `Makefile`
**When** Story 14.7 is implemented
**Then** a `make db-migrate` target exists for running Alembic migrations

**Given** `create_async_engine` in `database.py` with no pool config
**When** Story 14.7 is implemented
**Then** pool settings (`pool_size`, `max_overflow`, `pool_pre_ping`) from config are applied conditionally — only when the URL is not SQLite

**Given** `SpawnCheckpoint` with `DateTime` columns using `datetime.now(UTC).replace(tzinfo=None)`
**When** Story 14.7 is implemented
**Then** all datetime usage is timezone-aware (`datetime.now(UTC)` without stripping)
**And** the `DateTime(timezone=True)` column type is used
**And** the initial Alembic migration includes this column type

**Given** the decomposed combat helpers from Story 14.5
**When** Story 14.7 is implemented
**Then** per-participant transactions in combat resolution are consolidated from 3-4 per participant to 1 per participant
**And** per-participant isolation is preserved (participant A's failure does not roll back participant B)

**Given** all existing tests
**When** Story 14.7 is implemented
**Then** all tests pass

**Implementation notes:**
- ADR-14-5: Sync Alembic with derived URL (no async quirks)
- ADR-14-9: Merge transactions per participant (3→1), keep isolation
- ADR-14-11: Pool settings conditional on driver
- ADR-14-12: UTC-aware datetimes
- ADR-14-18: Auto-generate initial migration; dev DBs deleted and recreated
- ADR-14-21: Keep `create_all` alongside Alembic
- Future debt noted: sync Alembic creates two connection paths in PostgreSQL production
- Depends on 14.5 (transaction consolidation in decomposed helpers)

---

All 9 stories for Epic 14 are now written. Here's the summary:

| Story | Title | ACs | Status |
|-------|-------|-----|--------|
| 14.1 | Centralize Game Parameters in Config | 8 | Written |
| 14.2 | Data-Driven Loot Tables | 5 | Written |
| 14.3a | Core Message Enrichment | 7 | Written |
| 14.3b | XP & Stats Display Enrichment | 5 | Written |
| 14.4b | Room Accessors & Interact Signature | 4 | Written |
| 14.4a | PlayerSession Dataclass | 5 | Written |
| 14.5 | Decompose Handler Business Logic | 4 | Written |
| 14.6 | Concurrency Safety | 5 | Written |
| 14.7 | Database Migration & PostgreSQL Readiness | 7 | Written |

**FR coverage verified:** All 24 FRs (FR94-FR117) mapped to stories. FR118 in backlog.

Does the complete set look good? Any stories need adjustment before I save them all?

Players can register an account, login via WebSocket, and enter a room — seeing the full tile map, other players, and objects. This epic delivers the foundational systems: project scaffolding, database models, persistence layer, networking, authentication, and room loading.

### Story 1.1: Project Scaffolding & Configuration

As a developer,
I want the project directory structure, dependencies, and configuration in place,
So that all future stories have a consistent foundation to build on.

**Acceptance Criteria:**

**Given** the project repository exists
**When** the scaffolding story is complete
**Then** the domain-driven directory structure exists (core/, net/, player/, room/, combat/, items/, web/ under server/)
**And** pyproject.toml defines all dependencies (FastAPI, uvicorn, SQLAlchemy, aiosqlite, pydantic, pydantic-settings, bcrypt)
**And** dev dependencies are defined (pytest, pytest-asyncio, httpx)
**And** run.py starts the server via uvicorn
**And** server/core/config.py provides Pydantic BaseSettings with HOST, PORT, DEBUG, DATABASE_URL, DATA_DIR, MOB_RESPAWN_SECONDS, COMBAT_TURN_TIMEOUT_SECONDS, MAX_PLAYERS_PER_ROOM
**And** all __init__.py files are created for every package
**And** `pip install -e ".[dev]"` succeeds without errors

### Story 1.2: Database Engine & Base Models

As a developer,
I want the async database engine and all data models defined,
So that persistence is available for all domain features.

**Acceptance Criteria:**

**Given** the project scaffolding from Story 1.1 is in place
**When** the database models story is complete
**Then** core/database.py provides an async engine, session factory, and init_db() function
**And** Player model exists with columns: id, username (unique, indexed), password_hash, stats (JSON), inventory (JSON), card_collection (JSON), current_room_id, position_x, position_y
**And** Room model exists with columns: id, room_key (unique, indexed), name, schema_version, width, height, tile_data (JSON), exits (JSON), objects (JSON), spawn_points (JSON)
**And** RoomState model exists with columns: id, room_key (unique, indexed), mob_states (JSON), dynamic_state (JSON)
**And** PlayerObjectState model exists with columns: id, player_id, room_key, object_id, state_data (JSON) with unique constraint on (player_id, room_key, object_id)
**And** Card model exists with columns: id, card_key (unique, indexed), name, cost, effects (JSON list), description
**And** SpawnCheckpoint model exists with columns: id, npc_key, room_key, last_check_at, next_check_at, currently_spawned
**And** calling init_db() creates all tables in SQLite

### Story 1.3: Persistence Repositories

As a developer,
I want repository classes for Player, Room, and Card data access,
So that domain logic can read/write data without direct SQL.

**Acceptance Criteria:**

**Given** database models from Story 1.2 exist
**When** the persistence story is complete
**Then** player/repo.py provides get_by_username, get_by_id, create, save, update_position methods
**And** room/repo.py provides get_by_key, get_state, save_state methods
**And** room/provider.py defines a RoomProvider interface with a load_rooms() method
**And** a JsonRoomProvider implementation loads room JSON files from data/rooms/ into the database
**And** combat/cards/card_repo.py provides get_by_key, get_all, load_cards_from_json methods
**And** all repos use async sessions and do not leak connections

### Story 1.4: Tile System & Room Instance

As a developer,
I want the tile type system and room instance class,
So that rooms can represent a 100x100 grid with entities and movement validation.

**Acceptance Criteria:**

**Given** persistence repos from Story 1.3 exist
**When** the tile and room instance story is complete
**Then** room/tile.py defines TileType enum (floor, wall, exit, mob_spawn, water) with walkability rules
**And** WALKABLE_TILES contains floor, exit, mob_spawn
**And** room/room.py provides a Room class that builds a tile grid from 2D tile data
**And** Room supports add_entity, remove_entity, get_entities_at, get_player_spawn, get_player_ids
**And** Room.move_entity validates direction, checks bounds, checks walkability, returns result dict
**And** Room.move_entity returns exit info when stepping on exit tile
**And** Room.move_entity returns mob_encounter when stepping on a tile with an alive hostile mob
**And** Room.get_state returns a serializable snapshot of room_key, name, dimensions, tiles, entities, exits
**And** player/entity.py defines PlayerEntity dataclass with id, name, x, y, player_db_id, stats, in_combat flag
**And** room/manager.py provides RoomManager with get_room, load_room, unload_room, transfer_entity methods

### Story 1.5: WebSocket Connection & Message Routing

As a player,
I want to connect to the game server via WebSocket and have my messages routed to the correct handler,
So that I can communicate with the server in real-time.

**Acceptance Criteria:**

**Given** the server is running
**When** a client connects to /ws/game
**Then** the WebSocket connection is accepted
**And** the client can send JSON messages with an "action" field
**And** messages are routed to the correct handler based on the "action" value
**And** unknown actions return an error message: {"type": "error", "detail": "Unknown action: {action}"}
**And** malformed JSON returns an error message: {"type": "error", "detail": "Invalid JSON"}
**And** messages missing the "action" field return an error
**And** net/connection_manager.py tracks WebSocket-to-player-entity-ID mappings
**And** net/connection_manager.py supports send_to_player and broadcast_to_room

### Story 1.6: Player Registration

As a new player,
I want to create an account with a username and password,
So that I can start playing the game.

**Acceptance Criteria:**

**Given** a client is connected via WebSocket
**When** the client sends {"action": "register", "username": "hero", "password": "secret123"}
**Then** a new player is created in the database with bcrypt-hashed password
**And** the client receives {"type": "login_success", "player_id": 1, "username": "hero"}

**Given** a client sends a register action with username shorter than 3 characters
**When** the server processes the message
**Then** the client receives an error: "Username must be at least 3 characters"

**Given** a client sends a register action with password shorter than 6 characters
**When** the server processes the message
**Then** the client receives an error: "Password must be at least 6 characters"

**Given** a client sends a register action with a username that already exists
**When** the server processes the message
**Then** the client receives an error: "Username already taken"

### Story 1.7: Player Login & Room Entry

As a returning player,
I want to login and be placed in my last room seeing the full map,
So that I can continue playing where I left off.

**Acceptance Criteria:**

**Given** a registered player exists with username "hero"
**When** the client sends {"action": "login", "username": "hero", "password": "secret123"}
**Then** the password is verified against the bcrypt hash
**And** a PlayerEntity is created with the player's saved position and stats
**And** the entity is placed in the player's current_room_id
**And** the client receives {"type": "login_success", "player_id": 1, "username": "hero"}
**And** the client receives a room_state message with the full tile grid, all entities, and objects
**And** other players in the room receive an entity_entered message with the new player's info

**Given** a client sends login with invalid credentials
**When** the server processes the message
**Then** the client receives an error: "Invalid username or password"

**Given** a client sends login with empty username or password
**When** the server processes the message
**Then** the client receives an error: "Username and password required"

### Story 1.8: Game Orchestrator & Server Lifecycle

As a developer,
I want the Game class to tie all managers together with proper startup/shutdown,
So that the server initializes everything correctly and handles player disconnects.

**Acceptance Criteria:**

**Given** the server starts up
**When** the Game.startup() method runs
**Then** the database is initialized (tables created)
**And** rooms are loaded from JSON via JsonRoomProvider into the database and then into memory
**And** card definitions are loaded from JSON into the database
**And** all message handlers are registered with the MessageRouter
**And** the health check endpoint at GET /health returns {"status": "ok"}

**Given** a logged-in player disconnects
**When** the WebSocket connection closes
**Then** the player's current position is saved to the database
**And** the player's entity is removed from the room
**And** other players in the room receive an entity_left message
**And** the player is removed from player_entities tracking

**Given** the server shuts down
**When** Game.shutdown() is called
**Then** all active timers are cancelled
**And** resources are cleaned up gracefully

---

## Epic 2: Movement & Room Exploration

Players can move around the tile grid, encounter obstacles (walls, static objects like rocks and trees), transition between rooms via exit tiles, see other players moving, and chat with them.

### Story 2.1: Player Movement & Collision

As a player,
I want to move in four directions on the tile grid and be blocked by walls and obstacles,
So that I can explore the room within its boundaries.

**Acceptance Criteria:**

**Given** a logged-in player is in a room at position (5, 5)
**When** the client sends {"action": "move", "direction": "right"}
**Then** the player's position updates to (6, 5)
**And** all players in the room receive {"type": "entity_moved", "entity_id": "player_1", "x": 6, "y": 5}

**Given** a player attempts to move into a wall tile
**When** the server processes the move
**Then** the client receives an error: "Tile not walkable"
**And** the player's position does not change

**Given** a player attempts to move out of bounds
**When** the server processes the move
**Then** the client receives an error: "Out of bounds"

**Given** a player sends an invalid direction (e.g., "northwest")
**When** the server processes the move
**Then** the client receives an error: "Invalid direction: northwest"

**Given** a player is in combat
**When** the player attempts to move
**Then** the client receives an error: "Cannot move while in combat"

### Story 2.2: Static Room Objects

As a player,
I want to see trees, rocks, and other terrain features in the room,
So that the world feels like a real environment with natural obstacles.

**Acceptance Criteria:**

**Given** a room JSON defines static objects in its "objects" array (e.g., {"type": "rock", "x": 3, "y": 4, "category": "static"})
**When** the room is loaded
**Then** static objects are placed on the tile grid
**And** tiles occupied by blocking static objects are marked as non-walkable
**And** the room_state message includes the objects list

**Given** a player attempts to move onto a tile with a blocking static object (rock)
**When** the server processes the move
**Then** the client receives an error: "Tile not walkable"

**Given** a room has decorative static objects (e.g., flowers that don't block)
**When** a player moves onto that tile
**Then** the move succeeds normally

### Story 2.3: Room Transitions via Exit Tiles

As a player,
I want to walk onto an exit tile and be transported to another room,
So that I can explore the larger world across multiple zones.

**Acceptance Criteria:**

**Given** a player is adjacent to an exit tile that leads to "dark_cave"
**When** the player moves onto the exit tile
**Then** the player is removed from the current room
**And** other players in the old room receive an entity_left message
**And** the player is placed in "dark_cave" at the configured entry coordinates
**And** the player receives a room_state message with the new room's full data
**And** other players in the new room receive an entity_entered message
**And** the player's position and current_room_id are saved to the database

**Given** an exit tile references a room that doesn't exist in the database
**When** the player steps on it
**Then** the client receives an error: "Exit leads nowhere"
**And** the player's position does not change

### Story 2.4: Room Chat & Whispers

As a player,
I want to chat with other players in my room or whisper to a specific player,
So that I can communicate and coordinate with others.

**Acceptance Criteria:**

**Given** a player sends {"action": "chat", "message": "Hello everyone!"}
**When** the server processes the chat
**Then** all players in the same room receive {"type": "chat", "sender": "hero", "message": "Hello everyone!", "whisper": false}

**Given** a player sends {"action": "chat", "message": "Secret info", "whisper_to": "player_2"}
**When** the server processes the whisper
**Then** only the target player receives the chat message with whisper: true
**And** the sender also receives a copy of their whisper

**Given** a player sends a chat with an empty message
**When** the server processes it
**Then** the message is ignored (no broadcast)

**Given** a player is not logged in
**When** they send a chat action
**Then** the client receives an error: "Not logged in"

---

## Epic 3: Room Objects & NPC Spawning

The world becomes alive — players encounter interactive objects (chests with permanent one-time loot, levers that change room state), hostile NPCs spawn on configurable timers, and rare/epic NPC spawns trigger global announcements to all connected players.

### Story 3.1: Interactive Object Framework

As a player,
I want to interact with objects in the room that respond to my actions,
So that the world feels dynamic and explorable.

**Acceptance Criteria:**

**Given** a room contains interactive objects defined in its JSON
**When** a player sends {"action": "interact", "target_id": "chest_01"}
**Then** the server identifies the object and delegates to the appropriate interaction handler
**And** the client receives an interact_result message with the outcome

**Given** a player tries to interact with an object that doesn't exist
**When** the server processes the interact action
**Then** the client receives an error: "Object not found"

**Given** an interactive object has state_scope "player"
**When** the object's state is read
**Then** the state is loaded from PlayerObjectState for that specific player

**Given** an interactive object has state_scope "room"
**When** the object's state is read
**Then** the state is loaded from RoomState.dynamic_state, shared across all players

### Story 3.2: Chests with One-Time Loot

As a player,
I want to open chests and receive loot that's unique to me,
So that I'm rewarded for exploring the world.

**Acceptance Criteria:**

**Given** a player interacts with a chest they haven't opened before
**When** the server processes the interaction
**Then** loot is generated from the chest's configured loot_table
**And** the loot is added to the player's inventory
**And** a PlayerObjectState record is created marking this chest as opened for this player
**And** the client receives an interact_result with the loot received

**Given** a player interacts with a chest they have already opened
**When** the server processes the interaction
**Then** the client receives an interact_result: "Already looted"
**And** no items are added to inventory

**Given** Player A opens a chest
**When** Player B interacts with the same chest
**Then** Player B can open it independently and receive their own loot
**And** Player A's state is unaffected

### Story 3.3: Levers & Room-Shared State

As a player,
I want to pull levers that change the room for everyone,
So that I can solve environmental puzzles and open paths.

**Acceptance Criteria:**

**Given** a lever with config {"target": "gate_1", "action": "toggle"} exists in a room
**When** a player interacts with the lever
**Then** the target tile (gate_1) toggles between wall and floor
**And** the lever state is persisted to RoomState.dynamic_state
**And** all players in the room receive a state update with the changed tile
**And** the client receives an interact_result confirming the action

**Given** a lever has already been toggled to "on"
**When** a player interacts with it again
**Then** it toggles back to "off"
**And** the target tile reverts to its original state

### Story 3.4: NPC Entity & Hostile Behavior

As a player,
I want to encounter hostile NPCs placed in rooms,
So that the world has threats to fight.

**Acceptance Criteria:**

**Given** a room's configuration references NPC templates from data/npcs/
**When** the room is loaded
**Then** NPC entities are created with stats, behavior_type, and loot_table from the template
**And** NPCs appear in the room_state broadcast with their position and type

**Given** an NPC has behavior_type "hostile" and is alive
**When** a player moves onto the NPC's tile
**Then** the movement result includes mob_encounter with the NPC's entity ID
**And** this triggers combat initiation (handled in Epic 4)

**Given** an NPC has been killed (is_alive = false)
**When** a player moves onto its tile
**Then** no mob_encounter is triggered

### Story 3.5: Tiered NPC Spawn System

As a player,
I want NPCs to respawn after being killed and rare world bosses to appear on a schedule,
So that the world feels persistent and there are always things to fight.

**Acceptance Criteria:**

**Given** an NPC with spawn_type "persistent" is killed
**When** the configured respawn_seconds elapses
**Then** the NPC respawns at its original position with full HP
**And** players in the room receive an entity_entered message

**Given** an NPC with spawn_type "rare" has a check_interval_hours of 12 and spawn_chance of 0.15
**When** the scheduler runs the spawn check
**Then** a random roll determines if the NPC spawns (15% chance)
**And** the SpawnCheckpoint is updated with last_check_at and next_check_at
**And** if spawned, the NPC appears in the configured room

**Given** the server restarts
**When** the scheduler loads SpawnCheckpoints from the database
**Then** spawn timers resume from where they left off (not reset to zero)
**And** if a check was due during downtime, it runs on startup

**Given** a rare NPC has max_active: 1 and is already spawned
**When** the scheduler runs another check
**Then** no additional instance spawns

### Story 3.6: Global Rare Spawn Announcements

As a player,
I want to be notified when a rare or epic NPC spawns anywhere in the world,
So that I can race to find it before others.

**Acceptance Criteria:**

**Given** a rare NPC spawns in "Dark Cave"
**When** the spawn event fires
**Then** ALL connected players receive {"type": "announcement", "message": "An Ancient Forest Dragon has appeared in Dark Cave!"}
**And** the announcement is not limited to players in that room

**Given** core/events.py defines an EventBus
**When** a rare spawn event is emitted
**Then** the EventBus broadcasts the announcement through ConnectionManager to all connected WebSockets

**Given** no players are connected
**When** a rare NPC spawns
**Then** the spawn still occurs but no announcement is sent (no error)

---

## Epic 4: Turn-Based Card Combat

When a player encounters a hostile mob, turn-based card combat begins. Players draw cards, play them to deal damage/heal/shield via a multi-effect system, pass turns, or flee. Combat resolves with victory (rewards) or defeat. The shared effect registry is established as a core service.

### Story 4.1: Shared Effect Registry

As a developer,
I want a central effect resolution system that both cards and items can use,
So that all combat effects are handled consistently and new effect types are easy to add.

**Acceptance Criteria:**

**Given** the effect registry is initialized
**When** an effect with type "damage" and value 20 is resolved against a target with 100 HP
**Then** the target's HP is reduced to 80

**Given** an effect with type "heal" and value 15 is resolved on a player with 85/100 HP
**When** the effect resolves
**Then** the player's HP increases to 100 (capped at max_hp)

**Given** an effect with type "shield" and value 12 is resolved on a player
**When** the effect resolves
**Then** the player gains 12 shield points that absorb future damage

**Given** an effect with type "dot" (damage over time), subtype "poison", value 4, duration 3
**When** the effect resolves
**Then** the target takes 4 damage per turn for 3 turns

**Given** an effect with type "draw" and value 2 is resolved during combat
**When** the effect resolves
**Then** the player draws 2 additional cards from their deck

**Given** a new effect type needs to be added
**When** a developer creates a new handler file and registers it
**Then** cards and items can reference the new effect_type in JSON without any other code changes

### Story 4.2: Card Definitions & Hand Management

As a player,
I want to draw cards from a deck into my hand and have played cards cycle through a discard pile,
So that combat has strategic variety with each encounter.

**Acceptance Criteria:**

**Given** a CardDef with effects: [{"type": "damage", "subtype": "fire", "value": 20}]
**When** the card is loaded from JSON
**Then** the effects field is a list of effect objects (not a single effect_type/effect_value)

**Given** a deck of 15 cards and hand_size of 5
**When** a CardHand is created
**Then** 5 cards are drawn from the shuffled deck into the hand

**Given** a player plays a card from their hand
**When** the card is played
**Then** the card moves to the discard pile
**And** a new card is drawn from the deck to replace it
**And** the hand size remains at 5 (if cards remain in deck)

**Given** the deck is empty and a draw is needed
**When** a card needs to be drawn
**Then** the discard pile is shuffled back into the deck
**And** a card is drawn from the reshuffled deck

**Given** a player tries to play a card not in their hand
**When** the play is attempted
**Then** it returns an error: "Card not in hand"

### Story 4.3: Combat Instance & Turn Structure

As a player,
I want turn-based combat where I choose one action per turn — play a card, or pass,
So that combat is strategic and I make meaningful decisions each turn.

**Acceptance Criteria:**

**Given** a CombatInstance is created with a mob and card definitions
**When** a player is added as a participant
**Then** the player is marked as in_combat
**And** a CardHand is created for the player from the card definitions
**And** the player is added to the turn order

**Given** it is a player's turn
**When** the player plays a card
**Then** the turn advances to the next participant
**And** when all participants have acted (full cycle), the mob attacks a random player

**Given** it is a player's turn
**When** the player passes
**Then** the mob attacks the passing player
**And** the turn advances to the next participant

**Given** it is NOT a player's turn
**When** the player tries to play a card or pass
**Then** they receive an error: "Not your turn"

**Given** two players are in combat
**When** turns progress
**Then** they alternate: Player 1 → Player 2 → mob attacks random → Player 1 → ...

### Story 4.4: Card Effect Resolution

As a player,
I want my cards to deal damage, heal me, raise shields, and apply effects to the mob,
So that different cards create different tactical outcomes.

**Acceptance Criteria:**

**Given** a player plays a card with effects: [{"type": "damage", "value": 20}]
**When** the card resolves
**Then** each effect in the list is resolved sequentially through the EffectRegistry
**And** the mob's HP is reduced by 20

**Given** a player plays a card with effects: [{"type": "heal", "value": 15}]
**When** the card resolves
**Then** the player's HP is restored by 15 (capped at max)

**Given** a player has 12 shield points and the mob attacks for 8 damage
**When** the damage resolves
**Then** 8 shield points are consumed and the player takes 0 HP damage
**And** remaining shield is 4

**Given** a player has 5 shield points and the mob attacks for 12 damage
**When** the damage resolves
**Then** all 5 shield points are consumed and the player takes 7 HP damage

**Given** a card with multiple effects: [{"type": "damage", "value": 10}, {"type": "heal", "value": 5}]
**When** the card resolves
**Then** the mob takes 10 damage AND the player heals 5 HP

### Story 4.5: Combat Resolution & Rewards

As a player,
I want to win combat by defeating the mob and receive XP rewards, or lose and face consequences,
So that combat has meaningful stakes.

**Acceptance Criteria:**

**Given** a card play reduces the mob's HP to 0 or below
**When** the combat resolves
**Then** combat is marked as finished with victory: true
**And** all participants receive {"type": "combat_end", "victory": true, "rewards": {"xp": 25}}
**And** all participants are marked as in_combat: false
**And** mob respawn is scheduled via the spawn system

**Given** all players' HP reaches 0
**When** the combat resolves
**Then** combat is marked as finished with victory: false
**And** all participants receive {"type": "combat_end", "victory": false, "rewards": {}}
**And** all participants are marked as in_combat: false

**Given** combat ends (victory or defeat)
**When** cleanup runs
**Then** the CombatInstance is removed from CombatManager
**And** all player-to-instance mappings are cleaned up

### Story 4.6: Flee Combat

As a player,
I want to flee from combat if it's too dangerous,
So that I can avoid death and try again later.

**Acceptance Criteria:**

**Given** a player is in combat
**When** the player sends {"action": "flee"}
**Then** the player is removed from the CombatInstance
**And** the player's in_combat flag is set to false
**And** the player receives {"type": "combat_fled"}

**Given** a player flees and other participants remain
**When** the flee resolves
**Then** combat continues for the remaining participants
**And** remaining participants receive an updated combat state

**Given** the last participant flees
**When** the flee resolves
**Then** combat ends (no victory, no defeat)
**And** the CombatInstance is cleaned up

**Given** a player is not in combat
**When** the player sends a flee action
**Then** the client receives an error: "Not in combat"

### Story 4.7: Combat Entry from Mob Encounter

As a player,
I want combat to start automatically when I walk into a hostile mob,
So that exploration seamlessly leads to encounters.

**Acceptance Criteria:**

**Given** a player moves onto a tile with an alive hostile NPC
**When** the movement result includes mob_encounter
**Then** a CombatInstance is created via CombatManager with the mob and loaded card definitions
**And** the player is added as a participant
**And** the mob is marked as not alive (in combat)
**And** the player receives {"type": "combat_start", "instance_id": "...", "participants": [...], "mob": {"name": "...", "hp": ...}}
**And** the player receives a combat_turn message with current_player, hand, mob_hp, player_hps

**Given** combat is started
**When** the combat action handlers (play_card, pass_turn, flee) are invoked
**Then** they correctly find the CombatInstance for the player and process the action

**Given** a mob is already in combat (is_alive = false)
**When** another player moves onto its tile
**Then** no additional combat is triggered

---

## Epic 5: Items & Inventory

Players can collect items from chests, manage an inventory with unlimited stacking, and use consumable items both during combat (as their one action per turn, alternative to playing a card) and outside combat (healing between fights). Items share the same effect registry as cards.

### Story 5.1: Item Definitions & Loading

As a developer,
I want item definitions loaded from JSON with category, charges, and effect chains,
So that the game can support diverse item types through configuration.

**Acceptance Criteria:**

**Given** data/items/base_items.json exists with item definitions
**When** items are loaded on server startup
**Then** each item has: item_key, name, category (consumable|material), stackable flag, charges, effects list, usable_in_combat flag, usable_outside_combat flag, description
**And** item effects use the same format as card effects: [{"type": "heal", "value": 25}]
**And** items are accessible by item_key for lookup

**Given** base_items.json includes Healing Potion (heal 25, 3 charges, usable in/out combat), Antidote (cure poison, 1 charge), Fire Essence (material, non-usable), Iron Shard (material, non-usable)
**When** the items are loaded
**Then** all four items are available with correct properties

### Story 5.2: Player Inventory Management

As a player,
I want to view my inventory and have items stack without limits,
So that I can collect materials and consumables without worrying about space.

**Acceptance Criteria:**

**Given** a player has 3 Healing Potions and picks up 2 more
**When** the inventory is updated
**Then** the player has 5 Healing Potions (stacked, not separate entries)

**Given** a player sends {"action": "inventory"}
**When** the server processes the request
**Then** the player receives their full inventory with item details (name, quantity, charges, category)

**Given** a player uses the last charge of a consumable
**When** the charge is consumed
**Then** the item quantity is decremented by 1
**And** if quantity reaches 0, the item is removed from inventory

**Given** a player picks up a new item type they don't have
**When** the item is added
**Then** a new inventory entry is created with quantity 1

### Story 5.3: Use Items Outside Combat

As a player,
I want to use a healing potion between fights,
So that I can recover without needing to find a mob to fight.

**Acceptance Criteria:**

**Given** a player has a Healing Potion (usable_outside_combat: true) and is not in combat
**When** the player sends {"action": "use_item", "item_key": "healing_potion"}
**Then** the item's effects are resolved through the shared EffectRegistry
**And** the player's HP increases by the heal value (capped at max_hp)
**And** one charge is consumed from the item
**And** the player receives a result message confirming the effect

**Given** a player tries to use a material item (usable_outside_combat: false)
**When** the server processes the action
**Then** the client receives an error: "This item cannot be used"

**Given** a player tries to use an item they don't have in inventory
**When** the server processes the action
**Then** the client receives an error: "Item not in inventory"

**Given** a player is in combat and tries to use use_item action outside combat handler
**When** the server processes the action
**Then** the client receives an error: "Cannot use items this way during combat"

### Story 5.4: Use Items During Combat

As a player,
I want to use a consumable item as my combat action instead of playing a card,
So that I have a safety net when my card hand is bad.

**Acceptance Criteria:**

**Given** it is a player's turn in combat and they have a Healing Potion (usable_in_combat: true)
**When** the player sends {"action": "use_item", "item_key": "healing_potion"} during combat
**Then** the item's effects are resolved through the shared EffectRegistry
**And** one charge is consumed
**And** the turn advances to the next participant (same as playing a card)
**And** all participants receive an updated combat_turn message

**Given** a player tries to use an item during combat that has usable_in_combat: false
**When** the server processes the action
**Then** the client receives an error: "This item cannot be used in combat"

**Given** it is NOT the player's turn
**When** they send a use_item action
**Then** the client receives an error: "Not your turn"

**Given** a player's turn in combat
**When** they use an item
**Then** they cannot also play a card that turn (one action only)

---

## Epic 6: Integration, Sample Data & Testing

The complete prototype gameplay loop works end-to-end with sample content — two rooms (Town Square, Dark Cave), a 15-card base set, consumable items, hostile NPCs. Comprehensive test suite covers all systems. Full gameplay loop verified: Register → Login → Explore → Interact → Combat → Collect → Transition.

### Story 6.1: Sample Room Data

As a developer,
I want two fully configured room JSON files with tiles, objects, NPCs, and exits,
So that the gameplay loop has real content to test against.

**Acceptance Criteria:**

**Given** data/rooms/town_square.json exists
**When** it is loaded
**Then** it defines a 100x100 room named "Town Square"
**And** it includes player spawn points, floor tiles, wall borders
**And** it includes static objects (trees, rocks as decoration/blocking)
**And** it includes chests with loot_table configs (state_scope: player)
**And** it includes at least one lever (state_scope: room)
**And** it includes exit tiles leading south to "dark_cave"
**And** it does NOT include hostile NPCs (safe zone)

**Given** data/rooms/dark_cave.json exists
**When** it is loaded
**Then** it defines a 100x100 room named "Dark Cave"
**And** it includes hostile NPC references (Slime: timed respawn, Cave Troll: rare spawn)
**And** it includes chests with loot
**And** it includes exit tiles leading north back to "town_square"
**And** it includes static objects (rocks, stalagmites)

**Given** data/npcs/base_npcs.json exists
**When** it is loaded
**Then** it includes Slime (persistent, respawn 60s, low stats) and Cave Troll (rare, 12-hour check, 15% chance, high stats)

### Story 6.2: Sample Cards & Items Data

As a developer,
I want a base card set and starter items defined in JSON,
So that combat and inventory systems have content to work with.

**Acceptance Criteria:**

**Given** data/cards/base_set.json exists
**When** it is loaded
**Then** it contains 15 cards using the multi-effect format
**And** cards include: damage cards (fire/physical subtypes), heal cards, shield cards, poison DoT card, draw card
**And** each card has card_key, name, cost, effects (list), description

**Given** data/items/base_items.json exists
**When** it is loaded
**Then** it contains at minimum: Healing Potion (heal 25, 3 charges, usable in/out combat), Antidote (removes poison, 1 charge), Fire Essence (material), Iron Shard (material)
**And** each item has item_key, name, category, stackable, charges, effects, usable_in_combat, usable_outside_combat, description

### Story 6.3: End-to-End Startup & Gameplay Wiring

As a developer,
I want the Game orchestrator to initialize all systems in the correct order and wire everything together,
So that the full gameplay loop works from server start to player disconnect.

**Acceptance Criteria:**

**Given** the server starts with sample data in place
**When** Game.startup() completes
**Then** the database is initialized with all tables
**And** rooms are loaded from JSON (town_square, dark_cave) into DB and memory
**And** NPCs are spawned in their configured rooms
**And** cards and items are loaded from JSON
**And** the scheduler starts (spawn checks running)
**And** all handlers are registered (login, register, move, chat, interact, play_card, use_item, pass_turn, flee, inventory)
**And** GET /health returns {"status": "ok"}

**Given** all systems are wired together
**When** a player registers, logs in, moves, interacts with a chest, encounters a mob, fights with cards, uses an item, flees or wins, and transitions rooms
**Then** each action works correctly without errors
**And** other connected players receive appropriate broadcasts

### Story 6.4: Core System Unit Tests

As a developer,
I want unit tests for room, tile, movement, entity, and object systems,
So that the world simulation is verified to work correctly.

**Acceptance Criteria:**

**Given** tests/test_tile.py exists
**When** tests run
**Then** tile types are verified (floor walkable, wall not walkable, exit walkable, water not walkable)

**Given** tests/test_room.py exists
**When** tests run
**Then** room creation, entity add/remove, movement validation, wall collision, boundary checks, exit detection, and get_state are all verified

**Given** tests/test_movement.py exists
**When** tests run
**Then** sequential moves, invalid directions, room transfers via RoomManager, and mob encounters are verified

**Given** tests/test_objects.py exists
**When** tests run
**Then** static object blocking, interactive state_scope behavior, chest one-time loot, and lever toggle are verified

**And** all tests pass with `pytest tests/`

### Story 6.5: Combat & Item Unit Tests

As a developer,
I want unit tests for combat, cards, effects, items, and inventory,
So that the core gameplay mechanics are verified to work correctly.

**Acceptance Criteria:**

**Given** tests/test_cards.py exists
**When** tests run
**Then** hand management (draw, play, discard, reshuffle), multi-effect card format, and card_to_dict are verified

**Given** tests/test_combat.py exists
**When** tests run
**Then** instance creation, add participant, play card with effect resolution, pass turn with mob attack, victory, defeat, flee, and turn order with multiple players are verified

**Given** tests/test_effects.py exists
**When** tests run
**Then** each effect type (damage, heal, shield, dot, draw) resolves correctly through the registry

**Given** tests/test_inventory.py exists
**When** tests run
**Then** add/remove items, stacking, charge consumption, use item in/out combat, and material items (non-usable) are verified

**And** all tests pass with `pytest tests/`

### Story 6.6: WebSocket Integration Tests

As a developer,
I want integration tests that exercise the full gameplay loop over WebSocket,
So that the end-to-end player experience is verified.

**Acceptance Criteria:**

**Given** tests/test_integration.py exists with httpx WebSocket test client
**When** the full gameplay loop test runs
**Then** the following sequence completes without errors:
1. Register a new player → receive login_success
2. Login → receive login_success + room_state
3. Move in valid direction → receive entity_moved
4. Move into wall → receive error
5. Interact with chest → receive loot
6. Interact with same chest again → receive "Already looted"
7. Move to exit tile → receive new room_state
8. Encounter hostile mob → receive combat_start + combat_turn
9. Play a card → receive updated combat_turn
10. Use item during combat → receive updated combat_turn
11. Combat resolves (victory) → receive combat_end with rewards
12. Use item outside combat → receive effect result
13. Send chat message → other player receives chat
14. Disconnect → position saved, other players notified

**And** all integration tests pass with `pytest tests/`

---

## Epic 7: Server Hardening

Players experience a reliable, persistent game world — spawning at valid positions, keeping their stats and inventory across sessions, recovering from defeat, seeing accurate NPC states, and being protected from concurrent login abuse.

### Story 7.1: Spawn Point Resolution

As a new player,
I want to spawn at a safe, walkable location when I first log in,
So that I can immediately start exploring without being stuck in a wall.

**Acceptance Criteria:**

**Given** a newly registered player logs in for the first time (current_room_id is None)
**When** the server processes the login
**Then** the default room is "town_square" (not "test_room")
**And** the player is placed at the room's configured player spawn point via `get_player_spawn()`
**And** the spawn point is validated as walkable after static objects are applied
**And** if the spawn point is blocked, the player is placed at the first walkable floor tile
**And** `current_room_id`, `position_x`, and `position_y` are saved to the DB after placement

**Given** a returning player logs in (current_room_id is not None)
**When** the server processes the login
**Then** the player is placed at their saved position in their saved room (existing behavior unchanged)

**Given** existing tests assert spawn at (0,0) or default room "test_room"
**When** the story is complete
**Then** all affected tests are updated to reflect "town_square" and spawn point placement
**And** `pytest tests/` passes with no failures

### Story 7.2: Player Stats Persistence

As a player,
I want my HP and stats to be saved and restored between sessions,
So that damage I take and progress I make persists across logins and server restarts.

**Acceptance Criteria:**

**Given** a first-time player logs in with empty stats in DB
**When** the server creates their entity
**Then** defaults are applied: hp=100, max_hp=100, attack=10
**And** these defaults are saved to the DB

**Given** a player's HP changes during combat (damage taken, heal, shield consumed)
**When** the complete action resolves (not per individual effect)
**Then** stats are saved to the DB with only whitelisted keys: hp, max_hp, attack
**And** unknown keys are stripped before save

**Given** a player uses a consumable item that modifies both stats and inventory
**When** the action completes
**Then** both stats and inventory changes are committed in a single DB transaction

**Given** a player disconnects
**When** the disconnect handler fires
**Then** all player state (stats + inventory + position) is batched into one DB transaction

**Given** combat ends
**When** cleanup runs
**Then** shield is reset to 0 (NOT persisted — combat-only buffer)

**Given** a player logs back in after disconnect or server restart
**When** the server loads their entity
**Then** stats are restored from DB (hp, max_hp, attack) — not reset to defaults

**Given** `player/repo.py` currently has no `update_stats()` method
**When** the story is complete
**Then** a stats update method exists and all affected tests pass

### Story 7.3: Inventory Persistence

As a player,
I want my inventory to be saved and restored between sessions,
So that items I collect aren't lost when I log out or the server restarts.

**Acceptance Criteria:**

**Given** a player picks up an item (chest loot, combat reward)
**When** the item is added to inventory
**Then** the inventory is saved to the DB immediately

**Given** a player uses a consumable item
**When** the charge is consumed
**Then** the inventory is saved to the DB (in the same transaction as any stats changes)

**Given** a player logs in
**When** the server creates their entity
**Then** inventory is restored from the DB `inventory` JSON column using `Inventory.from_dict(data, item_lookup)`
**And** `from_dict` takes an item lookup callable `(str) -> ItemDef` to hydrate runtime objects without coupling Inventory to Game

**Given** `Inventory` class currently has no `to_dict()`/`from_dict()` methods
**When** the story is complete
**Then** `to_dict()` serializes to `{item_key: quantity}` pairs suitable for DB storage
**And** `from_dict(data, item_lookup)` reconstructs the Inventory with hydrated ItemDef objects
**And** round-trip is verified: `from_dict(to_dict()) == original`

**Given** a player dies in combat
**When** respawn occurs
**Then** items are retained (no item loss for prototype)

**Given** two concurrent sessions interact with the same chest (before FR55)
**When** both attempt to loot
**Then** chest loot granting uses upsert pattern (INSERT ON CONFLICT DO NOTHING) to prevent duplication

**Given** `test_integration.py:165` asserts empty inventory on login
**When** the story is complete
**Then** the test is updated and `pytest tests/` passes

### Story 7.4: Death & Respawn

As a player,
I want to respawn in town after being defeated,
So that death isn't permanent and I can try again.

**Acceptance Criteria:**

**Given** all players' HP reaches 0 in combat (defeat)
**When** combat ends
**Then** `game.respawn_player(entity_id)` is called for each defeated player

**Given** `game.respawn_player(entity_id)` is called
**When** the respawn executes
**Then** the synchronous cleanup sequence runs: combat removal → in_combat flag clear → set HP to max_hp → save all state to DB (stats + position + room_key = "town_square") → THEN in-memory room transfer to town_square at spawn point → broadcast entity_entered to town players
**And** DB save happens BEFORE in-memory room transfer (crash recovery places player correctly)

**Given** a player respawns in town_square
**When** the respawn completes
**Then** no death penalty is applied (no XP/item/gold loss — prototype)
**And** the player has full HP at the town spawn point

**Given** a player disconnects uncleanly during combat
**When** the disconnect handler fires
**Then** the player is treated as having fled (removed from combat, combat continues for others)

**Given** a player respawns in town_square
**When** an NPC is near the town_square spawn point
**Then** the player does not immediately re-enter combat (town_square has no hostile NPCs)

**Given** the server crashes mid-respawn (after DB save, before room transfer)
**When** the player logs back in
**Then** they are placed in town_square at the spawn point with full HP (from DB state)

### Story 7.5: Duplicate Login Protection

As a player,
I want to be able to reconnect if my browser crashes,
So that I'm not locked out of my account by a stale session.

**Acceptance Criteria:**

**Given** a player is already logged in with an active WebSocket session
**When** the same account logs in from a new connection
**Then** the old session is kicked immediately (deferred kick is a production optimization)

**Given** the old session is kicked
**When** the kick executes
**Then** the cleanup order is: save old session's state (stats + inventory + position) → remove entity from room → remove from connection_manager immediately (do not wait for disconnect event) → close old WebSocket → proceed with new login

**Given** the old session is in active combat when kicked
**When** the kick fires
**Then** the player is removed from the combat instance (forfeited)
**And** combat continues for remaining participants

**Given** the old WebSocket close handshake fails (network degraded)
**When** the close attempt times out or errors
**Then** the entity and connection_manager entries are already cleaned up (cleanup happens before close)
**And** no zombie socket blocks future broadcasts

**Given** no existing session for the account
**When** the player logs in
**Then** login proceeds normally (no kick needed)

### Story 7.6: NPC Death State Broadcast

As a player,
I want to see NPCs disappear from the room when someone defeats them,
So that the world state is consistent for all players.

**Acceptance Criteria:**

**Given** `NpcEntity` dataclass exists
**When** the story is complete
**Then** an `in_combat: bool = False` field is added to `NpcEntity`
**And** `to_dict()` does NOT include `in_combat` (server-internal state)

**Given** a player walks onto a hostile NPC's tile
**When** the encounter is detected in `room.py:move_entity`
**Then** the encounter check verifies both `is_alive` and `not in_combat`
**And** `npc.in_combat` is set to `True` (NOT `is_alive = False`)
**And** `is_alive` remains `True` until combat victory

**Given** combat ends with victory (mob HP ≤ 0)
**When** combat resolution runs
**Then** `npc.is_alive` is set to `False`
**And** `npc.in_combat` is set to `False`
**And** a `room_state` rebroadcast is sent to all players in the room

**Given** combat ends with defeat or all players flee
**When** combat resolution runs
**Then** `npc.in_combat` is set to `False` (NPC returns to available)
**And** `npc.is_alive` remains `True`

**Given** the server restarts
**When** NPCs are reloaded
**Then** `in_combat` defaults to `False` (purely in-memory, not persisted to DB)
**And** all NPCs are available for encounters

**Given** `movement.py:101` currently sets `npc.is_alive = False` at encounter
**When** the story is complete
**Then** this line is changed to set `npc.in_combat = True` instead
**And** all affected tests are updated and `pytest tests/` passes

---

## Epic 8: World Expansion

The game world grows with new mechanics — vertical room exits (stairs/ladders), and a mana/energy resource system that gives card costs mechanical meaning. Note: FR57 and FR58 are independent features grouped by implementation phase (both require design decisions before implementation), not by user journey.

### Story 8.1: Card Cost & Energy System

As a player,
I want cards to cost energy to play so I have to make strategic choices each turn,
So that combat has meaningful resource management beyond just picking the best card.

**Acceptance Criteria:**

**Given** a player enters combat
**When** the CombatInstance is created
**Then** the player starts with a configured energy amount (default: 10)
**And** energy is included in the `combat_start` message
**And** energy is included in every `combat_turn` message

**Given** it is a player's turn and they play a card with cost > 0
**When** the card is played
**Then** the player's energy is reduced by the card's cost
**And** if the player doesn't have enough energy, the play is rejected with error: "Not enough energy"

**Given** a new combat cycle begins (all participants have acted)
**When** the cycle resets
**Then** each player regenerates a configured amount of energy (default: 3 per cycle, capped at max)

**Given** a player uses an item during combat
**When** the item is used
**Then** no energy is consumed (items are free — energy is a card-only resource)

**Given** a player passes their turn
**When** the pass is processed
**Then** no energy is consumed

**Given** `data/cards/base_set.json` has cards with `cost: 0`
**When** the story is complete
**Then** card costs are rebalanced: cheap cards (cost 1-2), medium cards (cost 3-4), expensive cards (cost 5-7)
**And** the sum of costs across a typical hand allows meaningful play with starting energy

**Given** energy values need to be tunable
**When** the story is complete
**Then** `COMBAT_STARTING_ENERGY` and `COMBAT_ENERGY_REGEN` are added to server config (Pydantic BaseSettings)

**And** all existing combat tests are updated and `pytest tests/` passes

### Story 8.2: Vertical Room Exits

As a player,
I want to climb stairs and descend ladders to reach rooms above or below,
So that the world has vertical depth beyond flat horizontal connections.

**Acceptance Criteria:**

**Given** the `TileType` enum exists with FLOOR=0, WALL=1, EXIT=2, MOB_SPAWN=3, WATER=4
**When** the story is complete
**Then** `STAIRS_UP=5` and `STAIRS_DOWN=6` are added to the enum
**And** both are added to `WALKABLE_TILES`

**Given** a player walks onto a `STAIRS_UP` or `STAIRS_DOWN` tile
**When** `room.py:move_entity` processes the move
**Then** exit detection triggers for stairs tiles (same as EXIT tiles)
**And** the exit info is returned in the move result

**Given** room JSON `exits` array has entries for vertical exits
**When** the exit is configured
**Then** vertical exits use `"direction": "ascend"` or `"direction": "descend"` (NOT "up"/"down" which collide with movement direction strings)

**Given** movement direction strings are "up"/"down"/"left"/"right" (grid directions)
**When** a vertical exit is processed
**Then** "ascend"/"descend" are used exclusively for exit metadata — no collision with movement input

**Given** the client renders tiles
**When** a STAIRS_UP or STAIRS_DOWN tile is encountered
**Then** the tile type ID (5 or 6) is included in the room_state tiles grid for client rendering

**Given** existing room JSON files use tile values 0-4
**When** the new tile types are added
**Then** no existing room data is affected (5 and 6 were not used previously)

**Given** existing tests assert `TileType` has specific values
**When** the story is complete
**Then** tile tests are updated to include STAIRS_UP and STAIRS_DOWN
**And** walkability tests verify both are walkable
**And** `pytest tests/` passes

---

## Epic 9: Server Administration

Server operators can manage the game server without SSH process management — triggering graceful shutdown or restart via authenticated admin commands, with proper player state preservation and client notification.
**FRs covered:** FR59, FR60, FR61
**Dependencies:** 9.1 → 9.2, 9.1 → 9.3 (admin auth must come first). 9.2 and 9.3 are independent of each other.

### Story 9.1: Admin Authentication

As a server operator,
I want to authenticate as an admin using a shared secret,
So that only authorized users can trigger server management commands.

**Acceptance Criteria:**

**Given** the server configuration
**When** the story is complete
**Then** `ADMIN_SECRET` is added to server config (Pydantic BaseSettings) with no default (must be set to enable admin features)

**Given** an admin REST endpoint is called without the correct secret
**When** the request is processed
**Then** it is rejected with 403 Forbidden

**Given** `ADMIN_SECRET` is not configured (empty/None)
**When** any admin endpoint is called
**Then** it is rejected with 403 Forbidden and a log warning "Admin endpoints disabled — ADMIN_SECRET not configured"

**Given** the admin secret is provided correctly
**When** the request is processed
**Then** the admin action proceeds normally

**And** all existing tests pass after implementation

### Story 9.2: Admin Shutdown Command

As a server operator,
I want to trigger a graceful server shutdown via an authenticated REST endpoint,
So that I can shut down the server remotely without killing the process.

**Acceptance Criteria:**

**Given** the admin is authenticated (valid ADMIN_SECRET)
**When** `POST /admin/shutdown` is called
**Then** the server responds with `{"status": "shutting_down"}` immediately

**Given** shutdown has been triggered
**When** the shutdown process runs
**Then** `Game.shutdown()` is called (saves all player states, notifies clients, closes WebSockets)
**And** the uvicorn server process exits cleanly after shutdown completes

**Given** a shutdown is already in progress
**When** another shutdown request arrives
**Then** it is rejected with `{"status": "already_shutting_down"}`

**Given** players are connected when shutdown is triggered
**When** the shutdown completes
**Then** all players have received `server_shutdown` message
**And** all player states (position, stats, inventory) are saved to DB
**And** all WebSocket connections are closed with code 1001

**And** all existing tests pass after implementation

### Story 9.3: Server Restart Mechanism

As a server operator,
I want to trigger a graceful server restart via an authenticated REST endpoint,
So that I can apply updates or recover from issues without manual process management.

**Acceptance Criteria:**

**Given** the admin is authenticated (valid ADMIN_SECRET)
**When** `POST /admin/restart` is called
**Then** the server responds with `{"status": "restarting"}` immediately

**Given** restart has been triggered
**When** the restart process runs
**Then** `Game.shutdown()` is called first (saves all states, notifies clients, closes WebSockets)
**And** the server process re-executes itself (same Python interpreter, same arguments)
**And** the new process completes startup (init_db, load rooms/cards/items, start scheduler)

**Given** players were connected before restart
**When** the server comes back up
**Then** players can reconnect and login to find their saved state (position, stats, inventory) intact

**Given** the restart re-execution fails (e.g., syntax error in updated code)
**When** the new process cannot start
**Then** the failure is visible in the process output (no silent failure)
**And** the old process has already exited (no zombie process)

**Given** a shutdown or restart is already in progress
**When** a restart request arrives
**Then** it is rejected with `{"status": "already_shutting_down"}`

**And** all existing tests pass after implementation

---

## Epic 10: Gameplay Polish & Interaction

Players experience a polished, discoverable game world — interacting with objects via commands or proximity, managing inventory and using items through multiple access methods, receiving loot from defeated mobs, and seeing their stats at a glance. A unified slash command system provides engine-agnostic access to all game mechanics.

### Story 10.1: Player Logout

As a player,
I want to logout cleanly from the game,
So that my state is saved and I can return to the login screen without closing the browser.

**Acceptance Criteria:**

**Given** a logged-in player
**When** the server receives `{"action": "logout"}`
**Then** the player's state is saved to DB (position, stats, inventory)
**And** the player's entity is removed from the room
**And** other players in the room receive an `entity_left` message
**And** the player is removed from `player_entities` and `connection_manager`
**And** the player receives `{"type": "logged_out"}`
**And** the WebSocket remains open (player returns to auth state, can login again)

**Given** a player is in combat
**When** they send a logout action
**Then** the player is removed from combat (treated as flee)
**And** the player receives `{"type": "combat_fled"}` before `{"type": "logged_out"}`
**And** combat continues for other participants (remaining participants receive combat_update)
**And** if the player was the last participant, the combat instance is cleaned up and the mob resets (is_alive=true, in_combat=false)
**And** logout proceeds normally after combat removal (state save, room removal, entity_left broadcast)

**Given** a player is not logged in
**When** they send a logout action
**Then** the client receives an error: "Not logged in"

**Given** the web client receives a `logged_out` message
**When** the UI updates
**Then** the game viewport is hidden and the login form is shown
**And** a "Logout" button is visible in the game UI during gameplay
**And** `/logout` command is available via chat input

### Story 10.2: Non-Walkable Interactive Objects

As a player,
I want interactive objects (chests, levers) to block movement like obstacles,
So that I must stand next to them and interact deliberately, matching real game engine conventions.

**Acceptance Criteria:**

**Given** a room JSON defines a chest at position (25, 30) with `category: "interactive"`
**When** the room is loaded
**Then** the tile at (25, 30) is marked as non-walkable (blocked by the object)
**And** the chest is visible in the room_state objects list

**Given** a player attempts to move onto a tile occupied by an interactive object
**When** the server processes the move
**Then** the move is rejected with error: "Tile not walkable"
**And** the player's position does not change

**Given** a player is adjacent to a chest (one tile away in any cardinal direction)
**When** the player sends `{"action": "interact", "target_id": "chest_01"}`
**Then** the interaction succeeds as before (existing interact handler works)

**Given** a player is NOT adjacent to an interactive object
**When** the player sends an interact action for that object
**Then** the client receives an error: "Too far to interact"

**Given** static objects (trees, rocks) are already non-walkable
**When** the story is complete
**Then** interactive objects follow the same blocking pattern
**And** existing interact tests (test_objects.py, test_integration.py) that assume no distance check are updated to place the player adjacent to the object before interacting
**And** existing tests are updated for the new blocking behavior
**And** `pytest tests/` passes with no failures

### Story 10.3: Slash Command Parser

As a player,
I want to type `/commands` in the chat input to perform game actions,
So that I have an engine-agnostic way to access all game mechanics beyond clicking UI buttons.

**Acceptance Criteria:**

**Given** the web client chat input exists
**When** the player types a message starting with `/`
**Then** the message is intercepted by a client-side command parser before being sent as chat
**And** the parser extracts the command name and arguments

**Given** the player types `/help`
**When** the parser processes it
**Then** a help message is displayed locally listing all available commands with brief descriptions
**And** no message is sent to the server (client-side only)

**Given** the player types an unknown command like `/foobar`
**When** the parser processes it
**Then** the player sees a local error: "Unknown command: /foobar. Type /help for available commands."
**And** no message is sent to the server

**Given** the player types a regular chat message (no `/` prefix)
**When** the input is processed
**Then** it is sent as a normal chat message (existing behavior unchanged)

**Given** the parser exists
**When** the story is complete
**Then** the parser is extensible — adding a new command requires adding one entry to a command registry object
**And** the parser handles: command name extraction, argument splitting, command dispatch

### Story 10.4: Server Query Actions

As a player,
I want to query the server for information about my surroundings, who's online, and my stats,
So that I can make informed decisions without relying on UI-only displays.

**Acceptance Criteria:**

**Given** a logged-in player sends `{"action": "look"}`
**When** the server processes the action
**Then** the player receives `{"type": "look_result"}` containing:
- Interactive objects on the player's tile and all 4 adjacent tiles (with object id, type, direction)
- NPCs on/adjacent to the player (with name, alive status, direction)
- Other players on/adjacent to the player (with name, direction)

**Given** a logged-in player sends `{"action": "who"}`
**When** the server processes the action
**Then** the player receives `{"type": "who_result", "room": "town_square", "players": [{"name": "hero", "x": 50, "y": 50}, ...]}`

**Given** a logged-in player sends `{"action": "stats"}`
**When** the server processes the action
**Then** the player receives `{"type": "stats_result", "stats": {"hp": 85, "max_hp": 100, "attack": 10, "xp": 150}}`

**Given** a logged-in player sends `{"action": "help_actions"}`
**When** the server processes the action
**Then** the player receives `{"type": "help_result", "actions": ["move", "chat", "interact", "inventory", "use_item", "look", "who", "stats", "logout", ...]}`

**Given** a player is not logged in
**When** they send any query action
**Then** the client receives an error: "Not logged in"

**And** all new handlers are registered in `Game._register_handlers()`
**And** tests are added for each new action
**And** `pytest tests/` passes

### Story 10.5: Directional Object Interaction

As a player,
I want to interact with adjacent objects by specifying a direction and receive proximity notifications,
So that I can discover and interact with objects naturally without needing to know object IDs.

**Acceptance Criteria:**

**Given** a logged-in player sends `{"action": "interact", "direction": "east"}`
**When** the server processes the action
**Then** the server checks the tile one step east of the player's position
**And** if an interactive object exists on that tile, the interaction proceeds (delegates to existing interact handler)
**And** the `interact` handler accepts either `target_id` (existing) OR `direction` (new) — not both required

**Given** a player sends an interact with direction but no interactive object is in that direction
**When** the server processes the action
**Then** the client receives an error: "Nothing to interact with in that direction"

**Given** a player moves to a tile adjacent to an interactive object
**When** the movement completes
**Then** the server includes a `nearby_objects` field in the move result: `[{"id": "chest_01", "type": "chest", "direction": "east"}]`
**And** the web client displays a notification: "You see a chest to the east"

**Given** a player moves away from all interactive objects
**When** the movement completes
**Then** no `nearby_objects` field is included (or it's an empty list)

**Given** multiple interactive objects are adjacent to the player
**When** the movement completes
**Then** all nearby objects are listed with their directions

**And** existing `interact` by `target_id` continues to work (backward compatible)
**And** tests cover both `target_id` and `direction` interaction modes
**And** `pytest tests/` passes

### Story 10.6: Slash Command Integration

As a player,
I want all game actions available as slash commands in the chat input,
So that every mechanic is accessible via text commands for engine-agnostic testing.

**Acceptance Criteria:**

**Given** the slash command parser from Story 10.3 exists
**When** the story is complete
**Then** the following commands are registered and functional:

| Command | Server Action | Behavior |
|---------|--------------|----------|
| `/logout` | `logout` | Logs out the player |
| `/whisper @name message` | `chat` with `whisper_to` | Sends private message |
| `/interact <direction>` | `interact` with `direction` | Interacts with adjacent object |
| `/inventory` | `inventory` | Opens inventory panel + requests server data |
| `/use <item_key>` | `use_item` with `item_key` | Uses a consumable item |
| `/look` | `look` | Shows nearby objects, NPCs, players |
| `/who` | `who` | Lists players in room |
| `/stats` | `stats` | Shows player stats |
| `/flee` | `flee` | Flees combat |
| `/pass` | `pass_turn` | Passes combat turn |

**Given** the player types `/whisper @alice Hello there`
**When** the parser processes it
**Then** it sends `{"action": "chat", "message": "Hello there", "whisper_to": "alice"}`

**Given** the player types `/interact east`
**When** the parser processes it
**Then** it sends `{"action": "interact", "direction": "east"}`

**Given** the player types `/use healing_potion`
**When** the parser processes it
**Then** it sends `{"action": "use_item", "item_key": "healing_potion"}`

**Given** a command requires arguments but none are provided (e.g., `/whisper`)
**When** the parser processes it
**Then** the player sees a usage hint: "Usage: /whisper @name message"

**And** server responses from commands are displayed in the chat/log area
**And** `/help` is updated to list all registered commands

### Story 10.7: Mob Loot Drops

As a player,
I want defeated mobs to drop items based on their loot table,
So that combat has tangible rewards beyond XP.

**Acceptance Criteria:**

**Given** an NPC template defines `"loot_table": "slime_loot"`
**When** combat ends with victory (mob HP <= 0)
**Then** loot is generated from the NPC's loot table using `generate_loot()`
**And** items are added to each victorious player's inventory
**And** inventory is persisted to DB
**And** the `combat_end` message includes `"loot": [{"item_key": "...", "quantity": N}, ...]`

**Given** `LOOT_TABLES` in `chest.py` currently only has `common_chest` and `rare_chest`
**When** the story is complete
**Then** the following mob loot tables are added: `goblin_loot`, `slime_loot`, `bat_loot`, `troll_loot`, `dragon_loot`
**And** each table has thematically appropriate drops (e.g., slime → healing_potion, goblin → iron_shard)

**Given** the `generate_loot()` function exists in `chest.py`
**When** the story is complete
**Then** `generate_loot()` is moved to a shared location (e.g., `server/items/loot.py`) accessible by both chest and combat systems
**And** chest.py imports from the shared location
**And** existing tests that import `generate_loot` or `LOOT_TABLES` from `chest.py` are updated to use the new import path

**Given** multiple players are in combat when the mob is defeated
**When** loot is generated
**Then** each player receives the same loot (prototype — no loot splitting for now)

**Given** the web client receives a `combat_end` with loot
**When** the UI updates
**Then** the loot items are displayed in the combat result message

**And** tests verify loot generation, inventory integration, and combat_end payload
**And** `pytest tests/` passes

### Story 10.8: Player Stats HUD

As a player,
I want to always see my HP, XP, and attack stats during gameplay,
So that I know my current state without needing to type commands.

**Acceptance Criteria:**

**Given** a player logs in and enters the game
**When** the game viewport is displayed
**Then** a stats HUD panel is always visible showing:
- HP bar with current/max (e.g., "HP: 85/100") with color coding (green > 50%, yellow 25-50%, red < 25%)
- XP display (e.g., "XP: 150")
- Attack stat (e.g., "ATK: 10")

**Given** the player takes damage or heals (combat or item use)
**When** the stats update is received
**Then** the HUD updates in real-time

**Given** the player gains XP from combat victory
**When** the `combat_end` message is received
**Then** the XP display updates immediately

**Given** the player logs in
**When** `login_success` is received
**Then** stats from the login response populate the HUD immediately (no `/stats` command needed)

**Given** the existing `hp-section` element in index.html
**When** the story is complete
**Then** it is expanded into a full stats HUD that is always visible (not hidden by default)
**And** the HUD is positioned to not overlap the tile viewport or chat area

### Story 10.9: NPC Spawn Density

As a player,
I want more mobs spawned in larger rooms,
So that combat encounters happen at a reasonable rate while exploring.

**Acceptance Criteria:**

**Given** `data/rooms/town_square.json` is a 100x100 room
**When** the story is complete
**Then** the room has at least 12 NPC spawn points (up from current count)
**And** spawn points include a mix of slimes and goblins
**And** spawn points are spread across the map (not clustered in one area)

**Given** `data/rooms/dark_cave.json` is a 100x100 room
**When** the story is complete
**Then** the room has at least 10 NPC spawn points
**And** spawn points include slimes, bats, and the existing rare cave_troll

**Given** the increased spawn density
**When** a player explores town_square
**Then** they encounter a mob within approximately 20-30 tiles of walking from spawn
**And** mobs are distributed to make exploration consistently engaging

**Given** test_room and other_room are 5x5
**When** the story is complete
**Then** their spawn points are not changed (small rooms don't need more density)

**And** the server starts successfully with the updated room data
**And** `pytest tests/` passes

---

## Epic 11: Experience & Stat System

Players have meaningful character stats (STR, DEX, CON, INT, WIS, CHA) that affect card combat outcomes. NPCs use a hit_dice system for simplified stat derivation. Players gain XP from combat, exploration, and object interaction, with hooks ready for future quest and party XP. A configurable XP curve (quadratic default) drives leveling, where players choose which stats to boost — creating meaningful progression with player agency.

### Story 11.1: D&D Stat System & NPC Hit Dice

As a player,
I want my character to have meaningful ability scores (STR, DEX, CON, INT, WIS, CHA),
So that my character feels unique and stats affect gameplay beyond flat HP and attack.

**Acceptance Criteria:**

**Given** a new player registers and logs in for the first time
**When** the server creates their entity
**Then** the player has 6 ability scores: `strength=1, dexterity=1, constitution=1, intelligence=1, wisdom=1, charisma=1`
**And** `max_hp` is calculated as `100 + (constitution × 5)` = 105
**And** `level=1, xp=0`
**And** all 6 abilities + level are persisted to DB

**Given** a returning player logs in
**When** the server loads their entity
**Then** all 6 ability scores and level are restored from DB (not reset to defaults)

**Given** an existing player with pre-Epic-11 stats (hp, max_hp, attack, xp but no ability scores)
**When** they log in after Epic 11 is deployed
**Then** missing ability scores default to 1 and level defaults to 1
**And** existing hp, max_hp, and xp are preserved (not reset)
**And** max_hp is NOT recalculated from CON on this migration login (would change 100 to 110, healing the player unexpectedly)
**And** max_hp recalculation from CON takes effect on the player's next level-up

**Given** `player/repo.py` has a stats whitelist `{"hp", "max_hp", "attack", "xp"}`
**When** the story is complete
**Then** the whitelist is expanded to include `strength, dexterity, constitution, intelligence, wisdom, charisma, level`
**And** `attack` is kept in the whitelist as a derived/computed value during the transition period (deprecated in Story 11.2)

**Given** `_DEFAULT_STATS` in `auth.py` currently is `{"hp": 100, "max_hp": 100, "attack": 10, "xp": 0}`
**When** the story is complete
**Then** defaults become `{"hp": 105, "max_hp": 105, "attack": 10, "xp": 0, "level": 1, "strength": 1, "dexterity": 1, "constitution": 1, "intelligence": 1, "wisdom": 1, "charisma": 1}`
**And** `attack` remains present as a transitional computed value (= `floor(STR × 0.5)` for players, = `hit_dice × 2` for NPCs)
**And** `max_hp` is derived from CON for new players, not hardcoded

**Given** the CON-to-HP scaling needs to be tunable
**When** the story is complete
**Then** `CON_HP_PER_POINT: int = 5` is added to server config (Pydantic BaseSettings)
**And** `max_hp = 100 + (constitution × settings.CON_HP_PER_POINT)` — not hardcoded

**Given** `data/npcs/base_npcs.json` defines NPCs with flat `hp, max_hp, attack, defense` stats
**When** the story is complete
**Then** NPC data is restructured to use `hit_dice` and `hp_multiplier`:
- `cave_bat`: hit_dice=2, hp_multiplier=12 (HP=24)
- `slime`: hit_dice=3, hp_multiplier=10 (HP=30)
- `forest_goblin`: hit_dice=4, hp_multiplier=12 (HP=48)
- `cave_troll`: hit_dice=7, hp_multiplier=28 (HP=196)
- `forest_dragon`: hit_dice=10, hp_multiplier=50 (HP=500)

**Given** an NPC is loaded from JSON with `hit_dice=4`
**When** the NPC entity is created
**Then** all 6 abilities = 4 (derived from hit_dice)
**And** `max_hp = hit_dice × hp_multiplier`
**And** mob `attack` value = `hit_dice × 2` (transitional — used by combat instance until Story 11.2 wires STR directly)

**Given** the combat instance uses `mob_stats["attack"]` for mob damage
**When** the story is complete
**Then** mob `attack` is populated from `hit_dice × 2` at combat init (preserves existing combat flow until Story 11.2)

**And** all existing tests are updated for the new stat structure
**And** `pytest tests/` passes with no failures

### Story 11.2: Stat-to-Combat Integration

As a player,
I want my ability scores to meaningfully affect combat outcomes,
So that investing in different stats creates distinct playstyles and tactical choices.

**Acceptance Criteria:**

**Given** a player plays a card with `damage/physical` effect (e.g., Slash, base value 12)
**When** the damage effect resolves
**Then** the final damage = `base_value + floor(player_strength × 1.0)`
**And** a player with STR=1 deals 13 damage, STR=6 deals 18, STR=10 deals 22

**Given** a player plays a card with `damage/fire`, `damage/ice`, or `damage/arcane` effect
**When** the damage effect resolves
**Then** the final damage = `base_value + floor(player_intelligence × 1.0)`
**And** `damage/physical` is NOT scaled by INT (only STR)

**Given** a player plays a card with `heal` effect (e.g., Heal Light, base value 15)
**When** the heal effect resolves
**Then** the final heal = `base_value + floor(player_wisdom × 1.0)`
**And** healing is still capped at `max_hp`

**Given** a player takes damage from any source (card, mob attack)
**When** the damage is applied (after shield absorption)
**Then** damage is reduced by `floor(target_dexterity × 1.0)`
**And** minimum damage is always 1 (cannot reduce to 0)
**And** DEX reduction applies AFTER shield absorption: `actual = max(1, post_shield_damage - floor(DEX × 1.0))`

**Given** a `dot` effect ticks each turn
**When** DoT damage is applied
**Then** DoT damage is NOT reduced by DEX (design decision: poison/bleed bypasses physical defenses — it's already in your system)
**And** DoT damage is NOT modified by source stats (flat value from card)

**Given** a player's CON changes (e.g., from future level-up)
**When** max_hp is recalculated
**Then** `max_hp = 100 + (new_constitution × 5)`
**And** if current HP exceeds new max_hp, HP is capped at new max_hp

**Given** the `shield` effect type
**When** a shield card is played
**Then** shield value is NOT modified by any stat (flat value from card)

**Given** the stat-to-combat scaling needs to be tunable
**When** the story is complete
**Then** `STAT_SCALING_FACTOR: float = 1.0` is added to server config (Pydantic BaseSettings)
**And** all stat bonus formulas use `floor(stat × settings.STAT_SCALING_FACTOR)` — not hardcoded
**And** a code comment documents: "STAT_SCALING_FACTOR must be >= 1.0 for stat=1 to produce a non-zero bonus. Values below 1.0 are valid but mean new characters (all stats=1) have no stat bonuses until they invest 2+ points via level-up."

**Given** the effect handlers in `server/core/effects/` currently use `effect["value"]` directly
**When** the story is complete
**Then** `handle_damage` reads `source["strength"]` or `source["intelligence"]` based on `effect["subtype"]`
**And** `handle_heal` reads `source["wisdom"]`
**And** damage application (in `handle_damage` and mob attack) reads `target["dexterity"]`
**And** stat bonuses are sourced from the `source` and `target` dicts passed by `CombatInstance`

**Given** NPC stats are derived from `hit_dice` (Story 11.1)
**When** an NPC attacks or is attacked
**Then** NPC STR/DEX/INT/WIS all equal `hit_dice`, so NPC damage bonus = `floor(hit_dice × 1.0)` and NPC damage reduction = `floor(hit_dice × 1.0)`

**Given** the transitional `attack` field from Story 11.1
**When** the story is complete
**Then** mob attack damage is calculated as `(hit_dice × 2) + floor(mob_strength × 1.0)` with DEX reduction applied to the target
**And** the `attack` key is removed from the stats whitelist (fully deprecated)
**And** all references to `mob_stats["attack"]` in combat instance are replaced with STR-derived calculation

**And** all existing combat tests are updated with stat-aware assertions
**And** new tests verify each stat's combat effect independently
**And** `pytest tests/` passes

### Story 11.3: Configurable XP Curve & Combat Rewards

As a player,
I want to earn XP from defeating mobs scaled to their difficulty,
So that fighting stronger enemies is more rewarding than grinding weak ones.

**Acceptance Criteria:**

**Given** `server/core/config.py` defines server settings
**When** the story is complete
**Then** the following config values are added:
- `XP_CURVE_TYPE: str = "quadratic"` (supports "quadratic", "linear")
- `XP_CURVE_MULTIPLIER: int = 25`
- `XP_CHA_BONUS_PER_POINT: float = 0.03`
- `XP_LEVEL_THRESHOLD_MULTIPLIER: int = 1000`

**Given** an NPC with `hit_dice=4` is defeated in combat
**When** XP is calculated with `XP_CURVE_TYPE="quadratic"` and `XP_CURVE_MULTIPLIER=25`
**Then** `base_xp = 4² × 25 = 400`

**Given** `XP_CURVE_TYPE="linear"` and `XP_CURVE_MULTIPLIER=25`
**When** the same NPC (hit_dice=4) is defeated
**Then** `base_xp = 4 × 25 = 100`

**Given** a player with CHA=6 defeats an NPC with hit_dice=4 (base_xp=400, quadratic)
**When** the CHA bonus is applied with `XP_CHA_BONUS_PER_POINT=0.03`
**Then** `final_xp = floor(400 × (1 + 6 × 0.03)) = floor(400 × 1.18) = 472`

**Given** combat ends with victory
**When** XP is awarded to each participant
**Then** each player receives XP independently (each player's CHA applies to their own reward)
**And** the `combat_end` message includes `"rewards": {"xp": <player-specific-xp>}` per player
**And** the flat 25 XP reward (current implementation) is replaced by the hit_dice-based formula

**Given** the XP calculation logic
**When** the story is complete
**Then** XP calculation is a standalone function in `server/core/xp.py:calculate_combat_xp(hit_dice, cha)` reusable by future XP sources
**And** the function reads config values from settings, not hardcoded

**Given** the expected XP rewards per NPC (quadratic, multiplier=25, CHA=1):
**When** XP is calculated
**Then** the rewards are:
- cave_bat (hd=2): `floor(100 × 1.03)` = 103
- slime (hd=3): `floor(225 × 1.03)` = 231
- forest_goblin (hd=4): `floor(400 × 1.03)` = 412
- cave_troll (hd=7): `floor(1225 × 1.03)` = 1261
- forest_dragon (hd=10): `floor(2500 × 1.03)` = 2575

**Given** a fresh level-1 player with default stats
**When** they play through typical content (kill ~10 mixed mobs, visit 4 rooms, interact with ~5 objects)
**Then** they should reach level 2 in approximately 30-60 minutes of play
**And** if tuning shows progression is too fast or slow, `XP_CURVE_MULTIPLIER` should be adjusted (this AC documents the design intent, not a hard test)

**And** tests verify both curve types, CHA scaling, and edge cases (CHA=0, CHA=10)
**And** `pytest tests/` passes

### Story 11.4: Exploration & Interaction XP Sources

As a player,
I want to earn XP from discovering new rooms and interacting with objects for the first time,
So that exploration and curiosity are rewarded beyond just combat.

**Acceptance Criteria:**

**Given** a player transitions to a room they have never visited before
**When** the room transition completes
**Then** the player receives exploration XP (configurable, default: `XP_EXPLORATION_REWARD = 50`)
**And** the player receives a message: `{"type": "xp_gained", "amount": <xp>, "source": "exploration", "detail": "Discovered Town Square"}`
**And** the CHA bonus multiplier applies to exploration XP
**And** the room is marked as "visited" for this player (persisted to DB)

**Given** a player transitions to a room they have already visited
**When** the room transition completes
**Then** no exploration XP is granted
**And** no `xp_gained` message is sent for exploration

**Given** a player interacts with a chest or lever for the first time
**When** the interaction succeeds
**Then** the player receives interaction XP (configurable, default: `XP_INTERACTION_REWARD = 25`)
**And** the player receives a message: `{"type": "xp_gained", "amount": <xp>, "source": "interaction", "detail": "Opened Treasure Chest"}`
**And** the CHA bonus multiplier applies

**Given** a player interacts with a chest they have already opened
**When** the interaction completes (returns "Already looted")
**Then** no interaction XP is granted

**Given** player visited-rooms tracking needs persistence
**When** the story is complete
**Then** a `visited_rooms` field is added to the player DB model (JSON list of room_keys)
**And** visited rooms are saved on disconnect and restored on login
**And** a code comment notes: "Consider PlayerRoomVisit table for production scale"

**Given** the XP granting system
**When** the story is complete
**Then** a shared `grant_xp(player_entity, amount, source, detail)` function exists in `server/core/xp.py`
**And** it applies CHA bonus, updates player stats, persists to DB, and sends `xp_gained` message
**And** combat XP (Story 11.3), exploration XP, and interaction XP all use this shared function

**Given** future XP sources (quests, party bonus) don't exist yet
**When** the story is complete
**Then** `grant_xp` accepts any `source` string — no hardcoded enum
**And** config includes placeholder values: `XP_QUEST_REWARD = 100`, `XP_PARTY_BONUS_PERCENT = 10` (unused but documented)

**And** tests verify first-visit XP, repeat-visit no XP, first-interact XP, repeat-interact no XP
**And** `pytest tests/` passes

### Story 11.5: XP Level Thresholds & Level-Up Mechanic

As a player,
I want to level up when I accumulate enough XP and choose which stats to improve,
So that I have agency over my character's growth and build.

**Acceptance Criteria:**

**Given** a player is level 1 with `XP_LEVEL_THRESHOLD_MULTIPLIER=1000`
**When** their XP reaches or exceeds 1000
**Then** they are eligible to level up
**And** the threshold formula is: `next_level_xp = level × XP_LEVEL_THRESHOLD_MULTIPLIER` (cumulative, not reset)

**Given** a player's XP crosses the level threshold (e.g., XP goes from 950 to 1100 at level 1)
**When** `grant_xp` detects threshold crossed
**Then** the server sends `{"type": "level_up_available", "new_level": 2, "choose_stats": 3, "current_stats": {"strength": 1, ...}, "stat_cap": 10}`
**And** the player's level is NOT incremented yet — they must choose stats first

**Given** level-up choice is pending
**When** the player continues playing (moving, fighting, chatting)
**Then** gameplay is NOT blocked — level-up choice is non-blocking
**And** the player can continue all normal actions while the choice is pending

**Given** a player gains enough XP for another level while a previous level-up choice is pending
**When** `grant_xp` detects another threshold crossed
**Then** the additional level-up is queued (processed sequentially after the first choice is made)
**And** the player is NOT sent a second `level_up_available` until the first is resolved

**Given** the player receives `level_up_available`
**When** they send `{"action": "level_up", "stats": ["strength", "dexterity", "constitution"]}`
**Then** each chosen stat is incremented by 1 (up to 3 unique stats)
**And** stats are capped at 10 — if a chosen stat is already 10, it is skipped with a warning
**And** `level` is incremented by 1
**And** `max_hp` is recalculated: `100 + (new_constitution × 10)`
**And** `hp` is set to new `max_hp` (full heal on level-up)
**And** all stat changes are persisted to DB
**And** the server sends `{"type": "level_up_complete", "level": 2, "stat_changes": {"strength": 2, "dexterity": 2, "constitution": 2}, "new_max_hp": 110}`
**And** if another level-up is queued, the server immediately sends a new `level_up_available`

**Given** a player sends `level_up` action without a pending level-up
**When** the server processes it
**Then** the client receives an error: "No level-up available"

**Given** a player sends `level_up` with duplicate stats (e.g., `["strength", "strength", "dexterity"]`)
**When** the server processes it
**Then** duplicates are deduplicated — only unique stats are boosted (max 3 unique)

**Given** a player sends `level_up` with an invalid stat name (e.g., `"mana"`)
**When** the server processes it
**Then** the client receives an error: "Invalid stat: mana"

**Given** a player gains enough XP to cross multiple thresholds at once (e.g., level 1 with 3000 XP)
**When** the first level-up is processed
**Then** only one level-up occurs at a time — after completing level 2, if XP still exceeds the next threshold (2000), another `level_up_available` is sent

**Given** a player disconnects with a pending level-up
**When** they log back in
**Then** the server re-checks if XP >= threshold and re-sends `level_up_available` if needed

**And** the `level_up` handler is registered in `Game._register_handlers()`
**And** tests verify threshold math, stat choices, cap enforcement, multi-level, queuing, non-blocking behavior, and persistence
**And** `pytest tests/` passes

### Story 11.6: Level-Up Notification & UI

As a player,
I want to see my level, all stats, and XP progress in the UI, and have a clear level-up experience,
So that progression feels visible and rewarding.

**Acceptance Criteria:**

**Given** the stats HUD (from Story 10.8) currently shows HP, XP, ATK
**When** the story is complete
**Then** the main HUD shows only: HP bar (with current/max), Level (e.g., "LVL: 3"), and XP progress to next level (e.g., "XP: 2500/3000")
**And** the ATK display is removed (attack is deprecated, replaced by STR-derived bonuses)
**And** the 6 ability scores (STR, DEX, CON, INT, WIS, CHA) are in a collapsible "Stats" panel, hidden by default
**And** the Stats panel is toggled by clicking a "Stats" button in the HUD or typing `/stats`
**And** the Stats panel shows each ability's numeric value and a brief effect description (e.g., "STR: 3 (+3 physical dmg)  DEX: 2 (-2 incoming dmg)  CON: 4 (+20 max HP)  INT: 1 (+1 magic dmg)  WIS: 1 (+1 healing)  CHA: 2 (+6% XP)")

**Given** the XP display in the HUD
**When** the story is complete
**Then** XP is shown as a visual progress bar with text overlay (e.g., `████░░░░░░ 231/1000`), not just numbers
**And** the XP bar briefly flashes/highlights with a CSS animation when XP changes (subtle, ~0.5s)

**Given** a level-up is pending (player received `level_up_available` but hasn't chosen stats)
**When** the game viewport is displayed
**Then** a persistent "Level Up!" badge/indicator is visible on the HUD (e.g., flashing text or icon near the level display)
**And** clicking the badge reopens the level-up modal
**And** the badge disappears after the player completes their stat choice

**Given** the player receives an `xp_gained` message with `source: "combat"`
**When** the web client processes it
**Then** the XP bar updates immediately but NO chat notification is shown (combat XP is already displayed in the `combat_end` rewards message — avoid double-notification)

**Given** the player receives an `xp_gained` message with a non-combat source (e.g., `source: "exploration"` or `source: "interaction"`)
**When** the web client processes it
**Then** the XP bar updates immediately
**And** a notification appears in the chat/log: "+52 XP (exploration: Discovered Dark Cave)"

**Given** the player receives `level_up_available`
**When** the web client processes it
**Then** a level-up modal/panel appears showing:
- "Level Up!" congratulation message
- 6 stat buttons, each displaying: stat name, current value → new value (e.g., "STR: 1 → 2"), and a precise effect description (e.g., "STR: +1 damage added to each physical damage card per point")
- Click a stat button to toggle selection (highlighted border/background)
- Maximum 3 stats selectable — clicking a 4th shows "Max 3 selected" feedback
- Stats at cap (10) are grayed out and unclickable
- A "Confirm" button at the bottom (disabled until at least 1 stat is selected)
- Clicking Confirm sends the `level_up` action with selected stats
**And** the modal is dismissible — the player can close it and continue playing, then reopen via `/levelup` command or a UI button

**Given** the player receives `level_up_complete`
**When** the web client processes it
**Then** the HUD updates with new level, stats, and max_hp
**And** a celebration notification appears in chat: "You reached Level 2! STR+1, DEX+1, CON+1"

**Given** the `/stats` server action (Story 10.4)
**When** a player sends a stats query
**Then** the response includes: `{"type": "stats_result", "stats": {"hp": 110, "max_hp": 110, "level": 2, "xp": 1100, "xp_next": 2000, "strength": 2, "dexterity": 2, "constitution": 2, "intelligence": 1, "wisdom": 1, "charisma": 1}}`

**Given** the `room_state` and `entity_entered` messages include entity data
**When** a player's entity data is broadcast
**Then** `level` is included in the entity data visible to other players (e.g., `{"id": "player_1", "name": "hero", "level": 3, ...}`)

**Given** the `/stats` slash command (Story 10.6)
**When** the player types `/stats`
**Then** the response displays all 6 abilities, level, XP, XP-to-next-level, HP

**And** all existing web client functionality remains working
**And** `pytest tests/` passes

### Story 11.7: Session Factory Dependency Injection

As a developer,
I want the database session factory to be owned by the Game orchestrator and injected into all consumers,
So that tests cannot accidentally connect to the production database and future database migration (e.g., PostgreSQL) requires changing only one line.

**Acceptance Criteria:**

**Given** `server/core/database.py` defines a module-level `async_session` that 11 modules import directly via `from server.core.database import async_session`
**When** the story is complete
**Then** `Game.__init__()` sets `self.session_factory = async_session` (defaulting to the module-level factory from `server.core.database`)
**And** all 11 consumer modules replace `from server.core.database import async_session` with access through the `game` reference they already receive
**And** all 26 usage sites of `async with async_session() as session:` are changed to `async with game.session_factory() as session:` (or equivalent via `self._game.session_factory()` for Scheduler, `self` for Game methods)

**Given** the integration test fixture in `tests/test_integration.py` currently patches `async_session` in 6 individual modules (missing 5)
**When** the story is complete
**Then** the fixture sets `game.session_factory = test_session_factory` — one assignment, no per-module patches needed for `async_session`
**And** all existing per-module `async_session` patches are removed from the fixture
**And** `player_repo` patches remain as-is (separate concern — repo functions, not session factory)

**Given** `server.core.xp.grant_xp()` currently imports `async_session` from `server.core.database` (unpatched in integration tests, causing hangs when zombie processes hold SQLite locks)
**When** the story is complete
**Then** `grant_xp()` uses `game.session_factory()` via the `game` parameter it already receives
**And** no integration test can accidentally write to `data/game.db`

**Given** `server/room/objects/chest.py` and `server/room/objects/lever.py` use `async_session` in their `interact()` methods
**When** the story is complete
**Then** both use `game.session_factory()` via the `game` parameter their `interact()` methods already receive

**Given** `server/core/scheduler.py` uses `async_session` in spawn check methods
**When** the story is complete
**Then** Scheduler uses `self._game.session_factory()` via the `self._game` reference it already holds

**Given** `Game.startup()` needs a session factory before handlers run
**When** the story is complete
**Then** `Game.__init__()` defaults `self.session_factory` from the module-level import
**And** tests override it after construction but before handlers run (same pattern as `game.room_manager` swap)

**Given** other WebSocket test files (`test_login.py`, `test_auth.py`, `test_stats_persistence.py`) also patch `async_session` per-module
**When** the story is complete
**Then** those fixtures are updated to use `game.session_factory = test_session_factory` where applicable
**And** per-module `async_session` patches are removed

**And** all existing tests pass (`pytest tests/` excluding known hanging tests `test_disconnect_notifies_others`, `test_register_returns_player_id`)
**And** no test writes to `data/game.db` (verified by checking file mtime before/after test run)

## Epic 12: Social Systems

Players can trade items with each other, form parties for cooperative combat, and navigate the world using a discovered map — transforming the game from a solo experience into a social one. Trade is a mutual exchange model with session consent, multi-item offers, bait-and-switch prevention, and atomic DB swaps. Party system tracks leader/members with invite/accept/leave/disband/kick commands, leader succession, and combat integration.

### Story 12.1: Trade System

As a player,
I want to initiate a mutual trade session with another player in my room,
So that I can exchange items with other players through a fair, consent-based process.

**Acceptance Criteria:**

**Given** two players are in the same room
**When** Player A sends `/trade @PlayerB`
**Then** Player B receives a `trade_request` message containing Player A's name
**And** Player B can `/trade accept` to enter negotiation or `/trade reject` to decline

**Given** a trade request is pending
**When** 30 seconds pass without a response
**Then** the request auto-cancels and both players are notified

**Given** both players are in a negotiating session
**When** Player A sends `/trade offer healing_potion 2`
**Then** the item is validated (exists in inventory, sufficient quantity, `tradeable` flag is true)
**And** the offer is added to Player A's offer list
**And** both players receive a `trade_update` message showing current offers from both sides

**Given** both players are in a negotiating session
**When** Player A sends `/trade offer healing_potion 2 fire_essence 1` (multi-item syntax)
**Then** both items are validated and added to Player A's offer list

**Given** a player's offer list contains items
**When** the player sends `/trade remove healing_potion`
**Then** the item is removed from their offer list
**And** both players' ready state is reset

**Given** a player tries to offer more items than `MAX_TRADE_ITEMS` (default 10)
**When** the offer would exceed the limit
**Then** the offer is rejected with an error message

**Given** a player sends `/trade offer` with insufficient quantity
**When** the player has fewer items than offered
**Then** the offer is rejected with "You only have N of item_name"

**Given** both players are in a session
**When** either player sends `/trade ready`
**Then** that player's ready flag is set
**And** both players are notified of the ready state change

**Given** both players have sent `/trade ready`
**When** both ready flags are set
**Then** the trade executes atomically (see Story 12.2 for validation)

**Given** either player sends `/trade cancel`
**Then** the session is cancelled and both players are notified

**Given** a player adds or removes an offer
**When** either player was previously marked ready
**Then** both players' ready state is reset (bait-and-switch prevention)

**Given** a trade session completes, is cancelled, rejected, or times out
**When** a player tries to initiate a new trade
**Then** a 5-second cooldown applies before a new `/trade @player` is allowed

**Given** a player is not in an active trade session
**When** they send `/trade` (no subcommand)
**Then** they receive "You are not in a trade session"

**Given** a player is in an active trade session
**When** they send `/trade` (no subcommand)
**Then** they see current offers from both sides and ready status

**Given** the client sends a trade action with raw args string
**When** the trade handler processes it
**Then** the handler parses the first arg as subcommand and remaining args as parameters (server-side parsing)
**And** invalid subcommands return an error: "Unknown trade command. Use /help for options"

**Given** existing item JSON files don't include a `tradeable` field
**When** items are loaded from JSON at startup
**Then** `tradeable` defaults to `True` — all existing items are tradeable by default

**Given** the existing `_cleanup_player` disconnect handler
**When** Story 12.1 adds trade cancellation
**Then** the full cleanup order is established: (1) cancel trades, (2) remove from combat [existing], (3) party cleanup [placeholder for 12.3], (4) save state [existing], (5) remove from room [existing], (6) notify [existing]

**Given** the system needs player name resolution
**When** any `/trade @player` or `/party invite @player` is processed
**Then** `ConnectionManager` provides a name → entity_id index for lookup (maintained on connect/disconnect)

**Implementation notes:**
- Create `server/trade/` package with `manager.py` (TradeManager + Trade dataclass)
- Create `server/net/handlers/trade.py` for trade action handling
- Add `tradeable: bool = True` field to `ItemDef` and `Item` DB model
- Add name → entity_id mapping to `ConnectionManager`
- Add `TRADE_SESSION_TIMEOUT_SECONDS = 60`, `TRADE_REQUEST_TIMEOUT_SECONDS = 30`, `MAX_TRADE_ITEMS = 10` to config
- Trade state machine: `idle → request_pending → negotiating → one_ready → both_ready → executing → complete`
- Use `asyncio.call_later` for timeout scheduling
- `TradeManager` uses asyncio.Lock for trade assignment
- `/trade` accepts item display names (case-insensitive), consistent with `/use` (ISS-010)
- Register trade handler in message router, update `/help` output
- Disconnect cleanup order: cancel trades → remove from combat → handle party → save state → remove from room → notify

### Story 12.2: Trade Validation

As a player,
I want my trades to be safe and atomic,
So that items cannot be duplicated, lost, or stolen through exploits or edge cases.

**Acceptance Criteria:**

**Given** both players are ready and trade execution begins
**When** the server validates the trade
**Then** both players must still be in the same room, online, and not in combat
**And** all offered items are re-validated from live inventory (sufficient quantity, item exists, `tradeable` flag)
**And** if any offered quantity exceeds current inventory at execution time, the entire trade fails — no partial trades
**And** both players are notified with a `trade_result` message (success or failure with reason)

**Given** both players' offers are valid
**When** the trade executes
**Then** items are removed from both players' inventories and added to the other's in a single DB transaction
**And** in-memory inventory state is updated only after DB commit succeeds
**And** both players receive updated inventory data

**Given** Player A sends `/trade @PlayerA` (self-trade attempt)
**When** the server processes the request
**Then** the trade is rejected with "Cannot trade with yourself"
**And** validation checks `player_db_id` (not entity_id) to catch duplicate login edge cases

**Given** a player disconnects during an active trade session
**When** the disconnect is processed
**Then** the trade session is immediately cancelled
**And** the remaining player is notified: "Trade cancelled — player disconnected"

**Given** a player changes room during an active trade session
**When** the room transition is processed
**Then** the trade session is immediately cancelled
**And** both players are notified: "Trade cancelled — player left the room"
**And** `TradeManager.cancel_trades_for(entity_id)` is called in the movement handler before the room transfer

**Given** a player enters combat during an active trade session
**When** combat begins
**Then** the trade session is immediately cancelled
**And** both players are notified: "Trade cancelled — player entered combat"
**And** `TradeManager.cancel_trades_for(entity_id)` is called in the movement handler on combat entry

**Given** a player is kicked via duplicate login protection
**When** the kick is processed
**Then** all pending trades for that `player_db_id` are cancelled
**And** the other player in the session (if any) is notified

**Given** a player is already in a trade session
**When** another player sends `/trade @player` targeting them
**Then** the request is auto-rejected: "Player is already in a trade session"

**Given** trade requires same-room
**When** a player is in a party with the trade target but in a different room
**Then** the trade request is rejected — party membership has no effect on trade eligibility

**Given** the server crashes during trade execution
**When** the DB transaction did not commit
**Then** both inventories are unchanged (ACID guarantee)
**And** on restart, trade state is gone (ephemeral) — no stale sessions

**Implementation notes:**
- Trade cancellation hooks into: disconnect handler, room transition handler, combat entry handler, duplicate login handler
- Atomic swap: single `async with session.begin()` block — remove from A, add to B, commit
- In-memory `Inventory` objects updated only after successful DB commit
- All cancellation triggers send `trade_result` with `{status: "cancelled", reason: "..."}`
- Tests should cover: valid trade, insufficient items at execution, self-trade, disconnect mid-session, room change mid-session, combat entry mid-session, duplicate login, cross-room party trade attempt

### Story 12.3: Party Infrastructure

As a developer,
I want the server to support party groups with leader/member tracking,
So that the server can track cooperative groups for chat and combat features.

**Acceptance Criteria:**

**Given** the server starts up
**When** all managers are initialized
**Then** a `PartyManager` is created and owned by the `Game` class
**And** `PartyManager` tracks all active parties in-memory

**Given** a player creates a party (via invite acceptance — see Story 12.4)
**When** the party is formed
**Then** a `Party` dataclass is created with: `party_id`, `leader_entity_id`, `members` (ordered list of entity_ids), `created_at`
**And** the inviting player is set as party leader
**And** the accepting player is added as a member

**Given** a party exists
**When** `PartyManager.get_party(entity_id)` is called for any member
**Then** the party instance is returned
**And** `PartyManager.get_party(entity_id)` returns `None` for non-party players

**Given** a party has `MAX_PARTY_SIZE` (default 4) members
**When** another invite is attempted
**Then** the invite is rejected with "Party is full"

**Given** the party leader disconnects
**When** disconnect cleanup runs
**Then** leadership passes to the longest-standing member (earliest in members list)
**And** all remaining party members are notified of the new leader via `party_update` message

**Given** the last member leaves or disconnects
**When** the party has no remaining members
**Then** the party is dissolved and removed from `PartyManager`

**Given** a player disconnects
**When** they are a member (not leader) of a party
**Then** they are removed from the party
**And** remaining members are notified via `party_update`

**Given** an admin triggers server shutdown or restart
**When** shutdown cleanup runs
**Then** all parties are dissolved
**And** all connected players are notified: "Server restarting — all parties dissolved"

**Given** a player's entity_id is known
**When** any system needs to check party membership
**Then** `PartyManager` provides: `is_in_party(entity_id)`, `get_party(entity_id)`, `is_leader(entity_id)`, `get_party_members(entity_id)`

**Implementation notes:**
- Create `server/party/` package with `manager.py` (PartyManager + Party dataclass)
- `Party` dataclass: `party_id: str`, `leader: str` (entity_id), `members: list[str]` (entity_ids, ordered by join time), `pending_invites: dict[str, float]` (target_entity_id → invite_timestamp for cooldown tracking)
- `PartyManager` methods: `create_party(leader, member)`, `add_member(party_id, entity_id)`, `remove_member(entity_id)`, `disband(party_id)`, `get_party(entity_id)`, `is_in_party(entity_id)`, `is_leader(entity_id)`, `get_party_members(entity_id)`, `handle_disconnect(entity_id)`
- Leader succession: on leader disconnect, `members[0]` (after removing leader) becomes new leader
- Party cleanup integrated into disconnect handler (fills placeholder from Story 12.1)
- Shutdown handler dissolves all parties before saving state
- `MAX_PARTY_SIZE` added to config (default 4)

### Story 12.4: Party Commands

As a player,
I want to invite others to my party, accept invites, leave, and manage membership through slash commands,
So that I can form and manage cooperative groups during gameplay.

**Acceptance Criteria:**

**Given** a player is not in a party
**When** they send `/party invite @PlayerB`
**Then** Player B must be online (error: "Player not found" if nonexistent, "Player is not online" if offline)
**And** Player B must not already be in a party (error: "Player is already in a party")
**And** Player B receives a `party_invite` message with the inviter's name
**And** no same-room requirement for invites

**Given** a player receives a party invite
**When** they send `/party accept`
**Then** if the inviter is not yet in a party, a new party is created with the inviter as leader and the accepter as member
**And** if the inviter is already in a party, the accepter is added to that existing party
**And** all party members are notified via `party_update`

**Given** a player receives a party invite
**When** they send `/party reject`
**Then** the invite is declined and the inviter is notified

**Given** a pending party invite
**When** no response within 30 seconds
**Then** the invite auto-expires and both players are notified

**Given** a player has already sent a pending invite
**When** they send `/party invite @AnotherPlayer`
**Then** the previous invite is cancelled and the new invite is sent

**Given** a player was just kicked, or their invite was rejected/expired
**When** the inviter tries to re-invite the same player
**Then** a cooldown applies (e.g., 10 seconds) — "Please wait before re-inviting this player"

**Given** a player is in a party
**When** they send `/party leave`
**Then** they are removed from the party
**And** remaining members are notified via `party_update`
**And** if they were the leader, succession applies (Story 12.3)
**And** if they were in active combat, they remain in the combat instance — party leave does not affect current combat; XP calculated based on combat participants at victory

**Given** the party leader is not in shared combat with any members
**When** the leader sends `/party disband`
**Then** the party is dissolved and all members are notified via `party_update`

**Given** the party leader is not in shared combat with the target
**When** the leader sends `/party kick @PlayerC`
**Then** Player C is removed from the party
**And** Player C and remaining members are notified via `party_update`
**And** the cooldown for re-inviting Player C begins

**Given** the party leader sends `/party kick @PlayerC`
**When** the leader and Player C share an active combat instance
**Then** the kick is rejected: "Cannot kick a player during shared combat"

**Given** the party leader sends `/party disband`
**When** any party members share an active combat instance
**Then** the disband is rejected: "Cannot disband during active party combat"

**Given** a player is in a party
**When** they send `/party` (no subcommand)
**Then** they see: party members list, who is leader, each member's online/offline status and current room

**Given** a player is not in a party
**When** they send `/party` (no subcommand)
**Then** they receive: "You are not in a party"

**Given** the invite target is already in a party
**When** `/party invite @target` is sent
**Then** the invite is rejected: "Player is already in a party — they must /party leave first"

**Given** a player in a party sends `/party <text>` where text is not a known subcommand
**When** the handler processes it
**Then** it falls through to party chat (Story 12.5 will implement the handler; until then, return "Unknown party command")

**Implementation notes:**
- Create `server/net/handlers/party.py` for party action handling
- `/party` uses subcommand pattern: handler parses first arg as subcommand (`invite`, `accept`, `reject`, `leave`, `disband`, `kick`, or no subcommand for status)
- Register party handler in message router
- Update `/help` output to include party commands under "Social" category
- Update client-side slash command parser (`web-demo/js/game.js`) to route `/party` commands
- Invite timeout via `asyncio.call_later` (30s), cancelled on accept/reject
- Per-target cooldown tracked in `Party.pending_invites` dict with timestamps
- All responses use distinct `party_invite` and `party_update` message types

### Story 12.5: Party Chat

As a party member,
I want to send messages that only my party members can see regardless of what room they're in,
So that my party can coordinate across the game world.

**Acceptance Criteria:**

**Given** a player is in a party
**When** they send `/party Hey everyone, meet at dark_cave`
**Then** all party members receive a `party_chat` message with format `{type: "party_chat", from: "<sender_name>", message: "<text>"}`
**And** the message is delivered regardless of which room each member is in
**And** players NOT in the party do not receive the message

**Given** a player is not in a party
**When** they send `/party Some message`
**Then** they receive an error: "You are not in a party"

**Given** a player sends a party chat message
**When** the server processes it
**Then** the sender's name is set server-side from the entity (no client impersonation possible)
**And** the action is `party_chat` (dedicated action, not overloading existing `chat` action)

**Given** a party chat message exceeds `MAX_CHAT_MESSAGE_LENGTH` (default 500 characters)
**When** the server processes it
**Then** the message is rejected: "Message too long (max 500 characters)"

**Given** a party has 4 members across 3 different rooms
**When** one member sends a party chat message
**Then** all 4 members (including sender) receive the message
**And** no other players in any of those rooms see the message

**Given** a party member disconnects between message send and delivery
**When** the server iterates members to deliver
**Then** the send failure for the disconnected member is handled gracefully (no exception)
**And** the message is delivered to all remaining connected members

**Given** the web client receives a `party_chat` message
**When** the message is rendered in the chat log
**Then** it is visually distinct from room chat (e.g., prefixed with `[Party]` or color-coded)

**Given** Story 12.4's party handler receives an unrecognized subcommand from a player in a party
**When** Story 12.5 is implemented
**Then** the fallback routes to party chat instead of returning "Unknown party command"

**Implementation notes:**
- Party chat routing: handler receives `party_chat` action → validates sender is in party via `PartyManager` → iterates `get_party_members()` → sends to each via `ConnectionManager`
- Use same broadcast pattern as existing room chat (graceful send failure handling)
- Client-side slash command parser: `/party <message>` when the first word is NOT a subcommand routes as party chat
- Disambiguation: `/party invite` is a command; `/party hello` is a chat message. Parser checks first arg against known subcommands.
- Web client renders `party_chat` messages with `[Party]` prefix in a distinct color
- `MAX_CHAT_MESSAGE_LENGTH = 500` added to config
- Update 12.4's fallback handler to route to party chat

### Story 12.6: CombatInstance Multi-Player Extension

As a developer,
I want the CombatInstance to support multiple players in a single combat,
So that party combat can be built on a proven multi-player combat engine.

**Acceptance Criteria:**

**Given** the existing `CombatInstance` class
**When** Story 12.6 implementation begins
**Then** the developer audits `CombatInstance` internals: verify `players` supports a list, turn cycling handles N players, victory/defeat conditions work with N players

**Given** the existing `CombatManager.start_combat()` accepts a single player
**When** Story 12.6 extends it for multi-player
**Then** the method accepts either a single entity_id or a list of entity_ids
**And** solo combat (single player) continues to work identically to pre-12.6 behavior
**And** all existing combat tests pass without modification

**Given** a combat instance is created with N players
**When** turns are processed
**Then** turn order is round-robin through the player list (first player in list goes first)
**And** each player gets one action per turn (play card, use item, pass, or flee)

**Given** a combat instance has multiple players
**When** end of cycle is reached (all players have acted)
**Then** mob attacks one random player from the active player list
**And** only players still in combat are eligible targets

**Given** a player flees from multi-player combat
**When** the flee is processed
**Then** the player is removed from the combat instance's active player list
**And** their `in_combat` flag is cleared
**And** turn cycling continues with remaining players

**Given** a player dies in multi-player combat
**When** their HP reaches 0
**Then** they are removed from the combat instance (same as flee)
**And** death/respawn mechanic applies per existing FR53

**Given** all players in a combat instance have fled or died
**When** no active players remain
**Then** combat ends in defeat
**And** mob HP resets (existing behavior)

**Given** the mob's HP reaches 0 in multi-player combat
**When** combat ends in victory
**Then** victory is detected correctly regardless of which player dealt the killing blow
**And** all surviving players in the instance are eligible for rewards

**Implementation notes:**
- Audit `CombatInstance` first — check if `self.players` is already a list or single reference
- If single reference: refactor to list, update all internal references
- Turn cycling: maintain a `current_turn_index` that cycles through active players
- Mob targeting: `random.choice(active_players)` at end of cycle
- Flee/death: remove from active players list, adjust turn index if needed
- Victory: `mob.stats["hp"] <= 0` — unchanged logic
- Defeat: `len(active_players) == 0` — check after each player removal
- All existing solo combat tests must pass — this is additive, not a rewrite

### Story 12.7: Party Combat Integration

As a party member,
I want my nearby party members to join me in combat when I encounter a mob,
So that we can fight together as a team with scaled challenge and shared rewards.

**Acceptance Criteria:**

**Given** a player in a party moves onto a tile with an alive, non-`in_combat` hostile mob
**When** combat is triggered
**Then** all party members in the same room who are NOT already `in_combat` are pulled into the combat instance
**And** the triggering player and all joining members are set `in_combat = True`
**And** only the triggering player's party joins — other players/parties on the same tile are unaffected
**And** the mob is marked `in_combat` to prevent duplicate encounters

**Given** a party combat encounter starts with N party members
**When** the `CombatInstance` is created
**Then** mob HP is scaled: `base_hp × N` (party_size at encounter time)
**And** mob HP does not rescale if members leave mid-combat (flee/death)

**Given** party members are pulled into combat
**When** the combat instance is created
**Then** ALL participating players (triggering player AND pulled-in party members) receive a `combat_start` message
**And** each player's `combat_start` includes their hand, the mob info, and combat state

**Given** a party member sends `/flee` during party combat
**When** the flee is processed
**Then** remaining members are notified: "PlayerA has fled the battle!"

**Given** a party member dies during party combat
**When** their HP reaches 0
**Then** they respawn in `town_square` with full HP per existing death/respawn mechanic (FR53)
**And** they do NOT receive combat XP
**And** party membership persists across respawn

**Given** the mob is defeated in party combat
**When** combat ends in victory
**Then** combat XP is calculated per existing formula (hit_dice-based)
**And** `XP_PARTY_BONUS_PERCENT` (default 10) is applied ONLY if 2+ party members are in the combat instance at victory
**And** XP (with bonus if applicable) is awarded to each surviving combat participant

**Given** a mob is defeated in party combat
**When** loot is generated
**Then** each surviving combat participant receives an independent loot roll from the mob's loot table
**And** each participant's loot is added to their inventory independently
**And** each participant's `combat_end` message includes their own loot

**Given** a player `/party leave`s during active party combat
**When** the leave is processed
**Then** the player remains in the combat instance — party leave does not affect current combat
**And** XP is calculated based on combat participants at victory, not current party state

**Given** a non-party player in the same room
**When** a party member triggers combat
**Then** the non-party player is NOT pulled into combat

**Given** a party member in the same room is already `in_combat` (different combat instance)
**When** another party member triggers a new encounter
**Then** the already-in-combat member is NOT pulled into the new encounter

**Implementation notes:**
- Movement handler (`server/net/handlers/movement.py`): on mob encounter, check if player is in a party → gather eligible party members (same room, not in_combat) → pass list to `CombatManager.start_combat()`
- HP scaling: `mob.stats["max_hp"] * len(players)`, set `mob.stats["hp"]` to scaled value
- XP distribution: `base_xp = combat_xp_formula(hit_dice)`, if `len(surviving_players) >= 2`: `xp = base_xp * (1 + XP_PARTY_BONUS_PERCENT / 100)`, else `xp = base_xp`; each survivor gets full `xp` (not split)
- Loot: independent rolls per surviving participant
- `combat_start` message sent to ALL participants, not just triggering player
- `XP_PARTY_BONUS_PERCENT` already exists in config (placeholder from Epic 11)

### Story 12.8: World Map

As a player,
I want to see a map of rooms I've discovered and their connections,
So that I can navigate the game world and plan my exploration.

**Acceptance Criteria:**

**Given** a player sends `/map`
**When** the server processes the request
**Then** the server reads the player's `visited_rooms` from the Player model
**And** cross-references with room exit data from `RoomManager` using existing room exit definitions
**And** sends a `map_data` message to the player

**Given** a player has visited `town_square` and `dark_cave`
**When** they send `/map`
**Then** the `map_data` response includes only discovered rooms: `[{room_key: "town_square", name: "Town Square"}, {room_key: "dark_cave", name: "Dark Cave"}]`
**And** undiscovered rooms are omitted entirely — player cannot infer total room count or names

**Given** a discovered room has exits to both discovered and undiscovered rooms
**When** connections are built
**Then** connections to discovered rooms show the destination name: `{from: "town_square", to: "dark_cave", direction: "left"}`
**And** connections to undiscovered rooms show `???` as destination: `{from: "town_square", to: "???", direction: "right"}`

**Given** a player has visited all 4 rooms
**When** they send `/map`
**Then** all rooms and all connections are shown with full names (no `???`)

**Given** a player has visited zero rooms (edge case — should not happen since login places in a room)
**When** they send `/map`
**Then** they receive an empty map or the current room only

**Given** a room_key in `visited_rooms` is not found in `RoomManager` (stale data)
**When** the map is built
**Then** the stale room is skipped with a warning log (no error to player)

**Given** the `visited_rooms` field already exists on the Player model
**When** Story 12.8 is implemented
**Then** no new DB schema changes are needed — reuse existing `visited_rooms` list

**Given** the web client receives a `map_data` message
**When** the message is rendered
**Then** the client displays a text-based node list in a dedicated panel or chat section
**And** rooms are listed with their names
**And** connections show direction and destination (or `???` for undiscovered)
**And** the display is visually distinct from chat messages

**Given** a player discovers a new room (first visit via room transition)
**When** they subsequently send `/map`
**Then** the newly discovered room appears in the map data

**Given** all Epic 12 commands are implemented
**When** a player sends `/help`
**Then** commands are grouped by category: Movement, Combat, Social, Info

**Implementation notes:**
- Add `map` action to existing query handler (`server/net/handlers/query.py`)
- Map handler: `player.visited_rooms` → for each visited room, get room from `RoomManager` → extract exits → build connections list → filter undiscovered destinations to `???`
- Response format: `{type: "map_data", rooms: [{room_key, name}], connections: [{from_room, to_room, direction}]}`
- Register `map` action in message router
- Update client-side slash command parser to route `/map` → `{action: "map"}`
- Web client: render `map_data` as formatted text in chat or a collapsible panel
- Update `/help` output to group all commands by category (Movement, Combat, Social, Info)
- No new config values needed
- `visited_rooms` is already populated by exploration XP logic (Epic 11, Story 11.4)

## Epic 13: Database Infrastructure

Harden the database access layer for production readiness. Replace the current "repos commit internally" pattern with a transaction context manager that provides atomic multi-write operations, automatic rollback on exceptions, and proper transaction boundaries for future PostgreSQL migration.

### Story 13.1: Transaction Context Manager and Repo Refactor

As a developer,
I want all database writes within a single logical operation to be atomic (all-or-nothing),
So that the server never persists partial state on crash or concurrent access, and the codebase is ready for PostgreSQL.

**Acceptance Criteria:**

**Given** the `Game` class owns the session factory
**When** Story 13.1 is implemented
**Then** `Game` gains a `transaction()` async context manager method that yields an `AsyncSession`, auto-commits on clean exit, and auto-rolls back on exception

**Given** any repo write function (`update_position`, `update_stats`, `update_inventory`, `update_visited_rooms`, `create`, `save`, `upsert_room`, `load_cards_from_json`, `load_items_from_json`, `set_player_object_state`, `set_room_object_state`)
**When** called inside a `transaction()` block
**Then** the repo function executes the query but does NOT call `session.commit()` — the transaction context manager commits at block exit

**Given** a handler that performs multiple DB writes in one logical operation (e.g., `_save_player_state` with position + stats + inventory + visited_rooms)
**When** all writes are inside one `async with game.transaction() as session:` block
**Then** all writes commit atomically — a crash between writes results in zero writes persisted (rollback), not partial state

**Given** the trade swap in `_execute_trade` currently bypasses repos with raw `session.execute()` + direct `session.commit()`
**When** Story 13.1 is implemented
**Then** the trade swap uses `player_repo.update_inventory()` for both players inside one `transaction()` block — no more raw SQL bypass

**Given** the loot distribution in `_check_combat_end` currently bypasses repos with direct model mutation + `session.commit()`
**When** Story 13.1 is implemented
**Then** loot distribution uses `player_repo.update_inventory()` inside a `transaction()` block — no more raw SQL bypass

**Given** the chest interaction in `chest.py` currently uses direct model mutation + `session.commit()`
**When** Story 13.1 is implemented
**Then** chest interaction uses repo functions inside a `transaction()` block

**Given** the scheduler spawn checkpoint code currently uses direct `session.add()` + `session.commit()`
**When** Story 13.1 is implemented
**Then** scheduler uses a `transaction()` block (repo functions or equivalent)

**Given** all 26 `session_factory()` call sites in server code
**When** Story 13.1 is implemented
**Then** all are replaced with `game.transaction()` (or `self.transaction()` in `Game` methods)

**Given** all existing tests (804 tests)
**When** Story 13.1 is implemented
**Then** all tests pass with updated mock patterns — mock `transaction()` replaces mock `session_factory()`

**Given** a solo player triggers combat (not in a party)
**When** combat runs through to victory with loot and XP
**Then** behavior is identical to pre-13.1 — no gameplay changes

**Implementation notes:**
- `Game.transaction()` implementation: `@asynccontextmanager` wrapping `self.session_factory()`, yields session, commits on clean exit, rolls back + re-raises on exception
- Remove `await session.commit()` from all 18 occurrences across 9 repo files
- Replace `game.session_factory()` with `game.transaction()` in all 26 call sites across 12 server files
- Replace 4 bypass patterns (trade.py, combat.py loot, chest.py, scheduler.py) with repo calls inside `transaction()` blocks
- Test mock pattern: `game.transaction` returns same shape as `session_factory` — `MagicMock(return_value=mock_ctx)` where `mock_ctx` is an async context manager yielding a mock session. The key difference: mock session's `commit` is no longer called by repos, only by the context manager
- 159 test references to `session_factory` across 27 test files need updating
- No new dependencies, no schema changes, no config changes
- Pure refactor — zero gameplay behavior changes

---

## Epic 15: Server Architecture Refinement

The server's internal structure is tightened — player session lifecycle gets a dedicated manager, handler boilerplate is eliminated via middleware, cross-module dependencies flow in the correct direction, and remaining domain model gaps are closed. This is a pure refactoring epic: zero gameplay behavior changes, all existing tests pass unchanged.

**No new FRs** — internal refactoring driven by codebase review findings, not new functionality.
**Findings source:** Adversarial codebase review (2026-04-11).
**Deferred findings:** (A) `xp.py` mixing business logic with WebSocket sending — acknowledged trade-off; centralizing notification prevents forgotten sends, refactoring requires callback/event pattern design. (V) untyped stats dicts — requires TypedDict/dataclass design; scope for a future epic. (G) `TradeManager.set_connection_manager()` setter injection — low impact, defer unless touched by another story.

### Story 15.1: Player Session Manager

As a developer,
I want player session lifecycle (create, lookup, remove, iterate) managed by a dedicated `PlayerManager` class,
So that session operations are centralized instead of scattered across handlers and the `Game` class.

**Acceptance Criteria:**

**Given** `game.player_entities` / `self.player_entities` is a raw `dict[str, PlayerSession]` accessed directly from 13 server files (handlers + `chest.py`, `xp.py`, `app.py` via `self.`) with 7 distinct access patterns:
- `.get(entity_id)` — safe lookup (30+ sites across handlers, `chest.py`, `xp.py`)
- `[entity_id] = PlayerSession(...)` — direct assignment (`auth.py:370`)
- `.pop(entity_id, None)` — removal (`auth.py:169`)
- `[entity_id].attr = value` — attribute mutation through index (`auth.py:422`)
- `[entity_id]` — direct index lookup, assumes key exists (`movement.py:209`) — replace with `get_session()` + None guard
- `not in game.player_entities` — containment check (`party.py:190`)
- `.clear()` — bulk removal after shutdown cleanup loop (`app.py:141`)
**When** Story 15.1 is implemented
**Then** a `PlayerManager` class exists (in `server/player/manager.py`) with methods covering all patterns:
- `get_session(entity_id: str) -> PlayerSession | None` — replaces `.get()` and direct `[id]` lookups
- `set_session(entity_id: str, session: PlayerSession) -> None` — replaces `[id] = session`
- `remove_session(entity_id: str) -> PlayerSession | None` — replaces `.pop()`
- `has_session(entity_id: str) -> bool` — replaces `in` / `not in` checks
- `all_entity_ids() -> list[str]` — replaces `list(.keys())` for iterate-during-mutation (`app.py:119`)
- `all_sessions() -> Iterator[tuple[str, PlayerSession]]` — replaces `.items()` iteration
- `clear() -> None` — replaces `.clear()` (used in `shutdown()` after cleanup loop; may become unnecessary if loop already calls `remove_session` per entity)
**And** `game.player_manager` replaces `game.player_entities`

**Given** `PlayerSession` is constructed in `auth.py:370` with 6 keyword arguments (`entity`, `room_key`, `db_id`, `inventory`, `visited_rooms`, `pending_level_ups`)
**When** Story 15.1 is implemented
**Then** `set_session(entity_id, session)` takes a pre-constructed `PlayerSession` — construction remains at the call site in `auth.py` (no factory method needed)

**Given** all server files that access `player_entities` (~39 occurrences across 13 files, including `app.py` via `self.`, `chest.py`, and `xp.py`)
**When** Story 15.1 is implemented
**Then** they use the appropriate `PlayerManager` method instead
**And** the `player_entities` dict is no longer publicly accessible

**Given** all existing tests (807+) — ~146 `player_entities` references across 26 test files
**When** Story 15.1 is implemented
**Then** all tests pass with no assertion value changes
**And** test fixtures are updated to use `game.player_manager` methods

**Implementation notes:**
- Finding (I/W): most significant missing abstraction in the codebase
- `PlayerManager` is a plain Python class (no inheritance), owns the `dict` internally
- `Game.__init__` creates `self.player_manager = PlayerManager()`
- **Test impact is the largest effort**: ~146 references across 26 test files need mechanical `player_entities` → `player_manager` updates
- `all_entity_ids()` returns a snapshot list (not a view) so callers can safely iterate while sessions are removed (as in `app.py:119 shutdown()`)
- Pure refactor — zero gameplay behavior changes

### Story 15.2: Relocate Player Cleanup to Game Layer

As a developer,
I want the player cleanup orchestration function to live at the game layer rather than in a handler module,
So that the dependency direction is correct (orchestrator → handlers, not handlers → orchestrator).

**Acceptance Criteria:**

**Given** `_cleanup_player` is defined in `server/net/handlers/auth.py` (line 146) with a `_` private prefix
**And** it is imported by `server/app.py` via deferred imports at lines 114 and 359 — a reverse dependency
**When** Story 15.2 is implemented
**Then** the cleanup function is a method on `PlayerManager` (from Story 15.1): `player_manager.cleanup_session(entity_id, game)`
**And** the private sub-functions (`_cleanup_trade`, `_cleanup_combat`, `_cleanup_party`, `_save_player_state`, `_remove_from_room`) are either moved alongside or remain in `auth.py` and are called by the manager

**Given** `_cleanup_party` (auth.py:102-104) does a deferred import of `cleanup_pending_invites` from `party.py` handler
**When** Story 15.2 is implemented (before Story 15.4)
**Then** the deferred import moves to `PlayerManager.cleanup_session()` — this is temporary debt cleaned up by Story 15.4
**Or** if Story 15.4 is done first, the call becomes `game.party_manager.cleanup_invites(entity_id)` with no deferred import needed

**Given** `handle_logout` in `auth.py` calls `_cleanup_player`
**When** Story 15.2 is implemented
**Then** it calls `game.player_manager.cleanup_session(entity_id, game)` instead

**Given** `Game.shutdown()` (line 114) and `Game.handle_disconnect()` (line 359) each do a deferred import of `_cleanup_player` from `auth.py`
**When** Story 15.2 is implemented
**Then** both call `self.player_manager.cleanup_session(...)` instead
**And** the deferred imports in `app.py` are removed

**Given** all existing tests
**When** Story 15.2 is implemented
**Then** all tests pass with no assertion value changes

**Implementation notes:**
- Finding (U): reverse dependency where orchestrator imports handler's private function
- Depends on Story 15.1 (PlayerManager must exist)
- **Trade-off acknowledged (ADR-15-2):** `cleanup_session(entity_id, game)` takes the full `Game` object because cleanup touches trade, combat, party, room, and DB managers. This is the same "pass the orchestrator" pattern used by handlers — acceptable since the alternative (injecting 5 managers individually) adds complexity without reducing coupling
- The sub-cleanup functions can stay in auth.py as module-level helpers called by the manager, or move to the manager — developer's choice based on import complexity
- Pure refactor — zero gameplay behavior changes

### Story 15.3: Handler Auth Middleware

As a developer,
I want a `@requires_auth` decorator that injects `entity_id` and `player_info` into handler functions,
So that the 8-12 line auth-check boilerplate is not duplicated across 15+ handlers.

**Acceptance Criteria:**

**Given** the repeated auth-check pattern across handlers (post-15.1 form):
```python
entity_id = game.connection_manager.get_entity_id(websocket)
if entity_id is None:
    await websocket.send_json({"type": "error", "detail": "Not logged in"})
    return
player_info = game.player_manager.get_session(entity_id)
if player_info is None:
    await websocket.send_json({"type": "error", "detail": "Not logged in"})
    return
```
**When** Story 15.3 is implemented
**Then** a `@requires_auth` decorator (in `server/net/auth_middleware.py` or similar) wraps handler functions
**And** the **outer (decorated) function** retains the `(websocket, data, *, game)` signature — lambda registration in `app.py` is unaffected
**And** the **inner function** receives additional `entity_id: str` and `player_info: PlayerSession` keyword arguments injected by the decorator
**And** unauthenticated requests are rejected with the standard error before the inner handler body runs

**Given** 15+ handler functions that begin with the auth-check boilerplate
**When** Story 15.3 is implemented
**Then** they are decorated with `@requires_auth` and the manual boilerplate is removed
**And** handler signatures change to include `entity_id` and `player_info` keyword params

**Given** `handle_login`, `handle_register` (do not require auth)
**When** Story 15.3 is implemented
**Then** they are NOT decorated — they keep their current behavior

**Given** `handle_logout` performs the same auth-check boilerplate before calling cleanup
**When** Story 15.3 is implemented
**Then** `handle_logout` IS decorated with `@requires_auth` — it receives `entity_id` and `player_info`, then calls `game.player_manager.cleanup_session(entity_id, game)`

**Given** all existing tests
**When** Story 15.3 is implemented
**Then** all tests pass with no assertion value changes

**Implementation notes:**
- Finding (D): auth boilerplate duplicated 20 times across 10 handler files
- The decorator uses `functools.wraps` and has the same outer signature as current handlers
- Depends on Story 15.1 (decorator calls `game.player_manager.get_session()`) and Story 15.2 (`handle_logout` AC assumes `cleanup_session` exists)
- Pure refactor — zero gameplay behavior changes

### Story 15.4: Party Invite State → PartyManager

As a developer,
I want party invite tracking state managed by `PartyManager` instead of module-level globals in the party handler,
So that the handler is stateless and the unique `set_game_ref()` wiring pattern is eliminated.

**Acceptance Criteria:**

**Given** 4 module-level mutable dicts in `server/net/handlers/party.py`:
- `_pending_invites: dict[str, str]` (line 19)
- `_outgoing_invites: dict[str, str]` (line 20)
- `_invite_timeouts: dict[str, asyncio.TimerHandle]` (line 21)
- `_invite_cooldowns: dict[str, dict[str, float]]` (line 22)
**And** `_game_ref: Game | None` global (line 25) with `set_game_ref()` setter (line 28)
**When** Story 15.4 is implemented
**Then** these dicts and the game ref are attributes on `PartyManager` (in `server/party/manager.py`)
**And** the module-level globals and `set_game_ref()` function are removed

**Given** `_invite_timeouts` stores `asyncio.TimerHandle` objects whose sync callbacks (`_handle_invite_timeout`) need:
- `connection_manager` to send timeout notifications via `create_task(send_to_player(...))`
- `_get_entity_name()` which accesses `game.player_entities` for display names
**When** Story 15.4 is implemented
**Then** `PartyManager.__init__` accepts `connection_manager` via constructor injection (consistent with how `CombatManager` takes `effect_registry`)
**And** timer callbacks reference `self._connection_manager` instead of `_game_ref.connection_manager`
**And** display names are stored at invite creation time (in the invite tracking dicts) so the timeout callback does not need player session lookup at fire time

**Given** `app.py` line 235: `set_party_game_ref(self)` (aliased from `set_game_ref` at import on line 157)
**When** Story 15.4 is implemented
**Then** the `set_party_game_ref` call and its import are removed
**And** `PartyManager` construction in `Game.__init__` passes `connection_manager`: `self.party_manager = PartyManager(connection_manager=self.connection_manager)`

**Given** handler functions in `party.py` that access the module-level invite dicts
**When** Story 15.4 is implemented
**Then** they access `game.party_manager` methods/attributes instead

**Given** all existing tests
**When** Story 15.4 is implemented
**Then** all tests pass with no assertion value changes

**Implementation notes:**
- Finding (E): only handler that maintains state outside a manager
- `cleanup_pending_invites()` moves to `PartyManager.cleanup_invites(entity_id)`
- Constructor injection of `connection_manager` matches `CombatManager(effect_registry=...)` pattern
- Pure refactor — zero gameplay behavior changes

### Story 15.5a: Extract Effect Targeting

As a developer,
I want the duplicated effect source/target resolution extracted into a shared method on `CombatInstance`,
So that the effect targeting logic exists in exactly one place.

**Acceptance Criteria:**

**Given** `CombatInstance.resolve_card_effects()` (lines 96-107) and `CombatInstance.use_item()` (lines 199-206)
both contain identical logic to determine source/target based on effect type:
```python
if effect_type in ("heal", "shield", "draw"):
    source = player_stats; target = player_stats
else:
    source = player_stats; target = self.mob_stats
```
**When** Story 15.5a is implemented
**Then** a private method `_resolve_effect_targets(entity_id, effect_type) -> tuple[dict, dict]` is extracted
**And** both `resolve_card_effects()` and `use_item()` call it

**Given** all existing tests
**When** Story 15.5a is implemented
**Then** all tests pass with no assertion value changes

**Implementation notes:**
- Finding (Q): duplicated effect logic
- The `_resolve_effect_targets` method is ~5 lines, extracted from two near-identical blocks
- Single-file change (`server/combat/instance.py`), minimal risk
- Pure refactor — zero gameplay behavior changes

### Story 15.5b: NpcEntity & Dataclass Relocation

As a developer,
I want `NpcEntity` relocated from `room/objects/` to `room/`, and Trade/Party dataclasses split into their own files,
So that the domain model is accurately organized and consistent across modules.

**Acceptance Criteria:**

**Given** `NpcEntity` is a `@dataclass` in `server/room/objects/npc.py` alongside `InteractiveObject` subclasses (ChestObject, LeverObject) despite not extending `RoomObject` or `InteractiveObject`
**When** Story 15.5b is implemented
**Then** `NpcEntity` and all co-located functions (`create_npc_from_template`, `load_npc_templates`) are relocated to `server/room/npc.py` (at the room level, not inside `objects/`)
**And** all imports are updated — **16 import sites**: 4 server files (`app.py`, `scheduler.py`, `room.py`, `room/manager.py`) + 12 test files (`test_integration.py`, `test_query.py`, `test_loot.py`, `test_logout.py`, `test_room_system.py`, `test_npc.py`, `test_combat_entry.py`, `test_spawn.py`, `test_concurrency.py`, `test_startup_wiring.py`, `test_sample_data.py`, `test_events.py`)
**And** the old `server/room/objects/npc.py` file is deleted (no external consumers exist)

**Given** `Trade` dataclass is co-located in `server/trade/manager.py` (line 13) and `Party` dataclass is co-located in `server/party/manager.py` (line 12)
**When** Story 15.5b is implemented
**Then** `Trade` is moved to `server/trade/session.py` and `Party` is moved to `server/party/party.py`
**And** all imports are updated (including test files)

**Given** all existing tests
**When** Story 15.5b is implemented
**Then** all tests pass with no assertion value changes

**Implementation notes:**
- Findings (C, X): NpcEntity misplaced, inconsistent dataclass locations
- NPC relocation has the largest blast radius (16 import sites) — use find-and-replace
- Trade/Party dataclass splits are low-risk (few imports)
- Pure refactor — zero gameplay behavior changes

### Story 15.6: EventBus Resilience & Config Gaps

As a developer,
I want the EventBus to isolate subscriber failures, and remaining unconfigurable constants to be in `Settings`,
So that one broken subscriber cannot crash the emit loop and all operational constants are environment-overridable.

**Acceptance Criteria:**

**Given** `EventBus.emit()` in `server/core/events.py` (lines 20-21) iterates subscribers with no error isolation:
```python
for cb in self._subscribers.get(event_type, []):
    await cb(**data)  # exception propagates, remaining callbacks skipped
```
**When** Story 15.6 is implemented
**Then** each subscriber callback is wrapped in `try/except` with `logger.exception(...)` logging
**And** remaining subscribers are still called even if one fails
**And** a test verifies: subscriber A raises → subscriber B still executes

**Given** `_RARE_CHECK_INTERVAL = 60` in `server/core/scheduler.py` (line 28) is a module-level constant
**When** Story 15.6 is implemented
**Then** it is moved to `Settings` as `RARE_CHECK_INTERVAL_SECONDS: int = 60`
**And** `Scheduler` references `settings.RARE_CHECK_INTERVAL_SECONDS`

**Given** `RoomState.mob_states` field in `server/room/models.py` (line 28) is never written with actual data
**When** Story 15.6 is implemented
**Then** the field is removed from the model
**And** Alembic migration removes the column (using `op.batch_alter_table` for SQLite compatibility if SQLite < 3.35.0)
**Or** if the field is planned for future use, a code comment documents the intent

**Given** all existing tests
**When** Story 15.6 is implemented
**Then** all tests pass; new test added for EventBus error isolation

**Implementation notes:**
- Findings (R, O, L): EventBus fragility, unconfigurable constant, unused DB field
- Alembic infrastructure exists (Story 14.7 complete). SQLite `DROP COLUMN` requires version ≥ 3.35.0 or `batch_alter_table` — check version at implementation time
- If `mob_states` is intended for future NPC state persistence, add a `# Reserved for Story X` comment instead of removing
- One new test for EventBus error isolation; otherwise pure refactor

### Story 15.7: Data Layer Consistency

As a developer,
I want the SpawnCheckpoint data access to follow the repo pattern,
So that the data layer is consistent across all persistable entities.

**Acceptance Criteria:**

**Given** `SpawnCheckpoint` queries are inlined directly in `Scheduler._run_rare_spawn_checks()` (lines 128-206) and `_recover_checkpoints()` (lines 212-227) in `server/core/scheduler.py`
**When** Story 15.7 is implemented
**Then** a `server/room/spawn_repo.py` module exists with functions:
- `get_checkpoint(session, room_key, npc_template_key) -> SpawnCheckpoint | None`
- `upsert_checkpoint(session, room_key, npc_template_key, last_check) -> None`
- `get_all_checkpoints(session) -> list[SpawnCheckpoint]`
**And** `Scheduler` uses these repo functions instead of inline queries

**Given** all existing tests
**When** Story 15.7 is implemented
**Then** all tests pass with no assertion value changes

**Implementation notes:**
- Finding (J): SpawnCheckpoint breaks repo pattern
- `spawn_repo.py` follows the same stateless-functions-with-AsyncSession pattern as other repos
- `core/scheduler.py` already imports from `room/` (npc templates, spawn models) — the new `room/spawn_repo` import continues this existing dependency direction
- **Upsert unification (finding K) deferred:** The three upsert-from-JSON patterns (`room/repo.py`, `items/item_repo.py`, `combat/cards/card_repo.py`) handle different models with different field mappings and nested JSON structures. A generic utility would be more complex than the 3 separate ~20-line implementations it replaces. This is a premature abstraction — defer unless a 4th upsert pattern emerges.
- Pure refactor — zero gameplay behavior changes

---

### Epic 15 — Architecture Decisions

- **ADR-15-1:** `PlayerManager` is a plain class, not a base class — mirrors `PartyManager`/`TradeManager` style
- **ADR-15-2:** `cleanup_session(entity_id, game)` takes full `Game` object — cleanup touches 5 managers, injecting each individually adds complexity without reducing coupling. Acknowledged trade-off: same "pass the orchestrator" pattern handlers use
- **ADR-15-3:** `@requires_auth` decorator in dedicated `auth_middleware.py` — outer function retains `(websocket, data, *, game)` signature; inner function receives additional `entity_id`, `player_info` kwargs
- **ADR-15-4:** Party invite dicts become `PartyManager` attributes — `connection_manager` injected via constructor (matches `CombatManager(effect_registry=...)` pattern)
- **ADR-15-5:** `NpcEntity` moves to `server/room/npc.py` — stays in `room/` package since NPCs are room-spatial, but not in `objects/` since they're not `InteractiveObject`
- **ADR-15-6:** EventBus error isolation via try/except per callback — no retry, just log and continue
- **ADR-15-7:** `mob_states` field disposition decided at implementation time — remove if truly unused (with Alembic migration), comment if planned
- **ADR-15-8:** Upsert unification deferred — three upsert patterns differ enough in field mapping and nested JSON structure that a generic utility would be a premature abstraction

### Epic 15 — Definition of Done

- All stories complete
- All 807+ existing tests pass with no assertion value changes
- `grep -r "\.player_entities" server/ tests/` returns zero hits (catches both `game.` and `self.` access patterns)
- No `_cleanup_player` import in `app.py` or test files
- No module-level mutable state in `party.py` handler
- Auth boilerplate (entity_id lookup + player_info lookup + error return) appears in at most 2 places (the decorator itself, and possibly login/register)
- No duplicated effect source/target logic in `CombatInstance` — `_resolve_effect_targets` is the single call site
- No direct `select(SpawnCheckpoint)` or `session.add(SpawnCheckpoint(...))` in `scheduler.py` — all access via `spawn_repo`
- CLAUDE.md updated with: PlayerManager convention, `@requires_auth` usage, NpcEntity location
