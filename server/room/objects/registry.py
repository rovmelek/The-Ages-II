"""Object type registry — maps object type strings to handler classes."""
from __future__ import annotations

from typing import Type

from server.room.objects.base import InteractiveObject, RoomObject

# Maps object type string → InteractiveObject subclass.
# Populated by Story 3.2 (chests), 3.3 (levers), etc.
OBJECT_HANDLERS: dict[str, Type[InteractiveObject]] = {}


def register_object_type(type_name: str, cls: Type[InteractiveObject]) -> None:
    """Register an object type handler."""
    OBJECT_HANDLERS[type_name] = cls


def create_object(obj_dict: dict) -> RoomObject | InteractiveObject:
    """Build a RoomObject (or InteractiveObject subclass) from a JSON dict."""
    obj_type = obj_dict.get("type", "")
    handler_cls = OBJECT_HANDLERS.get(obj_type)

    if handler_cls is not None:
        return handler_cls(
            id=obj_dict["id"],
            type=obj_type,
            x=obj_dict.get("x", 0),
            y=obj_dict.get("y", 0),
            category=obj_dict.get("category", "interactive"),
            state_scope=obj_dict.get("state_scope"),
            config=obj_dict.get("config", {}),
        )

    # Fallback: plain RoomObject for unregistered types
    return RoomObject(
        id=obj_dict["id"],
        type=obj_type,
        x=obj_dict.get("x", 0),
        y=obj_dict.get("y", 0),
        category=obj_dict.get("category", "static"),
        state_scope=obj_dict.get("state_scope"),
        config=obj_dict.get("config", {}),
    )
