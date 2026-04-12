"""Card hand management — deck, hand, and discard pile for combat."""
from __future__ import annotations

import random
from copy import deepcopy

from server.combat.cards.card_def import CardDef
from server.core.config import settings


class CardHand:
    """Manages a player's deck, hand, and discard pile during combat."""

    def __init__(self, card_defs: list[CardDef], hand_size: int = settings.COMBAT_HAND_SIZE) -> None:
        self.hand_size = hand_size
        self.deck: list[CardDef] = [deepcopy(c) for c in card_defs]
        random.shuffle(self.deck)
        self.hand: list[CardDef] = []
        self.discard: list[CardDef] = []

        # Draw initial hand
        for _ in range(min(hand_size, len(self.deck))):
            card = self.draw_card()
            if card is None:
                break

    def draw_card(self) -> CardDef | None:
        """Draw a card from deck. If empty, reshuffle discard into deck first."""
        if not self.deck and self.discard:
            self.deck = self.discard
            self.discard = []
            random.shuffle(self.deck)

        if not self.deck:
            return None

        card = self.deck.pop(0)
        self.hand.append(card)
        return card

    def get_card_cost(self, card_key: str) -> int:
        """Return cost of a card in hand without removing it.

        Raises ValueError if card not in hand.
        """
        for card in self.hand:
            if card.card_key == card_key:
                return card.cost
        raise ValueError("Card not in hand")

    def play_card(self, card_key: str) -> CardDef:
        """Play a card from hand. Moves to discard and draws replacement.

        Raises ValueError if card not in hand.
        """
        for i, card in enumerate(self.hand):
            if card.card_key == card_key:
                played = self.hand.pop(i)
                self.discard.append(played)
                self.draw_card()
                return played

        raise ValueError("Card not in hand")

    def get_hand(self) -> list[dict]:
        """Return serialized hand for client."""
        return [card.to_dict() for card in self.hand]
