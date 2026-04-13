"""Tests for party command handler (Story 12.4)."""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.core.config import settings
from server.net.handlers.party import (
    handle_party,
)
from server.party.manager import PartyManager


from server.player.manager import PlayerManager
from server.player.session import PlayerSession


def _ps(d: dict) -> PlayerSession:
    """Build a PlayerSession from a dict (test helper)."""
    entity = d["entity"]
    return PlayerSession(
        entity=entity,
        room_key=d["room_key"],
        db_id=d.get("db_id") or getattr(entity, "player_db_id", 0),
        inventory=d.get("inventory"),
        visited_rooms=set(d.get("visited_rooms", [])),
        pending_level_ups=d.get("pending_level_ups", 0),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_game():
    """Create a mock Game with required managers."""
    game = MagicMock()
    game.connection_manager = MagicMock()
    game.connection_manager.get_entity_id = MagicMock()
    game.connection_manager.get_entity_id_by_name = MagicMock()
    game.connection_manager.get_websocket = MagicMock(return_value=MagicMock())
    game.connection_manager.get_room = MagicMock(return_value="town_square")
    game.connection_manager.send_to_player = AsyncMock()
    game.party_manager = PartyManager(connection_manager=game.connection_manager)
    game.combat_manager = MagicMock()
    game.combat_manager.get_player_instance = MagicMock(return_value=None)
    game.player_manager = PlayerManager()
    return game


def _make_ws():
    """Create a mock WebSocket."""
    ws = AsyncMock()
    return ws


def _register_player(game, entity_id: str, name: str):
    """Register a player in the game."""
    entity = MagicMock()
    entity.name = name
    entity.id = entity_id
    game.player_manager.set_session(entity_id, _ps({"entity": entity, "room_key": "town_square"}))
    game.connection_manager.get_entity_id_by_name.side_effect = (
        lambda n: entity_id if n.lower() == name.lower() else _orig_get_by_name(game, n)
    )
    return entity


def _orig_get_by_name(game, name):
    """Fallback name lookup scanning player sessions."""
    for eid, info in game.player_manager.all_sessions():
        if info.entity.name.lower() == name.lower():
            return eid
    return None


def _setup_name_resolver(game):
    """Set up name resolver that works across all registered players."""
    def resolver(name):
        for eid, info in game.player_manager.all_sessions():
            if info.entity.name.lower() == name.lower():
                return eid
        return None
    game.connection_manager.get_entity_id_by_name = MagicMock(side_effect=resolver)


# ---------------------------------------------------------------------------
# Invite tests
# ---------------------------------------------------------------------------

class TestInvite:
    """Tests for /party invite."""

    async def test_invite_success(self):
        game = _make_game()
        ws = _make_ws()
        game.connection_manager.get_entity_id.return_value = "player_1"
        _register_player(game, "player_1", "Alice")
        _register_player(game, "player_2", "Bob")
        _setup_name_resolver(game)

        await handle_party(ws, {"args": "invite @Bob"}, game=game)

        # Target should receive party_invite
        game.connection_manager.send_to_player.assert_called()
        calls = game.connection_manager.send_to_player.call_args_list
        invite_call = [c for c in calls if c[0][1].get("type") == "party_invite"]
        assert len(invite_call) == 1
        assert invite_call[0][0][0] == "player_2"
        assert invite_call[0][0][1]["from_player"] == "Alice"

        # Inviter should get confirmation
        ws.send_json.assert_called()
        last_msg = ws.send_json.call_args[0][0]
        assert last_msg["type"] == "party_invite_response"
        assert last_msg["status"] == "sent"

        # State tracking
        assert game.party_manager._pending_invites["player_2"] == "player_1"
        assert game.party_manager._outgoing_invites["player_1"] == "player_2"

    async def test_invite_target_offline(self):
        game = _make_game()
        ws = _make_ws()
        game.connection_manager.get_entity_id.return_value = "player_1"
        _register_player(game, "player_1", "Alice")
        _setup_name_resolver(game)

        await handle_party(ws, {"args": "invite @Ghost"}, game=game)

        ws.send_json.assert_called_with(
            {"type": "error", "detail": "Player is not online"}
        )

    async def test_invite_target_already_in_party(self):
        game = _make_game()
        ws = _make_ws()
        game.connection_manager.get_entity_id.return_value = "player_1"
        _register_player(game, "player_1", "Alice")
        _register_player(game, "player_2", "Bob")
        _register_player(game, "player_3", "Carol")
        _setup_name_resolver(game)

        # Put Bob in a party
        game.party_manager.create_party("player_2", "player_3")

        await handle_party(ws, {"args": "invite @Bob"}, game=game)

        ws.send_json.assert_called_with(
            {"type": "error", "detail": "Player is already in a party \u2014 they must /party leave first"}
        )

    async def test_invite_self(self):
        game = _make_game()
        ws = _make_ws()
        game.connection_manager.get_entity_id.return_value = "player_1"
        _register_player(game, "player_1", "Alice")
        _setup_name_resolver(game)

        await handle_party(ws, {"args": "invite @Alice"}, game=game)

        ws.send_json.assert_called_with(
            {"type": "error", "detail": "Cannot invite yourself"}
        )

    async def test_invite_cooldown(self):
        game = _make_game()
        ws = _make_ws()
        game.connection_manager.get_entity_id.return_value = "player_1"
        _register_player(game, "player_1", "Alice")
        _register_player(game, "player_2", "Bob")
        _setup_name_resolver(game)

        # Set cooldown
        game.party_manager.set_cooldown("player_1", "player_2")

        await handle_party(ws, {"args": "invite @Bob"}, game=game)

        ws.send_json.assert_called_with(
            {"type": "error", "detail": "Please wait before re-inviting this player"}
        )

    async def test_invite_cancels_previous(self):
        game = _make_game()
        ws = _make_ws()
        game.connection_manager.get_entity_id.return_value = "player_1"
        _register_player(game, "player_1", "Alice")
        _register_player(game, "player_2", "Bob")
        _register_player(game, "player_3", "Carol")
        _setup_name_resolver(game)

        # First invite Bob
        await handle_party(ws, {"args": "invite @Bob"}, game=game)
        assert game.party_manager._pending_invites.get("player_2") == "player_1"

        # Now invite Carol — should cancel Bob's invite
        await handle_party(ws, {"args": "invite @Carol"}, game=game)
        assert "player_2" not in game.party_manager._pending_invites
        assert game.party_manager._pending_invites.get("player_3") == "player_1"
        assert game.party_manager._outgoing_invites.get("player_1") == "player_3"

    async def test_invite_party_full(self):
        game = _make_game()
        ws = _make_ws()
        game.connection_manager.get_entity_id.return_value = "player_1"
        _register_player(game, "player_1", "Alice")
        _register_player(game, "player_2", "Bob")
        _register_player(game, "player_3", "Carol")
        _register_player(game, "player_4", "Dave")
        _register_player(game, "player_5", "Eve")
        _setup_name_resolver(game)

        # Create a full party (4 members)
        game.party_manager.create_party("player_1", "player_2")
        game.party_manager.add_member(game.party_manager.get_party("player_1").party_id, "player_3")
        game.party_manager.add_member(game.party_manager.get_party("player_1").party_id, "player_4")

        await handle_party(ws, {"args": "invite @Eve"}, game=game)

        ws.send_json.assert_called_with(
            {"type": "error", "detail": "Party is full"}
        )

    async def test_invite_target_has_pending(self):
        game = _make_game()
        ws = _make_ws()
        game.connection_manager.get_entity_id.return_value = "player_1"
        _register_player(game, "player_1", "Alice")
        _register_player(game, "player_2", "Bob")
        _register_player(game, "player_3", "Carol")
        _setup_name_resolver(game)

        # Carol already invited Bob
        game.party_manager._pending_invites["player_2"] = "player_3"

        await handle_party(ws, {"args": "invite @Bob"}, game=game)

        ws.send_json.assert_called_with(
            {"type": "error", "detail": "Player already has a pending invite"}
        )

    async def test_invite_without_at_sign(self):
        """Invite should work with or without @ prefix."""
        game = _make_game()
        ws = _make_ws()
        game.connection_manager.get_entity_id.return_value = "player_1"
        _register_player(game, "player_1", "Alice")
        _register_player(game, "player_2", "Bob")
        _setup_name_resolver(game)

        await handle_party(ws, {"args": "invite Bob"}, game=game)

        assert game.party_manager._pending_invites.get("player_2") == "player_1"


# ---------------------------------------------------------------------------
# Accept tests
# ---------------------------------------------------------------------------

class TestAccept:
    """Tests for /party accept."""

    async def test_accept_creates_new_party(self):
        game = _make_game()
        ws = _make_ws()
        game.connection_manager.get_entity_id.return_value = "player_2"
        _register_player(game, "player_1", "Alice")
        _register_player(game, "player_2", "Bob")

        # Set up pending invite
        game.party_manager._pending_invites["player_2"] = "player_1"

        await handle_party(ws, {"args": "accept"}, game=game)

        # Party should be created
        party = game.party_manager.get_party("player_1")
        assert party is not None
        assert party.leader == "player_1"
        assert "player_2" in party.members

        # All members notified
        game.connection_manager.send_to_player.assert_called()

    async def test_accept_joins_existing_party(self):
        game = _make_game()
        ws = _make_ws()
        game.connection_manager.get_entity_id.return_value = "player_3"
        _register_player(game, "player_1", "Alice")
        _register_player(game, "player_2", "Bob")
        _register_player(game, "player_3", "Carol")

        # Create existing party
        game.party_manager.create_party("player_1", "player_2")
        party = game.party_manager.get_party("player_1")

        # Set up invite from player_1 (who is in a party) to player_3
        game.party_manager._pending_invites["player_3"] = "player_1"

        await handle_party(ws, {"args": "accept"}, game=game)

        # Carol should be in the party
        assert game.party_manager.is_in_party("player_3")
        updated_party = game.party_manager.get_party("player_1")
        assert "player_3" in updated_party.members

    async def test_accept_no_pending_invite(self):
        game = _make_game()
        ws = _make_ws()
        game.connection_manager.get_entity_id.return_value = "player_2"
        _register_player(game, "player_2", "Bob")

        await handle_party(ws, {"args": "accept"}, game=game)

        ws.send_json.assert_called_with(
            {"type": "error", "detail": "No pending party invite"}
        )

    async def test_accept_already_in_party(self):
        game = _make_game()
        ws = _make_ws()
        game.connection_manager.get_entity_id.return_value = "player_2"
        _register_player(game, "player_1", "Alice")
        _register_player(game, "player_2", "Bob")
        _register_player(game, "player_3", "Carol")

        # Bob is already in a party with Carol
        game.party_manager.create_party("player_2", "player_3")

        # Alice invited Bob (somehow)
        game.party_manager._pending_invites["player_2"] = "player_1"

        await handle_party(ws, {"args": "accept"}, game=game)

        ws.send_json.assert_called_with(
            {"type": "error", "detail": "You are already in a party"}
        )

    async def test_accept_inviter_disconnected(self):
        game = _make_game()
        ws = _make_ws()
        game.connection_manager.get_entity_id.return_value = "player_2"
        _register_player(game, "player_2", "Bob")

        game.party_manager._pending_invites["player_2"] = "player_1"
        game.connection_manager.get_websocket.return_value = None

        await handle_party(ws, {"args": "accept"}, game=game)

        ws.send_json.assert_called_with(
            {"type": "error", "detail": "Inviter is no longer online"}
        )


# ---------------------------------------------------------------------------
# Reject tests
# ---------------------------------------------------------------------------

class TestReject:
    """Tests for /party reject."""

    async def test_reject_success(self):
        game = _make_game()
        ws = _make_ws()
        game.connection_manager.get_entity_id.return_value = "player_2"
        _register_player(game, "player_1", "Alice")
        _register_player(game, "player_2", "Bob")

        game.party_manager._pending_invites["player_2"] = "player_1"

        await handle_party(ws, {"args": "reject"}, game=game)

        # Invite removed
        assert "player_2" not in game.party_manager._pending_invites

        # Inviter notified
        game.connection_manager.send_to_player.assert_called()
        invite_response_calls = [
            c for c in game.connection_manager.send_to_player.call_args_list
            if c[0][1].get("type") == "party_invite_response"
        ]
        assert len(invite_response_calls) == 1
        assert invite_response_calls[0][0][0] == "player_1"
        assert invite_response_calls[0][0][1]["status"] == "rejected"

        # Cooldown set
        assert game.party_manager.check_cooldown("player_1", "player_2")

    async def test_reject_no_pending(self):
        game = _make_game()
        ws = _make_ws()
        game.connection_manager.get_entity_id.return_value = "player_2"
        _register_player(game, "player_2", "Bob")

        await handle_party(ws, {"args": "reject"}, game=game)

        ws.send_json.assert_called_with(
            {"type": "error", "detail": "No pending party invite"}
        )


# ---------------------------------------------------------------------------
# Leave tests
# ---------------------------------------------------------------------------

class TestLeave:
    """Tests for /party leave."""

    async def test_leave_success(self):
        game = _make_game()
        ws = _make_ws()
        game.connection_manager.get_entity_id.return_value = "player_2"
        _register_player(game, "player_1", "Alice")
        _register_player(game, "player_2", "Bob")
        _register_player(game, "player_3", "Carol")

        game.party_manager.create_party("player_1", "player_2")
        party = game.party_manager.get_party("player_1")
        game.party_manager.add_member(party.party_id, "player_3")

        await handle_party(ws, {"args": "leave"}, game=game)

        assert not game.party_manager.is_in_party("player_2")
        assert game.party_manager.is_in_party("player_1")

    async def test_leave_leader_succession(self):
        game = _make_game()
        ws = _make_ws()
        game.connection_manager.get_entity_id.return_value = "player_1"
        _register_player(game, "player_1", "Alice")
        _register_player(game, "player_2", "Bob")

        game.party_manager.create_party("player_1", "player_2")

        await handle_party(ws, {"args": "leave"}, game=game)

        assert not game.party_manager.is_in_party("player_1")
        assert game.party_manager.is_leader("player_2")

    async def test_leave_last_member_dissolves(self):
        game = _make_game()
        ws = _make_ws()
        game.connection_manager.get_entity_id.return_value = "player_1"
        _register_player(game, "player_1", "Alice")
        _register_player(game, "player_2", "Bob")

        game.party_manager.create_party("player_1", "player_2")

        # Player 2 leaves first
        game.party_manager.remove_member("player_2")

        # Player 1 leaves — party dissolves
        await handle_party(ws, {"args": "leave"}, game=game)

        assert not game.party_manager.is_in_party("player_1")

    async def test_leave_not_in_party(self):
        game = _make_game()
        ws = _make_ws()
        game.connection_manager.get_entity_id.return_value = "player_1"
        _register_player(game, "player_1", "Alice")

        await handle_party(ws, {"args": "leave"}, game=game)

        ws.send_json.assert_called_with(
            {"type": "error", "detail": "You are not in a party"}
        )


# ---------------------------------------------------------------------------
# Kick tests
# ---------------------------------------------------------------------------

class TestKick:
    """Tests for /party kick."""

    async def test_kick_success(self):
        game = _make_game()
        ws = _make_ws()
        game.connection_manager.get_entity_id.return_value = "player_1"
        _register_player(game, "player_1", "Alice")
        _register_player(game, "player_2", "Bob")
        _register_player(game, "player_3", "Carol")
        _setup_name_resolver(game)

        game.party_manager.create_party("player_1", "player_2")
        party = game.party_manager.get_party("player_1")
        game.party_manager.add_member(party.party_id, "player_3")

        await handle_party(ws, {"args": "kick @Bob"}, game=game)

        assert not game.party_manager.is_in_party("player_2")
        assert game.party_manager.is_in_party("player_1")
        assert game.party_manager.is_in_party("player_3")

        # Cooldown set
        assert game.party_manager.check_cooldown("player_1", "player_2")

    async def test_kick_not_leader(self):
        game = _make_game()
        ws = _make_ws()
        game.connection_manager.get_entity_id.return_value = "player_2"
        _register_player(game, "player_1", "Alice")
        _register_player(game, "player_2", "Bob")
        _setup_name_resolver(game)

        game.party_manager.create_party("player_1", "player_2")

        await handle_party(ws, {"args": "kick @Alice"}, game=game)

        ws.send_json.assert_called_with(
            {"type": "error", "detail": "Only the party leader can kick members"}
        )

    async def test_kick_target_not_in_party(self):
        game = _make_game()
        ws = _make_ws()
        game.connection_manager.get_entity_id.return_value = "player_1"
        _register_player(game, "player_1", "Alice")
        _register_player(game, "player_2", "Bob")
        _register_player(game, "player_3", "Carol")
        _setup_name_resolver(game)

        game.party_manager.create_party("player_1", "player_2")

        await handle_party(ws, {"args": "kick @Carol"}, game=game)

        ws.send_json.assert_called_with(
            {"type": "error", "detail": "Player is not in your party"}
        )

    async def test_kick_shared_combat_blocks(self):
        game = _make_game()
        ws = _make_ws()
        game.connection_manager.get_entity_id.return_value = "player_1"
        _register_player(game, "player_1", "Alice")
        _register_player(game, "player_2", "Bob")
        _setup_name_resolver(game)

        game.party_manager.create_party("player_1", "player_2")

        # Both in same combat instance
        mock_instance = MagicMock()
        mock_instance.instance_id = "combat_1"
        game.combat_manager.get_player_instance = MagicMock(return_value=mock_instance)

        await handle_party(ws, {"args": "kick @Bob"}, game=game)

        ws.send_json.assert_called_with(
            {"type": "error", "detail": "Cannot kick a player during shared combat"}
        )

    async def test_kick_different_combat_allowed(self):
        """Players in different combat instances should be kickable."""
        game = _make_game()
        ws = _make_ws()
        game.connection_manager.get_entity_id.return_value = "player_1"
        _register_player(game, "player_1", "Alice")
        _register_player(game, "player_2", "Bob")
        _setup_name_resolver(game)

        game.party_manager.create_party("player_1", "player_2")

        # Each in different combat instance
        inst_a = MagicMock()
        inst_a.instance_id = "combat_1"
        inst_b = MagicMock()
        inst_b.instance_id = "combat_2"

        def get_instance(eid):
            if eid == "player_1":
                return inst_a
            if eid == "player_2":
                return inst_b
            return None

        game.combat_manager.get_player_instance = MagicMock(side_effect=get_instance)

        await handle_party(ws, {"args": "kick @Bob"}, game=game)

        assert not game.party_manager.is_in_party("player_2")


# ---------------------------------------------------------------------------
# Disband tests
# ---------------------------------------------------------------------------

class TestDisband:
    """Tests for /party disband."""

    async def test_disband_success(self):
        game = _make_game()
        ws = _make_ws()
        game.connection_manager.get_entity_id.return_value = "player_1"
        _register_player(game, "player_1", "Alice")
        _register_player(game, "player_2", "Bob")

        game.party_manager.create_party("player_1", "player_2")

        await handle_party(ws, {"args": "disband"}, game=game)

        assert not game.party_manager.is_in_party("player_1")
        assert not game.party_manager.is_in_party("player_2")

        # Both notified
        calls = [
            c for c in game.connection_manager.send_to_player.call_args_list
            if c[0][1].get("action") == "disbanded"
        ]
        assert len(calls) == 2

    async def test_disband_not_leader(self):
        game = _make_game()
        ws = _make_ws()
        game.connection_manager.get_entity_id.return_value = "player_2"
        _register_player(game, "player_1", "Alice")
        _register_player(game, "player_2", "Bob")

        game.party_manager.create_party("player_1", "player_2")

        await handle_party(ws, {"args": "disband"}, game=game)

        ws.send_json.assert_called_with(
            {"type": "error", "detail": "Only the party leader can disband"}
        )

    async def test_disband_shared_combat_blocks(self):
        game = _make_game()
        ws = _make_ws()
        game.connection_manager.get_entity_id.return_value = "player_1"
        _register_player(game, "player_1", "Alice")
        _register_player(game, "player_2", "Bob")

        game.party_manager.create_party("player_1", "player_2")

        mock_instance = MagicMock()
        mock_instance.instance_id = "combat_1"
        game.combat_manager.get_player_instance = MagicMock(return_value=mock_instance)

        await handle_party(ws, {"args": "disband"}, game=game)

        ws.send_json.assert_called_with(
            {"type": "error", "detail": "Cannot disband during active party combat"}
        )


# ---------------------------------------------------------------------------
# Status tests
# ---------------------------------------------------------------------------

class TestStatus:
    """Tests for /party (no subcommand)."""

    async def test_status_in_party(self):
        game = _make_game()
        ws = _make_ws()
        game.connection_manager.get_entity_id.return_value = "player_1"
        _register_player(game, "player_1", "Alice")
        _register_player(game, "player_2", "Bob")

        game.party_manager.create_party("player_1", "player_2")

        await handle_party(ws, {"args": ""}, game=game)

        msg = ws.send_json.call_args[0][0]
        assert msg["type"] == "party_status"
        assert len(msg["members"]) == 2
        leader_member = [m for m in msg["members"] if m["is_leader"]]
        assert len(leader_member) == 1
        assert leader_member[0]["name"] == "Alice"

    async def test_status_not_in_party(self):
        game = _make_game()
        ws = _make_ws()
        game.connection_manager.get_entity_id.return_value = "player_1"
        _register_player(game, "player_1", "Alice")

        await handle_party(ws, {"args": ""}, game=game)

        ws.send_json.assert_called_with(
            {"type": "error", "detail": "You are not in a party"}
        )

    async def test_status_pending_invite(self):
        game = _make_game()
        ws = _make_ws()
        game.connection_manager.get_entity_id.return_value = "player_2"
        _register_player(game, "player_1", "Alice")
        _register_player(game, "player_2", "Bob")

        game.party_manager._pending_invites["player_2"] = "player_1"

        await handle_party(ws, {"args": ""}, game=game)

        msg = ws.send_json.call_args[0][0]
        assert msg["type"] == "party_status"
        assert msg["pending_invite"] is True
        assert msg["from_player"] == "Alice"


# ---------------------------------------------------------------------------
# Unknown subcommand test
# ---------------------------------------------------------------------------

class TestUnknownSubcommand:
    async def test_unknown_subcommand_not_in_party(self):
        """Unknown subcommand when not in a party returns 'not in a party'."""
        game = _make_game()
        ws = _make_ws()
        game.connection_manager.get_entity_id.return_value = "player_1"
        _register_player(game, "player_1", "Alice")

        await handle_party(ws, {"args": "bogus"}, game=game)

        ws.send_json.assert_called_with(
            {
                "type": "error",
                "detail": "You are not in a party",
            }
        )


# ---------------------------------------------------------------------------
# Timeout test
# ---------------------------------------------------------------------------

class TestInviteTimeout:
    async def test_invite_timeout_cleans_up(self):
        """Verify the timeout callback cleans up invite state."""
        game = _make_game()
        _register_player(game, "player_1", "Alice")
        _register_player(game, "player_2", "Bob")

        game.party_manager._pending_invites["player_2"] = "player_1"
        game.party_manager._outgoing_invites["player_1"] = "player_2"

        # Simulate timeout callback directly
        game.party_manager.handle_invite_timeout("player_2")

        assert "player_2" not in game.party_manager._pending_invites
        assert "player_1" not in game.party_manager._outgoing_invites
        assert game.party_manager.check_cooldown("player_1", "player_2")


# ---------------------------------------------------------------------------
# Disconnect cleanup test
# ---------------------------------------------------------------------------

class TestDisconnectCleanup:
    def test_cleanup_as_target(self):
        game = _make_game()
        game.party_manager._pending_invites["player_2"] = "player_1"
        game.party_manager._outgoing_invites["player_1"] = "player_2"

        game.party_manager.cleanup_invites("player_2")

        assert "player_2" not in game.party_manager._pending_invites
        assert "player_1" not in game.party_manager._outgoing_invites

    def test_cleanup_as_inviter(self):
        game = _make_game()
        game.party_manager._pending_invites["player_2"] = "player_1"
        game.party_manager._outgoing_invites["player_1"] = "player_2"

        game.party_manager.cleanup_invites("player_1")

        assert "player_2" not in game.party_manager._pending_invites
        assert "player_1" not in game.party_manager._outgoing_invites

    def test_cleanup_no_invites(self):
        """Should not raise if player has no invites."""
        game = _make_game()
        game.party_manager.cleanup_invites("player_99")


# ---------------------------------------------------------------------------
# Help category test
# ---------------------------------------------------------------------------

class TestHelpCategory:
    async def test_party_in_social_category(self):
        from server.net.handlers.query import handle_help_actions

        game = _make_game()
        ws = _make_ws()
        game.connection_manager.get_entity_id.return_value = "player_1"
        _register_player(game, "player_1", "Alice")

        await handle_help_actions(ws, {}, game=game)

        msg = ws.send_json.call_args[0][0]
        assert msg["type"] == "help_result"
        assert "party" in msg["categories"]["Social"]
        assert "trade" in msg["categories"]["Social"]


# ---------------------------------------------------------------------------
# Not logged in tests
# ---------------------------------------------------------------------------

class TestNotLoggedIn:
    async def test_not_logged_in_no_entity(self):
        game = _make_game()
        ws = _make_ws()
        game.connection_manager.get_entity_id.return_value = None

        await handle_party(ws, {"args": "invite @Bob"}, game=game)

        ws.send_json.assert_called_with(
            {"type": "error", "code": "AUTH_REQUIRED", "detail": "Not logged in"}
        )

    async def test_not_logged_in_no_player_info(self):
        game = _make_game()
        ws = _make_ws()
        game.connection_manager.get_entity_id.return_value = "player_1"
        # Don't register player — player_manager is empty

        await handle_party(ws, {"args": "invite @Bob"}, game=game)

        ws.send_json.assert_called_with(
            {"type": "error", "code": "AUTH_REQUIRED", "detail": "Not logged in"}
        )
