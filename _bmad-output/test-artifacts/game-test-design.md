# Game Test Design: The Ages II

**Version**: 1.0
**Created**: 2026-03-25
**Author**: Kevin (via GDS Game QA Workflow)

---

## Overview

### Game Description

The Ages II is a multiplayer room-based dungeon game with turn-based card combat, built as a Python game server (FastAPI + WebSockets) with a browser-based proof-of-concept client. Players connect via WebSocket, explore tile-based rooms, encounter hostile NPCs, engage in card combat, collect items from chests, and interact with room objects.

### Target Platforms

- [x] Web Browser (proof-of-concept demo client)
- [ ] Godot (planned production client)
- [x] Python Server (FastAPI + WebSockets + SQLite)

### Test Scope

**In scope**: All server-side systems (Epics 1-6 complete), WebSocket protocol, web demo client behavior, data integrity, multiplayer room sharing, combat mechanics, inventory, room transitions.

**Out of scope**: Godot production client (not yet built), visual/audio polish, mobile clients, performance under high load (deferred to Epic 7+).

---

## Risk Assessment

### High-Risk Areas

| Area | Risk | Mitigation |
|------|------|------------|
| Combat system | DoT effects never tick; victory rewards not applied; NPC marked dead before combat resolves | P0 functional tests + bug tracking |
| Data persistence | Inventory lost on disconnect; stats not persisted; position only saved on transitions/disconnect | P0 save/load round-trip scenarios |
| Server lifecycle | No graceful shutdown; NPC template load order was already buggy | P0 startup/shutdown testing |
| Authentication | No duplicate login protection; no session management | P1 security scenarios |
| Multiplayer state sync | Concurrent access untested; race conditions possible | P1 multi-client tests |
| Chest loot system | Items go to DB but not runtime inventory object | P0 integration test |

### Risk Priority Matrix

```
                    IMPACT
                Low      High
            ┌─────────┬─────────┐
      High  │   P2    │   P0    │
LIKELIHOOD  ├─────────┼─────────┤
      Low   │   P3    │   P1    │
            └─────────┴─────────┘
```

**P0 (High Likelihood + High Impact)**: Combat functional gaps, inventory data loss, server startup order
**P1 (Low Likelihood + High Impact)**: Duplicate login exploits, concurrent room transition races
**P2 (High Likelihood + Low Impact)**: Missing input validation (message length, username length)
**P3 (Low Likelihood + Low Impact)**: Water tile encounters (no water tiles in current data)

---

## Test Categories

### 1. Core Gameplay Tests

#### 1.1 Authentication & Session

```
SCENARIO: Successful Registration
  GIVEN server is running with no existing accounts
  WHEN client sends {action: "register", username: "testuser", password: "test123"}
  THEN server responds {type: "login_success", player_id: <int>, username: "testuser"}
  AND player record exists in database
  PRIORITY: P0
  CATEGORY: gameplay

SCENARIO: Registration Validates Username Length
  GIVEN server is running
  WHEN client sends {action: "register", username: "ab", password: "test123"}
  THEN server responds {type: "error", detail: "Username must be at least 3 characters"}
  AND no player record is created
  PRIORITY: P0
  CATEGORY: gameplay

SCENARIO: Registration Validates Password Length
  GIVEN server is running
  WHEN client sends {action: "register", username: "testuser", password: "12345"}
  THEN server responds {type: "error", detail: "Password must be at least 6 characters"}
  PRIORITY: P0
  CATEGORY: gameplay

SCENARIO: Registration Prevents Duplicate Username
  GIVEN user "testuser" already exists
  WHEN client sends {action: "register", username: "testuser", password: "newpass"}
  THEN server responds {type: "error", detail: "Username already taken"}
  PRIORITY: P0
  CATEGORY: gameplay

SCENARIO: Successful Login Places Player in Room
  GIVEN user "testuser" is registered
  WHEN client sends {action: "login", username: "testuser", password: "test123"}
  THEN server responds {type: "login_success"} followed by {type: "room_state"}
  AND room_state contains room_key, tiles, entities, npcs, exits, objects
  AND player entity appears at room's player spawn point
  PRIORITY: P0
  CATEGORY: gameplay

SCENARIO: Login With Invalid Credentials
  GIVEN user "testuser" is registered with password "test123"
  WHEN client sends {action: "login", username: "testuser", password: "wrong"}
  THEN server responds {type: "error", detail: "Invalid username or password"}
  PRIORITY: P0
  CATEGORY: gameplay

SCENARIO: New Player Spawns at Room Spawn Point Not Origin
  GIVEN new player has never logged in (DB position 0,0)
  AND town_square has player spawn at (50,50)
  WHEN player logs in
  THEN player entity position is (50,50), NOT (0,0)
  PRIORITY: P0
  CATEGORY: gameplay

SCENARIO: Register Then Login Flow (Web Client)
  GIVEN client registers a new account
  AND server responds with login_success (no room_state)
  WHEN client auto-sends login action with same credentials
  THEN server responds with login_success + room_state
  AND player is placed in town_square at spawn point
  PRIORITY: P0
  CATEGORY: gameplay

SCENARIO: Duplicate Login Not Protected
  GIVEN player "testuser" is logged in on WebSocket connection A
  WHEN same "testuser" logs in on WebSocket connection B
  THEN EXPECTED: second login should be rejected OR first connection should be disconnected
  AND ACTUAL: both connections exist simultaneously, entity is duplicated
  NOTE: Known gap — FR55 (Epic 7) not yet implemented
  PRIORITY: P1
  CATEGORY: gameplay

SCENARIO: Username Maximum Length Not Enforced
  GIVEN server is running
  WHEN client sends {action: "register", username: "a"*1000, password: "test123"}
  THEN EXPECTED: server should reject overly long usernames
  AND ACTUAL: no upper bound validation exists
  PRIORITY: P2
  CATEGORY: gameplay

SCENARIO: Special Characters in Username
  GIVEN server is running
  WHEN client sends {action: "register", username: "<script>alert(1)</script>", password: "test123"}
  THEN EXPECTED: server should reject or sanitize special characters
  AND ACTUAL: no character validation exists
  PRIORITY: P2
  CATEGORY: gameplay
```

