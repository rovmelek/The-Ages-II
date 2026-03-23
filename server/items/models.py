"""Item database model."""
from sqlalchemy import JSON, Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from server.core.database import Base


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_key: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(20))  # "consumable" or "material"
    stackable: Mapped[bool] = mapped_column(Boolean, default=True)
    charges: Mapped[int] = mapped_column(Integer, default=1)
    effects: Mapped[list] = mapped_column(JSON, default=list)
    usable_in_combat: Mapped[bool] = mapped_column(Boolean, default=False)
    usable_outside_combat: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str] = mapped_column(String(500), default="")
