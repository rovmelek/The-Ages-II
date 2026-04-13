"""Authentication handlers for WebSocket clients."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import WebSocket

from server.core.config import settings
from server.core.constants import PROTOCOL_VERSION
from server.net.auth_middleware import requires_auth
from server.net.schemas import with_request_id
from server.player import repo as player_repo
from server.player.auth import hash_password, verify_password
from server.core.xp import get_pending_level_ups, send_level_up_available
from server.player.service import (
    _build_login_response,
    _default_stats,
    build_stats_payload,
    setup_full_session,
)
from server.player.session import PlayerSession

if TYPE_CHECKING:
    from server.app import Game

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


@requires_auth
async def handle_logout(
    websocket: WebSocket, data: dict, *, game: Game,
    entity_id: str, player_info: PlayerSession,
) -> None:
    """Handle the 'logout' action: save state, clean up, keep WebSocket open."""
    game.token_store.revoke_for_player(player_info.db_id)
    game._cancel_heartbeat(entity_id)
    await game.player_manager.cleanup_session(entity_id, game)

    # Send confirmation via raw websocket (connection_manager already cleared)
    try:
        await websocket.send_json(with_request_id({"type": "logged_out"}, data))
    except Exception:
        pass  # Network dropped — cleanup already done


@requires_auth
async def handle_pong(
    websocket: WebSocket, data: dict, *, game: Game,
    entity_id: str, player_info: PlayerSession,
) -> None:
    """Handle 'pong' — heartbeat response, signals the pong event."""
    event = game._pong_events.get(entity_id)
    if event:
        event.set()


async def handle_register(websocket: WebSocket, data: dict, *, game: Game) -> None:
    """Handle the 'register' action: create a new player account."""
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if len(username) < settings.MIN_USERNAME_LENGTH:
        await websocket.send_json(
            with_request_id({"type": "error", "detail": f"Username must be at least {settings.MIN_USERNAME_LENGTH} characters"}, data)
        )
        return
    if len(password) < settings.MIN_PASSWORD_LENGTH:
        await websocket.send_json(
            with_request_id({"type": "error", "detail": f"Password must be at least {settings.MIN_PASSWORD_LENGTH} characters"}, data)
        )
        return

    async with game.transaction() as session:
        existing = await player_repo.get_by_username(session, username)
        if existing:
            await websocket.send_json(
                with_request_id({"type": "error", "detail": "Username already taken"}, data)
            )
            return

        hashed = hash_password(password)
        player = await player_repo.create(session, username, hashed)

        default_max_hp = settings.DEFAULT_BASE_HP + settings.DEFAULT_STAT_VALUE * settings.CON_HP_PER_POINT
        stats = _default_stats()
        stats["hp"] = default_max_hp
        stats["max_hp"] = default_max_hp
        await websocket.send_json(
            with_request_id({
                "type": "login_success",
                "protocol_version": PROTOCOL_VERSION,
                "player_id": player.id,
                "entity_id": f"player_{player.id}",
                "username": player.username,
                "stats": build_stats_payload(stats),
            }, data)
        )


async def _kick_old_session(entity_id: str, old_ws: WebSocket, game: Game) -> None:
    """Kick an existing session: save state, clean up, close old WebSocket."""
    game._cancel_heartbeat(entity_id)
    await game.player_manager.cleanup_session(entity_id, game)

    # Notify and close old WebSocket (best-effort)
    try:
        await old_ws.send_json(
            {"type": "kicked", "reason": "Logged in from another location"}
        )
    except Exception:
        pass
    try:
        await old_ws.close(code=1000)
    except Exception:
        pass


async def handle_login(websocket: WebSocket, data: dict, *, game: Game) -> None:
    """Handle the 'login' action: authenticate and place player in room."""
    username = data.get("username", "").strip()
    password = data.get("password", "")
    async with game.transaction() as session:
        player = await player_repo.get_by_username(session, username)
        if player is None or not verify_password(password, player.password_hash):
            await websocket.send_json(with_request_id({"type": "error", "detail": "Invalid username or password"}, data))
            return
        entity_id = f"player_{player.id}"
        # Check for grace-period session (WS gone, session still alive)
        existing_session = game.player_manager.get_session(entity_id)
        if existing_session is not None and game.connection_manager.get_websocket(entity_id) is None:
            cleanup_handle = game._cleanup_handles.pop(entity_id, None)
            if cleanup_handle is not None:
                cleanup_handle.cancel()
            game._cancel_heartbeat(entity_id)
            await game.player_manager.cleanup_session(entity_id, game)
        # Handle existing session for this account (active WebSocket)
        old_ws = game.connection_manager.get_websocket(entity_id)
        if old_ws is not None:
            if old_ws is websocket:
                await game.player_manager.cleanup_session(entity_id, game)
            else:
                await _kick_old_session(entity_id, old_ws, game)

        token = game.token_store.issue(player.id)
        if not await setup_full_session(
            websocket=websocket, player=player, session=session,
            game=game, session_token=token, data=data,
        ):
            return


async def handle_reconnect(websocket: WebSocket, data: dict, *, game: Game) -> None:
    """Handle the 'reconnect' action: validate token, restore session."""
    token = data.get("session_token", "")
    if not token:
        await websocket.send_json(
            with_request_id({"type": "error", "detail": "Missing session_token"}, data)
        )
        return

    db_id = game.token_store.validate(token)
    if db_id is None:
        await websocket.send_json(
            with_request_id({"type": "error", "detail": "Invalid or expired token"}, data)
        )
        return

    # Consume old token, issue new one
    game.token_store.revoke(token)
    entity_id = f"player_{db_id}"
    new_token = game.token_store.issue(db_id)

    # Security: if WebSocket already has a different player logged in, clean up first
    existing_entity = game.connection_manager.get_entity_id(websocket)
    if existing_entity is not None and existing_entity != entity_id:
        game._cancel_heartbeat(existing_entity)
        await game.player_manager.cleanup_session(existing_entity, game)

    # Check for Case 1: grace period resume (disconnected session still in memory)
    existing_session = game.player_manager.get_session(entity_id)

    if existing_session and existing_session.disconnected_at is not None:
        # Case 1: Cancel deferred cleanup, restore connection
        handle = game._cleanup_handles.pop(entity_id, None)
        if handle is not None:
            handle.cancel()

        # Re-check session after cancelling (race condition: timer may have fired)
        existing_session = game.player_manager.get_session(entity_id)
        if existing_session is None:
            # Session was cleaned up by timer — fall through to Case 2
            pass
        else:
            existing_session.disconnected_at = None
            existing_session.entity.connected = True
            game.connection_manager.connect(
                entity_id, websocket, existing_session.room_key,
                name=existing_session.entity.name,
            )
            room = game.room_manager.get_room(existing_session.room_key)
            await websocket.send_json(
                with_request_id(
                    _build_login_response(
                        existing_session.db_id, entity_id,
                        existing_session.entity.name,
                        existing_session.entity.stats,
                        session_token=new_token,
                    ),
                    data,
                )
            )
            if room:
                await websocket.send_json({"type": "room_state", **room.get_state()})
            # Broadcast entity_entered to room
            await game.connection_manager.broadcast_to_room(
                existing_session.room_key,
                {"type": "entity_entered", "entity": {
                    "id": entity_id,
                    "name": existing_session.entity.name,
                    "x": existing_session.entity.x,
                    "y": existing_session.entity.y,
                    "level": existing_session.entity.stats.get("level", 1),
                }},
                exclude=entity_id,
            )
            # Send combat state if in combat
            combat_instance = game.combat_manager.get_player_instance(entity_id)
            if combat_instance:
                await websocket.send_json(
                    {"type": "combat_update", **combat_instance.get_state()}
                )
            pending = get_pending_level_ups(existing_session.entity.stats)
            if pending > 0:
                existing_session.pending_level_ups = pending
                await send_level_up_available(entity_id, existing_session.entity, game)
            # Check if client is up to date on sequenced messages
            last_seq = data.get("last_seq")
            if last_seq is not None:
                current_seq = game.connection_manager.get_msg_seq(entity_id)
                if last_seq == current_seq:
                    await websocket.send_json(
                        with_request_id({"type": "seq_status", "status": "up_to_date"}, data)
                    )
            game._start_heartbeat(entity_id)
            return

    # Case 2: Full DB restore (no session exists or disconnected_at is None)
    async with game.transaction() as session:
        player = await player_repo.get_by_id(session, db_id)
        if player is None:
            await websocket.send_json(
                with_request_id({"type": "error", "detail": "Player not found"}, data)
            )
            return

        # Handle existing active session for this account (kick old)
        old_ws = game.connection_manager.get_websocket(entity_id)
        if old_ws is not None:
            if old_ws is websocket:
                await game.player_manager.cleanup_session(entity_id, game)
            else:
                await _kick_old_session(entity_id, old_ws, game)

        if not await setup_full_session(
            websocket=websocket, player=player, session=session,
            game=game, session_token=new_token, data=data,
        ):
            return