#### 1.2 Movement

```
SCENARIO: Move in All Four Directions
  GIVEN player is at position (50,50) on floor tile
  WHEN player sends {action: "move", direction: "up"}
  THEN player position becomes (50,49)
  AND server broadcasts {type: "entity_moved"} to all players in room
  (Repeat for down→(50,51), left→(49,50), right→(51,50))
  PRIORITY: P0
  CATEGORY: gameplay

SCENARIO: Wall Blocks Movement
  GIVEN player is adjacent to a wall tile
  WHEN player sends {action: "move"} toward the wall
  THEN server responds {type: "error", detail: "Cannot move there"}
  AND player position does not change
  PRIORITY: P0
  CATEGORY: gameplay

SCENARIO: Boundary Blocks Movement
  GIVEN player is at room edge (e.g., x=0)
  WHEN player sends {action: "move", direction: "left"}
  THEN server responds {type: "error"}
  AND player position does not change
  PRIORITY: P0
  CATEGORY: gameplay

SCENARIO: Movement While in Combat Blocked
  GIVEN player is in active combat
  WHEN player sends {action: "move", direction: "up"}
  THEN server responds {type: "error", detail: "Cannot move during combat"}
  PRIORITY: P0
  CATEGORY: gameplay

SCENARIO: Movement Without Login
  GIVEN WebSocket is connected but player has not logged in
  WHEN client sends {action: "move", direction: "up"}
  THEN server responds {type: "error"}
  PRIORITY: P0
  CATEGORY: gameplay

SCENARIO: Invalid Direction String
  GIVEN player is logged in
  WHEN client sends {action: "move", direction: "north"}
  THEN server responds {type: "error"}
  PRIORITY: P1
  CATEGORY: gameplay

SCENARIO: Rapid Movement Spam
  GIVEN player is logged in and on floor tiles
  WHEN client sends 20 move actions in 1 second
  THEN EXPECTED: server should rate-limit or handle gracefully
  AND ACTUAL: no server-side rate limiting exists
  NOTE: Client has movePending debounce but server does not
  PRIORITY: P2
  CATEGORY: gameplay
```

#### 1.3 Room Transitions

```
SCENARIO: Exit Tile Transitions to Target Room
  GIVEN player is adjacent to an exit tile
  AND exit tile leads to "test_room"
  WHEN player moves onto the exit tile
  THEN player receives {type: "room_state"} for test_room
  AND player is placed at test_room's player spawn point
  AND old room players receive {type: "entity_left"}
  AND new room players receive {type: "entity_entered"}
  PRIORITY: P0
  CATEGORY: gameplay

SCENARIO: Full Room Loop Traversal
  GIVEN player starts in town_square
  WHEN player traverses: town_square → test_room → other_room → dark_cave → town_square
  THEN player ends up back in town_square
  AND all room transitions succeed without errors
  PRIORITY: P0
  CATEGORY: gameplay

SCENARIO: Position Saved on Room Transition
  GIVEN player transitions from room A to room B
  WHEN position is checked in database
  THEN DB records player's new room_key and spawn coordinates
  PRIORITY: P0
  CATEGORY: gameplay

SCENARIO: Exit to Nonexistent Room
  GIVEN room data references a target room that doesn't exist in DB
  WHEN player moves onto exit tile
  THEN server responds with error
  AND player remains in current room
  PRIORITY: P1
  CATEGORY: gameplay
```

