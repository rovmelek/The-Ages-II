# Story 12.3: Party Infrastructure

Status: done

## Story

As a developer,
I want the server to support party groups with leader/member tracking,
so that the server can track cooperative groups for chat and combat features.

## Acceptance Criteria

1. **Given** the server starts up, **When** all managers are initialized, **Then** a `PartyManager` is created and owned by the `Game` class, **And** `PartyManager` tracks all active parties in-memory.

2. **Given** a player creates a party (via invite acceptance — see Story 12.4), **When** the party is formed, **Then** a `Party` dataclass is created with: `party_id`, `leader` (entity_id), `members` (ordered list of entity_ids), `pending_invites`, `created_at`, **And** the inviting player is set as party leader, **And** the accepting player is added as a member.

3. **Given** a party exists, **When** `PartyManager.get_party(entity_id)` is called for any member, **Then** the party instance is returned, **And** `PartyManager.get_party(entity_id)` returns `None` for non-party players.

4. **Given** a party has `MAX_PARTY_SIZE` (default 4) members, **When** another member is attempted to be added, **Then** the addition is rejected with "Party is full".

5. **Given** the party leader disconnects, **When** disconnect cleanup runs, **Then** leadership passes to the longest-standing member (earliest remaining in `members` list after removing leader), **And** all remaining party members are notified of the new leader via `party_update` message.

6. **Given** the last member leaves or disconnects, **When** the party has no remaining members, **Then** the party is dissolved and removed from `PartyManager`.

7. **Given** a player disconnects, **When** they are a member (not leader) of a party, **Then** they are removed from the party, **And** remaining members are notified via `party_update`.

8. **Given** an admin triggers server shutdown or restart, **When** shutdown cleanup runs via `Game.shutdown()`, **Then** all parties are dissolved (since `_cleanup_player` is called for each player, and party cleanup is part of that flow).

9. **Given** a player's entity_id is known, **When** any system needs to check party membership, **Then** `PartyManager` provides: `is_in_party(entity_id)`, `get_party(entity_id)`, `is_leader(entity_id)`, `get_party_members(entity_id)`.

## Tasks / Subtasks

