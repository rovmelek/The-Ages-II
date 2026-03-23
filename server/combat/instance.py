"""CombatInstance — manages a single turn-based combat encounter."""
from __future__ import annotations

import random
import uuid

from server.combat.cards.card_def import CardDef
from server.combat.cards.card_hand import CardHand


class CombatInstance:
    """A single combat encounter between players and a mob."""

    def __init__(
        self,
        instance_id: str | None = None,
        mob_name: str = "",
        mob_stats: dict | None = None,
    ) -> None:
        self.instance_id = instance_id or str(uuid.uuid4())
        self.mob_name = mob_name
        self.mob_stats: dict = dict(mob_stats) if mob_stats else {"hp": 50, "max_hp": 50, "attack": 10}
        self.participants: list[str] = []  # entity_ids in turn order
        self.participant_stats: dict[str, dict] = {}  # entity_id -> stats dict
        self.hands: dict[str, CardHand] = {}  # entity_id -> CardHand
        self._turn_index: int = 0
        self._actions_this_cycle: int = 0

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

    def remove_participant(self, entity_id: str) -> None:
        """Remove a player from combat (e.g. flee)."""
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

    def play_card(self, entity_id: str, card_key: str) -> dict:
        """Player plays a card. Validates turn, plays from hand, advances turn.

        Returns dict with card info and any mob attack from cycle end.
        """
        if entity_id != self.get_current_turn():
            raise ValueError("Not your turn")
        if self.participant_stats[entity_id]["hp"] <= 0:
            raise ValueError("You are dead")

        hand = self.hands[entity_id]
        played = hand.play_card(card_key)

        result: dict = {
            "action": "play_card",
            "entity_id": entity_id,
            "card": played.to_dict(),
        }

        # Advance turn — may trigger mob attack at end of cycle
        mob_attack = self._advance_turn()
        if mob_attack:
            result["mob_attack"] = mob_attack

        return result

    def pass_turn(self, entity_id: str) -> dict:
        """Player passes. Mob attacks the passer, then advance turn."""
        if entity_id != self.get_current_turn():
            raise ValueError("Not your turn")
        if self.participant_stats[entity_id]["hp"] <= 0:
            raise ValueError("You are dead")

        # Mob attacks the player who passed
        mob_attack = self._mob_attack_target(entity_id)

        result: dict = {
            "action": "pass_turn",
            "entity_id": entity_id,
            "mob_attack": mob_attack,
        }

        # Advance turn — may also trigger cycle-end mob attack
        cycle_attack = self._advance_turn()
        if cycle_attack:
            result["cycle_mob_attack"] = cycle_attack

        return result

    def _advance_turn(self) -> dict | None:
        """Advance to next participant. Returns mob attack if cycle complete."""
        self._actions_this_cycle += 1
        mob_attack = None

        if self._actions_this_cycle >= len(self.participants):
            # Full cycle complete — mob attacks a random player
            self._actions_this_cycle = 0
            if self.participants:
                target = random.choice(self.participants)
                mob_attack = self._mob_attack_target(target)

        self._turn_index = (self._turn_index + 1) % max(1, len(self.participants))
        return mob_attack

    def _mob_attack_target(self, target_id: str) -> dict:
        """Mob attacks a specific player. Returns attack result."""
        attack = self.mob_stats.get("attack", 10)
        stats = self.participant_stats[target_id]

        shield = stats.get("shield", 0)
        absorbed = min(shield, attack)
        stats["shield"] = shield - absorbed
        actual_damage = attack - absorbed
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
            })

        hands = {}
        for eid, hand in self.hands.items():
            hands[eid] = hand.get_hand()

        return {
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