#### 1.4 Combat — Core Loop

```
SCENARIO: Mob Encounter Initiates Combat
  GIVEN player is adjacent to a live hostile NPC
  WHEN player moves onto the NPC's tile
  THEN server sends {type: "entity_moved"} then {type: "combat_start"}
  AND combat_start contains: instance_id, current_turn, participants, mob, hands
  AND player's in_combat flag is set to true
  PRIORITY: P0
  CATEGORY: gameplay

SCENARIO: Dead NPC Does Not Trigger Combat
  GIVEN an NPC has is_alive=false
  WHEN player moves onto that NPC's tile
  THEN no combat_start is sent
  AND player moves normally
  PRIORITY: P0
  CATEGORY: gameplay

SCENARIO: Play Card Deals Damage
  GIVEN player is in combat and it is their turn
  AND player has "fire_bolt" card in hand (20 fire damage)
  AND mob has 50 HP
  WHEN player sends {action: "play_card", card_key: "fire_bolt"}
  THEN mob HP reduces to 30
  AND server sends {type: "combat_turn"} with updated state
  PRIORITY: P0
  CATEGORY: gameplay

SCENARIO: Play Card — Wrong Turn
  GIVEN player is in combat but it is NOT their turn
  WHEN player sends {action: "play_card", card_key: "fire_bolt"}
  THEN server responds {type: "error", detail: "Not your turn"}
  PRIORITY: P0
  CATEGORY: gameplay

SCENARIO: Pass Turn — Mob Attacks Passer
  GIVEN player is in combat and it is their turn
  WHEN player sends {action: "pass_turn"}
  THEN mob attacks the player who passed
  AND server sends {type: "combat_turn"} with mob_attack result
  PRIORITY: P0
  CATEGORY: gameplay

SCENARIO: Full Cycle — Mob Attacks Random Player
  GIVEN all participants have acted in this combat cycle
  WHEN the last participant completes their action
  THEN mob performs a cycle-end attack on a random participant
  AND turn order resets for next cycle
  PRIORITY: P0
  CATEGORY: gameplay

SCENARIO: Victory Ends Combat
  GIVEN mob has 10 HP remaining
  AND player plays a card dealing 15 damage
  WHEN mob HP reaches 0
  THEN server sends {type: "combat_end", victory: true, rewards: {xp: 25}}
  AND player's in_combat flag is cleared
  PRIORITY: P0
  CATEGORY: gameplay

SCENARIO: Defeat Ends Combat
  GIVEN player has 5 HP remaining
  AND mob attacks for 10 damage
  WHEN player HP reaches 0
  THEN server sends {type: "combat_end", victory: false}
  AND player's in_combat flag is cleared
  PRIORITY: P0
  CATEGORY: gameplay

SCENARIO: Flee Combat
  GIVEN player is in combat
  WHEN player sends {action: "flee"}
  THEN server sends {type: "combat_fled"} to the player
  AND player is removed from combat
  AND if other participants remain, combat continues for them
  PRIORITY: P0
  CATEGORY: gameplay

SCENARIO: Shield Absorbs Damage Before HP
  GIVEN player has 10 shield and 50 HP
  AND mob attacks for 15 damage
  WHEN damage is applied
  THEN shield reduces to 0 (absorbs 10)
  AND HP reduces to 45 (remaining 5 damage)
  PRIORITY: P0
  CATEGORY: gameplay

SCENARIO: Heal Capped at Max HP
  GIVEN player has 30/50 HP
  AND player plays "greater_heal" (30 heal)
  WHEN heal is applied
  THEN player HP is 50 (capped, not 60)
  PRIORITY: P1
  CATEGORY: gameplay

SCENARIO: Draw Card Effect
  GIVEN player has 3 cards in hand
  AND player plays "quick_draw" (draw 2)
  WHEN effect resolves
  THEN player draws 2 additional cards from deck
  PRIORITY: P1
  CATEGORY: gameplay

SCENARIO: DoT Effect Does Not Tick (Known Bug)
  GIVEN player plays "venom_fang" (6 poison DoT for 3 turns)
  WHEN subsequent turns pass
  THEN EXPECTED: mob should take 6 damage per turn for 3 turns
  AND ACTUAL: DoT is recorded in active_effects but never resolved per-turn
  NOTE: Functional gap — DoT tick resolution not implemented
  PRIORITY: P0
  CATEGORY: gameplay

SCENARIO: Victory XP Not Applied (Known Bug)
  GIVEN player wins combat
  AND combat_end message includes rewards: {xp: 25}
  WHEN player's stats are checked
  THEN EXPECTED: player XP should increase by 25
  AND ACTUAL: XP is returned in message but never written to player stats or DB
  NOTE: Functional gap — reward application not implemented
  PRIORITY: P1
  CATEGORY: gameplay

SCENARIO: Card Cost Not Enforced (Known Gap)
  GIVEN cards have a "cost" field (e.g., fire_bolt cost: 3)
  WHEN player plays any card
  THEN EXPECTED: cost should be deducted from a resource (mana/AP)
  AND ACTUAL: cost field exists in data but is never checked or deducted
  NOTE: FR57 (Epic 8) — not yet implemented
  PRIORITY: P2
  CATEGORY: gameplay

SCENARIO: Combat Timeout Not Implemented (Known Gap)
  GIVEN it is a player's turn in combat
  WHEN 30 seconds pass without action
  THEN EXPECTED: auto-pass or timeout mechanism (per NFR4)
  AND ACTUAL: no timeout exists; turn waits indefinitely
  PRIORITY: P2
  CATEGORY: gameplay
```

