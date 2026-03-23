"""Room objects subsystem — register all object types here."""
from server.room.objects.chest import ChestObject
from server.room.objects.lever import LeverObject
from server.room.objects.registry import register_object_type

register_object_type("chest", ChestObject)
register_object_type("lever", LeverObject)
