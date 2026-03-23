"""Tests for database engine, models, and init_db."""
import pytest
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from server.core.database import Base


@pytest.fixture
async def db_engine():
    """Create an in-memory async engine with all tables."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=True)
    # Import all models so Base.metadata knows about them
    import server.combat.cards.models  # noqa: F401
    import server.items.models  # noqa: F401
    import server.player.models  # noqa: F401
    import server.room.models  # noqa: F401
    import server.room.spawn_models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine):
    """Yield an async session bound to the test engine."""
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


async def test_init_db_creates_all_tables(db_engine):
    """Verify init_db creates all expected tables."""
    expected_tables = {
        "players",
        "rooms",
        "room_states",
        "player_object_states",
        "cards",
        "spawn_checkpoints",
        "items",
    }
    async with db_engine.connect() as conn:
        table_names = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
    assert expected_tables == set(table_names)


async def test_player_insert_and_query(db_session):
    """Verify a Player can be inserted and queried back."""
    from server.player.models import Player

    player = Player(
        username="testplayer",
        password_hash="fakehash123",
        stats={"hp": 100, "max_hp": 100, "attack": 10, "defense": 5, "xp": 0, "level": 1},
        current_room_id="spawn_room",
        position_x=5,
        position_y=10,
    )
    db_session.add(player)
    await db_session.commit()

    result = await db_session.execute(select(Player).where(Player.username == "testplayer"))
    loaded = result.scalar_one()

    assert loaded.username == "testplayer"
    assert loaded.password_hash == "fakehash123"
    assert loaded.stats["hp"] == 100
    assert loaded.current_room_id == "spawn_room"
    assert loaded.position_x == 5
    assert loaded.position_y == 10
    assert loaded.inventory == {}
    assert loaded.card_collection == []