#### 1.5 Inventory & Items

```
SCENARIO: View Empty Inventory
  GIVEN player is logged in with no items
  WHEN player sends {action: "inventory"}
  THEN server responds {type: "inventory", items: []}
  PRIORITY: P0
  CATEGORY: gameplay

SCENARIO: Use Healing Potion Outside Combat
  GIVEN player has healing_potion in inventory
  AND player has 30/50 HP
  WHEN player sends {action: "use_item", item_key: "healing_potion"}
  THEN player HP increases to 50 (heal 25, capped at max)
  AND potion quantity decreases by 1
  AND server responds {type: "item_used"}
  PRIORITY: P0
  CATEGORY: gameplay

SCENARIO: Use Item in Combat
  GIVEN player is in combat and it is their turn
  AND player has healing_potion
  WHEN player sends {action: "use_item_combat", item_key: "healing_potion"}
  THEN heal is applied and turn advances
  AND server responds with combat_turn state
  PRIORITY: P0
  CATEGORY: gameplay

SCENARIO: Cannot Use Material Items
  GIVEN player has iron_shard (category: material)
  WHEN player sends {action: "use_item", item_key: "iron_shard"}
  THEN server responds {type: "error"} — materials cannot be used
  PRIORITY: P1
  CATEGORY: gameplay

SCENARIO: Inventory Lost on Disconnect (Known Bug)
  GIVEN player has items in inventory
  WHEN player disconnects and reconnects
  THEN EXPECTED: inventory should be restored from database
  AND ACTUAL: inventory is created empty on each login — all items lost
  NOTE: FR54 (Epic 7) — inventory persistence not implemented
  PRIORITY: P0
  CATEGORY: gameplay

SCENARIO: Use Item Outside Combat Blocked During Combat
  GIVEN player is in active combat
  WHEN player sends {action: "use_item", item_key: "healing_potion"}
  THEN server responds {type: "error"} — must use use_item_combat action
  PRIORITY: P1
  CATEGORY: gameplay
```

#### 1.6 Room Objects & Interaction

```
SCENARIO: Open Chest Gets Loot
  GIVEN player is in a room with an unopened chest
  WHEN player sends {action: "interact", target_id: "chest_01"}
  THEN server responds {type: "interact_result"} with loot items
  AND items are added to player's database inventory
  PRIORITY: P0
  CATEGORY: gameplay

SCENARIO: Chest Already Looted (Per-Player)
  GIVEN player has already opened chest_01
  WHEN player sends {action: "interact", target_id: "chest_01"}
  THEN server responds indicating chest was already opened
  PRIORITY: P0
  CATEGORY: gameplay

SCENARIO: Two Players Can Loot Same Chest Independently
  GIVEN player A has opened chest_01 but player B has not
  WHEN player B sends {action: "interact", target_id: "chest_01"}
  THEN player B receives loot (independent per-player state)
  PRIORITY: P1
  CATEGORY: gameplay

SCENARIO: Chest Loot Not in Runtime Inventory (Known Bug)
  GIVEN player opens a chest and receives items
  WHEN player sends {action: "inventory"}
  THEN EXPECTED: chest items should appear in inventory
  AND ACTUAL: items are written to DB player.inventory but NOT to the runtime Inventory object
  NOTE: Functional gap — chest loot goes to DB only, runtime inventory is separate
  PRIORITY: P0
  CATEGORY: gameplay

SCENARIO: Toggle Lever Changes Tile
  GIVEN room has a lever targeting tile (x,y) which is a wall
  WHEN player sends {action: "interact", target_id: "lever_01"}
  THEN tile at (x,y) changes from wall to floor
  AND server broadcasts {type: "tile_changed"} to all players in room
  PRIORITY: P1
  CATEGORY: gameplay

SCENARIO: No Proximity Check on Interact (Known Gap)
  GIVEN player is at (0,0) and chest is at (99,99)
  WHEN player sends {action: "interact", target_id: "chest_01"}
  THEN EXPECTED: server should reject — player too far away
  AND ACTUAL: interaction succeeds regardless of distance
  PRIORITY: P2
  CATEGORY: gameplay

SCENARIO: Interact With Nonexistent Object
  GIVEN no object with id "fake_object" exists in room
  WHEN player sends {action: "interact", target_id: "fake_object"}
  THEN server responds {type: "error"} or interact_result indicating not found
  PRIORITY: P1
  CATEGORY: gameplay
```

