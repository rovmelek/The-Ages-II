"""EventBus — simple async pub-sub for global announcements and triggers."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, Coroutine


class EventBus:
    """Async publish-subscribe event bus."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[..., Coroutine[Any, Any, None]]]] = defaultdict(list)

    def subscribe(self, event_type: str, callback: Callable[..., Coroutine[Any, Any, None]]) -> None:
        """Register *callback* for *event_type*."""
        self._subscribers[event_type].append(callback)

    async def emit(self, event_type: str, **data: Any) -> None:
        """Call all subscribers for *event_type* with keyword data."""
        for cb in self._subscribers.get(event_type, []):
            await cb(**data)
