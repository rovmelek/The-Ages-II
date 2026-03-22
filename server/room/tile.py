"""Tile types and walkability rules."""
from enum import IntEnum


class TileType(IntEnum):
    FLOOR = 0
    WALL = 1
    EXIT = 2
    MOB_SPAWN = 3
    WATER = 4


WALKABLE_TILES: frozenset[TileType] = frozenset({TileType.FLOOR, TileType.EXIT, TileType.MOB_SPAWN})


def is_walkable(tile_type: int) -> bool:
    """Check whether a tile type value is walkable."""
    return tile_type in WALKABLE_TILES
