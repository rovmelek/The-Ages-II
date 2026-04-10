---
stepsCompleted: ["step-01-validate-prerequisites", "step-02-design-epics", "step-03-create-stories", "step-04-final-validation", "step-01-epic10-prerequisites", "step-02-epic10-design", "step-03-epic10-stories", "step-04-epic10-validation"]
inputDocuments:
  - "THE_AGES_SERVER_PLAN.md"
  - "_bmad-output/planning-artifacts/architecture.md"
  - "_bmad-output/planning-artifacts/execution-plan.md"
  - "_bmad-output/implementation-artifacts/tech-spec-web-test-client.md"
  - "CLAUDE.md"
  - "_bmad-output/implementation-artifacts/sprint-status.yaml"
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
FR78: Level-up mechanic — when XP exceeds threshold, player levels up with stat increases (HP, attack)
FR79: Level-up notification — server sends `level_up` message to player with new level and stat changes
FR80: Level display — player level shown in stats HUD and included in entity data visible to other players
FR81: `/stats` updated to include level and XP-to-next-level
FR82: Trade system — `/trade @player` initiates trade request; accept/reject flow; item transfer between inventories
FR83: Trade validation — both players must be in same room, online, not in combat; items validated before transfer
FR84: Party system — `/party invite @player`, `/party accept`, `/party leave`, `/party disband`
FR85: Party chat — `/party message` sends to party members only, regardless of room
FR86: Party combat — party members in same room enter combat together when any member encounters a mob
FR87: World map — `/map` shows discovered rooms and their connections; rooms discovered on first visit; persisted to DB

### NonFunctional Requirements

NFR1: Python 3.11+ required
NFR2: Max 30 players per room
NFR3: Mob respawn timer configurable (default 60s)
NFR4: Combat turn timeout configurable (default 30s)
NFR5: bcrypt password hashing for security
NFR6: Pydantic message validation for all client-server communication
NFR7: Room JSON schema versioned (schema_version field) for future migration support
NFR8: Room entry payload optimized (~50KB for 100x100 grid with integer tile type IDs)

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
| FR77 | Epic 11 | XP level thresholds |
| FR78 | Epic 11 | Level-up mechanic with stat increases |
| FR79 | Epic 11 | Level-up notification |
| FR80 | Epic 11 | Level display in HUD and entity data |
| FR81 | Epic 11 | `/stats` includes level and XP-to-next |
| FR82 | Epic 12 | Trade system |
| FR83 | Epic 12 | Trade validation |
| FR84 | Epic 12 | Party system |
| FR85 | Epic 12 | Party chat |
| FR86 | Epic 12 | Party combat |
| FR87 | Epic 12 | World map with room discovery |

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

### Epic 11: Leveling System
Players gain levels as they accumulate XP, receiving stat increases and visual feedback on their progression. Level is visible to other players, creating a sense of achievement and relative power.
**FRs covered:** FR77, FR78, FR79, FR80, FR81
**Dependencies:** Builds on Epic 10 (stats HUD, mob loot drops). Standalone.

### Epic 12: Social Systems
Players can trade items with each other, form parties for cooperative combat, and navigate the world using a discovered map — transforming the game from a solo experience into a social one.
**FRs covered:** FR82, FR83, FR84, FR85, FR86, FR87
**Dependencies:** Builds on Epics 10-11. Standalone.

---

## Epic 1: Player Registration & World Entry

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
