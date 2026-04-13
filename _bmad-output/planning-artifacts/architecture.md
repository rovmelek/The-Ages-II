# The Ages II — Architecture & Design Specification

## Document Purpose

This document captures all design decisions made during the epic planning design sessions. It serves as the authoritative reference for the game server architecture, superseding the original `THE_AGES_SERVER_PLAN.md` where conflicts arise.

The original plan remains useful as a code-level reference for individual file implementations, but this document defines the **structure, systems, and design boundaries**.

---

## 1. Project Overview

**The Ages II** is a multiplayer room-based dungeon game server with turn-based card combat.

- **Server**: Python 3.11+, FastAPI, WebSockets (real-time), SQLAlchemy async + SQLite
- **Client**: Web demo client (`web-demo/`) for testing and proof-of-concept; production client planned in Godot
- **Architecture style**: Domain-driven, JSON-configured, designed for future web-based room editor

---

## 2. Core Concepts

### 2.1 Room = Zone/Area

A "room" is a large area (e.g., Mountain St. Regis, Chasing-Storm Forest), not a small dungeon chamber. Key properties:

- **Size**: Up to 100x100 tiles (10,000 tiles per room)
- **Exits**: One or more exits connecting to other rooms
- **Content**: Tiles, static objects, interactive objects, NPCs, mobs
- **Future**: Players will be able to create rooms via a web-based level editor

### 2.2 Tile Grid

Each room is a 2D grid of tiles. Tile types determine movement rules:

| Tile Type | Walkable | Purpose |
|-----------|----------|---------|
| `floor` | Yes | Normal traversable terrain |
| `wall` | No | Impassable barrier |
| `exit` | Yes | Triggers room transition |
| `mob_spawn` | Yes | Mob spawn location |
| `water` | No | Terrain (future: swimable with ability) |

### 2.3 Entities

Everything that exists on the tile grid is an entity with a position. Two broad categories:

- **PlayerEntity**: Connected players with stats, inventory, card collection
- **RoomObject**: Everything placed in the room (NPCs, mobs, chests, levers, rocks, trees)

### 2.4 JSON-Driven Configuration

Game content is defined in JSON files for easy expansion:

- Room definitions (tiles, objects, exits, spawn points)
- Card definitions (effects, costs, descriptions)
- Item definitions (consumables, materials)
- NPC templates (stats, behavior type, spawn config, loot tables)

**Extensibility boundary**: JSON defines **what** (data, values, configurations). Python defines **how** (behaviors, effect resolution logic). Adding new cards/items with existing effect types = JSON only. Adding new effect types = Python code + JSON config.

---

## 3. Architecture

### 3.1 Directory Structure

