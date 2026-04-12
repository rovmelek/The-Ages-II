from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context

from server.core.config import settings
from server.core.database import Base

# Import all model modules so Base.metadata discovers them
import server.combat.cards.models  # noqa: F401
import server.items.models  # noqa: F401
import server.player.models  # noqa: F401
import server.room.models  # noqa: F401
import server.room.spawn_models  # noqa: F401

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_url() -> str:
    """Return the database URL: prefer config override, fall back to settings."""
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url
    return settings.ALEMBIC_DATABASE_URL


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = _get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = create_engine(
        _get_url(),
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
