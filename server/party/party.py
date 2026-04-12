"""Party group dataclass."""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class Party:
    """Represents an active party group."""

    party_id: str
    leader: str  # entity_id of party leader
    members: list[str] = field(default_factory=list)  # entity_ids, ordered by join time
    created_at: float = field(default_factory=time.time)
