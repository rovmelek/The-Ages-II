"""Effect registry — maps effect_type strings to async handler functions."""
from __future__ import annotations

from typing import Any, Callable, Coroutine

from server.core.constants import EffectType


EffectHandler = Callable[
    [dict, dict, dict, dict],
    Coroutine[Any, Any, dict],
]


class EffectRegistry:
    """Central registry for effect resolution handlers."""

    def __init__(self) -> None:
        self._handlers: dict[str, EffectHandler] = {}

    def register(self, effect_type: str, handler: EffectHandler) -> None:
        """Register a handler for the given effect type."""
        self._handlers[effect_type] = handler

    async def resolve(
        self,
        effect: dict,
        source: dict,
        target: dict,
        context: dict | None = None,
    ) -> dict:
        """Resolve an effect using the registered handler.

        Raises ValueError if no handler is registered for the effect type.
        """
        effect_type = effect.get("type", "")
        handler = self._handlers.get(effect_type)
        if handler is None:
            raise ValueError(f"No handler registered for effect type: {effect_type!r}")
        return await handler(effect, source, target, context or {})


def create_default_registry() -> EffectRegistry:
    """Create an EffectRegistry with all built-in handlers registered."""
    from server.core.effects.damage import handle_damage
    from server.core.effects.dot import handle_dot
    from server.core.effects.draw import handle_draw
    from server.core.effects.heal import handle_heal
    from server.core.effects.restore_energy import handle_restore_energy
    from server.core.effects.shield import handle_shield

    registry = EffectRegistry()
    registry.register(EffectType.DAMAGE, handle_damage)
    registry.register(EffectType.HEAL, handle_heal)
    registry.register(EffectType.SHIELD, handle_shield)
    registry.register(EffectType.DOT, handle_dot)
    registry.register(EffectType.DRAW, handle_draw)
    registry.register(EffectType.RESTORE_ENERGY, handle_restore_energy)
    return registry