#### 1.7 Chat

```
SCENARIO: Room Broadcast Chat
  GIVEN two players are in the same room
  WHEN player A sends {action: "chat", message: "hello"}
  THEN both players receive {type: "chat", sender: "playerA", message: "hello"}
  PRIORITY: P0
  CATEGORY: gameplay

SCENARIO: Whisper to Specific Player
  GIVEN players A, B, and C are in the same room
  WHEN player A sends {action: "chat", message: "secret", whisper_to: "player_2"}
  THEN player B receives the whisper
  AND player C does NOT receive the whisper
  PRIORITY: P1
  CATEGORY: gameplay

SCENARIO: Empty Message Ignored
  GIVEN player is logged in
  WHEN player sends {action: "chat", message: ""}
  THEN server does NOT broadcast any message
  PRIORITY: P1
  CATEGORY: gameplay

SCENARIO: Chat Message Length Not Limited (Known Gap)
  GIVEN player is logged in
  WHEN player sends {action: "chat", message: "a"*100000}
  THEN EXPECTED: server should reject overly long messages
  AND ACTUAL: no message length limit exists
  PRIORITY: P2
  CATEGORY: gameplay
```

---

### 2. Progression / Persistence Tests

#### 2.1 Player State Persistence

```
SCENARIO: Position Saved on Disconnect
  GIVEN player is at position (30,40) in dark_cave
  WHEN player's WebSocket disconnects
  AND player reconnects and logs in
  THEN player appears at (30,40) in dark_cave
  PRIORITY: P0
  CATEGORY: progression

SCENARIO: Position Saved on Room Transition
  GIVEN player transitions from town_square to test_room
  WHEN database is checked
  THEN player's current_room_id is "test_room"
  AND position is at test_room's spawn point
  PRIORITY: P0
  CATEGORY: progression

SCENARIO: Position NOT Saved on Regular Moves (Known Gap)
  GIVEN player moves from (50,50) to (52,50) within a room
  WHEN server crashes before player disconnects
  THEN EXPECTED: player should resume at (52,50)
  AND ACTUAL: player resumes at last saved position (room transition or previous disconnect)
  NOTE: Position is only saved on room transitions and disconnect, not per-move
  PRIORITY: P1
  CATEGORY: progression

SCENARIO: Stats Not Persisted After Combat (Known Gap)
  GIVEN player finishes combat with 20/50 HP
  WHEN player disconnects and reconnects
  THEN EXPECTED: player should have 20/50 HP
  AND ACTUAL: stats may not be persisted consistently (FR52 not implemented)
  PRIORITY: P1
  CATEGORY: progression

SCENARIO: NPC Death State After Server Restart
  GIVEN player killed a persistent NPC
  WHEN server restarts
  THEN NPC respawns (NPCs are in-memory only, not persisted as dead)
  NOTE: This is expected behavior — persistent NPCs have respawn timers
  PRIORITY: P2
  CATEGORY: progression
```

---

### 3. Multiplayer Tests

#### 3.1 Room State Synchronization

```
SCENARIO: Player Join Visible to Others
  GIVEN player A is in town_square
  WHEN player B logs in (default room: town_square)
  THEN player A receives {type: "entity_entered"} with player B's info
  AND player B's room_state contains player A in entities list
  PRIORITY: P0
  CATEGORY: multiplayer

SCENARIO: Player Leave Notifies Others
  GIVEN players A and B are in town_square
  WHEN player A disconnects
  THEN player B receives {type: "entity_left", entity_id: "player_<A>"}
  PRIORITY: P0
  CATEGORY: multiplayer

SCENARIO: Movement Broadcast to All Room Players
  GIVEN players A and B are in town_square
  WHEN player A moves right
  THEN player B receives {type: "entity_moved", entity_id: "player_<A>", x, y}
  PRIORITY: P0
  CATEGORY: multiplayer

SCENARIO: Room Transition Notifies Both Rooms
  GIVEN player A is in town_square with player B
  AND player C is in test_room
  WHEN player A moves to exit tile leading to test_room
  THEN player B receives {type: "entity_left"} for player A
  AND player C receives {type: "entity_entered"} for player A
  PRIORITY: P0
  CATEGORY: multiplayer
```

