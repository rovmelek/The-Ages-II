"""CombatInstance — manages a single turn-based combat encounter."""
from __future__ import annotations

import asyncio
import math
import random
import time
import uuid
from typing import TYPE_CHECKING, Callable

from server.combat.cards.card_def import CardDef
from server.core.constants import EffectType
from server.combat.cards.card_hand import CardHand
from server.core.config import settings


def compute_energy_regen(stats: dict) -> int:
    """Compute energy regen per combat cycle from INT+WIS (ADR-18-5)."""
    return math.floor(
        settings.BASE_COMBAT_ENERGY_REGEN
        + (stats.get("intelligence", 0) + stats.get("wisdom", 0))
        * settings.COMBAT_ENERGY_REGEN_FACTOR
    )

if TYPE_CHECKING:
    from server.core.effects.registry import EffectRegistry


class CombatInstance:
    """A single combat encounter between players and a mob."""

    def __init__(
        self,
        instance_id: str | None = None,
        mob_name: str = "",
        mob_stats: dict | None = None,
        effect_registry: EffectRegistry | None = None,
        npc_id: str | None = None,
        room_key: str | None = None,
        mob_hit_dice: int = 0,
    ) -> None:
        self.instance_id = instance_id or str(uuid.uuid4())
        self.mob_name = mob_name
        self.mob_stats: dict = dict(mob_stats) if mob_stats else {
            "hp": settings.DEFAULT_BASE_HP,
            "max_hp": settings.DEFAULT_BASE_HP,
            "attack": settings.DEFAULT_ATTACK,
        }
        self.npc_id = npc_id
        self.room_key = room_key
        self.mob_hit_dice = mob_hit_dice
        self.participants: list[str] = []  # entity_ids in turn order
        self.participant_stats: dict[str, dict] = {}  # entity_id -> stats dict
        self.hands: dict[str, CardHand] = {}  # entity_id -> CardHand
        self._turn_index: int = 0
        self._actions_this_cycle: int = 0
        self._effect_registry = effect_registry
        self._turn_timeout_handle: asyncio.TimerHandle | None = None
        self._turn_timeout_callback: Callable | None = None
        self._turn_timeout_at: float | None = None

    def add_participant(
        self, entity_id: str, player_stats: dict, card_defs: list[CardDef]
    ) -> CardHand:
        """Add a player to this combat. Returns their CardHand."""
        self.participants.append(entity_id)
        self.participant_stats[entity_id] = dict(player_stats)
        self.participant_stats[entity_id].setdefault("shield", 0)
        hand = CardHand(card_defs)
        self.hands[entity_id] = hand
        return hand

    def set_turn_timeout_callback(self, callback: Callable) -> None:
        """Set the callback invoked when a turn times out. Called once by Game setup."""
        self._turn_timeout_callback = callback

    def start_turn_timer(self) -> None:
        """Activate turn timeout for the current turn. Call AFTER set_turn_timeout_callback."""
        self._schedule_turn_timeout()

    def _schedule_turn_timeout(self) -> None:
        """Schedule auto-pass for the current turn."""
        self._cancel_turn_timeout()
        if not self.participants or self._turn_timeout_callback is None:
            return
        current = self.get_current_turn()
        if current is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # No event loop (e.g., tests without async context)
        timeout = settings.COMBAT_TURN_TIMEOUT_SECONDS
        self._turn_timeout_at = time.time() + timeout
        self._turn_timeout_handle = loop.call_later(
            timeout, self._turn_timeout_callback, current, self,
        )

    def _cancel_turn_timeout(self) -> None:
        """Cancel any pending turn timeout."""
        if self._turn_timeout_handle is not None:
            self._turn_timeout_handle.cancel()
            self._turn_timeout_handle = None
        self._turn_timeout_at = None

    def remove_participant(self, entity_id: str) -> None:
        """Remove a player from combat (e.g. flee)."""
        self._cancel_turn_timeout()
        if entity_id in self.participants:
            idx = self.participants.index(entity_id)
            self.participants.remove(entity_id)
            self.participant_stats.pop(entity_id, None)
            self.hands.pop(entity_id, None)
            # Adjust turn index: only decrement if removed before current turn
            if self.participants:
                if idx < self._turn_index:
                    self._turn_index -= 1
                # If idx == _turn_index, next person slides into this slot — no change
                self._turn_index = self._turn_index % len(self.participants)
            # Adjust cycle counter to match new participant count
            self._actions_this_cycle = min(self._actions_this_cycle, len(self.participants))

    def get_current_turn(self) -> str | None:
        """Return entity_id of the player whose turn it is."""
        if not self.participants:
            return None
        return self.participants[self._turn_index % len(self.participants)]

    def _resolve_effect_targets(
        self, entity_id: str, effect_type: str
    ) -> tuple[dict, dict]:
        """Return (source, target) stat dicts for an effect type.

        Self-targeting effects (heal, shield, draw) return (player, player).
        All others (damage, dot) return (player, mob).
        """
        player_stats = self.participant_stats[entity_id]
        if effect_type in (EffectType.HEAL, EffectType.SHIELD, EffectType.DRAW, EffectType.RESTORE_ENERGY):
            return player_stats, player_stats
        return player_stats, self.mob_stats

    async def resolve_card_effects(
        self, entity_id: str, card: CardDef
    ) -> list[dict]:
        """Resolve all effects on a played card through the EffectRegistry.

        Returns list of effect result dicts.
        """
        if self._effect_registry is None:
            return []

        results: list[dict] = []

        for effect in card.effects:
            effect_type = effect.get("type", "")
            source, target = self._resolve_effect_targets(entity_id, effect_type)

            result = await self._effect_registry.resolve(
                effect, source, target
            )
            results.append(result)

            # Handle draw effect: draw additional cards into hand
            if effect_type == EffectType.DRAW:
                hand = self.hands.get(entity_id)
                if hand:
                    draw_count = result.get("value", 1)
                    for _ in range(draw_count):
                        hand.draw_card()

        return results

    async def play_card(self, entity_id: str, card_key: str) -> dict:
        """Player plays a card. Validates turn, plays from hand, resolves effects, advances turn.

        Returns dict with card info, effect results, and any mob attack from cycle end.
        """
        self._cancel_turn_timeout()
        if entity_id != self.get_current_turn():
            self._schedule_turn_timeout()
            raise ValueError("Not your turn")
        if self.participant_stats[entity_id]["hp"] <= 0:
            self._schedule_turn_timeout()
            raise ValueError("You are dead")

        # Process DoT effects at start of turn
        dot_ticks = self._process_dot_effects(self.mob_stats, self.mob_name)
        dot_ticks += self._process_dot_effects(self.participant_stats[entity_id], entity_id)

        # If DoT killed the mob or this player, skip the action
        if self.is_finished:
            result: dict = {"action": "play_card", "entity_id": entity_id}
            if dot_ticks:
                result["dot_ticks"] = dot_ticks
            return result

        hand = self.hands[entity_id]
        stats = self.participant_stats[entity_id]

        # Check energy cost before playing (physical cards are free)
        card_def = hand.get_card_def(card_key)
        if card_def.card_type != "physical":
            card_cost = card_def.cost
            if stats.get("energy", 0) < card_cost:
                self._schedule_turn_timeout()
                raise ValueError("Not enough energy")

        played = hand.play_card(card_key)
        if card_def.card_type != "physical":
            stats["energy"] = max(0, stats.get("energy", 0) - card_def.cost)

        # Resolve card effects through EffectRegistry
        effect_results = await self.resolve_card_effects(entity_id, played)

        result = {
            "action": "play_card",
            "entity_id": entity_id,
            "card": played.to_dict(),
            "effect_results": effect_results,
        }

        if dot_ticks:
            result["dot_ticks"] = dot_ticks

        # Advance turn — may trigger mob attack at end of cycle
        mob_attack = self._advance_turn()
        if mob_attack:
            result["mob_attack"] = mob_attack

        return result

    async def use_item(self, entity_id: str, item_def) -> dict:
        """Player uses an item as their combat action. Validates turn, resolves effects, advances turn.

        Returns dict with item info, effect results, and any mob attack from cycle end.
        """
        self._cancel_turn_timeout()
        if entity_id != self.get_current_turn():
            self._schedule_turn_timeout()
            raise ValueError("Not your turn")
        if self.participant_stats[entity_id]["hp"] <= 0:
            self._schedule_turn_timeout()
            raise ValueError("You are dead")

        # Process DoT effects at start of turn
        dot_ticks = self._process_dot_effects(self.mob_stats, self.mob_name)
        dot_ticks += self._process_dot_effects(self.participant_stats[entity_id], entity_id)

        # If DoT killed the mob or this player, skip the action
        if self.is_finished:
            result: dict = {"action": "use_item", "entity_id": entity_id}
            if dot_ticks:
                result["dot_ticks"] = dot_ticks
            return result

        if self._effect_registry is None:
            effect_results: list[dict] = []
        else:
            effect_results = []
            for effect in item_def.effects:
                effect_type = effect.get("type", "")
                source, target = self._resolve_effect_targets(entity_id, effect_type)
                result = await self._effect_registry.resolve(effect, source, target)
                effect_results.append(result)

        result: dict = {
            "action": "use_item",
            "entity_id": entity_id,
            "item_key": item_def.item_key,
            "item_name": item_def.name,
            "effect_results": effect_results,
        }

        if dot_ticks:
            result["dot_ticks"] = dot_ticks

        # Advance turn — may trigger mob attack at end of cycle
        mob_attack = self._advance_turn()
        if mob_attack:
            result["mob_attack"] = mob_attack

        return result

    async def pass_turn(self, entity_id: str) -> dict:
        """Player passes. Mob attacks the passer, then advance turn."""
        self._cancel_turn_timeout()
        if entity_id != self.get_current_turn():
            self._schedule_turn_timeout()
            raise ValueError("Not your turn")
        if self.participant_stats[entity_id]["hp"] <= 0:
            self._schedule_turn_timeout()
            raise ValueError("You are dead")

        # Process DoT effects at start of turn
        dot_ticks = self._process_dot_effects(self.mob_stats, self.mob_name)
        dot_ticks += self._process_dot_effects(self.participant_stats[entity_id], entity_id)

        # If DoT killed the mob or this player, skip the action
        if self.is_finished:
            result: dict = {"action": "pass_turn", "entity_id": entity_id}
            if dot_ticks:
                result["dot_ticks"] = dot_ticks
            return result

        # Mob attacks the player who passed
        mob_attack = self._mob_attack_target(entity_id)

        result: dict = {
            "action": "pass_turn",
            "entity_id": entity_id,
            "mob_attack": mob_attack,
        }

        if dot_ticks:
            result["dot_ticks"] = dot_ticks

        # Advance turn — may also trigger cycle-end mob attack
        cycle_attack = self._advance_turn()
        if cycle_attack:
            result["cycle_mob_attack"] = cycle_attack

        return result

    def _process_dot_effects(self, target_stats: dict, target_label: str) -> list[dict]:
        """Tick all active DoT effects on a target.

        Applies damage (respecting shield), decrements remaining, removes expired.
        Returns list of tick result dicts for client display.
        """
        active = target_stats.get("active_effects")
        if not active:
            return []

        results: list[dict] = []
        surviving: list[dict] = []

        for dot in active:
            if dot.get("type") != EffectType.DOT:
                surviving.append(dot)
                continue

            value = dot.get("value", 0)

            # Apply damage respecting shield
            shield = target_stats.get("shield", 0)
            absorbed = min(shield, value)
            target_stats["shield"] = shield - absorbed
            actual_damage = value - absorbed
            target_stats["hp"] = max(0, target_stats["hp"] - actual_damage)

            dot["remaining"] -= 1

            results.append({
                "type": "dot_tick",
                "subtype": dot.get("subtype", "generic"),
                "value": actual_damage,
                "shield_absorbed": absorbed,
                "target": target_label,
                "target_hp": target_stats["hp"],
                "remaining": dot["remaining"],
            })

            if dot["remaining"] > 0:
                surviving.append(dot)

        target_stats["active_effects"] = surviving
        return results

    def _advance_turn(self) -> dict | None:
        """Advance to next participant. Returns mob attack if cycle complete."""
        self._actions_this_cycle += 1
        mob_attack = None

        if self._actions_this_cycle >= len(self.participants):
            # Full cycle complete — mob attacks a random player
            self._actions_this_cycle = 0
            alive = [eid for eid in self.participants if self.participant_stats[eid]["hp"] > 0]
            if alive:
                target = random.choice(alive)
                mob_attack = self._mob_attack_target(target)

                # Regenerate energy for all alive participants at cycle end
                for eid in self.participants:
                    s = self.participant_stats[eid]
                    if s["hp"] > 0:
                        regen = compute_energy_regen(s)
                        s["energy"] = min(
                            s.get("energy", 0) + regen,
                            s.get("max_energy", 0),
                        )

        self._turn_index = (self._turn_index + 1) % max(1, len(self.participants))

        # Skip dead players' turns
        for _ in range(len(self.participants)):
            current = self.get_current_turn()
            if current is None or self.participant_stats[current]["hp"] > 0:
                break
            self._turn_index = (self._turn_index + 1) % max(1, len(self.participants))

        # Schedule timeout for the new current turn
        if not self.is_finished:
            self._schedule_turn_timeout()

        return mob_attack

    def _mob_attack_target(self, target_id: str) -> dict:
        """Mob attacks a specific player. Returns attack result.

        Damage = base_attack + floor(mob STR × STAT_SCALING_FACTOR).
        DEX reduction applied after shield absorption (min 1).
        """
        import math
        from server.core.config import settings

        base_attack = self.mob_stats.get("attack", settings.DEFAULT_ATTACK)
        str_bonus = math.floor(
            self.mob_stats.get("strength", 0) * settings.STAT_SCALING_FACTOR
        )
        raw_damage = base_attack + str_bonus
        stats = self.participant_stats[target_id]

        # Shield absorption
        shield = stats.get("shield", 0)
        absorbed = min(shield, raw_damage)
        stats["shield"] = shield - absorbed
        post_shield = raw_damage - absorbed

        # DEX reduction (after shield, min 1 — but 0 if fully absorbed)
        dex_reduction = math.floor(
            stats.get("dexterity", 0) * settings.STAT_SCALING_FACTOR
        )
        actual_damage = max(settings.COMBAT_MIN_DAMAGE, post_shield - dex_reduction) if post_shield > 0 else 0
        stats["hp"] = max(0, stats["hp"] - actual_damage)

        return {
            "target": target_id,
            "damage": actual_damage,
            "shield_absorbed": absorbed,
            "target_hp": stats["hp"],
        }

    def get_state(self) -> dict:
        """Return current combat state for client."""
        participants = []
        for eid in self.participants:
            s = self.participant_stats[eid]
            participants.append({
                "entity_id": eid,
                "hp": s["hp"],
                "max_hp": s["max_hp"],
                "shield": s.get("shield", 0),
                "energy": s.get("energy", 0),
                "max_energy": s.get("max_energy", 0),
                "energy_regen": compute_energy_regen(s),
            })

        hands = {}
        for eid, hand in self.hands.items():
            hands[eid] = hand.get_hand()

        state = {
            "instance_id": self.instance_id,
            "current_turn": self.get_current_turn(),
            "participants": participants,
            "mob": {
                "name": self.mob_name,
                "hp": self.mob_stats["hp"],
                "max_hp": self.mob_stats["max_hp"],
            },
            "hands": hands,
        }
        if self._turn_timeout_at is not None:
            state["turn_timeout_at"] = self._turn_timeout_at
        return state

    @property
    def is_finished(self) -> bool:
        """Check if combat is over (mob dead or all players dead)."""
        if self.mob_stats["hp"] <= 0:
            return True
        if not self.participants:
            return True
        if all(self.participant_stats[eid]["hp"] <= 0 for eid in self.participants):
            return True
        return False

    def get_combat_end_result(self) -> dict | None:
        """Return combat end result if combat is finished, else None."""
        from server.core.xp import calculate_combat_xp

        if not self.is_finished:
            return None
        victory = self.mob_stats["hp"] <= 0
        if victory:
            rewards_per_player = {}
            for eid in self.participants:
                cha = self.participant_stats[eid].get("charisma", 0)
                rewards_per_player[eid] = {
                    "xp": calculate_combat_xp(self.mob_hit_dice, cha)
                }
            return {"victory": True, "rewards_per_player": rewards_per_player}
        return {"victory": False, "rewards_per_player": {}}
