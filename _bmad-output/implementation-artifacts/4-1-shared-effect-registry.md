# Story 4.1: Shared Effect Registry

Status: done

## Story

As a developer,
I want a central effect resolution system that both cards and items can use,
So that all combat effects are handled consistently and new effect types are easy to add.

## Acceptance Criteria

1. Effect registry initialized → effect with type "damage" and value 20 resolved against target with 100 HP → target's HP reduced to 80
2. Effect with type "heal" and value 15 resolved on player with 85/100 HP → player's HP increases to 100 (capped at max_hp)
3. Effect with type "shield" and value 12 resolved on player → player gains 12 shield points that absorb future damage
4. Effect with type "dot" (damage over time), subtype "poison", value 4, duration 3 → target takes 4 damage per turn for 3 turns (stored as active effect)
5. Effect with type "draw" and value 2 resolved during combat → player draws 2 additional cards from their deck (returns draw instruction, actual draw handled by combat)
6. New effect type added → developer creates handler file and registers it → cards and items can reference new effect_type in JSON without other code changes

## Tasks / Subtasks

- [x] Task 1: Create `server/core/effects/registry.py` with `EffectRegistry` class (AC: #1-6)
  - [x] `EffectRegistry` class with `_handlers: dict[str, Callable]` mapping effect_type → async handler
  - [x] `register(effect_type: str, handler: Callable)` to register handlers
  - [x] `async resolve(effect: dict, source: dict, target: dict, context: dict) -> dict` to resolve an effect
  - [x] `resolve` looks up handler by `effect["type"]`, calls it, returns result dict
  - [x] Raise `ValueError` for unregistered effect types
- [x] Task 2: Create `server/core/effects/damage.py` handler (AC: #1)
  - [x] `async def handle_damage(effect, source, target, context) -> dict`
  - [x] Subtracts `effect["value"]` from `target["hp"]` (respects shield if present)
  - [x] Shield absorption: if target has shield > 0, reduce shield first, remaining damage hits HP
  - [x] Returns `{"type": "damage", "value": actual_damage, "shield_absorbed": absorbed, "target_hp": new_hp}`
- [x] Task 3: Create `server/core/effects/heal.py` handler (AC: #2)
  - [x] `async def handle_heal(effect, source, target, context) -> dict`
  - [x] Adds `effect["value"]` to `target["hp"]`, capped at `target["max_hp"]`
  - [x] Returns `{"type": "heal", "value": actual_heal, "target_hp": new_hp}`
- [x] Task 4: Create `server/core/effects/shield.py` handler (AC: #3)
  - [x] `async def handle_shield(effect, source, target, context) -> dict`
  - [x] Adds `effect["value"]` to `target["shield"]` (initializes to 0 if missing)
  - [x] Returns `{"type": "shield", "value": effect["value"], "total_shield": new_shield}`
- [x] Task 5: Create `server/core/effects/dot.py` handler (AC: #4)
  - [x] `async def handle_dot(effect, source, target, context) -> dict`
  - [x] Appends a DoT entry to `target["active_effects"]` list: `{"type": "dot", "subtype": subtype, "value": value, "remaining": duration}`
  - [x] Returns `{"type": "dot", "subtype": subtype, "value": value, "duration": duration}`
- [x] Task 6: Create `server/core/effects/draw.py` handler (AC: #5)
  - [x] `async def handle_draw(effect, source, target, context) -> dict`
  - [x] Returns `{"type": "draw", "value": effect["value"]}` — actual card draw handled by combat system
- [x] Task 7: Create default registry factory function (AC: #6)
  - [x] `create_default_registry() -> EffectRegistry` in registry.py
  - [x] Registers all built-in handlers (damage, heal, shield, dot, draw)
  - [x] Export from `server/core/effects/__init__.py`
- [x] Task 8: Write tests `tests/test_effects.py` (AC: #1-6)
  - [x] Test damage reduces HP
  - [x] Test damage with shield absorption (partial and full)
  - [x] Test heal capped at max_hp
  - [x] Test heal when already at max_hp (no change)
  - [x] Test shield adds to existing shield
  - [x] Test DoT appends active effect with correct fields
  - [x] Test draw returns draw instruction
  - [x] Test unregistered effect type raises ValueError
  - [x] Test custom handler registration works
- [x] Task 9: Verify all tests pass
  - [x] Run `pytest tests/test_effects.py -v`
  - [x] Run `pytest tests/ -v` to verify no regressions

## Dev Notes

### Architecture Compliance

| Component | File Location |
|-----------|--------------|
| EffectRegistry | `server/core/effects/registry.py` (NEW) |
| Damage handler | `server/core/effects/damage.py` (NEW) |
| Heal handler | `server/core/effects/heal.py` (NEW) |
| Shield handler | `server/core/effects/shield.py` (NEW) |
| DoT handler | `server/core/effects/dot.py` (NEW) |
| Draw handler | `server/core/effects/draw.py` (NEW) |
| Package init | `server/core/effects/__init__.py` (MODIFY — exports) |
| Tests | `tests/test_effects.py` (NEW) |

### Existing Infrastructure to Reuse

- **`server/core/effects/__init__.py`** — exists but empty, ready for exports
- **`server/combat/cards/models.py`** — Card model already has `effects: Mapped[list] = mapped_column(JSON, default=list)` — stores effect lists as JSON
- **Card JSON effect format**: `[{"type": "damage", "subtype": "fire", "value": 20}]`

### Effect Handler Interface

All handlers share the same signature:
```python
async def handle_<type>(effect: dict, source: dict, target: dict, context: dict) -> dict
```

- `effect`: the effect dict from card/item JSON (type, value, subtype, duration, etc.)
- `source`: the entity applying the effect (stats dict with hp, max_hp, attack, defense, shield)
- `target`: the entity receiving the effect (stats dict, mutated in place)
- `context`: additional context (combat_instance, etc.) — extensible
- Returns: result dict describing what happened

### Damage with Shield Pattern

```python
raw_damage = effect["value"]
shield = target.get("shield", 0)
absorbed = min(shield, raw_damage)
target["shield"] = shield - absorbed
actual_damage = raw_damage - absorbed
target["hp"] = max(0, target["hp"] - actual_damage)
```

### Anti-Patterns to Avoid

- **DO NOT** implement combat instance or turn logic — Stories 4.3/4.4 handle that
- **DO NOT** implement card hand or deck management — Story 4.2 handles that
- **DO NOT** couple effects to WebSocket messages — effects are pure logic
- **DO NOT** make handlers depend on specific entity classes — use plain dicts for flexibility
- **DO NOT** add complex effect chaining, priorities, or conditional logic — keep handlers simple

### Previous Story Intelligence

From Epic 3:
- NpcEntity has `stats: dict` with hp, max_hp, attack, defense
- PlayerEntity has similar stats structure
- Game class is central orchestrator, will eventually hold effect_registry
- 174 existing tests must not regress

### Project Structure Notes

- New files: `server/core/effects/registry.py`, `damage.py`, `heal.py`, `shield.py`, `dot.py`, `draw.py`, `tests/test_effects.py`
- Modified files: `server/core/effects/__init__.py`

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#7 Shared Effect Registry]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 4.1]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Created `server/core/effects/registry.py` with `EffectRegistry` class and `create_default_registry()` factory
- Created 5 effect handlers: damage.py (with shield absorption), heal.py (capped at max_hp), shield.py (stackable), dot.py (active_effects list), draw.py (instruction only)
- Updated `server/core/effects/__init__.py` with exports
- 14 new tests covering all effect types, shield interactions, edge cases, and custom handler registration
- All 188 tests pass (174 existing + 14 new)

### File List

- `server/core/effects/registry.py` (NEW)
- `server/core/effects/damage.py` (NEW)
- `server/core/effects/heal.py` (NEW)
- `server/core/effects/shield.py` (NEW)
- `server/core/effects/dot.py` (NEW)
- `server/core/effects/draw.py` (NEW)
- `server/core/effects/__init__.py` (MODIFIED — added exports)
- `tests/test_effects.py` (NEW — 14 tests)
