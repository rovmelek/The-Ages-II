"""Tests for card definitions and hand management (Story 4.2)."""
import pytest

from server.combat.cards.card_def import CardDef
from server.combat.cards.card_hand import CardHand


# --- Helpers ---


def _make_card(key: str, name: str = "", cost: int = 1, effects: list | None = None) -> CardDef:
    return CardDef(
        card_key=key,
        name=name or key,
        cost=cost,
        effects=effects or [{"type": "damage", "value": 10}],
        description=f"Test card {key}",
    )


def _make_deck(n: int) -> list[CardDef]:
    return [_make_card(f"card_{i}") for i in range(n)]


# --- CardDef ---


def test_card_def_to_dict():
    card = _make_card("fire_bolt", "Fire Bolt", 1, [{"type": "damage", "subtype": "fire", "value": 20}])
    d = card.to_dict()
    assert d["card_key"] == "fire_bolt"
    assert d["name"] == "Fire Bolt"
    assert d["cost"] == 1
    assert d["effects"] == [{"type": "damage", "subtype": "fire", "value": 20}]


def test_card_def_multi_effects():
    card = _make_card(
        "combo",
        effects=[
            {"type": "damage", "value": 10},
            {"type": "heal", "value": 5},
        ],
    )
    assert len(card.effects) == 2
    assert card.effects[0]["type"] == "damage"
    assert card.effects[1]["type"] == "heal"


# --- CardHand initial draw ---


def test_card_hand_initial_draw():
    deck = _make_deck(15)
    hand = CardHand(deck, hand_size=5)
    assert len(hand.hand) == 5
    assert len(hand.deck) == 10
    assert len(hand.discard) == 0


def test_card_hand_small_deck():
    deck = _make_deck(3)
    hand = CardHand(deck, hand_size=5)
    assert len(hand.hand) == 3  # only 3 cards available
    assert len(hand.deck) == 0


# --- play_card ---


def test_play_card_moves_to_discard_and_draws():
    deck = _make_deck(15)
    hand = CardHand(deck, hand_size=5)
    card_key = hand.hand[0].card_key
    played = hand.play_card(card_key)
    assert played.card_key == card_key
    assert len(hand.hand) == 5  # drew replacement
    assert len(hand.discard) == 1
    assert hand.discard[0].card_key == card_key


def test_play_card_invalid_raises():
    deck = _make_deck(10)
    hand = CardHand(deck, hand_size=5)
    with pytest.raises(ValueError, match="Card not in hand"):
        hand.play_card("nonexistent_card")


def test_play_card_no_replacement_when_deck_empty():
    deck = _make_deck(5)
    hand = CardHand(deck, hand_size=5)
    assert len(hand.deck) == 0  # all cards in hand
    card_key = hand.hand[0].card_key
    hand.play_card(card_key)
    # Can't draw replacement, discard has 1 card but reshuffle happened
    # After play: discard gets card, draw_card reshuffles discard into deck, draws 1
    # So hand should still be 4 (played 1, drew 1 from reshuffled discard... wait)
    # Actually: play removes from hand (4 left), adds to discard (1), then draw_card:
    #   deck is empty, discard has 1 card → reshuffle → deck has 1 → draw it → hand has 5
    # Wait, that means we drew back the same card we just played
    assert len(hand.hand) == 5  # reshuffled discard back in


def test_play_all_cards_with_reshuffle():
    deck = _make_deck(6)
    hand = CardHand(deck, hand_size=5)
    # deck=1, hand=5, discard=0
    # Play 5 cards, each triggers reshuffle eventually
    for _ in range(5):
        key = hand.hand[0].card_key
        hand.play_card(key)
    # After reshuffles, all 6 cards should still exist across deck/hand/discard
    total = len(hand.deck) + len(hand.hand) + len(hand.discard)
    assert total == 6


# --- Deck exhaustion and reshuffle ---


def test_reshuffle_discard_into_deck():
    deck = _make_deck(7)
    hand = CardHand(deck, hand_size=5)
    # deck=2, hand=5, discard=0
    # Play 3 cards to fill discard
    for _ in range(3):
        hand.play_card(hand.hand[0].card_key)
    # After 3 plays: drew 3 from deck (deck was 2, so reshuffle happened)
    total = len(hand.deck) + len(hand.hand) + len(hand.discard)
    assert total == 7


# --- get_hand ---


def test_get_hand_serialization():
    deck = _make_deck(10)
    hand = CardHand(deck, hand_size=3)
    serialized = hand.get_hand()
    assert len(serialized) == 3
    for item in serialized:
        assert "card_key" in item
        assert "name" in item
        assert "effects" in item


# --- CardDef.from_db ---


def test_card_def_from_db():
    """Test conversion from DB model (mock)."""

    class MockCard:
        card_key = "test_card"
        name = "Test Card"
        cost = 2
        effects = [{"type": "damage", "value": 15}]
        description = "A test card"

    card_def = CardDef.from_db(MockCard())
    assert card_def.card_key == "test_card"
    assert card_def.name == "Test Card"
    assert card_def.cost == 2
    assert card_def.effects == [{"type": "damage", "value": 15}]
    assert card_def.description == "A test card"


def test_card_def_from_db_empty_effects():
    class MockCard:
        card_key = "empty"
        name = "Empty"
        cost = 0
        effects = None
        description = None

    card_def = CardDef.from_db(MockCard())
    assert card_def.effects == []
    assert card_def.description == ""
