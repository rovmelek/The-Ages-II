"""Tests for item usage outside and during combat (Stories 5-3, 5-4)."""
import pytest

from server.combat.cards.card_def import CardDef
from server.combat.instance import CombatInstance
from server.core.effects import create_default_registry
from server.items.inventory import Inventory
from server.items.item_def import ItemDef


# --- Helpers ---


def _registry():
    return create_default_registry()


def _healing_potion():
    return ItemDef(
        item_key="healing_potion",
        name="Healing Potion",
        category="consumable",
        charges=3,
        effects=[{"type": "heal", "value": 25}],
        usable_in_combat=True,
        usable_outside_combat=True,
    )


def _combat_only_item():
    return ItemDef(
        item_key="battle_salve",
        name="Battle Salve",
        category="consumable",
        charges=1,
        effects=[{"type": "shield", "value": 15}],
        usable_in_combat=True,
        usable_outside_combat=False,
    )


def _noncombat_item():
    return ItemDef(
        item_key="town_scroll",
        name="Town Scroll",
        category="consumable",
        charges=1,
        effects=[{"type": "heal", "value": 50}],
        usable_in_combat=False,
        usable_outside_combat=True,
    )


def _material():
    return ItemDef(
        item_key="iron_shard",
        name="Iron Shard",
        category="material",
        charges=0,
        effects=[],
        usable_in_combat=False,
        usable_outside_combat=False,
    )


def _make_player_stats(hp=80, max_hp=100, strength=0, dexterity=0, intelligence=0, wisdom=0):
    return {"hp": hp, "max_hp": max_hp, "attack": 10, "defense": 5, "shield": 0,
            "strength": strength, "dexterity": dexterity,
            "intelligence": intelligence, "wisdom": wisdom}


def _make_mob_stats(hp=100, attack=10, strength=0, dexterity=0, intelligence=0, wisdom=0):
    return {"hp": hp, "max_hp": hp, "attack": attack,
            "strength": strength, "dexterity": dexterity,
            "intelligence": intelligence, "wisdom": wisdom}


def _basic_cards(n=5):
    return [
        CardDef(card_key=f"card_{i}", name=f"Card {i}", cost=1,
                effects=[{"type": "damage", "value": 5}])
        for i in range(n)
    ]


def _two_player_combat(mob_hp=100, player_hp=80, player_max_hp=100):
    """Two-player instance so P1's action doesn't trigger cycle-end mob attack."""
    instance = CombatInstance(
        instance_id="test",
        mob_name="Goblin",
        mob_stats=_make_mob_stats(hp=mob_hp),
        effect_registry=_registry(),
    )
    instance.add_participant(
        "p1", _make_player_stats(hp=player_hp, max_hp=player_max_hp), _basic_cards()
    )
    instance.add_participant(
        "p2", _make_player_stats(hp=player_hp, max_hp=player_max_hp), _basic_cards()
    )
    return instance


# --- Story 5-3: Use Items Outside Combat ---


class TestUseItemOutsideCombat:
    """Tests for item effect resolution via EffectRegistry outside combat."""

    @pytest.mark.asyncio
    async def test_heal_effect_resolves(self):
        registry = _registry()
        stats = _make_player_stats(hp=50, max_hp=100)
        potion = _healing_potion()

        results = []
        for effect in potion.effects:
            result = await registry.resolve(effect, stats, stats)
            results.append(result)

        assert len(results) == 1
        assert results[0]["type"] == "heal"
        assert stats["hp"] == 75  # 50 + 25

    @pytest.mark.asyncio
    async def test_heal_capped_at_max_hp(self):
        registry = _registry()
        stats = _make_player_stats(hp=90, max_hp=100)
        potion = _healing_potion()

        for effect in potion.effects:
            await registry.resolve(effect, stats, stats)

        assert stats["hp"] == 100  # capped at max_hp

    def test_inventory_charge_consumed_after_use(self):
        inv = Inventory()
        inv.add_item(_healing_potion(), quantity=2)
        inv.use_charge("healing_potion")
        assert inv.get_quantity("healing_potion") == 1

    def test_noncombat_item_usable_flag(self):
        item = _noncombat_item()
        assert item.usable_outside_combat is True
        assert item.usable_in_combat is False

    def test_material_not_usable(self):
        item = _material()
        assert item.usable_outside_combat is False
        assert item.usable_in_combat is False


# --- Story 5-4: Use Items During Combat ---


class TestUseItemDuringCombat:
    @pytest.mark.asyncio
    async def test_use_healing_item_in_combat(self):
        instance = _two_player_combat(player_hp=60, player_max_hp=100)
        potion = _healing_potion()

        result = await instance.use_item("p1", potion)
        assert result["action"] == "use_item"
        assert result["entity_id"] == "p1"
        assert result["item_key"] == "healing_potion"
        assert len(result["effect_results"]) == 1
        assert result["effect_results"][0]["type"] == "heal"
        # HP should increase: 60 + 25 = 85
        assert instance.participant_stats["p1"]["hp"] == 85

    @pytest.mark.asyncio
    async def test_use_item_advances_turn(self):
        instance = _two_player_combat()
        assert instance.get_current_turn() == "p1"
        await instance.use_item("p1", _healing_potion())
        assert instance.get_current_turn() == "p2"

    @pytest.mark.asyncio
    async def test_use_item_not_your_turn(self):
        instance = _two_player_combat()
        with pytest.raises(ValueError, match="Not your turn"):
            await instance.use_item("p2", _healing_potion())

    @pytest.mark.asyncio
    async def test_use_item_dead_player(self):
        instance = _two_player_combat(player_hp=0)
        with pytest.raises(ValueError, match="You are dead"):
            await instance.use_item("p1", _healing_potion())

    @pytest.mark.asyncio
    async def test_use_shield_item_in_combat(self):
        instance = _two_player_combat()
        shield_item = _combat_only_item()

        result = await instance.use_item("p1", shield_item)
        assert result["effect_results"][0]["type"] == "shield"
        assert instance.participant_stats["p1"]["shield"] == 15

    @pytest.mark.asyncio
    async def test_use_item_no_effect_registry(self):
        """Instance without effect registry produces empty results."""
        instance = CombatInstance(
            instance_id="test",
            mob_name="Goblin",
            mob_stats=_make_mob_stats(),
            effect_registry=None,
        )
        instance.add_participant("p1", _make_player_stats(), _basic_cards())
        instance.add_participant("p2", _make_player_stats(), _basic_cards())

        result = await instance.use_item("p1", _healing_potion())
        assert result["effect_results"] == []

    @pytest.mark.asyncio
    async def test_use_item_cycle_end_triggers_mob_attack(self):
        """When both players act, cycle ends with mob attack."""
        instance = _two_player_combat()
        await instance.use_item("p1", _healing_potion())
        result = await instance.use_item("p2", _healing_potion())
        # Cycle complete after 2 actions — mob_attack should be present
        assert "mob_attack" in result

    @pytest.mark.asyncio
    async def test_combat_item_flag(self):
        item = _combat_only_item()
        assert item.usable_in_combat is True
        assert item.usable_outside_combat is False

    @pytest.mark.asyncio
    async def test_noncombat_item_flag_in_combat_context(self):
        item = _noncombat_item()
        assert item.usable_in_combat is False