#### 3.2 Disconnect / Reconnect

```
SCENARIO: Graceful Disconnect Cleanup
  GIVEN player is in a room with other players
  WHEN player's WebSocket connection drops
  THEN player entity is removed from room
  AND other players are notified via entity_left
  AND player's position is saved to DB
  PRIORITY: P0
  CATEGORY: multiplayer

SCENARIO: Disconnect During Combat
  GIVEN player is in combat with another player
  WHEN player disconnects
  THEN player is removed from combat participants
  AND remaining participants receive combat_update
  AND combat continues for remaining participants
  PRIORITY: P0
  CATEGORY: multiplayer

SCENARIO: Unauthenticated Disconnect
  GIVEN WebSocket is connected but player never logged in
  WHEN connection drops
  THEN server handles gracefully (no crash, no error broadcast)
  PRIORITY: P1
  CATEGORY: multiplayer

SCENARIO: Reconnect Restores State
  GIVEN player was in dark_cave at (30,40)
  WHEN player disconnects then reconnects and logs in
  THEN player receives room_state for dark_cave
  AND player position is (30,40)
  PRIORITY: P0
  CATEGORY: multiplayer
```

---

### 4. Server Lifecycle Tests

#### 4.1 Startup

```
SCENARIO: Server Starts Successfully
  GIVEN valid room, card, item, and NPC JSON data files
  WHEN server starts
  THEN /health returns {status: "ok"}
  AND all 4 rooms are loaded with NPCs spawned
  AND all 15 cards are loaded
  AND all 4 items are loaded
  PRIORITY: P0
  CATEGORY: platform

SCENARIO: NPC Templates Load Before Rooms
  GIVEN NPC JSON exists in data/npcs/
  WHEN server starts
  THEN NPC templates are loaded BEFORE rooms
  AND rooms successfully spawn NPCs from templates
  AND room_state contains NPC entities
  NOTE: Was ISS-001 — critical bug fixed by reordering startup
  PRIORITY: P0
  CATEGORY: platform

SCENARIO: Server Handles Missing Data Directory
  GIVEN data/rooms/ directory does not exist
  WHEN server starts
  THEN server starts without crashing
  AND no rooms are loaded
  PRIORITY: P1
  CATEGORY: platform
```

#### 4.2 Shutdown (Known Gap — No Graceful Shutdown)

```
SCENARIO: Graceful Shutdown Saves All Players (NOT IMPLEMENTED)
  GIVEN 3 players are connected in various rooms
  WHEN server receives shutdown signal
  THEN EXPECTED: all player positions and states are saved to DB
  AND EXPECTED: all players receive a shutdown notification
  AND EXPECTED: all players are moved to safe room (town_square)
  AND EXPECTED: all WebSocket connections are closed gracefully
  AND ACTUAL: server hard-stops; only players who disconnect naturally get saved
  NOTE: User-reported issue — needs implementation
  PRIORITY: P0
  CATEGORY: platform

SCENARIO: Shutdown During Combat
  GIVEN a player is in active combat
  WHEN server shuts down
  THEN EXPECTED: combat state is resolved (forfeit/save)
  AND EXPECTED: player state is saved
  AND ACTUAL: combat state is lost; no cleanup
  PRIORITY: P1
  CATEGORY: platform

SCENARIO: Server Restart Command (NOT IMPLEMENTED)
  GIVEN server is running with connected players
  WHEN admin issues restart command
  THEN EXPECTED: graceful shutdown (save all) → restart → players can reconnect
  AND ACTUAL: no restart command exists
  NOTE: User-reported issue — needs implementation
  PRIORITY: P1
  CATEGORY: platform
```

---

### 5. Web Client Tests

#### 5.1 Client-Server Integration