```
server/
├── core/                       # Bootstrap, config, database, shared services
│   ├── __init__.py
│   ├── config.py               # Server settings (Pydantic BaseSettings)
│   ├── database.py             # Async engine, session factory, init_db
│   ├── scheduler.py            # Periodic task runner (spawn checks, respawns)
│   ├── events.py               # Event bus (global announcements, triggers)
│   └── effects/                # Shared effect registry (cards AND items)
│       ├── __init__.py
│       ├── registry.py         # Maps effect_type string -> handler function
│       ├── damage.py           # Direct damage (with subtype: fire, ice, etc.)
│       ├── heal.py             # HP restoration
│       ├── shield.py           # Damage absorption
│       ├── dot.py              # Damage over time recording (bleed, poison)
│       └── draw.py             # Draw additional cards
├── net/                        # WebSocket protocol and connection layer
│   ├── __init__.py
│   ├── connection_manager.py   # WebSocket <-> player entity ID mapping + room tracking
│   ├── message_router.py       # Routes JSON messages by 'action' field
│   ├── websocket.py            # WebSocket utilities
│   └── handlers/               # Action handlers (thin, delegate to domain logic)
│       ├── __init__.py
│       ├── auth.py             # login, register, duplicate login protection (kick old session)
│       ├── movement.py         # move, room transitions
│       ├── chat.py             # room chat, whispers
│       ├── combat.py           # play_card, use_item_combat, pass_turn, flee
│       ├── interact.py         # interact with room objects (chests, levers, NPCs)
│       └── inventory.py        # inventory queries, use_item (outside combat)
├── player/                     # Player domain
│   ├── __init__.py
│   ├── models.py               # Player DB model (credentials, stats, position, inventory)
│   ├── repo.py                 # Player persistence (CRUD, position, stats whitelist, inventory)
│   ├── entity.py               # PlayerEntity runtime dataclass
│   └── auth.py                 # bcrypt password hashing and verification
├── room/                       # Room/zone domain
│   ├── __init__.py
│   ├── models.py               # Room, RoomState DB models
│   ├── repo.py                 # Room persistence
│   ├── tile.py                 # Tile types, walkability rules
│   ├── room.py                 # Room instance (grid, entities, NPCs, movement validation)
│   ├── provider.py             # RoomProvider interface (JSON today, DB/editor later)
│   ├── manager.py              # Active rooms, entity placement, room transfers
│   ├── spawn_models.py         # SpawnCheckpoint DB model (rare spawn persistence)
│   └── objects/                # Room objects subsystem
│       ├── __init__.py
│       ├── base.py             # RoomObject + InteractiveObject base classes
│       ├── chest.py            # Chests with one-time per-player loot
│       ├── lever.py            # Levers with room-shared state (toggle tiles)
│       ├── npc.py              # NpcEntity dataclass + template loading/creation
│       ├── registry.py         # Object type registry (maps type strings to classes)
│       └── state.py            # PlayerObjectState DB model (per-player object state)
├── combat/                     # Combat domain
│   ├── __init__.py
│   ├── instance.py             # CombatInstance (participants, turns, DoT ticking, effect resolution)
│   ├── manager.py              # Active combat instance tracking
│   └── cards/                  # Card subsystem
│       ├── __init__.py
│       ├── card_def.py         # CardDef with effect chain (list of effects)
│       ├── card_hand.py        # Deck/hand/discard cycling
│       ├── card_repo.py        # Load card definitions from JSON/DB
│       └── models.py           # Card DB model
├── items/                      # Items & inventory domain
│   ├── __init__.py
│   ├── item_def.py             # ItemDef (category: consumable|material, charges, stackable)
│   ├── item_repo.py            # Load item definitions from JSON/DB
│   ├── inventory.py            # Player inventory management (quantities, charges, serialization)
│   └── models.py               # Item DB model
└── web/                        # REST API (deferred, minimal in prototype)
    └── __init__.py

data/
├── rooms/                      # Room JSON definitions (4 rooms in circular loop)
│   ├── town_square.json        # 100x100 — default spawn room
│   ├── dark_cave.json          # 100x100 — cave with NPCs
│   ├── test_room.json          # 5x5 — small test room
│   └── other_room.json         # 5x5 — secondary small room
├── cards/                      # Card set JSON definitions
│   └── base_set.json
├── items/                      # Item JSON definitions
│   └── base_items.json
└── npcs/                       # NPC template JSON definitions
    └── base_npcs.json

tests/                          # pytest test suite

web-demo/                       # Browser-based test/demo client (vanilla HTML/CSS/JS)
├── index.html                  # Main page with auth, game viewport, combat overlay
├── css/
│   └── style.css               # Dark theme, tile rendering, card styling
├── js/
│   └── game.js                 # WebSocket client, state management, all UI logic
└── jsconfig.json               # IDE type-checking config
```

### 3.2 System Relationships

```
Game (central orchestrator)
├── session_factory      — DB session factory (default: async_session from database.py)
├── RoomManager          — owns active Room instances
│   └── Room             — owns tile grid + RoomObjects + entities
│       ├── StaticObject  (trees, rocks)
│       ├── InteractiveObject (chests, levers)
│       ├── NPC           (hostile, merchant, quest_giver)
│       └── Spawner       (manages NPC lifecycle)
├── CombatManager        — owns active CombatInstances
│   └── CombatInstance   — participants, turn order, card/item resolution
├── ConnectionManager    — maps WebSocket <-> player entity IDs
├── MessageRouter        — routes incoming JSON to handlers
├── Scheduler            — periodic tasks (spawn checks, respawn timers)
├── EventBus             — global announcements, cross-system triggers
└── EffectRegistry       — shared card + item effect resolution

Startup order (Game.startup):
1. init_db()
2. Load NPC templates from data/npcs/ (must precede room loading)
3. Load rooms from JSON → DB → memory (spawns NPCs using templates)
4. Load cards from data/cards/
5. Load items from data/items/
6. Register handlers and events
7. Start scheduler
```

