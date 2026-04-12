"""PartyManager — manages in-memory party groups with leader/member tracking."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from server.core.config import settings


@dataclass
class Party:
    """Represents an active party group."""

    party_id: str
    leader: str  # entity_id of party leader
    members: list[str] = field(default_factory=list)  # entity_ids, ordered by join time
    created_at: float = field(default_factory=time.time)


class PartyManager:
    """Manages active party groups (ephemeral, in-memory only)."""

    def __init__(self) -> None:
        self._parties: dict[str, Party] = {}  # party_id -> Party
        self._player_party: dict[str, str] = {}  # entity_id -> party_id

    def create_party(self, leader_id: str, member_id: str) -> Party | str:
        """Create a new party with leader and first member. Returns Party or error."""
        if leader_id in self._player_party:
            return "You are already in a party"
        if member_id in self._player_party:
            return "Player is already in a party"

        party_id = str(uuid.uuid4())
        party = Party(
            party_id=party_id,
            leader=leader_id,
            members=[leader_id, member_id],
        )
        self._parties[party_id] = party
        self._player_party[leader_id] = party_id
        self._player_party[member_id] = party_id
        return party

    def add_member(self, party_id: str, entity_id: str) -> Party | str:
        """Add a member to an existing party. Returns Party or error."""
        party = self._parties.get(party_id)
        if party is None:
            return "Party not found"
        if entity_id in self._player_party:
            return "Player is already in a party"
        if len(party.members) >= settings.MAX_PARTY_SIZE:
            return "Party is full"

        party.members.append(entity_id)
        self._player_party[entity_id] = party_id
        return party

    def remove_member(self, entity_id: str) -> tuple[Party | None, str | None]:
        """Remove a member from their party. Handles leader succession and dissolution.

        Returns (party_or_none, new_leader_id_or_none):
        - (party, new_leader_id) if leader left and succession occurred
        - (party, None) if non-leader left
        - (None, None) if party was dissolved (last member left)
        """
        party_id = self._player_party.pop(entity_id, None)
        if party_id is None:
            return None, None

        party = self._parties.get(party_id)
        if party is None:
            return None, None

        was_leader = party.leader == entity_id
        party.members.remove(entity_id)

        if not party.members:
            # Last member left — dissolve party
            self._parties.pop(party_id, None)
            return None, None

        new_leader_id = None
        if was_leader:
            # Promote longest-standing member (first in list)
            new_leader_id = party.members[0]
            party.leader = new_leader_id

        return party, new_leader_id

    def disband(self, party_id: str) -> list[str]:
        """Dissolve a party. Returns list of member entity_ids that were in the party."""
        party = self._parties.pop(party_id, None)
        if party is None:
            return []

        members = list(party.members)
        for mid in members:
            self._player_party.pop(mid, None)
        return members

    def get_party(self, entity_id: str) -> Party | None:
        """Get the party for a player, or None."""
        party_id = self._player_party.get(entity_id)
        if party_id is None:
            return None
        return self._parties.get(party_id)

    def is_in_party(self, entity_id: str) -> bool:
        """Check if a player is in any party."""
        return entity_id in self._player_party

    def is_leader(self, entity_id: str) -> bool:
        """Check if a player is the leader of their party."""
        party = self.get_party(entity_id)
        if party is None:
            return False
        return party.leader == entity_id

    def get_party_members(self, entity_id: str) -> list[str]:
        """Get member entity_ids for a player's party, or empty list."""
        party = self.get_party(entity_id)
        if party is None:
            return []
        return list(party.members)

    def handle_disconnect(self, entity_id: str) -> tuple[Party | None, str | None]:
        """Handle player disconnect — delegates to remove_member."""
        return self.remove_member(entity_id)
