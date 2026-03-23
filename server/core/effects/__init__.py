"""Shared effect registry — resolves card and item effects consistently."""
from server.core.effects.registry import EffectRegistry, create_default_registry

__all__ = ["EffectRegistry", "create_default_registry"]
