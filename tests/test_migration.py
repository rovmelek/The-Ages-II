"""Migration roundtrip test: verify alembic upgrade head == create_all schema."""
from __future__ import annotations

import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

# Import all model modules so Base.metadata discovers them
import server.combat.cards.models  # noqa: F401
import server.items.models  # noqa: F401
import server.player.models  # noqa: F401
import server.room.models  # noqa: F401
import server.room.spawn_models  # noqa: F401
from server.core.database import Base

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _get_schema(engine):
    """Extract schema info from a SQLAlchemy engine."""
    insp = inspect(engine)
    schema = {}
    for table_name in sorted(insp.get_table_names()):
        if table_name == "alembic_version":
            continue
        columns = {}
        for col in insp.get_columns(table_name):
            columns[col["name"]] = {
                "type": str(col["type"]),
                "nullable": col["nullable"],
            }
        schema[table_name] = columns
    return schema


def test_migration_matches_create_all():
    """Alembic upgrade head produces the same schema as create_all."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Database A: create_all
        db_a_path = Path(tmpdir) / "create_all.db"
        engine_a = create_engine(f"sqlite:///{db_a_path}")
        Base.metadata.create_all(engine_a)
        schema_a = _get_schema(engine_a)
        engine_a.dispose()

        # Database B: alembic upgrade head
        db_b_path = Path(tmpdir) / "alembic.db"
        alembic_cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
        alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_b_path}")
        alembic_cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
        command.upgrade(alembic_cfg, "head")

        engine_b = create_engine(f"sqlite:///{db_b_path}")
        schema_b = _get_schema(engine_b)
        engine_b.dispose()

    # Compare table names
    assert set(schema_a.keys()) == set(schema_b.keys()), (
        f"Table mismatch: create_all={sorted(schema_a.keys())}, "
        f"alembic={sorted(schema_b.keys())}"
    )

    # Compare columns per table
    for table_name in schema_a:
        cols_a = schema_a[table_name]
        cols_b = schema_b[table_name]
        assert set(cols_a.keys()) == set(cols_b.keys()), (
            f"Column mismatch in {table_name}: "
            f"create_all={sorted(cols_a.keys())}, alembic={sorted(cols_b.keys())}"
        )
        for col_name in cols_a:
            assert cols_a[col_name]["type"] == cols_b[col_name]["type"], (
                f"{table_name}.{col_name} type mismatch: "
                f"create_all={cols_a[col_name]['type']}, "
                f"alembic={cols_b[col_name]['type']}"
            )
            assert cols_a[col_name]["nullable"] == cols_b[col_name]["nullable"], (
                f"{table_name}.{col_name} nullable mismatch: "
                f"create_all={cols_a[col_name]['nullable']}, "
                f"alembic={cols_b[col_name]['nullable']}"
            )