```
SCENARIO: WebSocket Connection and Auto-Reconnect
  GIVEN client opens http://localhost:8000
  WHEN WebSocket connects
  THEN connection status shows "Connected" with green dot
  AND if connection drops, client retries with exponential backoff (max 5 attempts)
  PRIORITY: P0
  CATEGORY: platform

SCENARIO: Client Returns to Login on Disconnect (NOT IMPLEMENTED)
  GIVEN player is in game (explore or combat mode)
  WHEN WebSocket connection drops permanently
  THEN EXPECTED: client should return to login screen
  AND ACTUAL: client shows "Disconnected" but stays on game screen
  NOTE: User-reported issue — needs implementation
  PRIORITY: P1
  CATEGORY: platform

SCENARIO: Movement With Keyboard
  GIVEN player is in explore mode (not in combat, chat not focused)
  WHEN player presses W/A/S/D or arrow keys
  THEN corresponding move action is sent via WebSocket
  AND movePending prevents duplicate moves until response
  PRIORITY: P0
  CATEGORY: platform

SCENARIO: Keyboard Suppressed When Chat Focused
  GIVEN chat input is focused
  WHEN player presses W/A/S/D
  THEN NO move action is sent (keys are for typing)
  PRIORITY: P1
  CATEGORY: platform

SCENARIO: Icon Legend Displays Correctly
  GIVEN player is in game
  THEN map legend below viewport shows all icons:
    @ (cyan) = You, @ (blue) = Player, ! (red) = Mob, x (gray) = Dead
    Floor, Wall, Exit, Water tile swatches
    Chest, Rock object icons
  PRIORITY: P2
  CATEGORY: platform
```

---

### 6. E2E Journey Tests

```
E2E SCENARIO: New Player Full Onboarding
  GIVEN server is running with fresh database
  WHEN user opens browser to http://localhost:8000
  AND registers new account
  AND auto-login completes
  THEN player appears in town_square at (50,50)
  AND tile grid renders with visible objects (trees, rocks, fountain)
  AND player stats panel shows player name and position
  TIMEOUT: 10
  PRIORITY: P0
  CATEGORY: e2e

E2E SCENARIO: Complete Combat Encounter
  GIVEN player is logged in and near a hostile NPC
  WHEN player walks onto NPC tile
  AND combat overlay appears
  AND player plays cards until mob HP reaches 0
  THEN combat_end with victory=true is received
  AND combat overlay closes
  AND player returns to explore mode
  AND NPC appears dead (x icon) on map
  TIMEOUT: 30
  PRIORITY: P0
  CATEGORY: e2e

E2E SCENARIO: Room Traversal Loop
  GIVEN player is in town_square
  WHEN player navigates to exit at (99,50)
  AND transitions through test_room → other_room → dark_cave → town_square
  THEN player is back in town_square
  AND all room transitions showed correct room_state
  TIMEOUT: 60
  PRIORITY: P0
  CATEGORY: e2e

E2E SCENARIO: Combat Flee and Return
  GIVEN player encounters a mob and combat starts
  WHEN player clicks Flee
  THEN combat overlay closes
  AND player is back in explore mode
  AND player can move freely
  AND NPC is still alive at its position
  TIMEOUT: 15
  PRIORITY: P1
  CATEGORY: e2e

E2E SCENARIO: Multi-Player Room Interaction
  GIVEN player A is in town_square
  AND player B logs in (also in town_square)
  WHEN player A moves
  THEN player B sees entity_moved for player A
  AND player A sends chat message
  AND player B receives the chat message
  TIMEOUT: 15
  PRIORITY: P1
  CATEGORY: e2e

E2E SCENARIO: Chest Interaction and Inventory Check
  GIVEN player is in a room with an unopened chest
  WHEN player clicks the chest (interact)
  AND checks inventory
  THEN interact_result shows loot items
  AND inventory response includes the looted items
  NOTE: Currently WILL FAIL due to chest loot → DB only, not runtime inventory
  TIMEOUT: 10
  PRIORITY: P0
  CATEGORY: e2e
```

---

## Coverage Matrix

| Feature | P0 | P1 | P2 | P3 | Total |
|---------|----|----|----|----|-------|
| Authentication | 6 | 1 | 2 | 0 | 9 |
| Movement | 5 | 1 | 1 | 0 | 7 |
| Room Transition | 3 | 1 | 0 | 0 | 4 |
| Combat | 10 | 3 | 2 | 0 | 15 |
| Inventory/Items | 3 | 2 | 0 | 0 | 5 |
| Room Objects | 2 | 3 | 1 | 0 | 6 |
| Chat | 1 | 2 | 1 | 0 | 4 |
| Persistence | 2 | 2 | 1 | 0 | 5 |
| Multiplayer Sync | 4 | 1 | 0 | 0 | 5 |
| Disconnect | 2 | 1 | 0 | 0 | 3 |
| Server Lifecycle | 2 | 2 | 0 | 0 | 4 |
| Web Client | 1 | 2 | 1 | 0 | 4 |
| E2E Journeys | 3 | 2 | 0 | 0 | 5 |
| **Total** | **44** | **23** | **9** | **0** | **76** |

---

## Known Functional Gaps (Bugs & Missing Features)

These issues were identified during test design and should be tracked as ISS-XXX or stories:

### Critical Functional Bugs

