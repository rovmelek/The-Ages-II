"""Tests for player registration (Story 1.6)."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from server.core.database import Base
from server.player.auth import hash_password, verify_password
from server.player.models import Player


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def async_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(async_engine):
    session_factory = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest.fixture
def test_session_factory(async_engine):
    """Return an async_sessionmaker bound to the in-memory engine."""
    return async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )


@pytest.fixture
def client(test_session_factory):
    """TestClient with session_factory set to use in-memory DB."""
    from server.app import app, game

    original_sf = game.session_factory
    with TestClient(app) as c:
        game.session_factory = test_session_factory
        yield c
    game.session_factory = original_sf


# ---------------------------------------------------------------------------
# Unit tests: hash_password / verify_password
# ---------------------------------------------------------------------------

def test_hash_password_returns_string():
    hashed = hash_password("secret123")
    assert isinstance(hashed, str)
    assert hashed != "secret123"


def test_verify_password_correct():
    hashed = hash_password("secret123")
    assert verify_password("secret123", hashed) is True


def test_verify_password_wrong():
    hashed = hash_password("secret123")
    assert verify_password("wrong", hashed) is False


# ---------------------------------------------------------------------------
# Integration tests: handle_register via WebSocket
# ---------------------------------------------------------------------------

def test_register_success(client):
    with client.websocket_connect("/ws/game") as ws:
        ws.send_json({"action": "register", "username": "hero", "password": "secret123"})
        resp = ws.receive_json()
        assert resp["type"] == "login_success"
        assert resp["username"] == "hero"
        assert "player_id" in resp


def test_register_returns_player_id(client):
    with client.websocket_connect("/ws/game") as ws:
        ws.send_json({"action": "register", "username": "alice", "password": "password1"})
        resp = ws.receive_json()
        assert isinstance(resp["player_id"], int)
        assert resp["player_id"] > 0


def test_register_stores_bcrypt_hash(client, test_session_factory):
    import asyncio
    from sqlalchemy import select

    with client.websocket_connect("/ws/game") as ws:
        ws.send_json({"action": "register", "username": "bob", "password": "mypassword"})
        ws.receive_json()

    async def check():
        async with test_session_factory() as session:
            result = await session.execute(
                select(Player).where(Player.username == "bob")
            )
            player = result.scalar_one()
            assert player.password_hash != "mypassword"
            assert verify_password("mypassword", player.password_hash)

    asyncio.run(check())


def test_register_username_too_short(client):
    with client.websocket_connect("/ws/game") as ws:
        ws.send_json({"action": "register", "username": "ab", "password": "secret123"})
        resp = ws.receive_json()
        assert resp["type"] == "error"
        assert resp["detail"] == "Username must be at least 3 characters"


def test_register_username_empty(client):
    with client.websocket_connect("/ws/game") as ws:
        ws.send_json({"action": "register", "username": "", "password": "secret123"})
        resp = ws.receive_json()
        assert resp["type"] == "error"
        assert "username" in resp["detail"].lower()


def test_register_password_too_short(client):
    with client.websocket_connect("/ws/game") as ws:
        ws.send_json({"action": "register", "username": "hero", "password": "abc"})
        resp = ws.receive_json()
        assert resp["type"] == "error"
        assert resp["detail"] == "Password must be at least 6 characters"


def test_register_password_empty(client):
    with client.websocket_connect("/ws/game") as ws:
        ws.send_json({"action": "register", "username": "hero", "password": ""})
        resp = ws.receive_json()
        assert resp["type"] == "error"
        assert "password" in resp["detail"].lower()


def test_register_duplicate_username(client):
    with client.websocket_connect("/ws/game") as ws:
        ws.send_json({"action": "register", "username": "taken", "password": "secret123"})
        resp = ws.receive_json()
        assert resp["type"] == "login_success"

    with client.websocket_connect("/ws/game") as ws:
        ws.send_json({"action": "register", "username": "taken", "password": "other456"})
        resp = ws.receive_json()
        assert resp["type"] == "error"
        assert resp["detail"] == "Username already taken"


# ---------------------------------------------------------------------------
# Stats in login_success (Story 10.8)
# ---------------------------------------------------------------------------

def test_register_login_success_includes_stats(client):
    """Register login_success should include default stats with ability scores."""
    with client.websocket_connect("/ws/game") as ws:
        ws.send_json({"action": "register", "username": "statplayer", "password": "secret123"})
        resp = ws.receive_json()
        assert resp["type"] == "login_success"
        assert "stats" in resp
        stats = resp["stats"]
        assert stats["hp"] == 105  # 100 + CON(1) * 5
        assert stats["max_hp"] == 105
        assert stats["attack"] == 10
        assert stats["xp"] == 0
        assert stats["level"] == 1
        assert stats["strength"] == 1
        assert stats["dexterity"] == 1
        assert stats["constitution"] == 1
        assert stats["intelligence"] == 1
        assert stats["wisdom"] == 1
        assert stats["charisma"] == 1


def test_login_success_includes_stats(client):
    """Login login_success should include persisted player stats with ability scores."""
    # Register first
    with client.websocket_connect("/ws/game") as ws:
        ws.send_json({"action": "register", "username": "loginstats", "password": "secret123"})
        ws.receive_json()

    # Login — first-time, so CON-derived max_hp applied
    with client.websocket_connect("/ws/game") as ws:
        ws.send_json({"action": "login", "username": "loginstats", "password": "secret123"})
        resp = ws.receive_json()
        assert resp["type"] == "login_success"
        assert "stats" in resp
        stats = resp["stats"]
        assert stats["hp"] == 105  # 100 + CON(1) * 5
        assert stats["max_hp"] == 105
        assert stats["attack"] == 10
        assert stats["xp"] == 0
        assert stats["level"] == 1
        assert stats["strength"] == 1
        assert stats["constitution"] == 1
