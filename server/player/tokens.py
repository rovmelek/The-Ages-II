"""Session token generation and validation."""
from __future__ import annotations

import secrets
import time

from server.core.config import settings


def generate_session_token() -> str:
    """Generate a cryptographically random session token."""
    return secrets.token_urlsafe(32)


class TokenStore:
    """In-memory token-to-player mapping with expiry."""

    def __init__(self) -> None:
        self._tokens: dict[str, tuple[int, float]] = {}  # token -> (db_id, expires_at)

    def issue(self, db_id: int) -> str:
        """Issue a new token for a player DB ID. Invalidates any previous token."""
        self._purge_expired()
        # Revoke existing tokens for this db_id
        self._tokens = {
            t: v for t, v in self._tokens.items() if v[0] != db_id
        }
        token = generate_session_token()
        expires_at = time.time() + settings.SESSION_TOKEN_TTL_SECONDS
        self._tokens[token] = (db_id, expires_at)
        return token

    def validate(self, token: str) -> int | None:
        """Return db_id if token is valid and not expired, else None."""
        entry = self._tokens.get(token)
        if entry is None:
            return None
        db_id, expires_at = entry
        if time.time() > expires_at:
            self._tokens.pop(token, None)
            return None
        return db_id

    def revoke(self, token: str) -> None:
        """Revoke a specific token."""
        self._tokens.pop(token, None)

    def revoke_for_player(self, db_id: int) -> None:
        """Revoke all tokens for a player."""
        self._tokens = {
            t: v for t, v in self._tokens.items() if v[0] != db_id
        }

    def _purge_expired(self) -> None:
        """Remove all expired tokens from the store."""
        now = time.time()
        self._tokens = {t: v for t, v in self._tokens.items() if v[1] > now}