| ID | Description | Impact |
|----|-------------|--------|
| GAP-01 | DoT effects never tick — poison/bleed do nothing after being applied | Combat mechanic broken |
| GAP-02 | Victory XP rewards returned in message but never applied to player | Progression broken |
| GAP-03 | Chest loot written to DB but not runtime Inventory object | Items invisible after looting |
| GAP-04 | NPC marked dead at encounter, not at victory (FR56) | NPC appears dead before combat resolves |

### Missing Features (Documented in Epics 7-8)

| ID | Feature | Epic/Story |
|----|---------|------------|
| GAP-05 | Inventory not persisted across sessions | FR54 (Epic 7) |
| GAP-06 | Stats not persisted after combat | FR52 (Epic 7) |
| GAP-07 | No death/respawn mechanic for players | FR53 (Epic 7) |
| GAP-08 | No duplicate login protection | FR55 (Epic 7) |
| GAP-09 | Card cost not enforced (no resource system) | FR57 (Epic 8) |
| GAP-10 | No combat turn timeout | NFR4 |
| GAP-11 | No graceful server shutdown | User-reported |
| GAP-12 | Client doesn't return to login on disconnect | User-reported |

### Input Validation Gaps

| ID | Description | Risk |
|----|-------------|------|
| GAP-13 | No max username length | Low |
| GAP-14 | No username character validation | Low |
| GAP-15 | No chat message length limit | Low |
| GAP-16 | No interaction proximity check | Medium |
| GAP-17 | No server-side movement rate limiting | Low |

---

## Automation Strategy

### Recommended for Automation (Unit/Integration)

- **All P0 gameplay scenarios** — Pure server logic, no UI dependency, already partially covered
- **Combat effect resolution** — Deterministic, fast, high value (damage, heal, shield, DoT)
- **Room transitions** — State machine with clear inputs/outputs
- **Authentication flows** — Simple request/response validation
- **Inventory operations** — Pure logic, already well-tested
- **Multi-client sync** — WebSocket-based, automatable with `websockets` library

### Manual Testing Required

- **Web client keyboard interaction** — Requires real browser (WASD, arrow keys)
- **Visual tile rendering** — Icon positions, colors, viewport centering
- **Combat overlay UX** — Card layout, HP bar animations, turn indicator
- **Chat UX** — Whisper dropdown, message scrolling
- **Icon legend display** — Visual verification

### Automation Tools

- **Server**: Python 3.12, pytest, pytest-asyncio
- **WebSocket testing**: `websockets` library (direct WS client)
- **HTTP testing**: `httpx` (for REST endpoints and health check)
- **CI Integration**: Not yet set up (recommended: GitHub Actions)

---

## Playtesting Recommendations

### Internal Playtests

- **Focus**: Core loop validation (register → explore → combat → victory/defeat)
- **Participants**: Developer + 1-2 additional testers
- **Duration**: 30 minutes per session
- **Key questions**: Can you find mobs? Is combat understandable? Do room transitions feel right?

### Multi-Player Playtests

- **Focus**: Room sync, chat, entity visibility
- **Participants**: 2-4 simultaneous players
- **Duration**: 20 minutes
- **Key questions**: Do you see other players? Does chat work? What happens on disconnect?

---

## Next Steps

1. [ ] Review test design with team
2. [ ] Create ISS-XXX issue files for GAP-01 through GAP-04 (critical bugs)
3. [ ] Create Epic 7 stories for GAP-05 through GAP-12 (missing features)
4. [ ] Prioritize P0 test implementation using `/gds-test-automate`
5. [ ] Fix pytest-asyncio compatibility (v1.3.0 breaking changes)
6. [ ] Set up CI pipeline using `/gds-test-framework`

---

## Appendix

### Glossary

| Term | Definition |
|------|-----------|
| Entity | A player or NPC in a room, with position and state |
| Entity ID | `player_N` format (e.g., `player_1`), constructed from DB player ID |
| Room Instance | In-memory representation of a room with entities, NPCs, objects |
| Combat Instance | Tracks participants, turn order, mob HP, card hands for one fight |
| Effect Registry | Maps effect types (damage, heal, shield, dot, draw) to handler functions |
| Tile Types | FLOOR=0, WALL=1, EXIT=2, MOB_SPAWN=3, WATER=4 |
| NPC Spawn Tiers | persistent (respawn timer), standard, rare (chance roll) |

### References

- Game Design: `_bmad-output/planning-artifacts/architecture.md`
- Epics: `_bmad-output/planning-artifacts/epics.md`
- Implementation Spec: `THE_AGES_SERVER_PLAN.md`
- Sprint Status: `_bmad-output/implementation-artifacts/sprint-status.yaml`
- Knowledge Base: `_bmad/gds/gametest/qa-index.csv`
