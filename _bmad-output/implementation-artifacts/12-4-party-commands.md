# Story 12.4: Party Commands

Status: done

## Story

As a player,
I want to invite others to my party, accept invites, leave, and manage membership through slash commands,
so that I can form and manage cooperative groups during gameplay.

## Acceptance Criteria

1. **Given** a player is not in a party, **When** they send `/party invite @PlayerB`, **Then** Player B must be online (error: "Player is not online" if not connected — `ConnectionManager` cannot distinguish nonexistent accounts from offline ones without a DB lookup, so a single "not online" error suffices), **And** Player B must not already be in a party (error: "Player is already in a party — they must /party leave first"), **And** Player B receives a `party_invite` message with the inviter's name, **And** no same-room requirement for invites.

2. **Given** a player receives a party invite, **When** they send `/party accept`, **Then** if the inviter is not yet in a party, a new party is created with the inviter as leader and the accepter as member, **And** if the inviter is already in a party, the accepter is added to that existing party, **And** all party members are notified via `party_update`.

3. **Given** a player receives a party invite, **When** they send `/party reject`, **Then** the invite is declined and the inviter is notified.

4. **Given** a pending party invite, **When** no response within 30 seconds, **Then** the invite auto-expires and both players are notified.

5. **Given** a player has already sent a pending invite, **When** they send `/party invite @AnotherPlayer`, **Then** the previous invite is cancelled and the new invite is sent.

6. **Given** a player was just kicked, or their invite was rejected/expired, **When** the inviter tries to re-invite the same player, **Then** a cooldown applies (10 seconds) — "Please wait before re-inviting this player".

7. **Given** a player is in a party, **When** they send `/party leave`, **Then** they are removed from the party, **And** remaining members are notified via `party_update`, **And** if they were the leader, succession applies (via `PartyManager.remove_member`), **And** if they were in active combat, they remain in the combat instance — party leave does not affect current combat.

8. **Given** the party leader sends `/party disband`, **When** no party members share an active combat instance with each other, **Then** the party is dissolved and all members are notified via `party_update`.

9. **Given** the party leader sends `/party disband`, **When** any two or more party members share the same active combat instance, **Then** the disband is rejected: "Cannot disband during active party combat". (Note: members in separate, independent combat instances do NOT block disband — only shared instances do.)

10. **Given** the party leader is not in shared combat with the target, **When** the leader sends `/party kick @PlayerC`, **Then** Player C is removed from the party, **And** Player C and remaining members are notified via `party_update`, **And** the cooldown for re-inviting Player C begins.

11. **Given** the party leader sends `/party kick @PlayerC`, **When** the leader and Player C share an active combat instance, **Then** the kick is rejected: "Cannot kick a player during shared combat".

12. **Given** a player is in a party, **When** they send `/party` (no subcommand), **Then** they see: party members list, who is leader, each member's online/offline status and current room.

13. **Given** a player is not in a party and has no pending invites, **When** they send `/party` (no subcommand), **Then** they receive: "You are not in a party".

14. **Given** a player in a party sends `/party <text>` where text is not a known subcommand, **When** the handler processes it, **Then** it returns "Unknown party command. Use: invite, accept, reject, leave, kick, disband" (Story 12.5 will change this to route to party chat).

15. **Given** the `/help` command is sent, **When** the help response is generated, **Then** party commands (`party`) appear under the "Social" category.

16. **Given** the web client, **When** a player types `/party <subcommand> [args]`, **Then** it is routed as `{action: "party", args: "<subcommand> [args]"}` to the server.

## Tasks / Subtasks

