"""Game orchestrator and FastAPI application."""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse

from server.core.config import settings
from server.core.database import init_db
from server.core import database as _database
from server.net.connection_manager import ConnectionManager
from server.net.message_router import MessageRouter
from server.player import repo as player_repo
from server.combat.manager import CombatManager
from server.core.effects import create_default_registry
from server.core.events import EventBus
from server.core.scheduler import Scheduler
from server.net.handlers.admin import admin_router
from server.room.manager import RoomManager
from server.room.provider import JsonRoomProvider
from server.party.manager import PartyManager
from server.player.manager import PlayerManager
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
        self.trade_manager = TradeManager()
        self.trade_manager.set_connection_manager(self.connection_manager)
        self.party_manager = PartyManager(connection_manager=self.connection_manager)
        self.player_manager = PlayerManager()
        self.session_factory = _database.async_session
        self._shutting_down: bool = False
        self.loot_tables: dict = {}
        self.npc_templates: dict[str, dict] = {}

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
        await self.scheduler.stop()

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
        from server.net.handlers.auth import handle_login, handle_logout, handle_register
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

        self.router.register(
            "login", lambda ws, d: handle_login(ws, d, game=self)
        )
        self.router.register(
            "register", lambda ws, d: handle_register(ws, d, game=self)
        )
        self.router.register(
            "logout", lambda ws, d: handle_logout(ws, d, game=self)
        )
        self.router.register(
            "move", lambda ws, d: handle_move(ws, d, game=self)
        )
        self.router.register(
            "chat", lambda ws, d: handle_chat(ws, d, game=self)
        )
        self.router.register(
            "interact", lambda ws, d: handle_interact(ws, d, game=self)
        )
        self.router.register(
            "play_card", lambda ws, d: handle_play_card(ws, d, game=self)
        )
        self.router.register(
            "pass_turn", lambda ws, d: handle_pass_turn(ws, d, game=self)
        )
        self.router.register(
            "flee", lambda ws, d: handle_flee(ws, d, game=self)
        )
        self.router.register(
            "inventory", lambda ws, d: handle_inventory(ws, d, game=self)
        )
        self.router.register(
            "use_item", lambda ws, d: handle_use_item(ws, d, game=self)
        )
        self.router.register(
            "use_item_combat",
            lambda ws, d: handle_use_item_combat(ws, d, game=self),
        )
        self.router.register(
            "look", lambda ws, d: handle_look(ws, d, game=self)
        )
        self.router.register(
            "who", lambda ws, d: handle_who(ws, d, game=self)
        )
        self.router.register(
            "stats", lambda ws, d: handle_stats(ws, d, game=self)
        )
        self.router.register(
            "help_actions",
            lambda ws, d: handle_help_actions(ws, d, game=self),
        )
        self.router.register(
            "map", lambda ws, d: handle_map(ws, d, game=self)
        )
        self.router.register(
            "level_up",
            lambda ws, d: handle_level_up(ws, d, game=self),
        )
        self.router.register(
            "trade", lambda ws, d: handle_trade(ws, d, game=self)
        )
        self.router.register(
            "party", lambda ws, d: handle_party(ws, d, game=self)
        )
        self.router.register(
            "party_chat",
            lambda ws, d: handle_party_chat(ws, d, game=self),
        )
    def _register_events(self) -> None:
        """Register event bus subscribers."""

        async def _on_rare_spawn(npc_name: str, room_name: str) -> None:
            await self.connection_manager.broadcast_to_all(
                {
                    "type": "announcement",
                    "message": f"{npc_name} has appeared in {room_name}!",
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
        if tmpl and tmpl.get("spawn_type") == "persistent":
            respawn_seconds = tmpl.get("spawn_config", {}).get("respawn_seconds", settings.MOB_RESPAWN_SECONDS)
            self.scheduler.schedule_respawn(room_key, npc_id, respawn_seconds)

    @staticmethod
    def _reset_player_stats(entity) -> None:
        """Clear combat flags and restore HP to max for respawn."""
        entity.in_combat = False
        entity.stats["hp"] = entity.stats.get("max_hp", settings.DEFAULT_BASE_HP)
        entity.stats.pop("shield", None)

    @staticmethod
    def _find_spawn_point(spawn_room, spawn_room_key: str, entity_name: str) -> tuple[int, int]:
        """Find a walkable spawn point in the given room."""
        sx, sy = spawn_room.get_player_spawn()
        if not spawn_room.is_walkable(sx, sy):
            sx, sy = spawn_room.find_first_walkable()
        if not spawn_room.is_walkable(sx, sy):
            logger.warning(
                "Room %s has no walkable tile; placing %s at (%d, %d)",
                spawn_room_key, entity_name, sx, sy,
            )
        return sx, sy

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

        sx, sy = self._find_spawn_point(spawn_room, spawn_room_key, entity.name)

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
        """Handle a player disconnecting: save state, clean up, notify room."""
        entity_id = self.connection_manager.get_entity_id(websocket)
        if entity_id is None:
            return  # Unauthenticated connection, nothing to clean up

        await self.player_manager.cleanup_session(entity_id, self)


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
                await websocket.send_json(
                    {"type": "error", "detail": "Invalid JSON"}
                )
                continue
            if "action" not in data:
                await websocket.send_json(
                    {"type": "error", "detail": "Missing action field"}
                )
                continue
            await game.router.route(websocket, data)
    except WebSocketDisconnect:
        await game.handle_disconnect(websocket)


@app.get("/")
async def index():
    return FileResponse("web-demo/index.html")


app.mount("/static", StaticFiles(directory="web-demo"), name="static")
