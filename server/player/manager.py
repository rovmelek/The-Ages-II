"""PlayerManager — centralized player session lifecycle management."""
from __future__ import annotations

from typing import Iterator

from server.player.session import PlayerSession


class PlayerManager:
    """Manages player session lifecycle: create, lookup, remove, iterate."""

    def __init__(self) -> None:
        self._sessions: dict[str, PlayerSession] = {}

    def get_session(self, entity_id: str) -> PlayerSession | None:
        """Look up a player session by entity ID."""
        return self._sessions.get(entity_id)

    def set_session(self, entity_id: str, session: PlayerSession) -> None:
        """Register a player session."""
        self._sessions[entity_id] = session

    def remove_session(self, entity_id: str) -> PlayerSession | None:
        """Remove and return a player session, or None if not found."""
        return self._sessions.pop(entity_id, None)

    def has_session(self, entity_id: str) -> bool:
        """Check whether a player session exists."""
        return entity_id in self._sessions

    def all_entity_ids(self) -> list[str]:
        """Return a snapshot list of all entity IDs (safe to iterate during mutation)."""
        return list(self._sessions.keys())

    def all_sessions(self) -> Iterator[tuple[str, PlayerSession]]:
        """Iterate over all (entity_id, session) pairs."""
        return iter(self._sessions.items())

    def clear(self) -> None:
        """Remove all sessions."""
        self._sessions.clear()
