"""PlayerManager — centralized player session lifecycle management."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Iterator

from server.core.config import settings
from server.player import repo as player_repo
from server.player.session import PlayerSession

if TYPE_CHECKING:
    from server.app import Game

logger = logging.getLogger(__name__)


class PlayerManager:
    """Manages player session lifecycle: create, lookup, remove, iterate."""

    def __init__(self) -> None:
        self._sessions: dict[str, PlayerSession] = {}

    def get_session(self, entity_id: str) -> PlayerSession | None:
        """Look up a player session by entity ID."""
        return self._sessions.get(entity_id)

    def set_session(self, entity_id: str, session: PlayerSession) -> None:
        """Register a player session."""
        self._sessions[entity_id] = session

    def remove_session(self, entity_id: str) -> PlayerSession | None:
        """Remove and return a player session, or None if not found."""
        return self._sessions.pop(entity_id, None)

    def has_session(self, entity_id: str) -> bool:
        """Check whether a player session exists."""
        return entity_id in self._sessions

    def all_entity_ids(self) -> list[str]:
        """Return a snapshot list of all entity IDs (safe to iterate during mutation)."""
        return list(self._sessions.keys())

    def all_sessions(self) -> Iterator[tuple[str, PlayerSession]]:
        """Iterate over all (entity_id, session) pairs."""
        return iter(self._sessions.items())

    def clear(self) -> None:
        """Remove all sessions."""
        self._sessions.clear()

    # ------------------------------------------------------------------
    # Session cleanup (relocated from server/net/handlers/auth.py)
    # ------------------------------------------------------------------

    async def cleanup_session(self, entity_id: str, game: Game) -> None:
        """Clean up a player session: combat removal, state save, room removal.

        Used by both logout and same-socket re-login. Does NOT close the WebSocket
        or send any messages to the player.

        Cleanup order: trades -> combat -> party -> save state -> remove from room -> disconnect
        """
        player_info = self.get_session(entity_id)
        if not player_info:
            game.connection_manager.disconnect(entity_id)
            return

        entity = player_info.entity
        room_key = player_info.room_key

        await self._cleanup_trade(entity_id, game)
        await self._cleanup_combat(entity_id, entity, game)
        await self._cleanup_party(entity_id, game)
        await self._save_player_state(entity_id, player_info, game)
        await self._remove_from_room(entity_id, room_key, game)

        game.connection_manager.disconnect(entity_id)
        self.remove_session(entity_id)

    async def _cleanup_trade(self, entity_id: str, game: Game) -> None:
        """Cancel any active trade for a disconnecting player."""
        cancelled_trade = game.trade_manager.cancel_trades_for(entity_id)
        if cancelled_trade:
            other_id = (
                cancelled_trade.player_b
                if cancelled_trade.player_a == entity_id
                else cancelled_trade.player_a
            )
            await game.connection_manager.send_to_player(
                other_id,
                {
                    "type": "trade_result",
                    "status": "cancelled",
                    "reason": "Trade cancelled \u2014 player disconnected",
                },
            )

    async def _cleanup_combat(self, entity_id: str, entity, game: Game) -> None:
        """Sync combat stats, remove from instance, notify remaining participants."""
        combat_instance = game.combat_manager.get_player_instance(entity_id)
        if not combat_instance:
            return

        # Sync combat stats back to entity (only whitelisted keys)
        combat_stats = combat_instance.participant_stats.get(entity_id, {})
        for key in ("hp", "max_hp"):
            if key in combat_stats:
                entity.stats[key] = combat_stats[key]
        # Restore HP if dead in combat
        if entity.stats.get("hp", 0) <= 0:
            entity.stats["hp"] = entity.stats.get("max_hp", settings.DEFAULT_BASE_HP)
        entity.in_combat = False

        # Remove from combat instance (destroys participant_stats entry)
        combat_instance.remove_participant(entity_id)
        game.combat_manager.remove_player(entity_id)

        if not combat_instance.participants:
            # Last player — release NPC and clean up instance
            if combat_instance.npc_id and combat_instance.room_key:
                room = game.room_manager.get_room(combat_instance.room_key)
                if room:
                    npc = room.get_npc(combat_instance.npc_id)
                    if npc:
                        npc.in_combat = False
            game.combat_manager.remove_instance(combat_instance.instance_id)
        else:
            # Notify remaining participants (best-effort per recipient)
            state = combat_instance.get_state()
            for eid in combat_instance.participants:
                ws = game.connection_manager.get_websocket(eid)
                if ws:
                    try:
                        await ws.send_json({"type": "combat_update", **state})
                    except Exception:
                        pass

    async def _cleanup_party(self, entity_id: str, game: Game) -> None:
        """Remove from party, handle leader succession, clean up pending invites."""
        party_result, new_leader_id = game.party_manager.handle_disconnect(entity_id)
        if party_result and party_result.members:
            update_msg = {
                "type": "party_update",
                "action": "member_left",
                "entity_id": entity_id,
                "members": party_result.members,
                "leader": party_result.leader,
            }
            if new_leader_id:
                update_msg["new_leader"] = new_leader_id
            for mid in party_result.members:
                await game.connection_manager.send_to_player(mid, update_msg)

        game.party_manager.cleanup_invites(entity_id)

    async def _save_player_state(
        self, entity_id: str, player_info: PlayerSession, game: Game
    ) -> None:
        """Persist player position, stats, inventory, and visited rooms to DB."""
        entity = player_info.entity
        room_key = player_info.room_key
        inventory = player_info.inventory

        try:
            async with game.transaction() as session:
                await player_repo.update_position(
                    session, entity.player_db_id, room_key, entity.x, entity.y
                )
                await player_repo.update_stats(
                    session, entity.player_db_id, entity.stats
                )
                if inventory:
                    await player_repo.update_inventory(
                        session, entity.player_db_id, inventory.to_dict()
                    )
                visited_rooms = player_info.visited_rooms
                if visited_rooms:
                    await player_repo.update_visited_rooms(
                        session, entity.player_db_id, list(visited_rooms)
                    )
        except Exception:
            logger.exception("Failed to save state during cleanup for %s", entity_id)

    async def _remove_from_room(self, entity_id: str, room_key: str, game: Game) -> None:
        """Remove entity from room and broadcast departure."""
        room = game.room_manager.get_room(room_key)
        if room:
            room.remove_entity(entity_id)
            await game.connection_manager.broadcast_to_room(
                room_key,
                {"type": "entity_left", "entity_id": entity_id},
                exclude=entity_id,
            )
