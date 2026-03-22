"""Tests for static room objects (Story 2.2)."""
from server.player.entity import PlayerEntity
from server.room.room import RoomInstance
from server.room.tile import TileType


def _make_entity(eid="player_1", x=2, y=2):
    return PlayerEntity(id=eid, name="Hero", x=x, y=y, player_db_id=1)


# ---------------------------------------------------------------------------
# Blocking static objects
# ---------------------------------------------------------------------------

def test_blocking_object_makes_tile_wall():
    """A blocking static object should overwrite its tile to WALL."""
    tile_data = [[0] * 5 for _ in range(5)]
    objects = [
        {"id": "rock_01", "type": "rock", "x": 3, "y": 2, "category": "static", "blocking": True},
    ]
    room = RoomInstance("test", "Test", 5, 5, tile_data, objects=objects)

    assert room._grid[2][3] == TileType.WALL


def test_move_onto_blocking_object_fails():
    """Player cannot move onto a tile with a blocking static object."""
    tile_data = [[0] * 5 for _ in range(5)]
    objects = [
        {"id": "rock_01", "type": "rock", "x": 3, "y": 2, "category": "static", "blocking": True},
    ]
    room = RoomInstance("test", "Test", 5, 5, tile_data, objects=objects)
    entity = _make_entity(x=2, y=2)
    room.add_entity(entity)

    result = room.move_entity("player_1", "right")
    assert result["success"] is False
    assert result["reason"] == "wall"
    assert entity.x == 2  # Didn't move


# ---------------------------------------------------------------------------
# Non-blocking (decorative) objects
# ---------------------------------------------------------------------------

def test_decorative_object_allows_movement():
    """A non-blocking decorative object should not prevent movement."""
    tile_data = [[0] * 5 for _ in range(5)]
    objects = [
        {"id": "flower_01", "type": "flower", "x": 3, "y": 2, "category": "static", "blocking": False},
    ]
    room = RoomInstance("test", "Test", 5, 5, tile_data, objects=objects)
    entity = _make_entity(x=2, y=2)
    room.add_entity(entity)

    result = room.move_entity("player_1", "right")
    assert result["success"] is True
    assert entity.x == 3


def test_decorative_object_tile_unchanged():
    """Non-blocking objects should not change the tile type."""
    tile_data = [[0] * 5 for _ in range(5)]
    objects = [
        {"id": "flower_01", "type": "flower", "x": 3, "y": 2, "category": "static", "blocking": False},
    ]
    room = RoomInstance("test", "Test", 5, 5, tile_data, objects=objects)

    assert room._grid[2][3] == TileType.FLOOR


# ---------------------------------------------------------------------------
# room_state includes objects
# ---------------------------------------------------------------------------

def test_get_state_includes_objects():
    """get_state should include the objects list."""
    objects = [
        {"id": "rock_01", "type": "rock", "x": 1, "y": 1, "category": "static", "blocking": True},
        {"id": "flower_01", "type": "flower", "x": 2, "y": 1, "category": "static", "blocking": False},
    ]
    room = RoomInstance("test", "Test", 5, 5, [[0] * 5 for _ in range(5)], objects=objects)

    state = room.get_state()
    assert "objects" in state
    assert len(state["objects"]) == 2
    assert state["objects"][0]["id"] == "rock_01"


# ---------------------------------------------------------------------------
# RoomManager load_room preserves objects
# ---------------------------------------------------------------------------

def test_room_manager_loads_objects():
    """Objects from DB room model should be preserved in RoomInstance."""
    from server.room.manager import RoomManager

    class MockRoom:
        pass

    room_db = MockRoom()
    room_db.room_key = "forest"
    room_db.name = "Forest"
    room_db.width = 5
    room_db.height = 5
    room_db.tile_data = [[0] * 5 for _ in range(5)]
    room_db.exits = []
    room_db.objects = [
        {"id": "tree_01", "type": "tree", "x": 1, "y": 1, "category": "static", "blocking": True},
    ]
    room_db.spawn_points = []

    mgr = RoomManager()
    instance = mgr.load_room(room_db)

    assert len(instance.objects) == 1
    assert instance._grid[1][1] == TileType.WALL  # Blocking object applied


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_non_static_objects_ignored():
    """Objects without category 'static' should not affect tiles."""
    tile_data = [[0] * 5 for _ in range(5)]
    objects = [
        {"id": "chest_01", "type": "chest", "x": 3, "y": 2, "category": "interactive", "blocking": True},
    ]
    room = RoomInstance("test", "Test", 5, 5, tile_data, objects=objects)

    # Interactive objects are not processed in this story
    assert room._grid[2][3] == TileType.FLOOR


def test_blocking_object_out_of_bounds_ignored():
    """Objects at invalid coordinates should not crash."""
    tile_data = [[0] * 5 for _ in range(5)]
    objects = [
        {"id": "rock_99", "type": "rock", "x": 99, "y": 99, "category": "static", "blocking": True},
    ]
    # Should not raise
    room = RoomInstance("test", "Test", 5, 5, tile_data, objects=objects)
    assert room is not None
