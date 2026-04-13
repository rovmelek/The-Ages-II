"""Trade session dataclass."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import StrEnum


class TradeState(StrEnum):
    """Trade session state machine states."""

    REQUEST_PENDING = "request_pending"
    NEGOTIATING = "negotiating"
    ONE_READY = "one_ready"
    BOTH_READY = "both_ready"
    EXECUTING = "executing"
    CANCELLED = "cancelled"
    COMPLETE = "complete"


@dataclass
class Trade:
    """Represents an active trade session between two players."""

    trade_id: str
    player_a: str  # entity_id of initiator
    player_b: str  # entity_id of target
    state: TradeState
    offers_a: dict[str, int] = field(default_factory=dict)  # item_key -> qty
    offers_b: dict[str, int] = field(default_factory=dict)
    ready_a: bool = False
    ready_b: bool = False
    created_at: float = field(default_factory=time.time)
    timeout_handle: asyncio.TimerHandle | None = None
