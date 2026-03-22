# The Ages II — Architecture & Design Specification

## Document Purpose

This document captures all design decisions made during the epic planning design sessions. It serves as the authoritative reference for the game server architecture, superseding the original `THE_AGES_SERVER_PLAN.md` where conflicts arise.

The original plan remains useful as a code-level reference for individual file implementations, but this document defines the **structure, systems, and design boundaries**.

---

## 1. Project Overview

**The Ages II** is a multiplayer room-based dungeon game server with turn-based card combat.

- **Server**: Python 3.11+, FastAPI, WebSockets (real-time), SQLAlchemy async + SQLite
- **Client**: Not in scope yet — server tested via pytest, curl, websocat
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
│       ├── dot.py              # Damage over time (bleed, poison)
│       └── draw.py             # Draw additional cards
├── net/                        # WebSocket protocol and connection layer
│   ├── __init__.py
│   ├── connection_manager.py   # WebSocket <-> player entity ID mapping
│   ├── message_router.py      # Routes JSON messages by 'action' field
│   ├── protocol.py             # All message schemas (client->server, server->client)
│   └── handlers/               # Action handlers (thin, delegate to domain logic)
│       ├── __init__.py
│       ├── auth.py             # login, register
│       ├── movement.py         # move, room transitions
│       ├── chat.py             # room chat, whispers
│       ├── combat.py           # play_card, use_item, pass_turn, flee
│       └── inventory.py        # inventory queries
├── player/                     # Player domain
│   ├── __init__.py
│   ├── models.py               # Player DB model (credentials, stats, position)
│   ├── repo.py                 # Player persistence (CRUD, position updates)
│   ├── entity.py               # PlayerEntity runtime dataclass
│   └── auth.py                 # Login/register logic, bcrypt hashing
├── room/                       # Room/zone domain
│   ├── __init__.py
│   ├── models.py               # Room, RoomState DB models
│   ├── repo.py                 # Room persistence
│   ├── tile.py                 # Tile types, walkability rules
│   ├── room.py                 # Room instance (grid, entities, movement validation)
│   ├── provider.py             # RoomProvider interface (JSON today, DB/editor later)
│   ├── manager.py              # Active rooms, entity placement, room transfers
│   └── objects/                # Room objects subsystem
│       ├── __init__.py
│       ├── base.py             # RoomObject base (position, type, state_scope, interactable)
│       ├── static.py           # Trees, rocks, ponds (blocking/decoration)
│       ├── interactive.py      # Chests, levers (stateful, per-player or per-room)
│       ├── npc.py              # NPC definition (behavior_type, stats, dialogue ref)
│       └── spawner.py          # Spawn system (persistent, timed, rare with chance roll)
├── combat/                     # Combat domain
│   ├── __init__.py
│   ├── instance.py             # CombatInstance (participants, turns, effect resolution)
│   ├── manager.py              # Active combat instance tracking
│   ├── turn.py                 # Turn structure (play card OR use item OR pass)
│   └── cards/                  # Card subsystem
│       ├── __init__.py
│       ├── card_def.py         # CardDef with effect chain (list of effects)
│       ├── card_hand.py        # Deck/hand/discard cycling
│       ├── card_repo.py        # Load card definitions from JSON/DB
│       └── upgrade_tree.py     # Skill tree data model (nodes, edges, costs) [hook point]
├── items/                      # Items & inventory domain
│   ├── __init__.py
│   ├── item_def.py             # ItemDef (category: consumable|material, charges, stackable)
│   ├── item_repo.py            # Load item definitions from JSON/DB
│   └── inventory.py            # Player inventory management (quantities, charges)
└── web/                        # REST API (deferred, minimal in prototype)
    ├── __init__.py
    └── routes.py               # Player profiles, trades, filters

data/
├── rooms/                      # Room JSON definitions
│   ├── town_square.json
│   └── dark_cave.json
├── cards/                      # Card set JSON definitions
│   └── base_set.json
├── items/                      # Item JSON definitions
│   └── base_items.json
└── npcs/                       # NPC template JSON definitions
    └── base_npcs.json

