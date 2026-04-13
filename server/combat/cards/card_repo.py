"""Card persistence repository."""
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.combat.cards.models import Card


async def get_by_key(session: AsyncSession, card_key: str) -> Card | None:
    """Find a card by its unique key."""
    result = await session.execute(select(Card).where(Card.card_key == card_key))
    return result.scalar_one_or_none()


async def get_all(session: AsyncSession) -> list[Card]:
    """Return all card definitions."""
    result = await session.execute(select(Card))
    return list(result.scalars().all())


async def load_cards_from_json(session: AsyncSession, json_path: Path | str) -> list[Card]:
    """Read a JSON file of card definitions and upsert them into the database."""
    json_path = Path(json_path)
    with open(json_path) as f:
        card_list = json.load(f)

    cards: list[Card] = []
    for data in card_list:
        existing = await get_by_key(session, data["card_key"])
        if existing:
            existing.name = data["name"]
            existing.cost = data["cost"]
            existing.effects = data.get("effects", [])
            existing.description = data.get("description", "")
            existing.card_type = data.get("card_type", "physical")
            cards.append(existing)
        else:
            card = Card(
                card_key=data["card_key"],
                name=data["name"],
                cost=data["cost"],
                effects=data.get("effects", []),
                description=data.get("description", ""),
                card_type=data.get("card_type", "physical"),
            )
            session.add(card)
            cards.append(card)
    return cards
