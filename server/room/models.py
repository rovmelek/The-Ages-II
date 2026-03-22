"""Room, RoomState, and PlayerObjectState database models."""
from sqlalchemy import JSON, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from server.core.database import Base


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(primary_key=True)
    room_key: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    tile_data: Mapped[list] = mapped_column(JSON, default=list)
    exits: Mapped[list] = mapped_column(JSON, default=list)
    objects: Mapped[list] = mapped_column(JSON, default=list)
    spawn_points: Mapped[list] = mapped_column(JSON, default=list)


class RoomState(Base):
    __tablename__ = "room_states"

    id: Mapped[int] = mapped_column(primary_key=True)
    room_key: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    mob_states: Mapped[dict] = mapped_column(JSON, default=dict)
    dynamic_state: Mapped[dict] = mapped_column(JSON, default=dict)


class PlayerObjectState(Base):
    __tablename__ = "player_object_states"
    __table_args__ = (
        UniqueConstraint("player_id", "room_key", "object_id", name="uq_player_room_object"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(Integer)
    room_key: Mapped[str] = mapped_column(String(50))
    object_id: Mapped[str] = mapped_column(String(50))
    state_data: Mapped[dict] = mapped_column(JSON, default=dict)
