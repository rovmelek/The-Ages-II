"""Game orchestrator and FastAPI application."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse

from server.core.config import settings
from server.core.database import async_session, init_db
from server.net.connection_manager import ConnectionManager
from server.net.message_router import MessageRouter
from server.player import repo as player_repo
from server.combat.manager import CombatManager
from server.core.effects import create_default_registry
from server.core.events import EventBus
from server.core.scheduler import Scheduler
from server.room.manager import RoomManager
from server.room.provider import JsonRoomProvider


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
        self.player_entities: dict[str, dict] = {}

    async def startup(self) -> None:
        """Initialize database, load data, register handlers."""
        await init_db()

        # Load rooms from JSON into DB, then into memory
        async with async_session() as session:
            provider = JsonRoomProvider()
            rooms = await provider.load_rooms(session)
            for room_db in rooms:
                self.room_manager.load_room(room_db)

        # Load cards from JSON if any card files exist
        cards_dir = settings.DATA_DIR / "cards"
        if cards_dir.exists():
            from server.combat.cards import card_repo

            async with async_session() as session:
                for json_file in sorted(cards_dir.glob("*.json")):
                    await card_repo.load_cards_from_json(session, json_file)

        # Load items from JSON if any item files exist
        items_dir = settings.DATA_DIR / "items"
        if items_dir.exists():
            from server.items import item_repo

            async with async_session() as session:
                for json_file in sorted(items_dir.glob("*.json")):
                    await item_repo.load_items_from_json(session, json_file)

        # Load NPC templates
        npcs_dir = settings.DATA_DIR / "npcs"
        if npcs_dir.exists():
            from server.room.objects.npc import load_npc_templates

            load_npc_templates(npcs_dir)

        self._register_handlers()
        self._register_events()

        # Start scheduler after rooms and NPC templates are loaded
        await self.scheduler.start(self)

    def shutdown(self) -> None:
        """Clean up resources on server shutdown."""
        self.scheduler.stop()

    def _register_handlers(self) -> None:
        """Register all WebSocket action handlers."""
        from server.net.handlers.auth import handle_login, handle_register
        from server.net.handlers.chat import handle_chat
        from server.net.handlers.combat import (
            handle_flee,
            handle_pass_turn,
            handle_play_card,
            handle_use_item_combat,
        )
        from server.net.handlers.interact import handle_interact
        from server.net.handlers.inventory import handle_inventory, handle_use_item
        from server.net.handlers.movement import handle_move

        self.router.register(
            "login", lambda ws, d: handle_login(ws, d, game=self)
        )
        self.router.register(
            "register", lambda ws, d: handle_register(ws, d, game=self)
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

        # Schedule respawn for persistent NPCs
        tmpl = None
        from server.room.objects.npc import get_npc_template

        tmpl = get_npc_template(npc.npc_key)
        if tmpl and tmpl.get("spawn_type") == "persistent":
            respawn_seconds = tmpl.get("spawn_config", {}).get("respawn_seconds", 60)
            self.scheduler.schedule_respawn(room_key, npc_id, respawn_seconds)

    async def handle_disconnect(self, websocket: WebSocket) -> None:
        """Handle a player disconnecting: save state, clean up, notify room."""
        entity_id = self.connection_manager.get_entity_id(websocket)
        if entity_id is None:
            return  # Unauthenticated connection, nothing to clean up

        # Remove from combat if in combat
        combat_instance = self.combat_manager.get_player_instance(entity_id)
        if combat_instance:
            combat_instance.remove_participant(entity_id)
            self.combat_manager.remove_player(entity_id)
            # If no participants left, clean up instance
            if not combat_instance.participants:
                self.combat_manager.remove_instance(combat_instance.instance_id)
            else:
                # Notify remaining participants of updated state
                state = combat_instance.get_state()
                for eid in combat_instance.participants:
                    ws = self.connection_manager.get_websocket(eid)
                    if ws:
                        await ws.send_json({"type": "combat_update", **state})

        player_info = self.player_entities.pop(entity_id, None)
        if player_info:
            entity = player_info["entity"]
            room_key = player_info["room_key"]

            # Save position to database
            try:
                async with async_session() as session:
                    await player_repo.update_position(
                        session, entity.player_db_id, room_key, entity.x, entity.y
                    )
            except Exception:
                pass  # Best-effort save on disconnect

            # Remove from room and notify others
            room = self.room_manager.get_room(room_key)
            if room:
                room.remove_entity(entity_id)
                await self.connection_manager.broadcast_to_room(
                    room_key,
                    {"type": "entity_left", "entity_id": entity_id},
                    exclude=entity_id,
                )

        self.connection_manager.disconnect(entity_id)


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

game = Game()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await game.startup()
    yield
    game.shutdown()


app = FastAPI(title="The Ages II", lifespan=lifespan)


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
