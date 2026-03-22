"""Tests for tile system, PlayerEntity, RoomInstance, and RoomManager."""
from server.player.entity import PlayerEntity
from server.room.tile import WALKABLE_TILES, TileType, is_walkable
from server.room.room import RoomInstance
from server.room.manager import RoomManager


# --- TileType tests ---


def test_tile_type_values():
    assert TileType.FLOOR == 0
    assert TileType.WALL == 1
    assert TileType.EXIT == 2
    assert TileType.MOB_SPAWN == 3
    assert TileType.WATER == 4


def test_walkable_tiles():
    assert TileType.FLOOR in WALKABLE_TILES
    assert TileType.EXIT in WALKABLE_TILES
    assert TileType.MOB_SPAWN in WALKABLE_TILES
    assert TileType.WALL not in WALKABLE_TILES
    assert TileType.WATER not in WALKABLE_TILES


def test_is_walkable():
    assert is_walkable(0) is True  # FLOOR
    assert is_walkable(1) is False  # WALL
    assert is_walkable(2) is True  # EXIT
    assert is_walkable(3) is True  # MOB_SPAWN
    assert is_walkable(4) is False  # WATER


# --- PlayerEntity tests ---


def test_player_entity_creation():
    entity = PlayerEntity(id="player_1", name="Hero", x=5, y=10, player_db_id=42)
    assert entity.id == "player_1"
    assert entity.name == "Hero"
    assert entity.x == 5
    assert entity.y == 10
    assert entity.player_db_id == 42
    assert entity.stats == {}
    assert entity.in_combat is False


def test_player_entity_with_stats():
    entity = PlayerEntity(
        id="player_2", name="Mage", x=0, y=0, player_db_id=7,
        stats={"hp": 100}, in_combat=True,
    )
    assert entity.stats == {"hp": 100}
    assert entity.in_combat is True


# --- RoomInstance helper ---


def _make_room(
    width=5,
    height=5,
    tile_data=None,
    exits=None,
    spawn_points=None,
    room_key="test",
):
    if tile_data is None:
        # 5x5 all floor
        tile_data = [[0] * width for _ in range(height)]
    return RoomInstance(
        room_key=room_key,
        name="Test Room",
        width=width,
        height=height,
        tile_data=tile_data,
        exits=exits or [],
        spawn_points=spawn_points or [],
    )


def _make_entity(eid="player_1", x=2, y=2):
    return PlayerEntity(id=eid, name="Hero", x=x, y=y, player_db_id=1)


# --- RoomInstance entity tests ---


def test_add_remove_entity():
    room = _make_room()
    entity = _make_entity()
    room.add_entity(entity)
    assert room.get_player_ids() == ["player_1"]

    removed = room.remove_entity("player_1")
    assert removed is entity
    assert room.get_player_ids() == []

    assert room.remove_entity("nonexistent") is None


def test_get_entities_at():
    room = _make_room()
    e1 = _make_entity("p1", x=3, y=3)
    e2 = _make_entity("p2", x=3, y=3)
    e3 = _make_entity("p3", x=1, y=1)
    room.add_entity(e1)
    room.add_entity(e2)
    room.add_entity(e3)

    at_3_3 = room.get_entities_at(3, 3)
    assert len(at_3_3) == 2
    assert {e.id for e in at_3_3} == {"p1", "p2"}

    at_1_1 = room.get_entities_at(1, 1)
    assert len(at_1_1) == 1

    assert room.get_entities_at(0, 0) == []


def test_get_player_spawn():
    room = _make_room(spawn_points=[{"type": "player", "x": 3, "y": 4}])
    assert room.get_player_spawn() == (3, 4)


def test_get_player_spawn_fallback():
    room = _make_room(spawn_points=[])
    assert room.get_player_spawn() == (0, 0)


def test_get_player_ids():
    room = _make_room()
    room.add_entity(_make_entity("a"))
    room.add_entity(_make_entity("b"))
    ids = room.get_player_ids()
    assert set(ids) == {"a", "b"}


# --- RoomInstance movement tests ---


def test_move_entity_valid():
    room = _make_room()
    entity = _make_entity(x=2, y=2)
    room.add_entity(entity)

    result = room.move_entity("player_1", "right")
    assert result == {"success": True, "x": 3, "y": 2}
    assert entity.x == 3
    assert entity.y == 2


def test_move_entity_wall_blocked():
    # Put a wall at (3, 2)
    tile_data = [[0] * 5 for _ in range(5)]
    tile_data[2][3] = TileType.WALL
    room = _make_room(tile_data=tile_data)
    entity = _make_entity(x=2, y=2)
    room.add_entity(entity)

    result = room.move_entity("player_1", "right")
    assert result == {"success": False, "reason": "wall"}
    assert entity.x == 2  # didn't move