---

## 4. Room Object System

### 4.1 Object Categories

All objects placed in a room inherit from a common base with position and interaction rules:

| Category | Examples | Walkable | Interactable | State Scope |
|----------|----------|----------|--------------|-------------|
| Static | Trees, rocks, ponds, rivers | No (blocking) | No | N/A |
| Interactive | Chests, levers | Varies | Yes | Configurable |
| NPC | Mobs, merchants, quest givers | No (occupies tile) | Yes | Room (shared) |

### 4.2 State Scope

Each interactive object declares its state scope in the JSON definition:

- **`"room"`** (shared): All players see the same state. Example: a lever that opens a gate.
- **`"player"`** (instanced): Each player has independent state. Example: a chest with one-time loot.

```json
{
  "type": "chest",
  "x": 15, "y": 22,
  "state_scope": "player",
  "config": {
    "loot_table": "common_chest",
    "locked": false
  }
}
```

Per-player state is persisted in a `player_object_state` table:

```
player_id | room_key | object_id | state_data (JSON)
1         | forest   | chest_03  | {"opened": true, "looted_at": "..."}
```

**Chests are permanent one-time loot**: Once a player opens a chest, it remains opened for that player forever. No reset timers.

### 4.3 NPC Spawn System

Three-tier spawn behavior, defined in NPC JSON config:

| Spawn Type | Behavior | Config Fields |
|------------|----------|---------------|
| **Persistent** | Spawns at server init. Respawns on fixed timer after death. | `respawn_seconds` |
| **Standard** | Spawns at server init. Respawns after configurable delay. | `respawn_seconds` |
| **Rare/Epic** | System checks every N hours, rolls against spawn chance. | `check_interval_hours`, `spawn_chance`, `despawn_after_hours`, `max_active` |

```json
{
  "npc_key": "forest_dragon",
  "name": "Ancient Forest Dragon",
  "behavior_type": "hostile",
  "hit_dice": 10,
  "hp_multiplier": 50,
  "spawn_type": "rare",
  "spawn_config": {
    "check_interval_hours": 12,
    "spawn_chance": 0.15,
    "despawn_after_hours": 6,
    "max_active": 1
  }
}
```

**Global announcements**: When a rare/epic NPC spawns, a global announcement is broadcast to ALL connected players (not just those in the room). Example: `"An Ancient Forest Dragon has appeared in Chasing-Storm Forest!"`

**Spawn persistence**: Spawn check timestamps are persisted to the database so they survive server restarts. If the server restarts at hour 11 of a 12-hour cycle, the remaining 1 hour is preserved.

---

## 5. Combat System

### 5.1 Turn Structure

Turn-based combat. One action per turn:

```
Player's turn → Play a card FROM hand
                OR Use an item FROM inventory
                OR Pass turn
```

- **Play card**: Resolves card effects against the target. Draws replacement card.
- **Use item**: Resolves item effects. Consumes one charge (or removes from inventory).
- **Pass turn**: Mob attacks the passing player. Turn advances.

One action only — no card + item in the same turn. This keeps combat strategic and prevents players from becoming overpowered.

### 5.2 Card System

Cards are defined in JSON with a multi-effect chain:

```json
{
  "card_key": "fireball",
  "name": "Fireball",
  "cost": 3,
  "effects": [
    {"type": "damage", "subtype": "fire", "value": 20}
  ],
  "description": "Hurl a ball of fire."
}
```

**Why effect chains (list) instead of single effect**: This prepares for the card skill tree system. An upgraded fireball might have:

```json
"effects": [
  {"type": "damage", "subtype": "fire", "value": 20},
  {"type": "dot", "subtype": "bleed", "value": 4, "duration": 3}
]
```

The combat resolver iterates over the effects list from day one. Upgrades just modify the list.

### 5.3 Card Hand Management

- Each player gets a hand drawn from a deck (shuffled copy of available cards)
- Hand size: 5 cards (configurable)
- Playing a card: card goes to discard pile, draw a replacement
- Empty deck: shuffle discard pile back into deck

