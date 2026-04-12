"""Tests for persistence repositories."""
import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from server.core.database import Base


@pytest.fixture
async def db_session():
    """In-memory SQLite session with all tables created."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=True)
    import server.combat.cards.models  # noqa: F401
    import server.player.models  # noqa: F401
    import server.room.models  # noqa: F401
    import server.room.spawn_models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


# --- PlayerRepo tests ---


async def test_player_create(db_session):
    from server.player import repo as player_repo

    player = await player_repo.create(db_session, "alice", "hash123", "spawn_room")
    assert player.id is not None
    assert player.username == "alice"
    assert player.current_room_id == "spawn_room"


async def test_player_get_by_username(db_session):
    from server.player import repo as player_repo

    await player_repo.create(db_session, "bob", "hash456")
    found = await player_repo.get_by_username(db_session, "bob")
    assert found is not None
    assert found.username == "bob"

    missing = await player_repo.get_by_username(db_session, "nobody")
    assert missing is None


async def test_player_get_by_id(db_session):
    from server.player import repo as player_repo

    player = await player_repo.create(db_session, "charlie", "hash789")
    found = await player_repo.get_by_id(db_session, player.id)
    assert found is not None
    assert found.username == "charlie"

    missing = await player_repo.get_by_id(db_session, 9999)
    assert missing is None


async def test_player_save(db_session):
    from server.player import repo as player_repo

    player = await player_repo.create(db_session, "dave", "hashxyz")
    player.stats = {"hp": 50}
    saved = await player_repo.save(db_session, player)
    assert saved.stats == {"hp": 50}

    reloaded = await player_repo.get_by_id(db_session, player.id)
    assert reloaded.stats == {"hp": 50}


async def test_player_update_position(db_session):
    from server.player import repo as player_repo

    player = await player_repo.create(db_session, "eve", "hash000")
    await player_repo.update_position(db_session, player.id, "forest", 10, 20)

    reloaded = await player_repo.get_by_id(db_session, player.id)
    assert reloaded.current_room_id == "forest"
    assert reloaded.position_x == 10
    assert reloaded.position_y == 20


# --- RoomRepo tests ---


async def test_room_upsert_and_get_by_key(db_session):
    from server.room import repo as room_repo
    from server.room.models import Room

    room = Room(
        room_key="cave",
        name="Dark Cave",
        width=10,
        height=10,
        tile_data=[[0, 0], [0, 0]],
    )
    persisted = await room_repo.upsert_room(db_session, room)
    assert persisted.id is not None

    found = await room_repo.get_by_key(db_session, "cave")
    assert found is not None
    assert found.name == "Dark Cave"

    # Update via upsert
    updated_room = Room(
        room_key="cave",
        name="Bright Cave",
        schema_version=1,
        width=10,
        height=10,
        tile_data=[[1, 1], [1, 1]],
        exits=[],
        objects=[],
        spawn_points=[],
    )
    result = await room_repo.upsert_room(db_session, updated_room)
    assert result.name == "Bright Cave"
    assert result.tile_data == [[1, 1], [1, 1]]


async def test_room_state_save_and_get(db_session):
    from server.room import repo as room_repo
    from server.room.models import RoomState

    state = RoomState(
        room_key="cave",
        dynamic_state={"lever_1": "on"},
    )
    saved = await room_repo.save_state(db_session, state)
    assert saved.id is not None

    found = await room_repo.get_state(db_session, "cave")
    assert found is not None
    assert found.dynamic_state == {"lever_1": "on"}


# --- JsonRoomProvider tests ---


async def test_json_room_provider(db_session, tmp_path):
    from server.room import repo as room_repo
    from server.room.provider import JsonRoomProvider

    # Create a temp room JSON
    room_data = {
        "room_key": "temp_room",
        "name": "Temp Room",
        "schema_version": 1,
        "width": 3,
        "height": 3,
        "tile_data": [[0, 0, 0], [0, 0, 0], [0, 0, 0]],
        "exits": [],
        "objects": [],
        "spawn_points": [{"type": "player", "x": 1, "y": 1}],
    }
    json_file = tmp_path / "temp_room.json"
    json_file.write_text(json.dumps(room_data))

    provider = JsonRoomProvider(rooms_dir=tmp_path)
    rooms = await provider.load_rooms(db_session)
    assert len(rooms) == 1
    assert rooms[0].room_key == "temp_room"
    assert rooms[0].name == "Temp Room"

    # Verify persisted to DB
    found = await room_repo.get_by_key(db_session, "temp_room")
    assert found is not None
    assert found.width == 3


# --- CardRepo tests ---


async def test_card_load_from_json_and_queries(db_session, tmp_path):
    from server.combat.cards import card_repo

    card_data = [
        {
            "card_key": "fireball",
            "name": "Fireball",
            "cost": 3,
            "effects": [{"type": "damage", "subtype": "fire", "value": 15}],
            "description": "Hurls fire.",
        },
        {
            "card_key": "heal",
            "name": "Heal",
            "cost": 2,
            "effects": [{"type": "heal", "value": 10}],
            "description": "Restores HP.",
        },
    ]
    json_file = tmp_path / "cards.json"
    json_file.write_text(json.dumps(card_data))

    cards = await card_repo.load_cards_from_json(db_session, json_file)
    assert len(cards) == 2

    # get_by_key
    fb = await card_repo.get_by_key(db_session, "fireball")
    assert fb is not None
    assert fb.name == "Fireball"
    assert fb.cost == 3
    assert fb.effects[0]["type"] == "damage"

    # get_all
    all_cards = await card_repo.get_all(db_session)
    assert len(all_cards) == 2

    # missing key
    missing = await card_repo.get_by_key(db_session, "nonexistent")
    assert missing is None

    # upsert existing card
    card_data[0]["name"] = "Greater Fireball"
    json_file.write_text(json.dumps(card_data))
    updated = await card_repo.load_cards_from_json(db_session, json_file)
    assert updated[0].name == "Greater Fireball"
