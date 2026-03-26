# Issue: DoT effects are recorded but never resolved per-turn

**ID:** ISS-005
**Severity:** Critical
**Status:** Open
**Delivery:** Epic 4 (Combat System)
**Test:** Manual — play venom_fang card, observe mob HP on subsequent turns
**Created:** 2026-03-25
**Assigned:** BMad Developer

## Description

When a card with a DoT (damage-over-time) effect is played (e.g., `venom_fang` — 6 poison damage for 3 turns), the effect is appended to the target's `active_effects` list but is never ticked or resolved on subsequent turns. The DoT damage simply never happens.

## Expected

After playing a DoT card:
- Turn 1: DoT is applied (recorded)
- Turn 2: 6 poison damage is dealt to the target automatically
- Turn 3: 6 poison damage is dealt to the target automatically
- Turn 4: 6 poison damage is dealt to the target automatically
- After 3 turns: DoT effect is removed from active_effects

## Actual

- Turn 1: DoT is appended to `target["active_effects"]` list
- Turn 2+: Nothing happens. No tick resolution code exists anywhere in the codebase.
- The `active_effects` list grows indefinitely if multiple DoTs are applied.

## Impact

**Two cards are functionally broken:**
- `venom_fang` (6 poison DoT for 3 turns) — does zero damage
- `poison_strike` (8 physical + 4 poison DoT for 3 turns) — only the 8 physical works

Players who play DoT cards get no value from the DoT portion, making these cards strictly worse than alternatives.

## Design Reference

- Effect handler: `server/core/effects/dot.py` — appends to `active_effects` but no tick logic
- Combat instance: `server/combat/instance.py` — `resolve_action()` calls effect registry but no turn-start DoT resolution
- Card data: `data/cards/starter_cards.json` — `venom_fang` and `poison_strike`

## Steps to Reproduce

1. Start combat with any mob
2. Play `venom_fang` card (or `poison_strike`)
3. Observe mob HP — it does not decrease from DoT on subsequent turns
4. Check combat_turn response — no DoT tick results appear

## Root Cause

The `dot.py` effect handler only **records** the DoT:

```python
async def apply_dot(target: dict, effect: dict, **kwargs) -> dict:
    target.setdefault("active_effects", []).append({
        "type": effect.get("damage_type", "poison"),
        "value": effect.get("value", 0),
        "turns": effect.get("turns", 1),
    })
    return {"applied": "dot", ...}
```

There is no code anywhere that:
1. Iterates `active_effects` at turn start
2. Applies the `value` as damage
3. Decrements the `turns` counter
4. Removes expired effects

## Recommendation

Add a `resolve_dots(participant)` function called at the start of each participant's turn in `CombatInstance.resolve_action()` or a dedicated turn-start hook. It should:
1. Iterate `participant["active_effects"]`
2. Apply damage for each active DoT
3. Decrement `turns` by 1
4. Remove effects where `turns <= 0`
5. Include DoT tick results in the combat_turn response

## Related Issues

- None currently. This is a standalone functional gap.

---

**Priority for fix:** This release (Critical — game mechanic completely non-functional)