### 5.4 DoT Effect Ticking

Damage-over-time effects (poison, bleed) are processed at the **start of each player's action** (before card/item resolution):

1. `_process_dot_effects()` iterates `target["active_effects"]` on both mob and current player
2. Each DoT entry: applies `value` damage (respecting shield absorption), decrements `remaining`
3. Expired DoTs (`remaining <= 0`) are removed; non-DoT effects are preserved
4. If DoT kills the mob or player, `is_finished` check triggers early return — card/item resolution and mob attacks are skipped
5. Tick results returned as `dot_ticks` array in the action result for client display

**Separation of concerns**: `handle_dot()` in `core/effects/dot.py` **records** DoT entries to `active_effects`. `_process_dot_effects()` in `combat/instance.py` **ticks** them each turn. These are independent — do not modify one expecting changes in the other.

### 5.5 Combat Resolution

- Mob attacks on pass turn (targets the passing player)
- Mob attacks a random player at the end of each full turn cycle
- Shield absorbs damage before HP
- Victory: mob HP reaches 0 (including via DoT tick)
- Defeat: all player HPs reach 0
- Flee: player exits combat (mob stays, combat continues for other participants)
- Rewards on victory: XP applied in handler (`_check_combat_end`), not in CombatInstance
- Dead players' turns are skipped automatically by `_advance_turn()`

**Post-combat cleanup** (in `_check_combat_end`):
- Strip `shield` from entity stats (combat-only transient); `energy`/`max_energy` are now persistent and synced back
- Sync final combat stats (hp, max_hp, energy, max_energy) back to `PlayerEntity.stats` and persist to DB
- On defeat: respawn dead players in `town_square` with full HP and energy
- On victory: kill NPC, schedule respawn if persistent, broadcast room state update

### 5.6 Card Skill Tree (Deferred — Hook Points Only)

**Not in prototype.** But the architecture preserves the extension point:

- Cards use `effects: [...]` list from day one
- `upgrade_tree.py` contains the data model skeleton (nodes, edges, costs, prerequisites)
- Future: `player_card_trees` DB table tracks unlocked nodes per player per card
- Upgrade nodes can: modify effect values, add new effects to the chain, change subtypes
- Players can respec (reset tree) with a cost
- Upgrades cost materials (collected from combat loot, chests, etc.)

---

## 6. Item & Inventory System

### 6.1 Item Categories

| Category | Stackable | In Combat | Example |
|----------|-----------|-----------|---------|
| **Consumable** | Yes (by charges) | Yes (use as turn action) | Healing potion (3 charges) |
| **Material** | Yes (unlimited) | No | Fire essence, iron shard |

```json
{
  "item_key": "healing_potion",
  "name": "Healing Potion",
  "category": "consumable",
  "stackable": true,
  "max_stack": null,
  "charges": 3,
  "effects": [
    {"type": "heal", "value": 25}
  ],
  "usable_in_combat": true,
  "usable_outside_combat": true,
  "description": "Restores 25 HP. 3 uses."
}
```

### 6.2 Inventory

- **Unlimited stacking** for all item types
- Memory impact is negligible: stackable items store `{item_key: quantity}`, not individual instances
- Estimated ~10KB per player with 200 unique item types
- With 1,000 concurrent players: ~10MB total — well within limits

### 6.3 Items Outside Combat

Players can use consumable items outside of combat (e.g., heal between fights). The same effect registry resolves the effect. The `usable_outside_combat` flag on the item definition controls this.

---

## 7. Shared Effect Registry

The effect registry is a core service shared by both card and item systems:

```
core/effects/
├── registry.py    # Maps effect_type string -> resolution function
├── damage.py      # Direct damage (with subtype: fire, ice, physical, etc.)
├── heal.py        # HP restoration
├── shield.py      # Damage absorption buffer
├── dot.py         # Damage over time (bleed, poison — duration in turns)
├── draw.py        # Draw additional cards (combat only)
```

**Extension process** for new effect types:
1. Create new handler file in `core/effects/`
2. Register the effect_type string in the registry
3. Reference the new effect_type in card/item JSON definitions
4. No changes to combat instance, card hand, or item system code

---

## 8. Networking

### 8.1 WebSocket Protocol

