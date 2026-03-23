"""Tests for the shared effect registry (Story 4.1)."""
import pytest

from server.core.effects.registry import EffectRegistry, create_default_registry


@pytest.fixture
def registry():
    return create_default_registry()


def _make_target(hp=100, max_hp=100, shield=0):
    return {"hp": hp, "max_hp": max_hp, "shield": shield}


def _make_source():
    return {"hp": 100, "max_hp": 100}


# --- Damage ---


@pytest.mark.asyncio
async def test_damage_reduces_hp(registry):
    target = _make_target(hp=100)
    result = await registry.resolve(
        {"type": "damage", "value": 20}, _make_source(), target
    )
    assert target["hp"] == 80
    assert result["type"] == "damage"
    assert result["value"] == 20
    assert result["shield_absorbed"] == 0
    assert result["target_hp"] == 80


@pytest.mark.asyncio
async def test_damage_with_full_shield_absorption(registry):
    target = _make_target(hp=100, shield=30)
    result = await registry.resolve(
        {"type": "damage", "value": 20}, _make_source(), target
    )
    assert target["hp"] == 100  # no HP damage
    assert target["shield"] == 10
    assert result["shield_absorbed"] == 20
    assert result["value"] == 0  # actual HP damage


@pytest.mark.asyncio
async def test_damage_with_partial_shield_absorption(registry):
    target = _make_target(hp=100, shield=5)
    result = await registry.resolve(
        {"type": "damage", "value": 20}, _make_source(), target
    )
    assert target["hp"] == 85  # 20 - 5 shield = 15 damage
    assert target["shield"] == 0
    assert result["shield_absorbed"] == 5
    assert result["value"] == 15


@pytest.mark.asyncio
async def test_damage_does_not_go_below_zero(registry):
    target = _make_target(hp=10)
    result = await registry.resolve(
        {"type": "damage", "value": 50}, _make_source(), target
    )
    assert target["hp"] == 0
    assert result["target_hp"] == 0


# --- Heal ---


@pytest.mark.asyncio
async def test_heal_restores_hp(registry):
    target = _make_target(hp=80, max_hp=100)
    result = await registry.resolve(
        {"type": "heal", "value": 15}, _make_source(), target
    )
    assert target["hp"] == 95
    assert result["type"] == "heal"
    assert result["value"] == 15
    assert result["target_hp"] == 95


@pytest.mark.asyncio
async def test_heal_capped_at_max_hp(registry):
    target = _make_target(hp=85, max_hp=100)
    result = await registry.resolve(
        {"type": "heal", "value": 20}, _make_source(), target
    )
    assert target["hp"] == 100
    assert result["value"] == 15  # only healed 15


@pytest.mark.asyncio
async def test_heal_at_max_hp_no_change(registry):
    target = _make_target(hp=100, max_hp=100)
    result = await registry.resolve(
        {"type": "heal", "value": 10}, _make_source(), target
    )
    assert target["hp"] == 100
    assert result["value"] == 0


# --- Shield ---


@pytest.mark.asyncio
async def test_shield_adds_points(registry):
    target = _make_target()
    result = await registry.resolve(
        {"type": "shield", "value": 12}, _make_source(), target
    )
    assert target["shield"] == 12
    assert result["type"] == "shield"
    assert result["value"] == 12
    assert result["total_shield"] == 12


@pytest.mark.asyncio
async def test_shield_stacks_on_existing(registry):
    target = _make_target(shield=5)
    result = await registry.resolve(
        {"type": "shield", "value": 10}, _make_source(), target
    )
    assert target["shield"] == 15
    assert result["total_shield"] == 15


# --- DoT ---


@pytest.mark.asyncio
async def test_dot_appends_active_effect(registry):
    target = _make_target()
    result = await registry.resolve(
        {"type": "dot", "subtype": "poison", "value": 4, "duration": 3},
        _make_source(),
        target,
    )
    assert len(target["active_effects"]) == 1
    ae = target["active_effects"][0]
    assert ae["type"] == "dot"
    assert ae["subtype"] == "poison"
    assert ae["value"] == 4
    assert ae["remaining"] == 3
    assert result["type"] == "dot"
    assert result["duration"] == 3


@pytest.mark.asyncio
async def test_dot_stacks_multiple(registry):
    target = _make_target()
    await registry.resolve(
        {"type": "dot", "subtype": "poison", "value": 4, "duration": 3},
        _make_source(),
        target,
    )
    await registry.resolve(
        {"type": "dot", "subtype": "bleed", "value": 2, "duration": 5},
        _make_source(),
        target,
    )
    assert len(target["active_effects"]) == 2


# --- Draw ---


@pytest.mark.asyncio
async def test_draw_returns_instruction(registry):
    target = _make_target()
    result = await registry.resolve(
        {"type": "draw", "value": 2}, _make_source(), target
    )
    assert result["type"] == "draw"
    assert result["value"] == 2


# --- Registry behavior ---


@pytest.mark.asyncio
async def test_unregistered_effect_raises():
    registry = EffectRegistry()
    with pytest.raises(ValueError, match="No handler registered"):
        await registry.resolve(
            {"type": "unknown"}, _make_source(), _make_target()
        )


@pytest.mark.asyncio
async def test_custom_handler_registration():
    registry = EffectRegistry()

    async def custom_handler(effect, source, target, context):
        target["custom"] = effect["value"]
        return {"type": "custom", "value": effect["value"]}

    registry.register("custom", custom_handler)
    target = _make_target()
    result = await registry.resolve(
        {"type": "custom", "value": 42}, _make_source(), target
    )
    assert target["custom"] == 42
    assert result["value"] == 42