tests/                          # pytest test suite
```

### 3.2 System Relationships

```
Game (central orchestrator)
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
  "spawn_type": "rare",
  "spawn_config": {
    "check_interval_hours": 12,
    "spawn_chance": 0.15,
    "despawn_after_hours": 6,
    "max_active": 1
  },
  "stats": {"hp": 500, "max_hp": 500, "attack": 25, "defense": 15}
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

### 5.4 Combat Resolution

- Mob attacks on pass turn (targets the passing player)
- Mob attacks a random player at the end of each full turn cycle
- Shield absorbs damage before HP
- Victory: mob HP reaches 0
- Defeat: all player HPs reach 0
- Flee: player exits combat (mob stays, combat continues for other participants)
- Rewards on victory: XP, potential loot

### 5.5 Card Skill Tree (Deferred — Hook Points Only)

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
| `use_item` | Use a consumable item (combat or out of combat) |
| `pass_turn` | Pass combat turn |
| `flee` | Exit combat |
| `interact` | Interact with room object (chest, lever, NPC) |
| `inventory` | Request inventory contents |

### 8.3 Server -> Client Message Types

| Type | Purpose |
|------|---------|
| `login_success` | Auth confirmed, player ID returned |
| `room_state` | Full room data on entry (tiles, entities, objects) |
| `entity_moved` | Entity position update |
| `entity_entered` | New entity appeared in room |
| `entity_left` | Entity left room |
| `combat_start` | Combat initiated, participants and mob info |
| `combat_turn` | Turn update (current player, hand, HP states) |
| `combat_end` | Combat resolved (victory/defeat, rewards) |
| `combat_fled` | Player successfully fled |
| `chat` | Chat message from another player |
| `error` | Error response |
| `announcement` | Global announcement (rare spawn, etc.) |
| `interact_result` | Result of interacting with a room object |

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
| stats | JSON | `{hp, max_hp, attack, defense, xp, level}` |
| inventory | JSON | `{item_key: quantity, ...}` |
| card_collection | JSON | List of card_key strings |
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

## 10. Deferred Features & Hook Points

Features explicitly out of scope for the prototype, with the architectural hook points that preserve future extensibility:

| Deferred Feature | Hook Point in Prototype |
|------------------|------------------------|
| **Card skill tree** | Cards use `effects: [...]` list. `upgrade_tree.py` has data model skeleton. Future adds `player_card_trees` table |
| **Web-based room editor** | `RoomProvider` interface. Prototype: `JsonRoomProvider`. Editor adds `DbRoomProvider` |
| **NPC dialogue/shops/quests** | NPCs have `behavior_type` field. Prototype implements `"hostile"` only. Later: `"merchant"`, `"quest_giver"` |
| **Material drops from combat** | Loot table system exists (for chests). Combat rewards reference same system later |
| **Card respec** | Card upgrade data model includes cost tracking. Respec = reset nodes + refund |
| **REST API (trades, filters, profiles)** | `web/routes.py` exists. Endpoints added as needed |
| **Range-based broadcasting** | `room/broadcaster.py` placeholder. Prototype broadcasts to all players in room |

---

## 11. Prototype Gameplay Loop

The minimum playable loop the prototype must support:

```
Register account
    -> Login via WebSocket
    -> Enter starting room (receive full 100x100 map)
    -> See other players, NPCs, objects on map
    -> Move (4-directional, wall collision, boundary checks)
    -> Walk to exit tile -> transition to new room
    -> Encounter hostile NPC -> enter combat
    -> Combat turn: play card from hand OR use item from inventory OR pass
    -> Win combat -> receive XP/loot
    -> Interact with chest -> receive one-time loot
    -> See global announcement when rare NPC spawns
    -> Chat with other players in same room
    -> Disconnect -> position saved -> reconnect later
```

---

## 12. Tech Stack

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