- **Endpoint**: `/ws/game`
- **Format**: JSON messages with `action` field (client -> server) or `type` field (server -> client)
- **Auth flow**: Connect WebSocket first, then send `login` or `register` action

### 8.2 Client -> Server Actions

| Action | Purpose |
|--------|---------|
| `login` | Authenticate with username + password |
| `register` | Create new account |
| `move` | Move in direction (up/down/left/right) |
| `chat` | Send message to room (or whisper) |
| `play_card` | Play a card during combat turn |
| `pass_turn` | Pass combat turn |
| `flee` | Exit combat |
| `interact` | Interact with room object (chest, lever, NPC) |
| `inventory` | Request inventory contents |
| `use_item` | Use a consumable item outside combat |
| `use_item_combat` | Use a consumable item as combat turn action |

### 8.3 Server -> Client Message Types

| Type | Purpose |
|------|---------|
| `login_success` | Auth confirmed, player ID returned |
| `room_state` | Full room data on entry (tiles, entities, objects) |
| `entity_moved` | Entity position update |
| `entity_entered` | New entity appeared in room |
| `entity_left` | Entity left room |
| `combat_start` | Combat initiated, participants and mob info |
| `combat_turn` | Turn update with result (includes `dot_ticks` if DoTs active) |
| `combat_update` | Combat state update (participant left/joined) |
| `combat_end` | Combat resolved (victory/defeat, rewards) |
| `combat_fled` | Player successfully fled |
| `chat` | Chat message from another player |
| `error` | Error response |
| `announcement` | Global announcement (rare spawn, etc.) |
| `interact_result` | Result of interacting with a room object |
| `inventory` | Player inventory contents |
| `item_used` | Item consumed successfully (outside combat) |
| `tile_changed` | Tile type changed (lever toggle) |
| `server_shutdown` | Server shutting down — save and disconnect |
| `kicked` | Duplicate login — old session terminated |
| `respawn` | Player respawned in town_square after death |

### 8.4 Room Entry Payload

On room entry, the full 100x100 tile grid is sent to the client. Estimated payload:

- Tiles as integer type IDs: ~40-50KB
- Entity list: ~1-5KB depending on population
- Object list: ~1-5KB
- Total: ~50KB one-time load per room transition

No fog of war — players see the entire map on entry. Entity updates (movement, spawn, despawn) stream in real-time after the initial load.

### 8.5 Broadcasting

**Prototype**: Broadcast all entity updates to all players in the room. Simple, correct.

**Future optimization** (if performance requires): Range-based filtering — only send updates for entities within N tiles of the player. This is an optimization, not a requirement for the prototype.

---

## 9. Data Models (Database)

### 9.1 Player

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | Auto-increment |
| username | String(50) | Unique, indexed |
| password_hash | String(128) | bcrypt |
| stats | JSON | `{hp, max_hp, energy, max_energy, xp, level, strength, dexterity, constitution, intelligence, wisdom, charisma}` — persisted via `_STATS_WHITELIST`; `shield`, `active_effects` are combat-only transient |
| inventory | JSON | `{item_key: quantity, ...}` |
| card_collection | JSON | List of card_key strings |
| visited_rooms | JSON | List of room_key strings (exploration XP tracking) |
| current_room_id | String(50) | FK to room_key |
| position_x | Integer | Tile X coordinate |
| position_y | Integer | Tile Y coordinate |

### 9.2 Room

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | Auto-increment |
| room_key | String(50) | Unique, indexed |
| name | String(100) | Display name |
| schema_version | Integer | For future migration support |
| width | Integer | Grid width (up to 100) |
| height | Integer | Grid height (up to 100) |
| tile_data | JSON | 2D list of tile type integers |
| exits | JSON | Exit definitions |
| objects | JSON | Room object definitions |
| spawn_points | JSON | Player + NPC spawn point list |

### 9.3 RoomState

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | Auto-increment |
| room_key | String(50) | Unique, indexed |
| mob_states | JSON | `{mob_id: {alive, respawn_at}}` |
| dynamic_state | JSON | Shared interactive object states |

### 9.4 PlayerObjectState

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | Auto-increment |
| player_id | Integer | FK to player |
| room_key | String(50) | Room containing the object |
| object_id | String(50) | Object identifier within room |
| state_data | JSON | `{opened: true, looted_at: ...}` |

