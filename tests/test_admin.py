"""Tests for admin authentication and endpoints."""
from __future__ import annotations

import sys
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from server.app import app, game


@pytest.fixture
def _set_admin_secret(monkeypatch):
    """Set ADMIN_SECRET for tests that need a valid secret."""
    monkeypatch.setenv("ADMIN_SECRET", "test-secret-123")
    from server.core.config import settings
    monkeypatch.setattr(settings, "ADMIN_SECRET", "test-secret-123")


@pytest.fixture
def _clear_admin_secret(monkeypatch):
    """Ensure ADMIN_SECRET is empty (disabled)."""
    from server.core.config import settings
    monkeypatch.setattr(settings, "ADMIN_SECRET", "")


@pytest.fixture(autouse=True)
def _reset_shutdown_flag():
    """Reset shutdown flag before each test."""
    game._shutting_down = False
    yield
    game._shutting_down = False


# --- Auth tests (Story 9.1) ---


@pytest.mark.usefixtures("_set_admin_secret")
async def test_admin_status_no_auth_header():
    """Request without Authorization header returns 403."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/admin/status")
    assert resp.status_code == 403


@pytest.mark.usefixtures("_set_admin_secret")
async def test_admin_status_wrong_secret():
    """Request with wrong secret returns 403."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/admin/status",
            headers={"Authorization": "Bearer wrong-secret"},
        )
    assert resp.status_code == 403


@pytest.mark.usefixtures("_set_admin_secret")
async def test_admin_status_correct_secret():
    """Request with correct secret returns 200."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/admin/status",
            headers={"Authorization": "Bearer test-secret-123"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["admin"] is True


@pytest.mark.usefixtures("_clear_admin_secret")
async def test_admin_status_secret_not_configured(caplog):
    """When ADMIN_SECRET is empty, all requests are rejected with 403 and a warning is logged."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with caplog.at_level("WARNING", logger="server.net.handlers.admin"):
            resp = await client.get(
                "/admin/status",
                headers={"Authorization": "Bearer anything"},
            )
    assert resp.status_code == 403
    assert "Admin endpoints disabled" in caplog.text


@pytest.mark.usefixtures("_set_admin_secret")
async def test_admin_status_bearer_prefix_required():
    """Authorization header without 'Bearer ' prefix is rejected."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/admin/status",
            headers={"Authorization": "test-secret-123"},
        )
    assert resp.status_code == 403


# --- Shutdown tests (Story 9.2) ---


@pytest.mark.usefixtures("_set_admin_secret")
async def test_shutdown_returns_shutting_down():
    """POST /admin/shutdown with valid secret returns 200 and shutting_down status."""
    with patch("server.net.handlers.admin._do_shutdown", new_callable=AsyncMock):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/admin/shutdown",
                headers={"Authorization": "Bearer test-secret-123"},
            )
    assert resp.status_code == 200
    assert resp.json() == {"status": "shutting_down"}


@pytest.mark.usefixtures("_set_admin_secret")
async def test_shutdown_already_in_progress():
    """POST /admin/shutdown when already shutting down returns 409."""
    game._shutting_down = True
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/admin/shutdown",
            headers={"Authorization": "Bearer test-secret-123"},
        )
    assert resp.status_code == 409
    assert resp.json() == {"status": "already_shutting_down"}


@pytest.mark.usefixtures("_set_admin_secret")
async def test_shutdown_without_auth():
    """POST /admin/shutdown without auth returns 403."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/admin/shutdown")
    assert resp.status_code == 403


@pytest.mark.usefixtures("_set_admin_secret")
async def test_shutdown_calls_game_shutdown():
    """Shutdown endpoint triggers game.shutdown() via background task."""
    mock_shutdown = AsyncMock()
    with patch.object(game, "shutdown", mock_shutdown), \
         patch("server.net.handlers.admin.os.kill"):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/admin/shutdown",
                headers={"Authorization": "Bearer test-secret-123"},
            )
        assert resp.status_code == 200

        # Allow background task to run
        import asyncio
        await asyncio.sleep(0.1)

        mock_shutdown.assert_called_once()


@pytest.mark.usefixtures("_set_admin_secret")
async def test_shutdown_sets_flag():
    """Shutdown endpoint sets _shutting_down flag to True."""
    assert game._shutting_down is False
    with patch("server.net.handlers.admin._do_shutdown", new_callable=AsyncMock):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/admin/shutdown",
                headers={"Authorization": "Bearer test-secret-123"},
            )
    assert game._shutting_down is True


# --- Restart tests (Story 9.3) ---


@pytest.mark.usefixtures("_set_admin_secret")
async def test_restart_returns_restarting():
    """POST /admin/restart with valid secret returns 200 and restarting status."""
    with patch("server.net.handlers.admin._do_restart", new_callable=AsyncMock):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/admin/restart",
                headers={"Authorization": "Bearer test-secret-123"},
            )
    assert resp.status_code == 200
    assert resp.json() == {"status": "restarting"}


@pytest.mark.usefixtures("_set_admin_secret")
async def test_restart_already_in_progress():
    """POST /admin/restart when already shutting down returns 409."""
    game._shutting_down = True
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/admin/restart",
            headers={"Authorization": "Bearer test-secret-123"},
        )
    assert resp.status_code == 409
    assert resp.json() == {"status": "already_shutting_down"}


@pytest.mark.usefixtures("_set_admin_secret")
async def test_restart_without_auth():
    """POST /admin/restart without auth returns 403."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/admin/restart")
    assert resp.status_code == 403


@pytest.mark.usefixtures("_set_admin_secret")
async def test_restart_calls_game_shutdown_then_execv():
    """Restart endpoint calls game.shutdown() then os.execv() to re-execute."""
    mock_shutdown = AsyncMock()
    with patch.object(game, "shutdown", mock_shutdown), \
         patch("server.net.handlers.admin.os.execv") as mock_execv:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/admin/restart",
                headers={"Authorization": "Bearer test-secret-123"},
            )
        assert resp.status_code == 200

        # Allow background task to run
        import asyncio
        await asyncio.sleep(0.1)

        mock_shutdown.assert_called_once()
        mock_execv.assert_called_once_with(
            sys.executable, [sys.executable] + sys.argv
        )


@pytest.mark.usefixtures("_set_admin_secret")
async def test_restart_sets_flag():
    """Restart endpoint sets _shutting_down flag to True."""
    assert game._shutting_down is False
    with patch("server.net.handlers.admin._do_restart", new_callable=AsyncMock):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/admin/restart",
                headers={"Authorization": "Bearer test-secret-123"},
            )
    assert game._shutting_down is True
