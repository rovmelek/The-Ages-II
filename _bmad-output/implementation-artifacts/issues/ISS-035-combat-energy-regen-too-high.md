# ISS-035: Combat Energy Regen Too High

**Severity**: Medium — balance issue, energy management trivial for casters
**Status**: Done
**Found**: Playtesting at level 4

## Symptoms

At level 4 with modest INT/WIS (~2 each), combat energy regen is ~3–4 per cycle. Most magical cards cost 1–3 energy (fire_bolt=1, heal_light=1, fortify=2, arcane_surge=3). Players can cast almost any card every cycle indefinitely, making energy a non-decision. Out-of-combat regen (2 energy/10s) feels slow by comparison.

## Root Cause

In `compute_energy_regen()` (`server/combat/instance.py:17-23`), the formula uses:
- `BASE_COMBAT_ENERGY_REGEN = 2` (too generous as a floor)
- `COMBAT_ENERGY_REGEN_FACTOR = 0.5` (scales too fast with INT+WIS)

At INT=2, WIS=2: `floor(2 + 4 * 0.5) = 4` energy/cycle — exceeds cost of most cards.

Out-of-combat regen (`REGEN_ENERGY_PER_TICK = 2` every 10s in `server/core/regen.py`) is correct but feels slow compared to the generous combat regen, so out-of-combat recovery should be faster.

## Proposed Fix

1. Reduce `BASE_COMBAT_ENERGY_REGEN` from 2 → 1
2. Reduce `COMBAT_ENERGY_REGEN_FACTOR` from 0.5 → 0.2
3. Increase `REGEN_ENERGY_PER_TICK` from 2 → 4 (faster out-of-combat recovery)

New combat regen at INT=2, WIS=2: `floor(1 + 4 * 0.2) = 1` — must choose wisely between 1-cost spells each cycle.
At INT=5, WIS=5 (late game): `floor(1 + 10 * 0.2) = 3` — can sustain cheap spells, still careful with 3-cost.

Out-of-combat: 4 energy/10s → full energy (20 base) in ~50s instead of ~100s.

## Impact

- `server/core/config.py` — 3 settings adjusted (formula unchanged, values tuned)
- `tests/test_combat.py` — 4 tests updated with new expected regen values

## Files Changed

- `server/core/config.py` — 3 settings adjusted
- `tests/test_combat.py` — updated `test_cycle_regenerates_energy`, `test_compute_energy_regen_default_stats`, `test_compute_energy_regen_high_stats`, `test_compute_energy_regen_starting_stats`
