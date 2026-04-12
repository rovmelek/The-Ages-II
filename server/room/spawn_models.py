"""SpawnCheckpoint database model for NPC spawn tracking."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from server.core.database import Base


class SpawnCheckpoint(Base):
    __tablename__ = "spawn_checkpoints"

    id: Mapped[int] = mapped_column(primary_key=True)
    npc_key: Mapped[str] = mapped_column(String(50))
    room_key: Mapped[str] = mapped_column(String(50))
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    currently_spawned: Mapped[bool] = mapped_column(Boolean, default=False)
