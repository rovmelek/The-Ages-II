# Story 4.2: Card Definitions & Hand Management

Status: done

## Story

As a player,
I want to draw cards from a deck into my hand and have played cards cycle through a discard pile,
So that combat has strategic variety with each encounter.

## Acceptance Criteria

1. CardDef with effects: [{"type": "damage", "subtype": "fire", "value": 20}] → loaded from JSON → effects field is a list of effect objects
2. Deck of 15 cards and hand_size of 5 → CardHand created → 5 cards drawn from shuffled deck into hand
3. Player plays a card from hand → card moves to discard pile → new card drawn from deck → hand size remains at 5 (if deck has cards)
4. Deck is empty and draw needed → discard pile shuffled back into deck → card drawn from reshuffled deck
5. Player tries to play card not in hand → error: "Card not in hand"

## Tasks / Subtasks

- [x] Task 1: Create starter card JSON data `data/cards/starter_cards.json` (AC: #1)
  - [x] Define 6-8 starter cards with multi-effect lists (damage, heal, shield, draw, dot)
  - [x] Format: `[{"card_key": "...", "name": "...", "cost": 1, "effects": [...], "description": "..."}]`
- [x] Task 2: Create `server/combat/cards/card_def.py` with `CardDef` dataclass (AC: #1)
  - [x] `CardDef` with `card_key`, `name`, `cost`, `effects` (list of dicts), `description`
  - [x] `from_db(card: Card) -> CardDef` class method to convert from DB model
  - [x] `to_dict() -> dict` for serialization
- [x] Task 3: Create `server/combat/cards/card_hand.py` with `CardHand` class (AC: #2-5)
  - [x] `__init__(card_defs: list[CardDef], hand_size: int = 5)` — shuffles deck, draws initial hand
  - [x] `deck: list[CardDef]`, `hand: list[CardDef]`, `discard: list[CardDef]`
  - [x] `draw_card() -> CardDef | None` — draw from deck; if empty, reshuffle discard into deck first
  - [x] `play_card(card_key: str) -> CardDef` — remove from hand, add to discard, draw replacement; raise ValueError if not in hand
  - [x] `get_hand() -> list[dict]` — return serialized hand for client
- [x] Task 4: Add card loading helper to convert DB cards to CardDefs (AC: #1)
  - [x] `async def load_card_defs(session) -> list[CardDef]` in card_def.py or card_repo.py
  - [x] Converts all Card DB rows to CardDef instances
- [x] Task 5: Write tests `tests/test_cards.py` (AC: #1-5)
  - [x] Test CardDef creation and to_dict
  - [x] Test CardHand initial draw (hand_size cards in hand)
  - [x] Test play_card moves to discard and draws replacement
  - [x] Test deck exhaustion triggers reshuffle from discard
  - [x] Test play_card with invalid card_key raises ValueError
  - [x] Test CardDef.from_db conversion
  - [x] Test card loading from JSON via existing pipeline
- [x] Task 6: Verify all tests pass
  - [x] Run `pytest tests/test_cards.py -v`
  - [x] Run `pytest tests/ -v` to verify no regressions

## Dev Notes

### Architecture Compliance

| Component | File Location |
|-----------|--------------|
| CardDef | `server/combat/cards/card_def.py` (NEW) |
| CardHand | `server/combat/cards/card_hand.py` (NEW) |
| Starter cards | `data/cards/starter_cards.json` (NEW) |
| Tests | `tests/test_cards.py` (NEW) |

### Existing Infrastructure to Reuse

- **`Card` DB model** at `server/combat/cards/models.py` — already has `effects: JSON` column storing effect lists
- **`card_repo`** at `server/combat/cards/card_repo.py` — `load_cards_from_json()`, `get_all()`, `get_by_key()`
- **`Game.startup()`** already loads card JSON from `data/cards/` directory
- **`Player.card_collection`** — list of card_key strings in DB model

### Card JSON Format

```json
[
  {
    "card_key": "fire_bolt",
    "name": "Fire Bolt",
    "cost": 1,
    "effects": [{"type": "damage", "subtype": "fire", "value": 20}],
    "description": "Hurls a bolt of fire at the enemy."
  }
]
```

### CardHand Lifecycle

1. Combat starts → `CardHand(card_defs, hand_size=5)` created
2. Deck shuffled, 5 cards drawn to hand
3. Player plays card → card to discard, draw replacement from deck
4. Deck empty → shuffle discard into deck, continue drawing
5. Combat ends → CardHand discarded

### Anti-Patterns to Avoid

- **DO NOT** implement combat instance or turn logic — Story 4.3 handles that
- **DO NOT** implement effect resolution during card play — Story 4.4 handles that
- **DO NOT** persist hand state to DB — CardHand is in-memory during combat only
- **DO NOT** implement card collection management or deck building — deferred feature

### Previous Story Intelligence

From Story 4-1:
- EffectRegistry resolves effects from `[{"type": "damage", "value": 20}]` format
- Effects are plain dicts — CardDef.effects stores the same format
- 188 existing tests must not regress

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#Card System]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 4.2]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Created `data/cards/starter_cards.json` with 8 starter cards (fire_bolt, ice_shard, slash, heal_light, iron_shield, poison_strike, arcane_surge, fortify)
- Created `server/combat/cards/card_def.py` with `CardDef` dataclass, `from_db()` and `to_dict()` methods
- Created `server/combat/cards/card_hand.py` with `CardHand` class: deck/hand/discard management, draw with reshuffle, play with replacement
- 12 new tests covering CardDef creation/serialization, hand management, deck exhaustion/reshuffle, error handling
- All 200 tests pass (188 existing + 12 new)

### File List

- `data/cards/starter_cards.json` (NEW — 8 starter cards)
- `server/combat/cards/card_def.py` (NEW)
- `server/combat/cards/card_hand.py` (NEW)
- `tests/test_cards.py` (NEW — 12 tests)
