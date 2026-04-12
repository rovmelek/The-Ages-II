"""Item persistence repository."""
import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.items.models import Item


async def get_by_key(session: AsyncSession, item_key: str) -> Item | None:
    """Find an item by its unique key."""
    result = await session.execute(select(Item).where(Item.item_key == item_key))
    return result.scalar_one_or_none()


async def get_all(session: AsyncSession) -> list[Item]:
    """Return all item definitions."""
    result = await session.execute(select(Item))
    return list(result.scalars().all())


def load_loot_tables(data_dir: Path) -> dict[str, list[dict[str, Any]]]:
    """Load loot table definitions from JSON file."""
    loot_file = data_dir / "loot_tables.json"
    if not loot_file.exists():
        return {}
    with open(loot_file) as f:
        return json.load(f)


async def load_items_from_json(session: AsyncSession, json_path: Path | str) -> list[Item]:
    """Read a JSON file of item definitions and upsert them into the database."""
    json_path = Path(json_path)
    with open(json_path) as f:
        item_list = json.load(f)

    items: list[Item] = []
    for data in item_list:
        existing = await get_by_key(session, data["item_key"])
        if existing:
            existing.name = data["name"]
            existing.category = data["category"]
            existing.stackable = data.get("stackable", True)
            existing.charges = data.get("charges", 1)
            existing.effects = data.get("effects", [])
            existing.usable_in_combat = data.get("usable_in_combat", False)
            existing.usable_outside_combat = data.get("usable_outside_combat", False)
            existing.description = data.get("description", "")
            existing.tradeable = data.get("tradeable", True)
            items.append(existing)
        else:
            item = Item(
                item_key=data["item_key"],
                name=data["name"],
                category=data["category"],
                stackable=data.get("stackable", True),
                charges=data.get("charges", 1),
                effects=data.get("effects", []),
                usable_in_combat=data.get("usable_in_combat", False),
                usable_outside_combat=data.get("usable_outside_combat", False),
                description=data.get("description", ""),
                tradeable=data.get("tradeable", True),
            )
            session.add(item)
            items.append(item)
    return items
