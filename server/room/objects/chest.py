"""Chest interactive object — one-time loot per player."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from server.core.database import async_session
from server.items.item_def import ItemDef
from server.items import item_repo as items_repo
from server.player import repo as player_repo
from server.room.objects.base import InteractiveObject
from server.room.objects.state import get_player_object_state, set_player_object_state

if TYPE_CHECKING:
    from server.app import Game


# ---------------------------------------------------------------------------
# Prototype loot tables — simple static lookup
# ---------------------------------------------------------------------------

LOOT_TABLES: dict[str, list[dict[str, Any]]] = {
    "common_chest": [
        {"item_key": "healing_potion", "quantity": 1},
        {"item_key": "iron_shard", "quantity": 2},
    ],
    "rare_chest": [
        {"item_key": "healing_potion", "quantity": 3},
        {"item_key": "fire_essence", "quantity": 1},
    ],
}


def generate_loot(loot_table: str) -> list[dict[str, Any]]:
    """Return loot items for a given loot table key."""
    return list(LOOT_TABLES.get(loot_table, []))


# ---------------------------------------------------------------------------
# ChestObject
# ---------------------------------------------------------------------------

class ChestObject(InteractiveObject):
    """A chest with per-player one-time loot."""

    async def interact(self, player_id: int, game: Game) -> dict[str, Any]:
        room_key = self._get_room_key(game)

        async with async_session() as session:
            # Check if already opened by this player
            state = await get_player_object_state(session, player_id, room_key, self.id)
            if state.get("opened"):
                return {"status": "already_looted", "message": "Already looted"}

            # Generate loot
            loot_table = self.config.get("loot_table", "common_chest")
            items = generate_loot(loot_table)

            # Add items to player DB inventory
            player = await player_repo.get_by_id(session, player_id)
            if player is not None:
                db_inventory = dict(player.inventory or {})
                for item in items:
                    key = item["item_key"]
                    db_inventory[key] = db_inventory.get(key, 0) + item["quantity"]
                player.inventory = db_inventory
                await session.commit()

            # Sync to runtime inventory (items immediately visible)
            entity_id = f"player_{player_id}"
            player_info = game.player_entities.get(entity_id)
            if player_info:
                runtime_inv = player_info.get("inventory")
                if runtime_inv:
                    for item in items:
                        item_db = await items_repo.get_by_key(session, item["item_key"])
                        if item_db:
                            item_def = ItemDef.from_db(item_db)
                            runtime_inv.add_item(item_def, item["quantity"])

            # Mark as opened
            await set_player_object_state(session, player_id, room_key, self.id, {"opened": True})

        return {"status": "looted", "items": items}

    def _get_room_key(self, game: Game) -> str:
        """Find which room this object belongs to."""
        for room_key, room in game.room_manager._rooms.items():
            if room.get_object(self.id) is not None:
                return room_key
        return ""
