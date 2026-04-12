"""Tests for multi-player combat support in CombatInstance and CombatManager."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.combat.cards.card_def import CardDef
from server.combat.instance import CombatInstance
from server.combat.manager import CombatManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_card(key: str = "slash", cost: int = 1, damage: int = 10) -> CardDef:
    return CardDef(
        card_key=key, name=key.title(), cost=cost,
        effects=[{"type": "damage", "value": damage}],
    )


def _make_cards(n: int = 5) -> list[CardDef]:
    return [_make_card(f"card_{i}") for i in range(n)]


def _make_stats(hp: int = 100) -> dict:
    return {"hp": hp, "max_hp": hp, "attack": 10, "shield": 0}


def _make_mob(hp: int = 200) -> dict:
    return {"hp": hp, "max_hp": hp, "attack": 5, "strength": 0}


def _make_instance(
    mob_hp: int = 200,
    player_ids: list[str] | None = None,
    player_hp: int = 100,
) -> CombatInstance:
    """Create a CombatInstance with N players."""
    from server.core.effects.registry import EffectRegistry

    registry = EffectRegistry()
    instance = CombatInstance(
        mob_name="Test Mob",
        mob_stats=_make_mob(mob_hp),
        effect_registry=registry,
    )
    ids = player_ids or ["player_1"]
    cards = _make_cards()
    for eid in ids:
        instance.add_participant(eid, _make_stats(player_hp), cards)
    return instance


# ---------------------------------------------------------------------------
# CombatManager.start_combat — single & multi-player
# ---------------------------------------------------------------------------

class TestStartCombat:
    """Tests for CombatManager.start_combat()."""

    def test_start_combat_single_player_string(self):
        """Single entity_id string creates instance with one participant."""
        mgr = CombatManager()
        cards = _make_cards()
        stats = {"player_1": _make_stats()}
        instance = mgr.start_combat(
            "Goblin", _make_mob(), "player_1", stats, cards,
        )
        assert instance.participants == ["player_1"]
        assert mgr.get_player_instance("player_1") is instance

    def test_start_combat_single_player_list(self):
        """Single-element list works the same as string."""
        mgr = CombatManager()
        cards = _make_cards()
        stats = {"player_1": _make_stats()}
        instance = mgr.start_combat(
            "Goblin", _make_mob(), ["player_1"], stats, cards,
        )
        assert instance.participants == ["player_1"]
        assert mgr.get_player_instance("player_1") is instance

    def test_start_combat_multiple_players(self):
        """Multiple players all get added and mapped."""
        mgr = CombatManager()
        cards = _make_cards()
        ids = ["player_1", "player_2", "player_3"]
        stats = {eid: _make_stats() for eid in ids}
        instance = mgr.start_combat(
            "Dragon", _make_mob(), ids, stats, cards,
        )
        assert instance.participants == ids
        for eid in ids:
            assert mgr.get_player_instance(eid) is instance

    def test_start_combat_preserves_npc_metadata(self):
        """npc_id, room_key, mob_hit_dice are passed through."""
        mgr = CombatManager()
        cards = _make_cards()
        stats = {"player_1": _make_stats()}
        instance = mgr.start_combat(
            "Boss", _make_mob(), "player_1", stats, cards,
            npc_id="npc_boss", room_key="dark_cave", mob_hit_dice=5,
        )
        assert instance.npc_id == "npc_boss"
        assert instance.room_key == "dark_cave"
        assert instance.mob_hit_dice == 5

    def test_start_combat_identical_to_manual_flow(self):
        """start_combat produces the same state as manual create+add."""
        mgr1 = CombatManager()
        mgr2 = CombatManager()
        cards = _make_cards()
        stats = {"p1": _make_stats(80), "p2": _make_stats(90)}
        mob = _make_mob(150)

        # Via start_combat
        inst1 = mgr1.start_combat("Mob", dict(mob), ["p1", "p2"], stats, cards)

        # Via manual flow
        inst2 = mgr2.create_instance("Mob", dict(mob))
        inst2.add_participant("p1", dict(stats["p1"]), cards)
        mgr2.add_player_to_instance("p1", inst2.instance_id)
        inst2.add_participant("p2", dict(stats["p2"]), cards)
        mgr2.add_player_to_instance("p2", inst2.instance_id)

        assert inst1.participants == inst2.participants
        assert inst1.participant_stats["p1"]["hp"] == inst2.participant_stats["p1"]["hp"]
        assert inst1.participant_stats["p2"]["hp"] == inst2.participant_stats["p2"]["hp"]


# ---------------------------------------------------------------------------
# Turn order — round-robin
# ---------------------------------------------------------------------------

class TestTurnOrder:
    """Turn cycling through N players."""

    def test_first_player_goes_first(self):
        instance = _make_instance(player_ids=["p1", "p2", "p3"])
        assert instance.get_current_turn() == "p1"

    @pytest.mark.asyncio
    async def test_round_robin_order(self):
        instance = _make_instance(player_ids=["p1", "p2", "p3"])
        turns = []
        for _ in range(6):  # 2 full cycles
            turns.append(instance.get_current_turn())
            await instance.pass_turn(instance.get_current_turn())
        assert turns == ["p1", "p2", "p3", "p1", "p2", "p3"]

    @pytest.mark.asyncio
    async def test_each_player_one_action_per_cycle(self):
        instance = _make_instance(player_ids=["p1", "p2"])
        # p1 acts
        assert instance.get_current_turn() == "p1"
        await instance.pass_turn("p1")
        # p2 acts
        assert instance.get_current_turn() == "p2"
        await instance.pass_turn("p2")
        # Back to p1
        assert instance.get_current_turn() == "p1"


# ---------------------------------------------------------------------------
# Cycle-end mob attack targeting
# ---------------------------------------------------------------------------

class TestCycleEndMobAttack:
    """Mob attacks at end of each full cycle."""

    @pytest.mark.asyncio
    async def test_mob_attacks_after_full_cycle(self):
        """After all players act, mob attacks someone."""
        instance = _make_instance(player_ids=["p1", "p2"], mob_hp=200)
        await instance.pass_turn("p1")
        result = await instance.pass_turn("p2")
        # cycle_mob_attack comes from _advance_turn at cycle end
        assert "cycle_mob_attack" in result or "mob_attack" in result

    @pytest.mark.asyncio
    async def test_mob_only_targets_alive_players(self):
        """Dead players should not be targeted by cycle-end mob attack."""
        instance = _make_instance(player_ids=["p1", "p2"], mob_hp=200)

        # p1 acts first (alive), then kill p1 before cycle end
        await instance.pass_turn("p1")
        instance.participant_stats["p1"]["hp"] = 0

        # p2 acts — this completes the cycle
        result = await instance.pass_turn("p2")

        # The mob attack should target p2 (the only alive player)
        mob_attack = result.get("cycle_mob_attack")
        assert mob_attack is not None, "Expected cycle-end mob attack after full cycle"
        assert mob_attack["target"] == "p2"

    @pytest.mark.asyncio
    async def test_mob_targets_random_from_alive(self):
        """With multiple alive players, mob picks randomly among them."""
        instance = _make_instance(player_ids=["p1", "p2", "p3"], mob_hp=200)
        targets = set()
        for _ in range(20):
            # Reset for each trial
            for eid in instance.participants:
                instance.participant_stats[eid]["hp"] = 100
            instance._turn_index = 0
            instance._actions_this_cycle = 0

            # Complete a full cycle
            for eid in ["p1", "p2", "p3"]:
                result = await instance.pass_turn(eid)
            mob_attack = result.get("cycle_mob_attack")
            if mob_attack:
                targets.add(mob_attack["target"])

        # With 20 trials, we should see at least 2 different targets
        assert len(targets) >= 2


# ---------------------------------------------------------------------------
# Flee in multi-player combat
# ---------------------------------------------------------------------------

class TestFleeMultiplayer:
    """Flee behavior in multi-player combat."""

    def test_flee_removes_from_participants(self):
        instance = _make_instance(player_ids=["p1", "p2", "p3"])
        instance.remove_participant("p2")
        assert "p2" not in instance.participants
        assert len(instance.participants) == 2

    def test_flee_continues_turn_cycling(self):
        instance = _make_instance(player_ids=["p1", "p2", "p3"])
        # p1's turn; remove p2
        instance.remove_participant("p2")
        assert instance.get_current_turn() == "p1"

    def test_flee_adjusts_turn_index_before_current(self):
        """Removing a player before current index shifts index down."""
        instance = _make_instance(player_ids=["p1", "p2", "p3"])
        instance._turn_index = 2  # p3's turn
        instance.remove_participant("p1")
        # Index should shift: was 2, p1 (index 0) removed → now 1
        assert instance._turn_index == 1
        assert instance.get_current_turn() == "p3"

    def test_flee_adjusts_turn_index_at_current(self):
        """Removing player at current index — next player slides in."""
        instance = _make_instance(player_ids=["p1", "p2", "p3"])
        instance._turn_index = 1  # p2's turn
        instance.remove_participant("p2")
        # p3 slides into index 1
        assert instance.get_current_turn() == "p3"

    def test_all_fled_combat_ends(self):
        """If all players flee, combat ends in defeat."""
        instance = _make_instance(player_ids=["p1", "p2"])
        instance.remove_participant("p1")
        instance.remove_participant("p2")
        assert instance.is_finished
        assert not instance.participants


# ---------------------------------------------------------------------------
# Dead player turn skipping
# ---------------------------------------------------------------------------

class TestDeadPlayerSkipping:
    """Dead players' turns are skipped."""

    @pytest.mark.asyncio
    async def test_dead_player_turn_skipped(self):
        instance = _make_instance(player_ids=["p1", "p2", "p3"], mob_hp=200)
        # Kill p2
        instance.participant_stats["p2"]["hp"] = 0

        # p1 acts
        assert instance.get_current_turn() == "p1"
        await instance.pass_turn("p1")

        # p2 should be skipped → p3's turn
        assert instance.get_current_turn() == "p3"

    @pytest.mark.asyncio
    async def test_multiple_dead_players_skipped(self):
        instance = _make_instance(player_ids=["p1", "p2", "p3", "p4"], mob_hp=200)
        # Kill p2 and p3
        instance.participant_stats["p2"]["hp"] = 0
        instance.participant_stats["p3"]["hp"] = 0

        assert instance.get_current_turn() == "p1"
        await instance.pass_turn("p1")
        # p2 and p3 skipped → p4's turn
        assert instance.get_current_turn() == "p4"