- [x] Task 1: Add config settings for party invites (AC: #4, #6)
  - [x] 1.1: Add `PARTY_INVITE_TIMEOUT_SECONDS: int = 30` to `Settings` in `server/core/config.py` (after `MAX_PARTY_SIZE` on line 34)
  - [x] 1.2: Add `PARTY_INVITE_COOLDOWN_SECONDS: int = 10` to `Settings` (after the new timeout setting)

- [x] Task 2: Create `server/net/handlers/party.py` (AC: #1-14)
  - [x] 2.1: Create the party handler module with `handle_party(websocket, data, *, game)` signature matching the trade handler pattern (`server/net/handlers/trade.py:56-58`)
  - [x] 2.2: Implement invite tracking as module-level dicts:
    - `_pending_invites: dict[str, str]` — target_entity_id → inviter_entity_id
    - `_outgoing_invites: dict[str, str]` — inviter_entity_id → target_entity_id (reverse index for efficient outgoing invite lookup/cancellation)
    - `_invite_timeouts: dict[str, asyncio.TimerHandle]` — target_entity_id → timeout handle
    - `_invite_cooldowns: dict[str, dict[str, float]]` — inviter_entity_id → {target_entity_id → cooldown_end_timestamp}
  - [x] 2.3: Implement subcommand dispatch: parse `data.get("args", "").strip()`, split first word as subcommand, route to internal functions
  - [x] 2.4: Implement `invite` subcommand:
    - Extract target name from args (supports `@PlayerB` or `PlayerB`)
    - Resolve target via `game.connection_manager.get_entity_id_by_name(name)` — error if None: "Player is not online"
    - Validate target has an entry in `game.player_entities` (guards against race condition during login) — error if missing: "Player is not online"
    - Reject self-invite (same entity_id)
    - Reject if target already in a party: `game.party_manager.is_in_party(target_id)` → "Player is already in a party — they must /party leave first"
    - Reject if target already has a pending invite: `target_id in _pending_invites` → "Player already has a pending invite"
    - Check per-target cooldown in `_invite_cooldowns[inviter_id][target_id]`
    - If inviter has an existing pending outgoing invite (check `_outgoing_invites[inviter_id]`), cancel it: remove target from `_pending_invites`, remove inviter from `_outgoing_invites`, cancel timeout handle in `_invite_timeouts`
    - Reject if inviter is in a full party: `party and len(party.members) >= settings.MAX_PARTY_SIZE` → "Party is full"
    - Store invite: `_pending_invites[target_id] = inviter_id`
    - Schedule timeout via `loop.call_later(settings.PARTY_INVITE_TIMEOUT_SECONDS, _on_invite_timeout)` — same pattern as `TradeManager.initiate_trade` timeout setup (lines 105-111 of `server/trade/manager.py`) with async notification via `loop.create_task` (lines 133-141)
    - Send `party_invite` to target via `game.connection_manager.send_to_player(target_id, ...)`
    - Confirm to inviter
  - [x] 2.5: Implement `accept` subcommand:
    - Check `_pending_invites.get(entity_id)` — error if no pending invite
    - Cancel timeout handle
    - Remove from `_pending_invites`
    - Verify inviter is still online: `game.connection_manager.get_websocket(inviter_id) is not None` — error if None: "Inviter is no longer online"
    - If inviter is already in a party, add accepter via `game.party_manager.add_member(party.party_id, entity_id)` — handle error string return
    - If inviter is NOT in a party, create new party via `game.party_manager.create_party(inviter_id, entity_id)` — handle error string return
    - Send `party_update` with `action: "member_joined"` to all party members
  - [x] 2.6: Implement `reject` subcommand:
    - Check `_pending_invites.get(entity_id)` — error if no pending invite
    - Cancel timeout handle, remove from `_pending_invites`
    - Set per-target cooldown for the inviter re-inviting this player
    - Notify inviter: `party_invite_response` with `status: "rejected"`
    - Confirm to rejecter
  - [x] 2.7: Implement `leave` subcommand:
    - Check `game.party_manager.is_in_party(entity_id)` — error if not in party
    - Call `game.party_manager.remove_member(entity_id)` — returns `tuple[Party | None, str | None]`
    - If return is `(None, None)`: party dissolved (last member left) — confirm to player, skip `party_update` (no remaining members)
    - If `party` is not None: send `party_update` with `action: "member_left"` to remaining members (same pattern as `_cleanup_player` party cleanup in `server/net/handlers/auth.py:92-105`); include `new_leader` if succession occurred
    - Confirm to the leaving player
    - Note: does NOT affect combat — player stays in any active `CombatInstance`
  - [x] 2.8: Implement `kick` subcommand:
    - Verify sender is party leader: `game.party_manager.is_leader(entity_id)` — error if not leader
    - Resolve target name via `game.connection_manager.get_entity_id_by_name(name)`
    - Verify target is in the same party
    - Check shared combat: both leader and target must NOT share an active `CombatInstance` — use `game.combat_manager.get_player_instance(entity_id)` and check if same instance. Error: "Cannot kick a player during shared combat"
    - Call `game.party_manager.remove_member(target_id)`
    - Set per-target cooldown for re-inviting
    - Send `party_update` with `action: "member_kicked"` to remaining members AND the kicked player
  - [x] 2.9: Implement `disband` subcommand:
    - Verify sender is party leader
    - Check that no party members share an active combat instance — iterate members, check `game.combat_manager.get_player_instance()`, error if any two members are in the same instance: "Cannot disband during active party combat"
    - Call `game.party_manager.disband(party.party_id)` — returns list of member entity_ids
    - Send `party_update` with `action: "disbanded"` to all former members
  - [x] 2.10: Implement status display (no subcommand, AC: #12-13):
    - If not in party and no pending invite: "You are not in a party"
    - If has pending invite: show "You have a pending party invite from <name>. Use /party accept or /party reject"
    - If in party: list members with leader indicator, each member's room from `game.connection_manager.get_room(mid)` (None = offline)
  - [x] 2.11: Handle invite timeout callback:
    - Use `loop.call_later` + `loop.create_task` pattern from `TradeManager` (lines 105-111 for `call_later` setup, lines 118-141 for `_handle_timeout` with `loop.create_task` in `server/trade/manager.py`)
    - On timeout: remove invite, set per-target cooldown, notify both players
  - [x] 2.12: Implement cleanup for disconnecting players' pending invites:
    - Add `_cleanup_pending_invites(entity_id)` function that removes any outgoing or incoming invites for the entity
    - Call this from within `handle_party` module — BUT it should be called from `_cleanup_player`. Add an import and call after party manager disconnect (after line 105 of `server/net/handlers/auth.py`).

- [x] Task 3: Register party handler and update help (AC: #15)
  - [x] 3.1: In `server/app.py` `_register_handlers()`, import `handle_party` from `server.net.handlers.party` (after trade handler import on line 135)
  - [x] 3.2: Register: `self.router.register("party", lambda ws, d: handle_party(ws, d, game=self))` (after trade registration on line 204)
  - [x] 3.3: In `server/net/handlers/query.py` `handle_help_actions()`, add `"party"` and `"trade"` to the `"Social"` category list (line 153 — `"trade"` is currently missing from the Social category despite being implemented in Stories 12.1-12.2)

- [x] Task 4: Update web client (AC: #16)
  - [x] 4.1: In `web-demo/js/game.js`, add `party` entry to the `COMMANDS` object (after the `trade` entry near line 262):
    ```javascript
    party: {
      handler: (args) => sendAction('party', { args: args.join(' ') }),
      description: 'Party commands',
      usage: '/party invite @player | accept | reject | leave | kick @player | disband',
    },
    ```
  - [x] 4.2: Add `party_invite` message handler in the WebSocket `onmessage` handler — display invite notification in chat with system styling
  - [x] 4.3: Add `party_update` message handler — display party membership changes in chat
  - [x] 4.4: Add `party_status` message handler — display party member list

- [x] Task 5: Integrate invite cleanup into `_cleanup_player` (AC: implicit)
  - [x] 5.1: In `server/net/handlers/auth.py`, after the party manager cleanup block (line 105), import and call `cleanup_pending_invites(entity_id)` from `server.net.handlers.party` to clean up any pending invites the disconnecting player has (as inviter or target)

- [x] Task 6: Write tests (AC: #1-16)
  - [x] 6.1: Create `tests/test_party_commands.py` with tests for:
    - Invite: success, target offline, target already in party, self-invite, cooldown, cancel previous invite, party full
    - Accept: success (new party created), success (added to existing party), no pending invite, inviter disconnected
    - Reject: success, no pending invite, cooldown set on inviter
    - Leave: success, leader succession, not in party, combat unaffected
    - Kick: success, not leader, target not in party, shared combat blocks kick, cooldown set
    - Disband: success, not leader, shared combat blocks disband
    - Status: in party (shows members/rooms/leader), not in party
    - Invite timeout: auto-expire after configured seconds
    - Unknown subcommand: error message returned
    - Help: party appears in Social category
    - Disconnect cleanup: pending invites cleaned up on disconnect

## Dev Notes

### Architecture Compliance

- **Handler pattern**: `async def handle_party(ws: WebSocket, data: dict, *, game: Game)` — same as `handle_trade` in `server/net/handlers/trade.py:56-58`. `game` is passed via lambda closure at registration.
- **Import guard**: Use `TYPE_CHECKING` for `Game` type: `if TYPE_CHECKING: from server.app import Game`
- **`from __future__ import annotations`** must be first import in the new module.
- **Subcommand parsing**: Parse `data.get("args", "").strip()` → split → first word is subcommand. Same pattern as trade handler (lines 71-86 of `server/net/handlers/trade.py`).
- **Name resolution**: Use `game.connection_manager.get_entity_id_by_name(name)` (case-insensitive, line 42-44 of `server/net/connection_manager.py`). Strip leading `@` from target name.
- **Error format**: `{"type": "error", "detail": "..."}` — matches all existing handler error responses.
- **Party state is ephemeral** (in-memory only) — no DB operations needed for party logic itself.

### Existing Code to Reuse

- **`PartyManager`** (`server/party/manager.py`): `create_party(leader_id, member_id)`, `add_member(party_id, entity_id)`, `remove_member(entity_id)`, `disband(party_id)`, `get_party(entity_id)`, `is_in_party(entity_id)`, `is_leader(entity_id)`, `get_party_members(entity_id)`. Returns `Party | str` (string = error message).
- **`ConnectionManager.send_to_player(entity_id, msg)`** (`server/net/connection_manager.py:59`): Send messages to individual players.
- **`ConnectionManager.get_entity_id_by_name(name)`** (`server/net/connection_manager.py:42`): Case-insensitive name → entity_id lookup.
- **`ConnectionManager.get_room(entity_id)`** (`server/net/connection_manager.py:46`): Get player's current room — returns `None` if offline/disconnected.
- **`CombatManager.get_player_instance(entity_id)`** (`server/combat/manager.py:51`): Check if player is in combat — returns `CombatInstance | None`.
- **Timeout pattern**: `loop.call_later()` + `loop.create_task()` for async notification from sync callback — see `TradeManager` (`server/trade/manager.py:105-111` for `call_later` setup, `118-141` for `_handle_timeout` with `loop.create_task`).
- **`_cleanup_player` party block** (`server/net/handlers/auth.py:92-105`): Existing pattern for sending `party_update` to remaining members on disconnect.
- **Trade handler** (`server/net/handlers/trade.py`): Model for entire handler structure — subcommand dispatch, entity lookup, error handling.

### Invite System Design

- **Invite tracking is module-level** (in `server/net/handlers/party.py`), NOT on the `Party` dataclass. **Deliberate deviation from epic implementation note** (epics.md line 2656 says to use `Party.pending_invites`). Reason: invites exist before a party does (the invite creates the party on accept), so they cannot be stored on a `Party` that doesn't exist yet. The `Party.pending_invites` field from Story 12.3 remains available for future per-party invite tracking if needed, but this story uses module-level dicts instead.
- **One pending invite per target**: A player can only have one incoming invite at a time. If the same target receives another invite before responding, the first is replaced.
- **One outgoing invite per inviter at a time**: Sending a new invite cancels any previous pending outgoing invite.
- **Cooldown is per-inviter-per-target**: After kick, reject, or expiry, the inviter cannot re-invite that specific target for `PARTY_INVITE_COOLDOWN_SECONDS` (10s). Other invites are unaffected.
- **Timeout callback**: Uses `asyncio.get_running_loop().call_later()` like `TradeManager`. The callback is sync but schedules an async notification via `loop.create_task()`.

### Shared Combat Check (AC: #9, #11)

To determine if party members share an active combat instance:
```python
def _members_share_combat(game, members: list[str]) -> bool:
    instances = set()
    for mid in members:
        inst = game.combat_manager.get_player_instance(mid)
        if inst is not None:
            if inst.instance_id in instances:
                return True
            instances.add(inst.instance_id)
    return False
```
This handles the case where different members might be in different, separate combat instances (which is allowed — only shared instances block kick/disband).

### Message Types (Server → Client)

| Type | When | Payload |
|------|------|---------|
| `party_invite` | Player receives invite | `{type: "party_invite", from_player: str, from_entity_id: str}` |
| `party_invite_response` | Invite rejected/expired/cancelled | `{type: "party_invite_response", status: "rejected"\|"expired"\|"cancelled", target?: str}` |
| `party_update` | Member join/leave/kick/disband/leader change | `{type: "party_update", action: "member_joined"\|"member_left"\|"member_kicked"\|"disbanded", entity_id?: str, members: list[str], leader: str, new_leader?: str}` |
| `party_status` | Status query response | `{type: "party_status", members: [{name: str, entity_id: str, is_leader: bool, room: str\|null}], party_id: str}` |

### Testing Patterns

- **Unit tests**: Create `PartyManager()` + mock `Game`, `ConnectionManager`, `CombatManager`, and `WebSocket` (all `AsyncMock` or `MagicMock` as appropriate). Call `handle_party()` directly.
- **Mock session factory**: `MagicMock(return_value=mock_ctx)` (sync callable returning async context manager) — NOT `AsyncMock()`. (Not needed for party tests since no DB access, but needed if testing `_cleanup_player` integration.)
- **Timeout testing**: Use `asyncio.get_event_loop().call_later()` — in tests, can use `asyncio.sleep()` or mock `time.time()` and manually trigger the callback.
- **Flat test file**: `tests/test_party_commands.py` — no nested directories.

### Project Structure Notes

- New files: `server/net/handlers/party.py`, `tests/test_party_commands.py`
- Modified files: `server/core/config.py` (2 new settings), `server/app.py` (handler import + registration), `server/net/handlers/query.py` (help text), `server/net/handlers/auth.py` (invite cleanup on disconnect), `web-demo/js/game.js` (party command + message handlers)

### References

- [Source: `_bmad-output/planning-artifacts/epics.md` — Story 12.4, lines 2571-2658]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — Epic 12 planned features, lines 626-666]
- [Source: `_bmad-output/project-context.md` — Epic 12 patterns, lines 197-220]
- [Source: `server/party/manager.py` — PartyManager API, lines 1-132]
- [Source: `server/trade/manager.py` — TradeManager timeout pattern, lines 105-141]
- [Source: `server/net/handlers/trade.py` — Trade handler subcommand pattern, lines 56-351]
- [Source: `server/net/connection_manager.py` — Name resolution + send_to_player, lines 42-63]
- [Source: `server/combat/manager.py` — get_player_instance, lines 51-56]
- [Source: `server/app.py` — Handler registration, lines 123-205]
- [Source: `server/net/handlers/auth.py` — _cleanup_player party block, lines 92-105]
- [Source: `server/core/config.py` — Settings class, lines 7-36]
- [Source: `web-demo/js/game.js` — COMMANDS object + trade entry, lines 258-262]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Implemented full party command handler with all subcommands: invite, accept, reject, leave, kick, disband, and status display
- Invite system uses module-level tracking dicts with timeout via `asyncio.call_later` and per-target cooldowns
- Added `PARTY_INVITE_TIMEOUT_SECONDS = 30` and `PARTY_INVITE_COOLDOWN_SECONDS = 10` to config
- Registered `party` action handler in message router
- Added `party` and `trade` to Social help category (trade was missing)
- Updated web client with `/party` slash command and handlers for `party_invite`, `party_update`, `party_status`, and `party_invite_response` messages
- Integrated invite cleanup into `_cleanup_player` disconnect flow
- 39 new tests covering all subcommands, edge cases (self-invite, cooldown, party full, shared combat blocks, leader succession, party dissolution, timeout, disconnect cleanup, help category, not-logged-in, accept-while-in-party)
- Code review fixes: added accept-while-in-party guard, snapshot member lists in messages, display name in timeout notifications
- 778 tests pass total, zero regressions

### File List

New files:
- server/net/handlers/party.py
- tests/test_party_commands.py

Modified files:
- server/core/config.py (added PARTY_INVITE_TIMEOUT_SECONDS, PARTY_INVITE_COOLDOWN_SECONDS)
- server/app.py (party handler import, registration, game ref setup)
- server/net/handlers/query.py (added party and trade to Social help category)
- server/net/handlers/auth.py (invite cleanup in _cleanup_player)
- web-demo/js/game.js (party command + message handlers)
