"""PlayerEntity runtime dataclass."""
from dataclasses import dataclass, field


@dataclass
class PlayerEntity:
    """In-memory representation of a connected player on the tile grid."""

    id: str  # Entity ID, e.g. "player_1"
    name: str
    x: int
    y: int
    player_db_id: int  # DB primary key
    stats: dict = field(default_factory=dict)
    in_combat: bool = False