- [x] Task 1: Add `MAX_PARTY_SIZE` config setting (AC: #4)
  - [x] 1.1: Add `MAX_PARTY_SIZE: int = 4` to `Settings` class in `server/core/config.py` (after `MAX_TRADE_ITEMS` on line 33)

- [x] Task 2: Create `server/party/` package with Party dataclass and PartyManager (AC: #1-9)
  - [x] 2.1: Create `server/party/__init__.py` (empty, standard package init)
  - [x] 2.2: Create `server/party/manager.py` with:
    - `Party` dataclass:
      - `party_id: str`
      - `leader: str` (entity_id)
      - `members: list[str]` (entity_ids, ordered by join time — leader is always `members[0]`) — use `field(default_factory=list)`
      - `pending_invites: dict[str, float]` (target_entity_id → invite_timestamp, for Story 12.4 invite tracking) — use `field(default_factory=dict)`
      - `created_at: float` (via `field(default_factory=time.time)`)
    - `PartyManager` class:
      - `_parties: dict[str, Party]` — party_id → Party
      - `_player_party: dict[str, str]` — entity_id → party_id
      - `create_party(leader_id: str, member_id: str) -> Party | str` — validates neither player is already in a party, creates Party with leader as `members[0]` and member as `members[1]`
      - `add_member(party_id: str, entity_id: str) -> Party | str` — validates party exists, not full (`MAX_PARTY_SIZE`), player not already in a party; appends to `members` list
      - `remove_member(entity_id: str) -> tuple[Party | None, str | None]` — removes player from party; if player was leader, promotes `members[0]` (after removal) as new leader; if party empty, dissolves; returns `(party_or_none, new_leader_id_or_none)`
      - `disband(party_id: str) -> list[str]` — dissolves party, returns list of member entity_ids that were in the party
      - `get_party(entity_id: str) -> Party | None` — returns Party for a player or None
      - `is_in_party(entity_id: str) -> bool`
      - `is_leader(entity_id: str) -> bool`
      - `get_party_members(entity_id: str) -> list[str]` — returns member entity_ids or empty list
      - `handle_disconnect(entity_id: str) -> tuple[Party | None, str | None]` — calls `remove_member`; returns party and new leader (if succession occurred) for notification by caller

- [x] Task 3: Add PartyManager to Game class (AC: #1)
  - [x] 3.1: Import `PartyManager` in `server/app.py` (after `TradeManager` import on line 25)
  - [x] 3.2: Instantiate `self.party_manager = PartyManager()` in `Game.__init__()` (after `self.trade_manager` setup on line 42)

- [x] Task 4: Integrate party cleanup into `_cleanup_player` (AC: #5, #7, #8)
  - [x] 4.1: In `_cleanup_player` (`server/net/handlers/auth.py`, line 25), add party cleanup between combat cleanup (step 1, line 90) and save state to DB (step 2, line 92). This follows the disconnect order specified in `architecture.md:657`: cancel trades → remove from combat → **handle party departure** → save state → remove from room → notify.
    ```python
    # 1.5. Party cleanup (remove from party, handle leader succession)
    party_result, new_leader_id = game.party_manager.handle_disconnect(entity_id)
    if party_result and party_result.members:
        update_msg = {
            "type": "party_update",
            "action": "member_left",
            "entity_id": entity_id,
            "members": party_result.members,
            "leader": party_result.leader,
        }
        if new_leader_id:
            update_msg["new_leader"] = new_leader_id
        for mid in party_result.members:
            await game.connection_manager.send_to_player(mid, update_msg)
    ```

- [x] Task 5: Write tests (AC: #1-9)
  - [x] 5.1: Create `tests/test_party.py` with tests for:
    - PartyManager creation (empty state)
    - `create_party` — success, both players registered in `_player_party`
    - `create_party` — failure when player already in a party
    - `get_party` — returns Party for members, None for non-members
    - `is_in_party` — true for members, false for non-members
    - `is_leader` — true for leader, false for non-leader members
    - `get_party_members` — returns correct ordered list
    - `add_member` — success, appends to end of members list
    - `add_member` — failure when party full (`MAX_PARTY_SIZE`)
    - `add_member` — failure when player already in a party
    - `add_member` — failure when party_id doesn't exist
    - `remove_member` (non-leader) — removes from party, no succession
    - `remove_member` (leader) — promotes `members[0]` as new leader
    - `remove_member` (last member) — dissolves party, returns `(None, None)`
    - `disband` — all members removed, party deleted
    - `handle_disconnect` — delegates to `remove_member`, returns correct tuple
    - Leader succession with 3+ members — leader leaves, second member promoted
    - Integration: party cleanup in `_cleanup_player` sends `party_update` to remaining members

## Dev Notes

### Architecture Compliance

- **Manager ownership**: `PartyManager` is an instance attribute of `Game` — accessed as `game.party_manager`. Same pattern as `TradeManager` (`server/trade/manager.py`).
- **State storage**: Party state is **ephemeral** (in-memory only) — dissolved on server restart. ADR-2 rationale: reform cost ~3s < persistence complexity. No DB tables needed.
- **Import guard**: Use `TYPE_CHECKING` for `Game` type imports: `if TYPE_CHECKING: from server.app import Game`
- **`from __future__ import annotations`** must be first import in every new module.
- **Session factory**: Party operations do NOT touch the database — no `session_factory` usage needed in PartyManager.
- **No handler registration in this story**: Party commands (`/party invite`, `/party accept`, etc.) are handled by Story 12.4 which creates `server/net/handlers/party.py`. This story only provides the infrastructure (PartyManager + Party dataclass + disconnect integration).

### Existing Code to Reuse

- **`TradeManager` pattern** (`server/trade/manager.py`): Follow the same structure — `_parties` dict + `_player_party` reverse index, same pattern as `_trades` + `_player_trade`.
- **`Trade` dataclass pattern** (`server/trade/manager.py:12-25`): Follow `@dataclass` with `field(default_factory=...)` for mutable defaults.
- **`ConnectionManager.send_to_player(entity_id, message)`** (`server/net/connection_manager.py:59`): Send `party_update` messages to party members during disconnect cleanup.
- **`_cleanup_player` flow** (`server/net/handlers/auth.py:25-125`): Insert party cleanup between combat cleanup (line 90) and save state to DB (line 92), per the disconnect order in `architecture.md:657`.

### Disconnect Cleanup Order (Updated)

Current order in `_cleanup_player` (`server/net/handlers/auth.py:25-125`):
0. Cancel active trades (lines 40-55)
1. Combat cleanup (lines 57-90)
2. Save state to DB (lines 92-111)
3. Remove from room + broadcast (lines 113-121)
4. Clean up connection_manager + player_entities (lines 123-125)

New order after 12.3 (per `architecture.md:657` — cancel trades → remove from combat → handle party departure → save state → remove from room → notify):
0. Cancel active trades (existing)
1. Combat cleanup (existing)
1.5. **Party cleanup — remove from party, handle leader succession, notify members** (NEW)
2. Save state to DB (existing)
3. Remove from room + broadcast (existing)
4. Clean up connection_manager + player_entities (existing)

Party cleanup goes after combat because:
- The architecture specifies this order: trades → combat → party → save → room → notify
- Combat cleanup syncs HP stats back to entity (needed before DB save in step 2)
- Party departure is independent of combat state — removing from party doesn't affect combat instances
- Party members can still receive notifications because the disconnecting player's WebSocket is not cleaned up until step 4

### Message Types (Server → Client)

| Type | When | Payload |
|------|------|---------|
| `party_update` | Member joins, leaves, disconnects, or leader changes | `{type, action: "member_left"\|"member_joined"\|"disbanded"\|"leader_changed", entity_id: str, members: list[str], leader: str, new_leader?: str}` |

### Key Design Decisions

- **Leader is always `members[0]`**: The leader's entity_id is both stored in `party.leader` AND is always `members[0]`. This means succession simply sets `party.leader = party.members[0]` after removing the old leader.
- **`pending_invites` dict**: Stored on the `Party` dataclass for Story 12.4 invite cooldown tracking. Initialized empty in this story — not used until Story 12.4.
- **`handle_disconnect` returns tuple**: Returns `(party_or_none, new_leader_id_or_none)` so the caller (`_cleanup_player`) can send appropriate notifications. If the party was dissolved (last member left), returns `(None, None)`.
- **No `set_connection_manager` pattern**: Unlike `TradeManager` which needs `ConnectionManager` for async timeout callbacks, `PartyManager` does NOT need a `ConnectionManager` reference. Notifications are handled by the caller (the handler or `_cleanup_player`).

### Testing Patterns

- **PartyManager unit tests**: Direct class testing, no server or DB needed. Create `PartyManager()`, call methods, assert state.
- **Integration test**: Test `_cleanup_player` party cleanup path — requires `Game()` instance with mocked WebSocket (`AsyncMock`) and `game.party_manager` populated.
- **Mock session factory**: `MagicMock(return_value=mock_ctx)` (sync callable returning async context manager) — NOT `AsyncMock()`.
- **Flat test file**: `tests/test_party.py` — no nested directories.

### Project Structure Notes

- New directories: `server/party/` (with `__init__.py` and `manager.py`)
- New files: `tests/test_party.py`
- Modified files: `server/core/config.py`, `server/app.py`, `server/net/handlers/auth.py`
- `server/net/handlers/party.py` is NOT created in this story — that's Story 12.4

### References

- [Source: `_bmad-output/planning-artifacts/epics.md` — Story 12.3 section, lines 2511-2569]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — Section 11, Epic 12 planned features, lines 626-666]
- [Source: `_bmad-output/project-context.md` — Epic 12 patterns section, lines 197-220]
- [Source: `server/trade/manager.py` — TradeManager pattern reference, lines 1-305]
- [Source: `server/app.py` — Game.__init__ lines 33-45, _register_handlers lines 121-203]
- [Source: `server/net/handlers/auth.py` — _cleanup_player lines 25-125]
- [Source: `server/core/config.py` — Settings class lines 7-35]
- [Source: `server/net/connection_manager.py` — ConnectionManager class lines 1-85]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Implemented PartyManager with Party dataclass, leader succession, member tracking, and dissolution
- Integrated party cleanup into `_cleanup_player` at step 1.5 (between combat cleanup and DB save), following architecture.md disconnect order
- Added `MAX_PARTY_SIZE = 4` config setting
- 42 new tests covering all PartyManager methods, leader succession (2/3/4 member scenarios), dissolution, and `_cleanup_player` integration
- Fixed pre-existing test regression in `test_exploration_xp.py` (added `party_manager.handle_disconnect` mock)
- 737 tests pass total, 2 pre-existing failures unrelated to party changes (movement.py send_to_player mock issue)

### File List

New files:
- server/party/__init__.py
- server/party/manager.py
- tests/test_party.py

Modified files:
- server/core/config.py (added MAX_PARTY_SIZE setting)
- server/app.py (PartyManager import and instantiation)
- server/net/handlers/auth.py (party cleanup in _cleanup_player)
- tests/test_exploration_xp.py (added party_manager mock for cleanup test)
