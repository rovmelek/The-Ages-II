"""Shared loot table definitions and loot generation."""
from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Loot tables — simple static lookup (used by chests and mob drops)
# ---------------------------------------------------------------------------

LOOT_TABLES: dict[str, list[dict[str, Any]]] = {
    # Chest loot tables
    "common_chest": [
        {"item_key": "healing_potion", "quantity": 1},
        {"item_key": "iron_shard", "quantity": 2},
    ],
    "rare_chest": [
        {"item_key": "healing_potion", "quantity": 3},
        {"item_key": "fire_essence", "quantity": 1},
    ],
    # Mob loot tables
    "slime_loot": [
        {"item_key": "healing_potion", "quantity": 1},
    ],
    "goblin_loot": [
        {"item_key": "iron_shard", "quantity": 1},
    ],
    "bat_loot": [
        {"item_key": "antidote", "quantity": 1},
    ],
    "troll_loot": [
        {"item_key": "healing_potion", "quantity": 1},
        {"item_key": "iron_shard", "quantity": 2},
    ],
    "dragon_loot": [
        {"item_key": "fire_essence", "quantity": 2},
        {"item_key": "healing_potion", "quantity": 2},
    ],
}


def generate_loot(loot_table: str) -> list[dict[str, Any]]:
    """Return loot items for a given loot table key."""
    return list(LOOT_TABLES.get(loot_table, []))