# ---------------------------------------------------------------------------
# Victory & defeat conditions
# ---------------------------------------------------------------------------

class TestCombatEndConditions:
    """Multi-player victory and defeat."""

    def test_all_players_dead_is_defeat(self):
        instance = _make_instance(player_ids=["p1", "p2"])
        instance.participant_stats["p1"]["hp"] = 0
        instance.participant_stats["p2"]["hp"] = 0
        assert instance.is_finished
        result = instance.get_combat_end_result()
        assert result is not None
        assert result["victory"] is False

    def test_mob_dead_is_victory(self):
        instance = _make_instance(player_ids=["p1", "p2"])
        instance.mob_stats["hp"] = 0
        assert instance.is_finished
        result = instance.get_combat_end_result()
        assert result is not None
        assert result["victory"] is True

    def test_victory_rewards_all_surviving_players(self):
        instance = _make_instance(player_ids=["p1", "p2", "p3"], mob_hp=1)
        # p1 dead, p2 and p3 alive
        instance.participant_stats["p1"]["hp"] = 0
        instance.mob_stats["hp"] = 0
        result = instance.get_combat_end_result()
        assert result["victory"] is True
        # All participants (including dead) are in rewards_per_player
        # because they are still in participants list
        assert "p1" in result["rewards_per_player"]
        assert "p2" in result["rewards_per_player"]
        assert "p3" in result["rewards_per_player"]

    def test_victory_regardless_of_killing_blow(self):
        """Victory detected no matter which player deals the killing blow."""
        instance = _make_instance(player_ids=["p1", "p2"])
        instance.mob_stats["hp"] = 0
        assert instance.is_finished
        result = instance.get_combat_end_result()
        assert result["victory"] is True

    def test_not_finished_while_alive_players_remain(self):
        instance = _make_instance(player_ids=["p1", "p2"])
        instance.participant_stats["p1"]["hp"] = 0
        # p2 still alive, mob still alive
        assert not instance.is_finished

    def test_all_fled_is_defeat(self):
        instance = _make_instance(player_ids=["p1", "p2"])
        instance.remove_participant("p1")
        instance.remove_participant("p2")
        assert instance.is_finished
        result = instance.get_combat_end_result()
        assert result is not None
        assert result["victory"] is False