def test_move_entity_bounds_blocked():
    room = _make_room()
    entity = _make_entity(x=0, y=0)
    room.add_entity(entity)

    result = room.move_entity("player_1", "up")
    assert result == {"success": False, "reason": "bounds"}

    result = room.move_entity("player_1", "left")
    assert result == {"success": False, "reason": "bounds"}


def test_move_entity_invalid_direction():
    room = _make_room()
    entity = _make_entity()
    room.add_entity(entity)

    result = room.move_entity("player_1", "diagonal")
    assert result == {"success": False, "reason": "invalid_direction"}


def test_move_entity_exit_detection():
    tile_data = [[0] * 5 for _ in range(5)]
    tile_data[2][3] = TileType.EXIT
    exits = [{"target_room": "cave", "x": 3, "y": 2, "direction": "east"}]
    room = _make_room(tile_data=tile_data, exits=exits)
    entity = _make_entity(x=2, y=2)
    room.add_entity(entity)

    result = room.move_entity("player_1", "right")
    assert result["success"] is True
    assert result["x"] == 3
    assert result["exit"]["target_room"] == "cave"


def test_move_entity_mob_encounter():
    tile_data = [[0] * 5 for _ in range(5)]
    tile_data[2][3] = TileType.MOB_SPAWN
    room = _make_room(tile_data=tile_data)
    player = _make_entity(x=2, y=2)
    mob = PlayerEntity(id="mob_goblin_1", name="Goblin", x=3, y=2, player_db_id=0)
    room.add_entity(player)
    room.add_entity(mob)

    result = room.move_entity("player_1", "right")
    assert result["success"] is True
    assert result["mob_encounter"]["entity_id"] == "mob_goblin_1"
    assert result["mob_encounter"]["name"] == "Goblin"


def test_move_entity_not_found():
    room = _make_room()
    result = room.move_entity("nonexistent", "up")
    assert result == {"success": False, "reason": "entity_not_found"}


# --- RoomInstance get_state ---


def test_get_state():
    room = _make_room(
        room_key="forest",
        exits=[{"target_room": "cave", "x": 4, "y": 4}],
    )
    entity = _make_entity(x=1, y=1)
    room.add_entity(entity)

    state = room.get_state()
    assert state["room_key"] == "forest"
    assert state["name"] == "Test Room"
    assert state["width"] == 5
    assert state["height"] == 5
    assert len(state["tiles"]) == 5
    assert len(state["entities"]) == 1
    assert state["entities"][0]["id"] == "player_1"
    assert state["exits"] == [{"target_room": "cave", "x": 4, "y": 4}]


# --- RoomManager tests ---


def _make_mock_room_db(room_key="town", name="Town", width=5, height=5):
    """Create a mock object that looks like a Room DB model."""

    class MockRoom:
        pass

    r = MockRoom()
    r.room_key = room_key
    r.name = name
    r.width = width
    r.height = height
    r.tile_data = [[0] * width for _ in range(height)]
    r.exits = []
    r.objects = []
    r.spawn_points = [{"type": "player", "x": 2, "y": 2}]
    return r


def test_room_manager_load_and_get():
    mgr = RoomManager()
    room_db = _make_mock_room_db()
    instance = mgr.load_room(room_db)

    assert instance.room_key == "town"
    assert mgr.get_room("town") is instance
    assert mgr.get_room("nonexistent") is None


def test_room_manager_unload():
    mgr = RoomManager()
    mgr.load_room(_make_mock_room_db())
    mgr.unload_room("town")
    assert mgr.get_room("town") is None


def test_room_manager_transfer_entity():
    mgr = RoomManager()
    mgr.load_room(_make_mock_room_db("town"))
    cave_db = _make_mock_room_db("cave")
    cave_db.spawn_points = [{"type": "player", "x": 1, "y": 1}]
    mgr.load_room(cave_db)

    entity = _make_entity(x=3, y=3)
    mgr.get_room("town").add_entity(entity)

    target = mgr.transfer_entity(entity, "town", "cave")
    assert target is not None
    assert target.room_key == "cave"
    assert entity.x == 1
    assert entity.y == 1
    assert "player_1" in target.get_player_ids()
    assert "player_1" not in mgr.get_room("town").get_player_ids()


def test_room_manager_transfer_to_unloaded():
    mgr = RoomManager()
    mgr.load_room(_make_mock_room_db("town"))
    entity = _make_entity()
    mgr.get_room("town").add_entity(entity)

    result = mgr.transfer_entity(entity, "town", "nonexistent")
    assert result is None
