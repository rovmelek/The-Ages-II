"""Authentication handlers for WebSocket clients."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import WebSocket

from server.items import item_repo
from server.items.inventory import Inventory
from server.items.item_def import ItemDef
from server.net.auth_middleware import requires_auth
from server.net.schemas import with_request_id
from server.player import repo as player_repo
from server.core.config import settings
from server.core.xp import get_pending_level_ups, send_level_up_available
from server.player.auth import hash_password, verify_password
from server.player.session import PlayerSession
from server.player.entity import PlayerEntity
from server.room import repo as room_repo

if TYPE_CHECKING:
    from server.app import Game

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Login helpers
# ---------------------------------------------------------------------------


def _default_stats() -> dict[str, int]:
    """Build default stats from current settings.

    Function (not constant) to support test monkeypatching — reads settings.*
    on each call so patched values are always reflected (ADR-16-7).
    """
    return {
        "hp": settings.DEFAULT_BASE_HP, "max_hp": settings.DEFAULT_BASE_HP,
        "attack": settings.DEFAULT_ATTACK, "xp": 0, "level": 1,
        "strength": settings.DEFAULT_STAT_VALUE, "dexterity": settings.DEFAULT_STAT_VALUE,
        "constitution": settings.DEFAULT_STAT_VALUE, "intelligence": settings.DEFAULT_STAT_VALUE,
        "wisdom": settings.DEFAULT_STAT_VALUE, "charisma": settings.DEFAULT_STAT_VALUE,
    }


async def _resolve_stats(player, session) -> dict:
    """Resolve player stats: apply defaults for first-time, restore for returning."""
    db_stats = player.stats or {}
    if not db_stats:
        stats = _default_stats()
        stats["max_hp"] = settings.DEFAULT_BASE_HP + stats["constitution"] * settings.CON_HP_PER_POINT
        stats["hp"] = stats["max_hp"]
        await player_repo.update_stats(session, player.id, stats)
    else:
        stats = {**_default_stats(), **db_stats}
    return stats


async def _resolve_room_and_place(entity, player, room_key: str, game, session):
    """Load room if needed, find safe spawn position, update DB if relocated.

    Raises ValueError if the room cannot be found.
    """
    room = game.room_manager.get_room(room_key)
    if room is None:
        room_db = await room_repo.get_by_key(session, room_key)
        if room_db is None:
            raise ValueError("Room not found")
        room = game.room_manager.load_room(room_db)

    is_first_login = player.current_room_id is None
    needs_relocation = is_first_login or not room.is_walkable(entity.x, entity.y)
    if needs_relocation:
        sx, sy = room.get_player_spawn()
        if not room.is_walkable(sx, sy):
            sx, sy = room.find_first_walkable()
        if not room.is_walkable(sx, sy):
            logger.warning(
                "Room %s has no walkable tile; placing %s at (%d, %d)",
                room_key, entity.name, sx, sy,
            )
        entity.x = sx
        entity.y = sy
        await player_repo.update_position(session, player.id, room_key, sx, sy)
    return room_key, room


async def _hydrate_inventory(player, session) -> Inventory:
    """Rebuild runtime Inventory from DB state."""
    db_inventory = player.inventory or {}
    if db_inventory:
        all_items = await item_repo.get_all(session)
        item_defs = {i.item_key: ItemDef.from_db(i) for i in all_items}
        return Inventory.from_dict(db_inventory, lambda k: item_defs.get(k))
    return Inventory()


def _build_login_response(
    db_id: int, entity_id: str, username: str, stats: dict,
    session_token: str | None = None,
) -> dict:
    """Construct the login_success JSON payload.

    Takes field parameters (not Player DB model) so it works for both
    handle_login and future handle_reconnect (Story 16.9).
    """
    result = {
        "type": "login_success",
        "player_id": db_id,
        "entity_id": entity_id,
        "username": username,
        "stats": {
            "hp": stats.get("hp", settings.DEFAULT_BASE_HP),
            "max_hp": stats.get("max_hp", settings.DEFAULT_BASE_HP),
            "attack": stats.get("attack", settings.DEFAULT_ATTACK),
            "xp": stats.get("xp", 0),
            "level": stats.get("level", 1),
            "xp_for_next_level": stats.get("level", 1) * settings.XP_LEVEL_THRESHOLD_MULTIPLIER,
            "xp_for_current_level": (stats.get("level", 1) - 1) * settings.XP_LEVEL_THRESHOLD_MULTIPLIER,
            "strength": stats.get("strength", settings.DEFAULT_STAT_VALUE),
            "dexterity": stats.get("dexterity", settings.DEFAULT_STAT_VALUE),
            "constitution": stats.get("constitution", settings.DEFAULT_STAT_VALUE),
            "intelligence": stats.get("intelligence", settings.DEFAULT_STAT_VALUE),
            "wisdom": stats.get("wisdom", settings.DEFAULT_STAT_VALUE),
            "charisma": stats.get("charisma", settings.DEFAULT_STAT_VALUE),
        },
    }
    if session_token is not None:
        result["session_token"] = session_token
    return result


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
        await websocket.send_json(
            with_request_id({
                "type": "login_success",
                "player_id": player.id,
                "entity_id": f"player_{player.id}",
                "username": player.username,
                "stats": {
                    "hp": default_max_hp,
                    "max_hp": default_max_hp,
                    "attack": settings.DEFAULT_ATTACK,
                    "xp": 0,
                    "level": 1,
                    "xp_for_next_level": 1 * settings.XP_LEVEL_THRESHOLD_MULTIPLIER,
                    "xp_for_current_level": 0,
                    "strength": settings.DEFAULT_STAT_VALUE,
                    "dexterity": settings.DEFAULT_STAT_VALUE,
                    "constitution": settings.DEFAULT_STAT_VALUE,
                    "intelligence": settings.DEFAULT_STAT_VALUE,
                    "wisdom": settings.DEFAULT_STAT_VALUE,
                    "charisma": settings.DEFAULT_STAT_VALUE,
                },
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
        stats = await _resolve_stats(player, session)
        entity = PlayerEntity(
            id=entity_id, name=player.username,
            x=player.position_x, y=player.position_y,
            player_db_id=player.id, stats=stats,
        )
        room_key = player.current_room_id or settings.DEFAULT_SPAWN_ROOM
        try:
            room_key, room = await _resolve_room_and_place(entity, player, room_key, game, session)
        except ValueError:
            await websocket.send_json(with_request_id({"type": "error", "detail": "Room not found"}, data))
            return
        room.add_entity(entity)
        game.connection_manager.connect(entity_id, websocket, room_key, name=player.username)
        inventory = await _hydrate_inventory(player, session)
        visited_rooms = player.visited_rooms or []
        if room_key not in visited_rooms:
            visited_rooms.append(room_key)
        game.player_manager.set_session(entity_id, PlayerSession(
            entity=entity, room_key=room_key, db_id=player.id,
            inventory=inventory, visited_rooms=set(visited_rooms), pending_level_ups=0,
        ))
        token = game.token_store.issue(player.id)
        await websocket.send_json(with_request_id(_build_login_response(player.id, entity_id, player.username, stats, session_token=token), data))
        await websocket.send_json({"type": "room_state", **room.get_state()})
        await game.connection_manager.broadcast_to_room(
            room_key,
            {"type": "entity_entered", "entity": {
                "id": entity.id, "name": entity.name,
                "x": entity.x, "y": entity.y, "level": stats.get("level", 1),
            }},
            exclude=entity_id,
        )
        pending = get_pending_level_ups(stats)
        if pending > 0:
            player_session = game.player_manager.get_session(entity_id)
            if player_session:
                player_session.pending_level_ups = pending
            await send_level_up_available(entity_id, entity, game)
        # Start heartbeat after successful login (AC #1, #11)
        game._start_heartbeat(entity_id)


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

        stats = await _resolve_stats(player, session)
        entity = PlayerEntity(
            id=entity_id, name=player.username,
            x=player.position_x, y=player.position_y,
            player_db_id=player.id, stats=stats,
        )
        room_key = player.current_room_id or settings.DEFAULT_SPAWN_ROOM
        try:
            room_key, room = await _resolve_room_and_place(
                entity, player, room_key, game, session
            )
        except ValueError:
            await websocket.send_json(
                with_request_id({"type": "error", "detail": "Room not found"}, data)
            )
            return
        room.add_entity(entity)
        game.connection_manager.connect(
            entity_id, websocket, room_key, name=player.username
        )
        inventory = await _hydrate_inventory(player, session)
        visited_rooms = player.visited_rooms or []
        if room_key not in visited_rooms:
            visited_rooms.append(room_key)
        game.player_manager.set_session(entity_id, PlayerSession(
            entity=entity, room_key=room_key, db_id=player.id,
            inventory=inventory, visited_rooms=set(visited_rooms),
            pending_level_ups=0,
        ))
        await websocket.send_json(
            with_request_id(
                _build_login_response(
                    player.id, entity_id, player.username, stats,
                    session_token=new_token,
                ),
                data,
            )
        )
        await websocket.send_json({"type": "room_state", **room.get_state()})
        await game.connection_manager.broadcast_to_room(
            room_key,
            {"type": "entity_entered", "entity": {
                "id": entity.id, "name": entity.name,
                "x": entity.x, "y": entity.y,
                "level": stats.get("level", 1),
            }},
            exclude=entity_id,
        )
        pending = get_pending_level_ups(stats)
        if pending > 0:
            player_session = game.player_manager.get_session(entity_id)
            if player_session:
                player_session.pending_level_ups = pending
            await send_level_up_available(entity_id, entity, game)
        game._start_heartbeat(entity_id)
