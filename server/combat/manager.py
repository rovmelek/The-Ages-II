"""CombatManager — tracks active combat instances."""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from server.combat.instance import CombatInstance

if TYPE_CHECKING:
    from server.core.effects.registry import EffectRegistry


class CombatManager:
    """Manages all active combat instances and player-to-instance mappings."""

    def __init__(self, effect_registry: EffectRegistry | None = None) -> None:
        self._instances: dict[str, CombatInstance] = {}
        self._player_to_instance: dict[str, str] = {}  # entity_id -> instance_id
        self._effect_registry = effect_registry

    def create_instance(
        self,
        mob_name: str,
        mob_stats: dict,
        npc_id: str | None = None,
        room_key: str | None = None,
    ) -> CombatInstance:
        """Create a new combat instance and register it."""
        instance_id = str(uuid.uuid4())
        instance = CombatInstance(
            instance_id=instance_id,
            mob_name=mob_name,
            mob_stats=mob_stats,
            effect_registry=self._effect_registry,
            npc_id=npc_id,
            room_key=room_key,
        )
        self._instances[instance_id] = instance
        return instance

    def add_player_to_instance(self, entity_id: str, instance_id: str) -> None:
        """Register a player-to-instance mapping."""
        self._player_to_instance[entity_id] = instance_id

    def get_instance(self, instance_id: str) -> CombatInstance | None:
        """Get a combat instance by ID."""
        return self._instances.get(instance_id)

    def get_player_instance(self, entity_id: str) -> CombatInstance | None:
        """Get the combat instance a player is in."""
        instance_id = self._player_to_instance.get(entity_id)
        if instance_id is None:
            return None
        return self._instances.get(instance_id)

    def remove_player(self, entity_id: str) -> None:
        """Remove a player's instance mapping."""
        self._player_to_instance.pop(entity_id, None)

    def remove_instance(self, instance_id: str) -> None:
        """Remove a combat instance and all player mappings."""
        instance = self._instances.pop(instance_id, None)
        if instance:
            for eid in list(instance.participants):
                self._player_to_instance.pop(eid, None)
