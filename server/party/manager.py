"""PartyManager — manages in-memory party groups with leader/member tracking."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid

from server.core.config import settings
from server.net.connection_manager import ConnectionManager
from server.party.party import Party

logger = logging.getLogger(__name__)


class PartyManager:
    """Manages active party groups (ephemeral, in-memory only)."""

    def __init__(self, *, connection_manager: ConnectionManager | None = None) -> None:
        self._parties: dict[str, Party] = {}  # party_id -> Party
        self._player_party: dict[str, str] = {}  # entity_id -> party_id
        # Invite tracking (moved from party.py handler)
        self._pending_invites: dict[str, str] = {}  # target_entity_id -> inviter_entity_id
        self._outgoing_invites: dict[str, str] = {}  # inviter_entity_id -> target_entity_id
        self._invite_timeouts: dict[str, asyncio.TimerHandle] = {}  # target_entity_id -> handle
        self._invite_cooldowns: dict[str, dict[str, float]] = {}  # inviter_id -> {target_id -> end_ts}
        self._invite_names: dict[str, str] = {}  # target_id -> target_name (for timeout callback)
        self._connection_manager = connection_manager

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

    # ------------------------------------------------------------------
    # Invite tracking
    # ------------------------------------------------------------------

    def cancel_invite(self, target_id: str) -> str | None:
        """Cancel a pending invite for a target. Returns the inviter_id or None."""
        inviter_id = self._pending_invites.pop(target_id, None)
        if inviter_id is not None:
            self._outgoing_invites.pop(inviter_id, None)
        handle = self._invite_timeouts.pop(target_id, None)
        if handle is not None:
            handle.cancel()
        self._invite_names.pop(target_id, None)
        return inviter_id

    def set_cooldown(self, inviter_id: str, target_id: str) -> None:
        """Set a per-target invite cooldown for an inviter."""
        if inviter_id not in self._invite_cooldowns:
            self._invite_cooldowns[inviter_id] = {}
        self._invite_cooldowns[inviter_id][target_id] = time.time() + settings.PARTY_INVITE_COOLDOWN_SECONDS

    def check_cooldown(self, inviter_id: str, target_id: str) -> bool:
        """Return True if inviter is in cooldown for this target."""
        cds = self._invite_cooldowns.get(inviter_id)
        if cds is None:
            return False
        end = cds.get(target_id)
        if end is None:
            return False
        return time.time() < end

    def has_pending_invite(self, target_id: str) -> bool:
        """Check if a target has a pending invite."""
        return target_id in self._pending_invites

    def get_pending_invite(self, target_id: str) -> str | None:
        """Get the inviter_id for a pending invite, or None."""
        return self._pending_invites.get(target_id)

    def get_outgoing_invite(self, entity_id: str) -> str | None:
        """Get the target_id for an outgoing invite, or None."""
        return self._outgoing_invites.get(entity_id)

    def create_invite(self, inviter_id: str, target_id: str, target_name: str) -> None:
        """Store an invite, schedule timeout, and store display name."""
        self._pending_invites[target_id] = inviter_id
        self._outgoing_invites[inviter_id] = target_id
        self._invite_names[target_id] = target_name

        loop = asyncio.get_running_loop()
        self._invite_timeouts[target_id] = loop.call_later(
            settings.PARTY_INVITE_TIMEOUT_SECONDS,
            self.handle_invite_timeout,
            target_id,
        )

    def handle_invite_timeout(self, target_id: str) -> None:
        """Handle invite timeout (sync callback from event loop timer)."""
        inviter_id = self._pending_invites.pop(target_id, None)
        if inviter_id is None:
            return
        self._outgoing_invites.pop(inviter_id, None)
        self._invite_timeouts.pop(target_id, None)
        target_name = self._invite_names.pop(target_id, target_id)

        self.set_cooldown(inviter_id, target_id)

        cm = self._connection_manager
        if cm is not None:
            loop = asyncio.get_running_loop()
            msg_inviter = {
                "type": "party_invite_response",
                "status": "expired",
                "target": target_name,
            }
            msg_target = {
                "type": "party_invite_response",
                "status": "expired",
            }
            loop.create_task(cm.send_to_player(inviter_id, msg_inviter))
            loop.create_task(cm.send_to_player(target_id, msg_target))

    def cleanup_invites(self, entity_id: str) -> None:
        """Clean up all pending invites involving this entity (as inviter or target)."""
        # As target
        self.cancel_invite(entity_id)
        # As inviter
        target_id = self._outgoing_invites.pop(entity_id, None)
        if target_id is not None:
            self._pending_invites.pop(target_id, None)
            handle = self._invite_timeouts.pop(target_id, None)
            if handle is not None:
                handle.cancel()
            self._invite_names.pop(target_id, None)

    def handle_disconnect(self, entity_id: str) -> tuple[Party | None, str | None]:
        """Handle player disconnect — delegates to remove_member."""
        return self.remove_member(entity_id)
