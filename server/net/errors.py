"""Structured error codes and send_error helper for protocol/auth errors."""
from __future__ import annotations

from enum import StrEnum

from fastapi import WebSocket

from server.net.schemas import with_request_id


class ErrorCode(StrEnum):
    """Machine-readable error codes for protocol and auth-level errors."""

    INVALID_JSON = "INVALID_JSON"
    MISSING_ACTION = "MISSING_ACTION"
    UNKNOWN_ACTION = "UNKNOWN_ACTION"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    AUTH_REQUIRED = "AUTH_REQUIRED"


async def send_error(
    websocket: WebSocket,
    code: ErrorCode,
    detail: str,
    data: dict | None = None,
) -> None:
    """Send a structured error message to the client.

    Constructs {"type": "error", "code": <code>, "detail": <detail>} and
    optionally echoes request_id from *data* when provided.
    """
    response: dict = {"type": "error", "code": code.value, "detail": detail}
    if data is not None:
        with_request_id(response, data)
    await websocket.send_json(response)
