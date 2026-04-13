"""Game orchestrator and FastAPI application."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.responses import FileResponse

from server.core.config import settings
from server.core.constants import SPAWN_PERSISTENT
from server.core.database import init_db
from server.core import database as _database
from server.net.connection_manager import ConnectionManager
from server.net.message_router import MessageRouter
from server.net.errors import ErrorCode, send_error, sanitize_validation_error
from server.net.schemas import ACTION_SCHEMAS
from server.player import repo as player_repo
from server.player.service import find_spawn_point
from server.combat.manager import CombatManager
from server.core.effects import create_default_registry
from server.core.events import EventBus
from server.core.scheduler import Scheduler
from server.net.handlers.admin import admin_router
from server.room.manager import RoomManager
from server.room.provider import JsonRoomProvider
from server.party.manager import PartyManager
from server.player.manager import PlayerManager
from server.player.tokens import TokenStore
from server.trade.manager import TradeManager

logger = logging.getLogger(__name__)


class Game:
    """Central game orchestrator — holds all managers and state."""

    def __init__(self) -> None:
        self.router = MessageRouter()
        self.connection_manager = ConnectionManager()
        self.room_manager = RoomManager()
        self.scheduler = Scheduler()
        self.event_bus = EventBus()
        self.effect_registry = create_default_registry()
        self.combat_manager = CombatManager(effect_registry=self.effect_registry)
        self.trade_manager = TradeManager(connection_manager=self.connection_manager)
        self.party_manager = PartyManager(connection_manager=self.connection_manager)
        self.player_manager = PlayerManager()
        self.session_factory = _database.async_session
        self._shutting_down: bool = False
        self.loot_tables: dict = {}
        self.npc_templates: dict[str, dict] = {}
        self._heartbeat_tasks: dict[str, asyncio.Task] = {}
        self._pong_events: dict[str, asyncio.Event] = {}
        self.token_store = TokenStore()
        self._cleanup_handles: dict[str, asyncio.TimerHandle] = {}

    @asynccontextmanager
    async def transaction(self):
        """Yield an AsyncSession that auto-commits on success, rolls back on error."""
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def startup(self) -> None:
        """Initialize database, load data, register handlers."""
        self._shutting_down = False
        await init_db()

        # Load NPC templates first (needed before room NPC spawning)
        npcs_dir = settings.DATA_DIR / "npcs"
        if npcs_dir.exists():
            from server.room.npc import load_npc_templates

            self.npc_templates = load_npc_templates(npcs_dir)

        # Load rooms from JSON into DB, then into memory
        async with self.transaction() as session:
            provider = JsonRoomProvider()
            rooms = await provider.load_rooms(session)
            for room_db in rooms:
                self.room_manager.load_room(room_db, self.npc_templates)

        # Load cards from JSON if any card files exist
        cards_dir = settings.DATA_DIR / "cards"
        if cards_dir.exists():
            from server.combat.cards import card_repo

            async with self.transaction() as session:
                for json_file in sorted(cards_dir.glob("*.json")):
                    await card_repo.load_cards_from_json(session, json_file)

        # Load items from JSON if any item files exist
        items_dir = settings.DATA_DIR / "items"
        if items_dir.exists():
            from server.items import item_repo

            async with self.transaction() as session:
                for json_file in sorted(items_dir.glob("*.json")):
                    await item_repo.load_items_from_json(session, json_file)

        # Load loot tables from JSON (after items, since loot references item keys)
        loot_dir = settings.DATA_DIR / "loot"
        if loot_dir.exists():
            from server.items import item_repo

            self.loot_tables = item_repo.load_loot_tables(loot_dir)

        self._register_handlers()
        self._register_events()

        # Start scheduler after rooms and NPC templates are loaded
        await self.scheduler.start(self)

    async def shutdown(self) -> None:
        """Gracefully shut down: save all player states, notify, and disconnect."""
        self._shutting_down = True
        await self.scheduler.stop()

        # Cancel all pending deferred cleanup timers
        for handle in self._cleanup_handles.values():
            handle.cancel()
        self._cleanup_handles.clear()

        # Cancel all heartbeat tasks before session cleanup (AC #6)
        for entity_id in list(self._heartbeat_tasks):
            self._cancel_heartbeat(entity_id)

        player_count = 0
        for entity_id in self.player_manager.all_entity_ids():
            # Notify before cleanup (WebSocket still mapped)
            ws = self.connection_manager.get_websocket(entity_id)
            if ws:
                try:
                    await ws.send_json(
                        {"type": "server_shutdown", "reason": "Server is shutting down"}
                    )
                except Exception:
                    pass

            await self.player_manager.cleanup_session(entity_id, self)

            # Close WebSocket after cleanup
            if ws:
                try:
                    await ws.close(code=1001)
                except Exception:
                    pass

            player_count += 1

        self.player_manager.clear()
        logger.info("Shutdown complete: %d players saved and disconnected.", player_count)

    def _register_handlers(self) -> None:
        """Register all WebSocket action handlers."""
        from server.net.handlers.auth import handle_login, handle_logout, handle_pong, handle_reconnect, handle_register
        from server.net.handlers.chat import handle_chat
        from server.net.handlers.combat import (
            handle_flee,
            handle_pass_turn,
            handle_play_card,
            handle_use_item_combat,
        )
        from server.net.handlers.interact import handle_interact
        from server.net.handlers.inventory import handle_inventory, handle_use_item
        from server.net.handlers.trade import handle_trade
        from server.net.handlers.party import handle_party, handle_party_chat
        from server.net.handlers.levelup import handle_level_up
        from server.net.handlers.movement import handle_move
        from server.net.handlers.query import (
            handle_help_actions,
            handle_look,
            handle_map,
            handle_stats,
            handle_who,
        )

        handlers: dict[str, object] = {
            "login": handle_login,
            "register": handle_register,
            "logout": handle_logout,
            "move": handle_move,
            "chat": handle_chat,
            "interact": handle_interact,
            "play_card": handle_play_card,
            "pass_turn": handle_pass_turn,
            "flee": handle_flee,
            "inventory": handle_inventory,
            "use_item": handle_use_item,
            "use_item_combat": handle_use_item_combat,
            "look": handle_look,
            "who": handle_who,
            "stats": handle_stats,
            "help_actions": handle_help_actions,
            "map": handle_map,
            "level_up": handle_level_up,
            "trade": handle_trade,
            "party": handle_party,
            "party_chat": handle_party_chat,
            "pong": handle_pong,
            "reconnect": handle_reconnect,
        }

        for action, handler in handlers.items():
            self.router.register(
                action, lambda ws, d, h=handler: h(ws, d, game=self)
            )

    def _register_events(self) -> None:
        """Register event bus subscribers."""

        async def _on_rare_spawn(npc_name: str, room_name: str) -> None:
            await self.connection_manager.broadcast_to_all(
                {
                    "type": "announcement",
                    "message": f"{npc_name} has appeared in {room_name}!",
                    "format": settings.CHAT_FORMAT,
                }
            )

        self.event_bus.subscribe("rare_spawn", _on_rare_spawn)

    async def kill_npc(self, room_key: str, npc_id: str) -> None:
        """Mark an NPC as dead and schedule respawn if persistent."""
        room = self.room_manager.get_room(room_key)
        if room is None:
            return
        npc = room.get_npc(npc_id)
        if npc is None or not npc.is_alive:
            return

        npc.is_alive = False
        npc.in_combat = False

        # Schedule respawn for persistent NPCs
        tmpl = self.npc_templates.get(npc.npc_key)
        if tmpl and tmpl.get("spawn_type") == SPAWN_PERSISTENT:
            respawn_seconds = tmpl.get("spawn_config", {}).get("respawn_seconds", settings.MOB_RESPAWN_SECONDS)
            self.scheduler.schedule_respawn(room_key, npc_id, respawn_seconds)

    @staticmethod
    def _reset_player_stats(entity) -> None:
        """Clear combat flags and restore HP to max for respawn."""
        entity.in_combat = False
        entity.stats["hp"] = entity.stats.get("max_hp", settings.DEFAULT_BASE_HP)
        entity.stats.pop("shield", None)

    async def respawn_player(self, entity_id: str) -> None:
        """Respawn a defeated player in town_square with full HP."""
        player_info = self.player_manager.get_session(entity_id)
        if player_info is None:
            return

        entity = player_info.entity
        old_room_key = player_info.room_key

        self._reset_player_stats(entity)

        spawn_room_key = settings.DEFAULT_SPAWN_ROOM
        spawn_room = self.room_manager.get_room(spawn_room_key)
        if spawn_room is None:
            return  # Cannot respawn without town_square

        sx, sy = find_spawn_point(spawn_room, spawn_room_key, entity.name)

        # Save to DB FIRST (crash recovery: player placed correctly on re-login)
        try:
            async with self.transaction() as session:
                await player_repo.update_position(
                    session, entity.player_db_id, spawn_room_key, sx, sy
                )
                await player_repo.update_stats(
                    session, entity.player_db_id, entity.stats
                )
        except Exception:
            pass  # Best-effort DB save

        # In-memory room transfer
        old_room = self.room_manager.get_room(old_room_key)
        if old_room and old_room_key != spawn_room_key:
            old_room.remove_entity(entity_id)
            await self.connection_manager.broadcast_to_room(
                old_room_key,
                {"type": "entity_left", "entity_id": entity_id},
                exclude=entity_id,
            )

        entity.x = sx
        entity.y = sy
        spawn_room.add_entity(entity)
        player_info.room_key = spawn_room_key
        self.connection_manager.update_room(entity_id, spawn_room_key)

        # Send respawn + new room state to player
        ws = self.connection_manager.get_websocket(entity_id)
        if ws:
            await ws.send_json({
                "type": "respawn",
                "room_key": spawn_room_key,
                "x": sx,
                "y": sy,
                "hp": entity.stats["hp"],
                "max_hp": entity.stats["max_hp"],
            })
            await ws.send_json({"type": "room_state", **spawn_room.get_state()})

        # Notify town_square players
        await self.connection_manager.broadcast_to_room(
            spawn_room_key,
            {
                "type": "entity_entered",
                "entity": {"id": entity.id, "name": entity.name, "x": sx, "y": sy},
            },
            exclude=entity_id,
        )

    async def handle_disconnect(self, websocket: WebSocket) -> None:
        """Handle a player disconnecting: deferred cleanup with grace period."""
        entity_id = self.connection_manager.get_entity_id(websocket)
        if entity_id is None:
            return  # Unauthenticated connection, nothing to clean up

        # During shutdown, shutdown() handles all cleanup
        if self._shutting_down:
            return

        self._cancel_heartbeat(entity_id)

        session = self.player_manager.get_session(entity_id)
        if session is None:
            self.connection_manager.disconnect(entity_id)
            return

        # Disconnect WebSocket mapping but keep session alive
        self.connection_manager.disconnect(entity_id)

        # Mark as disconnected
        session.disconnected_at = time.time()
        session.entity.connected = False

        # Cancel trades immediately (can't block other players)
        await self.player_manager.cancel_trade(entity_id, self)

        # Cancel any existing deferred timer (defensive idempotency)
        old_handle = self._cleanup_handles.pop(entity_id, None)
        if old_handle is not None:
            old_handle.cancel()

        # Immediate cleanup if grace period is 0 (test mode)
        if settings.DISCONNECT_GRACE_SECONDS <= 0:
            await self.player_manager.deferred_cleanup(entity_id, self)
            return

        # Schedule deferred full cleanup
        loop = asyncio.get_running_loop()

        def _on_grace_expired():
            loop.create_task(self._deferred_cleanup(entity_id))

        handle = loop.call_later(settings.DISCONNECT_GRACE_SECONDS, _on_grace_expired)
        self._cleanup_handles[entity_id] = handle

    async def _deferred_cleanup(self, entity_id: str) -> None:
        """Run full cleanup if player hasn't reconnected within grace period."""
        self._cleanup_handles.pop(entity_id, None)

        session = self.player_manager.get_session(entity_id)
        if session is None:
            return  # Already cleaned up
        if session.disconnected_at is None:
            return  # Player reconnected

        await self.player_manager.deferred_cleanup(entity_id, self)

    def _start_heartbeat(self, entity_id: str) -> None:
        """Start a heartbeat task for a connected player."""
        self._cancel_heartbeat(entity_id)  # Cancel any existing task first
        event = asyncio.Event()
        self._pong_events[entity_id] = event
        task = asyncio.create_task(self._heartbeat_loop(entity_id))
        self._heartbeat_tasks[entity_id] = task

    def _cancel_heartbeat(self, entity_id: str) -> None:
        """Cancel and remove heartbeat task and pong event for an entity."""
        task = self._heartbeat_tasks.pop(entity_id, None)
        if task and not task.done():
            task.cancel()
        self._pong_events.pop(entity_id, None)

    async def _heartbeat_loop(self, entity_id: str) -> None:
        """Send periodic pings and close connection if pong not received."""
        try:
            while True:
                await asyncio.sleep(settings.HEARTBEAT_INTERVAL_SECONDS)
                ws = self.connection_manager.get_websocket(entity_id)
                if ws is None:
                    break
                try:
                    await ws.send_json({"type": "ping"})
                except Exception:
                    break
                event = self._pong_events.get(entity_id)
                if event is None:
                    break
                event.clear()
                try:
                    await asyncio.wait_for(
                        event.wait(),
                        timeout=settings.HEARTBEAT_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    # No pong received — close WebSocket
                    try:
                        await ws.close(code=1001)
                    except Exception:
                        pass
                    break
        except asyncio.CancelledError:
            pass


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

game = Game()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await game.startup()
    yield
    await game.shutdown()


app = FastAPI(title="The Ages II", lifespan=lifespan)
app.include_router(admin_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.websocket("/ws/game")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Accept a WebSocket connection and route incoming messages."""
    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await send_error(websocket, ErrorCode.INVALID_JSON, "Invalid JSON")
                continue
            if "action" not in data:
                await send_error(
                    websocket, ErrorCode.MISSING_ACTION, "Missing action field", data
                )
                continue
            action = data["action"]
            schema_cls = ACTION_SCHEMAS.get(action)
            if schema_cls:
                try:
                    validated = schema_cls(**data)
                    data = validated.model_dump()
                except ValidationError as e:
                    await send_error(
                        websocket, ErrorCode.VALIDATION_ERROR,
                        sanitize_validation_error(e), data,
                    )
                    continue
            await game.router.route(websocket, data)
    except WebSocketDisconnect:
        await game.handle_disconnect(websocket)


@app.get("/")
async def index():
    return FileResponse("web-demo/index.html")


app.mount("/static", StaticFiles(directory="web-demo"), name="static")