# ---------------------------------------------------------------------------
# Disconnect cleanup with multi-player combat
# ---------------------------------------------------------------------------

class TestDisconnectCleanup:
    """_cleanup_player handles multi-player combat disconnect."""

    @pytest.mark.asyncio
    async def test_disconnect_removes_from_combat_notifies_remaining(self):
        """Disconnecting player is removed; remaining participants notified."""
        from server.net.handlers.auth import _cleanup_player

        game = MagicMock()
        game.transaction = MagicMock(return_value=MagicMock(
            __aenter__=AsyncMock(return_value=MagicMock()),
            __aexit__=AsyncMock(return_value=False),
        ))

        # Set up two-player combat instance
        instance = _make_instance(player_ids=["player_1", "player_2"])

        game.combat_manager.get_player_instance.return_value = instance

        # Player entities
        entity1 = MagicMock()
        entity1.stats = {"hp": 50, "max_hp": 100}
        entity1.player_db_id = 1
        entity1.in_combat = True

        entity2 = MagicMock()
        entity2.stats = {"hp": 80, "max_hp": 100}
        entity2.player_db_id = 2
        entity2.in_combat = True

        game.player_entities = {
            "player_1": {
                "entity": entity1,
                "room_key": "town_square",
                "inventory": None,
                "db_id": 1,
            },
        }

        # Mock trade manager
        game.trade_manager.cancel_trades_for.return_value = None

        # Mock party manager
        party_result = MagicMock()
        party_result.members = []
        game.party_manager.handle_disconnect.return_value = (None, None)

        # Mock connection manager
        ws2 = AsyncMock()
        game.connection_manager.get_websocket.side_effect = lambda eid: ws2 if eid == "player_2" else None
        game.connection_manager.send_to_player = AsyncMock()
        game.connection_manager.disconnect = MagicMock()
        game.connection_manager.broadcast_to_room = AsyncMock()

        # Mock room manager
        game.room_manager.get_room.return_value = MagicMock()

        # Mock player_repo
        import server.player.repo as player_repo
        with patch.object(player_repo, "update_stats", new_callable=AsyncMock):
            with patch.object(player_repo, "update_position", new_callable=AsyncMock):
                with patch.object(player_repo, "update_inventory", new_callable=AsyncMock):
                    await _cleanup_player("player_1", game)

        # player_1 should be removed from the instance
        assert "player_1" not in instance.participants
        # player_2 should still be in combat
        assert "player_2" in instance.participants
        # player_1 marked not in combat
        assert entity1.in_combat is False
        # ws2 should have been sent a combat_update
        ws2.send_json.assert_called()
        call_args = ws2.send_json.call_args[0][0]
        assert call_args["type"] == "combat_update"
