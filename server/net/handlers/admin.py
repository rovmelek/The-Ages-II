"""Admin REST endpoints with shared-secret authentication."""
from __future__ import annotations

import asyncio
import hmac
import logging
import os
import signal
import sys

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from server.core.config import settings

logger = logging.getLogger(__name__)

admin_router = APIRouter(prefix="/admin", tags=["admin"])


async def verify_admin_secret(request: Request) -> None:
    """FastAPI dependency: verify the admin secret from Authorization header."""
    if not settings.ADMIN_SECRET:
        logger.warning("Admin endpoints disabled — ADMIN_SECRET not configured")
        raise HTTPException(status_code=403, detail="Forbidden")

    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=403, detail="Forbidden")

    token = auth_header[len("Bearer "):]
    if not hmac.compare_digest(token, settings.ADMIN_SECRET):
        raise HTTPException(status_code=403, detail="Forbidden")


@admin_router.get("/status", dependencies=[Depends(verify_admin_secret)])
async def admin_status():
    """Admin auth verification endpoint."""
    return {"status": "ok", "admin": True}


async def _do_shutdown() -> None:
    """Background task: run Game.shutdown() then SIGTERM self to stop uvicorn."""
    from server.app import game

    await game.shutdown()
    os.kill(os.getpid(), signal.SIGTERM)


@admin_router.post("/shutdown", dependencies=[Depends(verify_admin_secret)])
async def admin_shutdown():
    """Trigger graceful server shutdown."""
    from server.app import game

    if game._shutting_down:
        return JSONResponse(
            status_code=409,
            content={"status": "already_shutting_down"},
        )

    game._shutting_down = True
    asyncio.create_task(_do_shutdown())
    return {"status": "shutting_down"}


async def _do_restart() -> None:
    """Background task: run Game.shutdown() then re-execute the server process."""
    from server.app import game

    await game.shutdown()
    os.execv(sys.executable, [sys.executable] + sys.argv)


@admin_router.post("/restart", dependencies=[Depends(verify_admin_secret)])
async def admin_restart():
    """Trigger graceful server restart."""
    from server.app import game

    if game._shutting_down:
        return JSONResponse(
            status_code=409,
            content={"status": "already_shutting_down"},
        )

    game._shutting_down = True
    asyncio.create_task(_do_restart())
    return {"status": "restarting"}
