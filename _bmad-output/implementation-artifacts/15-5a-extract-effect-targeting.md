# Story 15.5a: Extract Effect Targeting

Status: done

## Story

As a developer,
I want the duplicated effect source/target resolution extracted into a shared method on `CombatInstance`,
So that the effect targeting logic exists in exactly one place.

## Acceptance Criteria

1. **Given** `CombatInstance.resolve_card_effects()` (lines 100-107) and `CombatInstance.use_item()` (lines 204-209) both contain identical if/else logic to determine source/target based on effect type:
   ```python
   if effect_type in ("heal", "shield", "draw"):
       source = player_stats; target = player_stats
   else:
       source = player_stats; target = self.mob_stats
   ```
   **When** Story 15.5a is implemented,
   **Then** a private method `_resolve_effect_targets(entity_id: str, effect_type: str) -> tuple[dict, dict]` is extracted on `CombatInstance`,
   **And** both `resolve_card_effects()` and `use_item()` call it instead of inlining the logic.

2. **Given** the `_resolve_effect_targets` method,
   **When** called with a self-targeting effect type (`"heal"`, `"shield"`, `"draw"`),
   **Then** it returns `(player_stats, player_stats)` — both source and target are the participant's stats.

3. **Given** the `_resolve_effect_targets` method,
   **When** called with any other effect type (e.g. `"damage"`, `"dot"`),
   **Then** it returns `(player_stats, self.mob_stats)` — source is participant, target is mob.

4. **Given** all existing tests (807+),
   **When** Story 15.5a is implemented,
   **Then** all tests pass with no assertion value changes.

## Tasks / Subtasks

