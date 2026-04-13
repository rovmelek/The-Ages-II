"""Card database model."""
from sqlalchemy import JSON, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from server.core.database import Base


class Card(Base):
    __tablename__ = "cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    card_key: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    cost: Mapped[int] = mapped_column(Integer)
    effects: Mapped[list] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(String(500), default="")
    card_type: Mapped[str] = mapped_column(String(30), server_default=text("'physical'"))
