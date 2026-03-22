"""Player database model."""
from sqlalchemy import JSON, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from server.core.database import Base


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    inventory: Mapped[dict] = mapped_column(JSON, default=dict)
    card_collection: Mapped[list] = mapped_column(JSON, default=list)
    current_room_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    position_x: Mapped[int] = mapped_column(Integer, default=0)
    position_y: Mapped[int] = mapped_column(Integer, default=0)