Unique constraint on `(player_id, room_key, object_id)`.

### 9.5 Card

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | Auto-increment |
| card_key | String(50) | Unique, indexed |
| name | String(100) | Display name |
| cost | Integer | Action cost |
| effects | JSON | `[{type, subtype, value, ...}]` |
| description | String(500) | Card text |

### 9.6 SpawnCheckpoint

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | Auto-increment |
| npc_key | String(50) | NPC template key |
| room_key | String(50) | Room where NPC spawns |
| last_check_at | DateTime | When spawn chance was last rolled |
| next_check_at | DateTime | When to roll next |
| currently_spawned | Boolean | Whether the NPC is currently alive |

---

## 10. Server Hardening & Persistence

### 10.1 Player State Persistence

Player state is saved to the database at multiple trigger points:
- **Disconnect**: Position, stats (whitelisted), and inventory saved on WebSocket close
- **Room transition**: Position updated when entering a new room
- **Combat end**: Stats (HP, XP) synced and persisted after victory or defeat
- **Server shutdown**: All connected players saved before disconnect
- **Item use in combat**: Inventory persisted after consuming an item

**Stats whitelist**: Only `{hp, max_hp, energy, max_energy, xp, level, strength, dexterity, constitution, intelligence, wisdom, charisma}` are persisted. `shield` and `active_effects` are combat-only transient data, stripped by `_STATS_WHITELIST` in `player/repo.py`. Energy is persistent (Epic 18): `max_energy` is derived from `DEFAULT_BASE_ENERGY + INT * INT_ENERGY_PER_POINT + WIS * WIS_ENERGY_PER_POINT`.

**Database access pattern**: All DB access goes through `game.session_factory()` — the `Game` class owns the session factory (defaults to `async_session` from `server/core/database.py`). Consumer modules (handlers, xp, scheduler, interactive objects) receive `game` as a parameter and use `async with game.session_factory() as session:`. No module imports `async_session` directly. This enables test isolation (swap `game.session_factory = test_factory`) and future database migration (swap the factory in `Game.__init__()`).

### 10.2 Death & Respawn

When a player dies in combat (HP reaches 0):
1. Combat ends with defeat result
2. `Game.respawn_player()`: restore HP to max, clear `shield`, set `in_combat = False`
3. Transfer player to `town_square` spawn point (save to DB first for crash recovery)
4. Send `respawn` message with new position and HP
5. Send fresh `room_state` for town_square
6. Notify town_square players of arrival

### 10.3 Duplicate Login Protection

When a player logs in while already connected from another session:
1. `_kick_old_session()`: save old session state (position, stats, inventory)
2. Remove from combat (if in combat), notify remaining participants
3. Remove from room, broadcast `entity_left`
4. Send `kicked` message to old WebSocket, close it
5. Proceed with new login normally

### 10.4 Graceful Server Shutdown

`Game.shutdown()` (called via FastAPI `lifespan` context manager):
1. Stop scheduler (cancel all respawn timers)
2. For each connected player: remove from combat, save all state to DB
3. Send `server_shutdown` message to each client
4. Close all WebSockets with code 1001
5. Clear `player_entities`

---

## 11. Deferred Features & Hook Points

Features explicitly out of scope for the prototype, with the architectural hook points that preserve future extensibility:

| Deferred Feature | Hook Point in Prototype |
|------------------|------------------------|
| **Card skill tree** | Cards use `effects: [...]` list from day one. Future adds `upgrade_tree.py` data model + `player_card_trees` table |
| **Web-based room editor** | `RoomProvider` interface. Prototype: `JsonRoomProvider`. Editor adds `DbRoomProvider` |
| **NPC dialogue/shops/quests** | NPCs have `behavior_type` field. Prototype implements `"hostile"` only. Later: `"merchant"`, `"quest_giver"` |
| **Material drops from combat** | Loot table system exists (for chests). Combat rewards reference same system later |
| **Card respec** | Card upgrade data model includes cost tracking. Respec = reset nodes + refund |
| **REST API (trades, filters, profiles)** | `web/` package exists. Endpoints added as needed |
| **Range-based broadcasting** | Prototype broadcasts to all players in room. Future: filter by proximity |

