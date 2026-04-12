"""Tests for PartyManager — party infrastructure (Story 12.3)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.party.manager import Party, PartyManager


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
# PartyManager unit tests
# ---------------------------------------------------------------------------


class TestPartyManagerCreation:
    """PartyManager starts with empty state."""

    def test_empty_state(self):
        pm = PartyManager()
        assert pm._parties == {}
        assert pm._player_party == {}

    def test_get_party_returns_none_for_unknown(self):
        pm = PartyManager()
        assert pm.get_party("player_1") is None

    def test_is_in_party_false_for_unknown(self):
        pm = PartyManager()
        assert pm.is_in_party("player_1") is False

    def test_is_leader_false_for_unknown(self):
        pm = PartyManager()
        assert pm.is_leader("player_1") is False

    def test_get_party_members_empty_for_unknown(self):
        pm = PartyManager()
        assert pm.get_party_members("player_1") == []


class TestCreateParty:
    """create_party forms a party with two members."""

    def test_success(self):
        pm = PartyManager()
        result = pm.create_party("player_1", "player_2")
        assert isinstance(result, Party)
        assert result.leader == "player_1"
        assert result.members == ["player_1", "player_2"]
        assert "player_1" in pm._player_party
        assert "player_2" in pm._player_party

    def test_leader_already_in_party(self):
        pm = PartyManager()
        pm.create_party("player_1", "player_2")
        result = pm.create_party("player_1", "player_3")
        assert isinstance(result, str)
        assert "already in a party" in result

    def test_member_already_in_party(self):
        pm = PartyManager()
        pm.create_party("player_1", "player_2")
        result = pm.create_party("player_3", "player_2")
        assert isinstance(result, str)
        assert "already in a party" in result

    def test_created_at_set(self):
        pm = PartyManager()
        party = pm.create_party("player_1", "player_2")
        assert party.created_at > 0


class TestGetParty:
    """get_party returns Party for members, None for non-members."""

    def test_returns_party_for_leader(self):
        pm = PartyManager()
        party = pm.create_party("player_1", "player_2")
        assert pm.get_party("player_1") is party

    def test_returns_party_for_member(self):
        pm = PartyManager()
        party = pm.create_party("player_1", "player_2")
        assert pm.get_party("player_2") is party

    def test_returns_none_for_non_member(self):
        pm = PartyManager()
        pm.create_party("player_1", "player_2")
        assert pm.get_party("player_3") is None


class TestIsInParty:
    """is_in_party returns correct boolean."""

    def test_true_for_members(self):
        pm = PartyManager()
        pm.create_party("player_1", "player_2")
        assert pm.is_in_party("player_1") is True
        assert pm.is_in_party("player_2") is True

    def test_false_for_non_members(self):
        pm = PartyManager()
        pm.create_party("player_1", "player_2")
        assert pm.is_in_party("player_3") is False


class TestIsLeader:
    """is_leader returns correct boolean."""

    def test_true_for_leader(self):
        pm = PartyManager()
        pm.create_party("player_1", "player_2")
        assert pm.is_leader("player_1") is True

    def test_false_for_non_leader_member(self):
        pm = PartyManager()
        pm.create_party("player_1", "player_2")
        assert pm.is_leader("player_2") is False

    def test_false_for_non_member(self):
        pm = PartyManager()
        assert pm.is_leader("player_1") is False


class TestGetPartyMembers:
    """get_party_members returns ordered list or empty."""

    def test_returns_ordered_list(self):
        pm = PartyManager()
        pm.create_party("player_1", "player_2")
        assert pm.get_party_members("player_1") == ["player_1", "player_2"]

    def test_returns_copy(self):
        pm = PartyManager()
        party = pm.create_party("player_1", "player_2")
        members = pm.get_party_members("player_1")
        members.append("player_99")
        assert "player_99" not in party.members

    def test_returns_empty_for_non_member(self):
        pm = PartyManager()
        assert pm.get_party_members("player_1") == []


class TestAddMember:
    """add_member appends to existing party."""

    def test_success(self):
        pm = PartyManager()
        party = pm.create_party("player_1", "player_2")
        result = pm.add_member(party.party_id, "player_3")
        assert isinstance(result, Party)
        assert result.members == ["player_1", "player_2", "player_3"]
        assert pm._player_party["player_3"] == party.party_id

    def test_appends_to_end(self):
        pm = PartyManager()
        party = pm.create_party("player_1", "player_2")
        pm.add_member(party.party_id, "player_3")
        pm.add_member(party.party_id, "player_4")
        assert party.members == ["player_1", "player_2", "player_3", "player_4"]

    @patch("server.party.manager.settings")
    def test_party_full(self, mock_settings):
        mock_settings.MAX_PARTY_SIZE = 2
        pm = PartyManager()
        party = pm.create_party("player_1", "player_2")
        result = pm.add_member(party.party_id, "player_3")
        assert isinstance(result, str)
        assert "full" in result.lower()

    def test_player_already_in_party(self):
        pm = PartyManager()
        party_a = pm.create_party("player_1", "player_2")
        pm.create_party("player_3", "player_4")
        result = pm.add_member(party_a.party_id, "player_3")
        assert isinstance(result, str)
        assert "already in a party" in result

    def test_party_not_found(self):
        pm = PartyManager()
        result = pm.add_member("nonexistent-id", "player_1")
        assert isinstance(result, str)
        assert "not found" in result.lower()


class TestRemoveMember:
    """remove_member handles non-leader, leader succession, and dissolution."""

    def test_remove_non_leader(self):
        pm = PartyManager()
        pm.create_party("player_1", "player_2")
        party, new_leader = pm.remove_member("player_2")
        assert party is not None
        assert party.members == ["player_1"]
        assert party.leader == "player_1"
        assert new_leader is None
        assert "player_2" not in pm._player_party

    def test_remove_leader_succession(self):
        pm = PartyManager()
        pm.create_party("player_1", "player_2")
        party, new_leader = pm.remove_member("player_1")
        assert party is not None
        assert party.leader == "player_2"
        assert new_leader == "player_2"
        assert party.members == ["player_2"]
        assert "player_1" not in pm._player_party

    def test_remove_last_member_dissolves(self):
        pm = PartyManager()
        party = pm.create_party("player_1", "player_2")
        party_id = party.party_id
        pm.remove_member("player_2")
        result_party, new_leader = pm.remove_member("player_1")
        assert result_party is None
        assert new_leader is None
        assert party_id not in pm._parties
        assert "player_1" not in pm._player_party

    def test_remove_non_member_returns_none(self):
        pm = PartyManager()
        party, new_leader = pm.remove_member("player_99")
        assert party is None
        assert new_leader is None

    def test_leader_succession_three_members(self):
        pm = PartyManager()
        party = pm.create_party("player_1", "player_2")
        pm.add_member(party.party_id, "player_3")
        assert party.members == ["player_1", "player_2", "player_3"]

        # Remove leader — player_2 (next in order) promoted
        result_party, new_leader = pm.remove_member("player_1")
        assert result_party is not None
        assert result_party.leader == "player_2"
        assert new_leader == "player_2"
        assert result_party.members == ["player_2", "player_3"]

    def test_leader_succession_four_members(self):
        pm = PartyManager()
        party = pm.create_party("player_1", "player_2")
        pm.add_member(party.party_id, "player_3")
        pm.add_member(party.party_id, "player_4")

        # Remove leader — player_2 promoted
        result_party, new_leader = pm.remove_member("player_1")
        assert result_party.leader == "player_2"
        assert new_leader == "player_2"
        assert result_party.members == ["player_2", "player_3", "player_4"]


class TestDisband:
    """disband dissolves the party and returns members."""

    def test_disband_returns_members(self):
        pm = PartyManager()
        party = pm.create_party("player_1", "player_2")
        members = pm.disband(party.party_id)
        assert set(members) == {"player_1", "player_2"}
        assert "player_1" not in pm._player_party
        assert "player_2" not in pm._player_party
        assert party.party_id not in pm._parties

    def test_disband_nonexistent(self):
        pm = PartyManager()
        result = pm.disband("nonexistent-id")
        assert result == []

    def test_disband_three_members(self):
        pm = PartyManager()
        party = pm.create_party("player_1", "player_2")
        pm.add_member(party.party_id, "player_3")
        members = pm.disband(party.party_id)
        assert len(members) == 3
        assert pm._player_party == {}


class TestHandleDisconnect:
    """handle_disconnect delegates to remove_member."""

    def test_delegates_to_remove_member(self):
        pm = PartyManager()
        pm.create_party("player_1", "player_2")
        party, new_leader = pm.handle_disconnect("player_2")
        assert party is not None
        assert party.members == ["player_1"]
        assert new_leader is None

    def test_leader_disconnect_succession(self):
        pm = PartyManager()
        pm.create_party("player_1", "player_2")
        party, new_leader = pm.handle_disconnect("player_1")
        assert party is not None
        assert new_leader == "player_2"
        assert party.leader == "player_2"

    def test_non_member_disconnect(self):
        pm = PartyManager()
        party, new_leader = pm.handle_disconnect("player_99")
        assert party is None
        assert new_leader is None


# ---------------------------------------------------------------------------
# Integration test: party cleanup in PlayerManager.cleanup_session
# ---------------------------------------------------------------------------


class TestCleanupPlayerPartyIntegration:
    """Party cleanup is called during cleanup_session and notifies members."""

    @pytest.fixture
    def game_with_party(self):
        """Create a Game-like object with party members."""
        from server.party.manager import PartyManager
        from server.trade.manager import TradeManager

        game = MagicMock()
        game.party_manager = PartyManager()
        game.trade_manager = TradeManager()
        game.combat_manager = MagicMock()
        game.combat_manager.get_player_instance.return_value = None
        game.connection_manager = MagicMock()
        game.connection_manager.send_to_player = AsyncMock()
        game.connection_manager.broadcast_to_room = AsyncMock()
        game.connection_manager.disconnect = MagicMock()
        game.room_manager = MagicMock()

        # Mock session factory (sync callable returning async context manager)
        mock_session = AsyncMock()
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        game.transaction = MagicMock(return_value=mock_ctx)

        # Set up player entities
        entity_1 = MagicMock()
        entity_1.player_db_id = 1
        entity_1.x = 5
        entity_1.y = 5
        entity_1.stats = {"hp": 100, "max_hp": 100}
        entity_1.in_combat = False

        entity_2 = MagicMock()
        entity_2.player_db_id = 2
        entity_2.x = 6
        entity_2.y = 6
        entity_2.stats = {"hp": 100, "max_hp": 100}
        entity_2.in_combat = False

        game.player_manager = PlayerManager()
        game.player_manager.set_session("player_1", _ps({
            "entity": entity_1,
            "room_key": "town_square",
            "inventory": None,
        }))
        game.player_manager.set_session("player_2", _ps({
            "entity": entity_2,
            "room_key": "town_square",
            "inventory": None,
        }))

        # Create a party
        game.party_manager.create_party("player_1", "player_2")

        return game

    @pytest.mark.asyncio
    async def test_cleanup_notifies_remaining_members(self, game_with_party):
        game = game_with_party

        # Disconnect player_2 (non-leader)
        await game.player_manager.cleanup_session("player_2", game)

        # player_1 should receive party_update
        calls = game.connection_manager.send_to_player.call_args_list
        party_updates = [
            c for c in calls if c[0][1].get("type") == "party_update"
        ]
        assert len(party_updates) == 1
        msg = party_updates[0][0][1]
        assert msg["action"] == "member_left"
        assert msg["entity_id"] == "player_2"
        assert msg["members"] == ["player_1"]
        assert msg["leader"] == "player_1"
        assert "new_leader" not in msg

    @pytest.mark.asyncio
    async def test_cleanup_leader_disconnect_notifies_with_new_leader(self, game_with_party):
        game = game_with_party

        # Disconnect player_1 (leader)
        await game.player_manager.cleanup_session("player_1", game)

        # player_2 should receive party_update with new_leader
        calls = game.connection_manager.send_to_player.call_args_list
        party_updates = [
            c for c in calls if c[0][1].get("type") == "party_update"
        ]
        assert len(party_updates) == 1
        msg = party_updates[0][0][1]
        assert msg["action"] == "member_left"
        assert msg["new_leader"] == "player_2"
        assert msg["leader"] == "player_2"

    @pytest.mark.asyncio
    async def test_cleanup_last_member_no_notification(self, game_with_party):
        game = game_with_party

        # Remove player_2 first
        game.party_manager.remove_member("player_2")

        # Now disconnect player_1 (last member)
        await game.player_manager.cleanup_session("player_1", game)

        # No party_update should be sent (party dissolved, no members to notify)
        calls = game.connection_manager.send_to_player.call_args_list
        party_updates = [
            c for c in calls if c[0][1].get("type") == "party_update"
        ]
        assert len(party_updates) == 0


class TestMaxPartySizeConfig:
    """MAX_PARTY_SIZE config is accessible."""

    def test_default_value(self):
        from server.core.config import settings
        assert settings.MAX_PARTY_SIZE == 4