- [x] Task 1: Extract `_resolve_effect_targets` method (AC: #1, #2, #3)
  - [x] 1.1: Add `_resolve_effect_targets(self, entity_id: str, effect_type: str) -> tuple[dict, dict]` to `CombatInstance`
  - [x] 1.2: Method body: look up `self.participant_stats[entity_id]`, return `(player_stats, player_stats)` for `("heal", "shield", "draw")`, else `(player_stats, self.mob_stats)`
  - [x] 1.3: Update `resolve_card_effects()` — replace the if/else block (lines 100-107) with `source, target = self._resolve_effect_targets(entity_id, effect_type)`; remove the now-unnecessary `player_stats` local at line 94
  - [x] 1.4: Update `use_item()` — replace the if/else block (lines 204-209) with `source, target = self._resolve_effect_targets(entity_id, effect_type)`; remove the now-unnecessary `player_stats` local at line 201. Keep the surrounding `if self._effect_registry is None: ... else: ...` structure intact

- [x] Task 2: Verify tests (AC: #4)
  - [x] 2.1: Run `make test` — all 807+ tests must pass with 0 failures, 0 warnings

## Dev Notes

### Architecture & Patterns

- **Pure refactor** — zero gameplay behavior changes
- **Single-file change**: only `server/combat/instance.py` is modified
- The new method is ~5 lines, extracted from two near-identical blocks
- **ADR-15-5a** (from epic): no duplicated effect source/target logic in `CombatInstance` — `_resolve_effect_targets` is the single call site

### Current Duplication

In `resolve_card_effects()` (line 94 sets `player_stats`, lines 100-107 is the if/else targeting block):
```python
player_stats = self.participant_stats[entity_id]

for effect in card.effects:
    effect_type = effect.get("type", "")

    # Determine source and target based on effect type
    if effect_type in ("heal", "shield", "draw"):
        # Self-targeting effects
        source = player_stats
        target = player_stats
    else:
        # Damage, dot, draw — target the mob  (NOTE: "draw" is wrong here — fix during extraction)
        source = player_stats
        target = self.mob_stats

    result = await self._effect_registry.resolve(
        effect, source, target
    )
    results.append(result)
```

In `use_item()` (line 201 sets `player_stats`, lines 204-209 is the if/else targeting block). Note: `use_item` wraps effect resolution in an `if self._effect_registry is None: ... else: ...` block (lines 197-211) — the targeting code is inside the `else` branch:
```python
player_stats = self.participant_stats[entity_id]
for effect in item_def.effects:
    effect_type = effect.get("type", "")
    if effect_type in ("heal", "shield", "draw"):
        source = player_stats
        target = player_stats
    else:
        source = player_stats
        target = self.mob_stats
    result = await self._effect_registry.resolve(effect, source, target)
    effect_results.append(result)
```

### Target Implementation

```python
def _resolve_effect_targets(self, entity_id: str, effect_type: str) -> tuple[dict, dict]:
    """Return (source, target) stat dicts for an effect type.

    Self-targeting effects (heal, shield, draw) return (player, player).
    All others (damage, dot) return (player, mob).
    """
    player_stats = self.participant_stats[entity_id]
    if effect_type in ("heal", "shield", "draw"):
        return player_stats, player_stats
    return player_stats, self.mob_stats
```

Each call site simplifies to (inside the effect loop, after extracting `effect_type`):
```python
source, target = self._resolve_effect_targets(entity_id, effect_type)
```

Note: the `player_stats` lookup moves into `_resolve_effect_targets`, called once per effect. This is functionally equivalent since it returns the same dict reference each time. The standalone `player_stats` assignment before the loop (line 94 in `resolve_card_effects`, line 201 in `use_item`) can be removed.

### Important: `resolve_card_effects` draw effect handling

After refactoring, `resolve_card_effects()` no longer needs the standalone `player_stats = self.participant_stats[entity_id]` line at line 94 — it gets `player_stats` back from `_resolve_effect_targets` via the `source` return value. The draw effect handling (lines 115-120) only accesses `self.hands.get(entity_id)` and the `result` dict — it does not use `player_stats` directly, so the refactoring does not affect it.

### Files to Modify

| File | Changes |
|------|---------|
| `server/combat/instance.py` | Add `_resolve_effect_targets` method; update `resolve_card_effects()` and `use_item()` to call it |

### Anti-Patterns to Avoid

- Do NOT change any gameplay behavior — pure refactor
- Fix the incorrect inline comment at line 105 (`# Damage, dot, draw — target the mob`) — "draw" is self-targeting, not mob-targeting. The extracted method's docstring documents this correctly
- Do NOT change assertion values in any test
- Do NOT modify any file other than `server/combat/instance.py`
- Do NOT change the method signatures of `resolve_card_effects()` or `use_item()`
- Do NOT move the draw effect handling (lines 115-120 in `resolve_card_effects`) — only the source/target resolution is extracted

### Previous Story Intelligence

From Story 15.4:
- Pure refactor pattern: move duplicated logic, update call sites, verify all 807+ tests pass
- Single-concern changes keep the diff small and review easy

From Story 15.3:
- `@requires_auth` decorator pattern — handlers are already decorated, no changes needed here

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Story 15.5a (lines 3784-3812)]
- [Source: server/combat/instance.py — resolve_card_effects() (lines 83-122)]
- [Source: server/combat/instance.py — use_item() (lines 176-229)]
- [Source: _bmad-output/planning-artifacts/epics.md — Epic 15 DoD (line 3930)]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- All 807 tests pass (0 failures, 0 warnings, ~4.2s)
- `grep -c "_resolve_effect_targets" server/combat/instance.py` = 3 (definition + 2 call sites)
- No duplicated effect source/target if/else blocks remain in `resolve_card_effects()` or `use_item()`

### Completion Notes List

- Extracted `_resolve_effect_targets(entity_id, effect_type) -> tuple[dict, dict]` as a private method on `CombatInstance`
- Updated `resolve_card_effects()` to use `_resolve_effect_targets` — removed standalone `player_stats` local and the 8-line if/else block
- Updated `use_item()` to use `_resolve_effect_targets` — removed standalone `player_stats` local and the 6-line if/else block, kept surrounding `if self._effect_registry is None` structure intact
- Removed incorrect comment `# Damage, dot, draw — target the mob` (draw is self-targeting)
- Pure refactor — zero gameplay behavior changes, single-file change

### File List

**Modified:**
- `server/combat/instance.py` — Added `_resolve_effect_targets` method; updated `resolve_card_effects()` and `use_item()` to call it