### Epic 12: Social Systems (Planned)

The following systems are designed and story-specced but not yet implemented:

**Trade System** (`server/trade/`)
- `TradeManager` — manages mutual exchange trade sessions with async lock, timeouts
- State machine: `idle → request_pending → negotiating → one_ready → both_ready → executing → complete`
- `ItemDef` gains `tradeable: bool = True` field for trade eligibility
- Atomic two-player inventory swap in single DB transaction
- Auto-cancel on disconnect, room change, or combat entry
- Config: `TRADE_SESSION_TIMEOUT_SECONDS=60`, `TRADE_REQUEST_TIMEOUT_SECONDS=30`, `MAX_TRADE_ITEMS=10`

**Party System** (`server/party/`)
- `PartyManager` — tracks in-memory party groups (ephemeral, lost on restart)
- `Party` dataclass: `party_id`, `leader` (entity_id), `members` (ordered list), `pending_invites`
- Leader succession on disconnect (longest-standing member)
- Config: `MAX_PARTY_SIZE=4`
- `/party kick` and `/party disband` blocked during shared combat

**Party Combat** (extends `server/combat/`)
- `CombatInstance` extended for N players (round-robin turns, random mob targeting)
- Mob HP scales with party size at encounter time (HP × N)
- `XP_PARTY_BONUS_PERCENT` (default 10) applied when 2+ members at victory
- Independent loot rolls per surviving participant

**World Map** (extends `server/net/handlers/query.py`)
- `/map` reuses existing `visited_rooms` field — no new DB schema
- Connections derived from room exit data; undiscovered destinations shown as `???`

**Cross-Cutting Changes:**
- `ConnectionManager` gains name → entity_id index for player name resolution
- Disconnect cleanup order: cancel trades → remove from combat → handle party departure → save state → remove from room → notify
- `/help` output grouped by category (Movement, Combat, Social, Info)

**Architecture Decisions (ADRs):**
- ADR-1: Trade state in-memory only (60s sessions; DB atomicity handles crashes)
- ADR-2: Party state in-memory only (reform cost 3s < persistence complexity)
- ADR-3: New `server/trade/` and `server/party/` packages (matches domain-driven structure)
- ADR-4: Name → entity_id index in `ConnectionManager` (already owns "who is online" data)
- ADR-5: Extend `CombatInstance` for multi-player, don't rewrite (preserve 600+ tests)
- ADR-6: Map data computed on request, no caching (trivial cost)

---

## 12. Prototype Gameplay Loop

The minimum playable loop the prototype supports:

```
Register account
    -> Login via WebSocket
    -> Enter starting room (receive full 100x100 map)
    -> See other players, NPCs, objects on map
    -> Move (4-directional, wall collision, boundary checks)
    -> Walk to exit tile -> transition to new room
    -> Encounter hostile NPC -> enter combat
    -> Combat turn: play card from hand OR use item from inventory OR pass
    -> DoT effects tick each turn (poison, bleed deal damage automatically)
    -> Win combat -> receive XP (applied to stats, persisted to DB)
    -> Lose combat -> respawn in town_square with full HP
    -> Interact with chest -> receive one-time loot (synced to runtime + restored on login)
    -> See global announcement when rare NPC spawns
    -> Chat with other players in same room
    -> Disconnect -> position + stats + inventory saved -> reconnect later
    -> Duplicate login -> old session kicked, state saved, new session takes over
    -> Server shutdown -> all player states saved, clients notified
```

---

## 13. Tech Stack

| Component | Technology | Version |
|-----------|------------|---------|
| Language | Python | 3.11+ |
| Web framework | FastAPI | >= 0.110.0 |
| ASGI server | Uvicorn | >= 0.27.0 |
| Database | SQLite (async) | via aiosqlite >= 0.19.0 |
| ORM | SQLAlchemy (async) | >= 2.0.0 |
| Validation | Pydantic | >= 2.0.0 |
| Settings | pydantic-settings | >= 2.0.0 |
| Password hashing | bcrypt | >= 4.1.0 |
| Testing | pytest + pytest-asyncio | >= 8.0.0 |
| HTTP test client | httpx | >= 0.27.0 |
