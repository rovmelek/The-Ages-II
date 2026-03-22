"""Game orchestrator and FastAPI application."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from server.core.config import settings
from server.core.database import async_session, init_db
from server.net.connection_manager import ConnectionManager
from server.net.message_router import MessageRouter
from server.player import repo as player_repo
from server.room.manager import RoomManager
from server.room.provider import JsonRoomProvider


class Game:
    """Central game orchestrator — holds all managers and state."""

    def __init__(self) -> None:
        self.router = MessageRouter()
        self.connection_manager = ConnectionManager()
        self.room_manager = RoomManager()
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

        self._register_handlers()

    def shutdown(self) -> None:
        """Clean up resources on server shutdown."""
        # TimerService cancellation will be added in later epics
        pass

    def _register_handlers(self) -> None:
        """Register all WebSocket action handlers."""
        from server.net.handlers.auth import handle_login, handle_register
        from server.net.handlers.chat import handle_chat
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

    async def handle_disconnect(self, websocket: WebSocket) -> None:
        """Handle a player disconnecting: save state, clean up, notify room."""
        entity_id = self.connection_manager.get_entity_id(websocket)
        if entity_id is None:
            return  # Unauthenticated connection, nothing to clean up

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
