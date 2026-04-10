# Implementation Readiness Assessment Report

**Date:** 2026-04-10
**Project:** The-Ages-II
**Scope:** Epic 10 — Gameplay Polish & Interaction (Stories 10.1-10.9, FR62-FR76)

## Document Inventory

| Document Type | Status | Path |
|---------------|--------|------|
| GDD | Not found | N/A — architecture.md + epics.md serve as functional equivalent |
| Architecture | Found | `_bmad-output/planning-artifacts/architecture.md` |
| Epics & Stories | Found | `_bmad-output/planning-artifacts/epics.md` |
| UX Design | Not found | N/A — web demo is proof-of-concept, no formal UX spec |

**Issues:** No duplicates. GDD and UX are absent but not required — this is a polish epic building on an existing, complete codebase (Epics 1-9 done).

## GDD Analysis

### Functional Requirements (Epic 10 scope: FR62-FR76)

FR62: Player logout — server action `logout` that saves state, removes from room, notifies others, closes WebSocket
FR63: Player logout — web client `/logout` command and logout button returning to login screen
FR64: Interactive objects (chests, levers) are non-walkable — players interact from adjacent tiles
FR65: Directional interaction — `/interact <direction>` command resolves to adjacent interactive object and sends `interact` action
FR66: Slash command parser — client-side parser translating `/command args` into server actions via chat input
FR67: Slash commands: `/logout`, `/whisper @name message`, `/interact <direction>`, `/inventory`, `/use <item>`, `/look`, `/who`, `/stats`, `/help`, `/flee`, `/pass`
FR68: Server action `look` — returns objects, NPCs, and players on current tile and adjacent tiles
FR69: Server action `who` — returns list of players in current room
FR70: Server action `stats` — returns current player stats (HP, max_hp, attack, XP)
FR71: Server action `help` — returns list of available actions/commands
FR72: Proximity notification — server notifies player when they move adjacent to an interactive object
FR73: Player stats HUD — always-visible HP bar, XP display, attack stat in web client
FR74: Mob loot drops — combat victory generates loot from NPC's `loot_table`, adds to player inventory, included in `combat_end` message
FR75: Mob loot tables — add loot table entries for all NPC types (goblin_loot, slime_loot, bat_loot, troll_loot, dragon_loot)
FR76: Increased NPC spawn density — add more slime/mob spawn points in larger rooms (town_square, dark_cave)

Total FRs: 15

### Relevant Existing FRs (touched by Epic 10)

FR19: Chest interaction with permanent one-time loot per player (affected by FR64 non-walkable change)
FR26: JSON message routing by 'action' field (extended by FR62, FR68-71 new actions)
FR30: Entity movement broadcasting (extended by FR72 proximity notifications)
FR42: Shared effect registry (loot system reuse for FR74)
FR50: Player disconnect handling (related to FR62 logout)

### Non-Functional Requirements

No new NFRs for Epic 10. Existing NFRs that apply:
NFR2: Max 30 players per room (FR69 `who` action must handle this scale)
NFR8: Room entry payload ~50KB (FR72 proximity data adds minimal overhead)

### GDD Completeness Assessment

Requirements are clearly defined with specific server actions, message formats, and behaviors. Each FR is actionable and testable. No ambiguous requirements identified.

## Epic Coverage Validation

### Coverage Matrix

| FR | Requirement | Epic/Story Coverage | Status |
|----|-------------|-------------------|--------|
| FR62 | Player logout server action | 10.1 Player Logout | Covered |
| FR63 | Player logout client UI + command | 10.1 Player Logout | Covered |
| FR64 | Non-walkable interactive objects | 10.2 Non-Walkable Interactive Objects | Covered |
| FR65 | Directional `/interact <direction>` | 10.5 Directional Object Interaction | Covered |
| FR66 | Slash command parser | 10.3 Slash Command Parser | Covered |
| FR67 | All slash commands wired | 10.6 Slash Command Integration | Covered |
| FR68 | Server action `look` | 10.4 Server Query Actions | Covered |
| FR69 | Server action `who` | 10.4 Server Query Actions | Covered |
| FR70 | Server action `stats` | 10.4 Server Query Actions | Covered |
| FR71 | Server action `help` | 10.4 Server Query Actions | Covered |
| FR72 | Proximity notification | 10.5 Directional Object Interaction | Covered |
| FR73 | Player stats HUD | 10.8 Player Stats HUD | Covered |
| FR74 | Mob loot drops | 10.7 Mob Loot Drops | Covered |
| FR75 | Mob loot tables | 10.7 Mob Loot Drops | Covered |
| FR76 | Increased NPC spawn density | 10.9 NPC Spawn Density | Covered |

### Missing Requirements

None. All 15 FRs (FR62-FR76) are covered by stories in Epic 10.

### Coverage Statistics

- Total Epic 10 FRs: 15
- FRs covered in stories: 15
- Coverage percentage: 100%

## UX Alignment Assessment

### UX Document Status

Not found. No formal UX specification exists. The web demo (`web-demo/`) is a proof-of-concept test client. Production client planned in Godot.

### Architecture ↔ UX Alignment for Epic 10

| UX Feature | Architecture Support | Status |
|-----------|---------------------|--------|
| Logout button + command | No `logout` action in architecture section 8.2 | Gap — FR62 extends the action table |
| Slash command parser | Client-side only; architecture defines server actions | Aligned — parser is a translation layer |
| Stats HUD | Stats sent in `login_success` (architecture 8.3) | Aligned — data available, client renders |
| Proximity notifications | Movement result in architecture 8.3 | Gap — `entity_moved` doesn't include nearby objects; FR72 extends move results |
| Directional interaction | `interact` action exists (architecture 8.2) | Gap — current `interact` requires `target_id`, not direction; FR65 extends the handler |
| Mob loot drops | `combat_end` message exists (architecture 8.3); NPC `loot_table` field defined (architecture 4.3) | Aligned — hook points exist, just needs wiring |
| Non-walkable objects | Room object system (architecture 4.1) lists interactive objects as "Varies" walkability | Aligned — design change, not architectural conflict |

### Warnings

1. **Architecture doc needs update after Epic 10:** Section 8.2 (Client→Server Actions) should be updated to include new actions (`logout`, `look`, `who`, `stats`, `help_actions`). Section 8.3 (Server→Client Messages) should include new types (`logged_out`, `look_result`, `who_result`, `stats_result`, `help_result`).
2. **No UX spec for slash command syntax:** The command syntax is defined in story acceptance criteria only. For consistency when building the Godot client, consider documenting the command reference as a standalone artifact after implementation.

## Epic Quality Review

### Best Practices Compliance

- [x] Epic delivers player/user value
- [x] Epic can function independently
- [x] Stories appropriately sized
- [x] No forward dependencies
- [x] Data structures created when needed
- [x] Clear acceptance criteria (Given/When/Then)
- [x] Traceability to FRs maintained (15/15 mapped)

### Violations Found

#### Critical Violations
None.

#### Major Issues

1. **Story 10.2 — Adjacency check may break existing interact tests.** The story adds a "Too far to interact" error for non-adjacent players, but existing tests (Story 3.1, 3.2) were written assuming players can interact regardless of distance. The acceptance criteria should explicitly note that existing interact tests need updating. **Severity: Major.** **Remediation:** Add AC to Story 10.2: "Given existing interaction tests assume no distance check, When the story is complete, Then all affected tests in test_objects.py and test_integration.py are updated."

2. **Story 10.7 — Loot table relocation may break chest tests.** Moving `generate_loot()` from `chest.py` to `server/items/loot.py` changes the import path. Existing chest tests that import from `chest.py` will break. **Severity: Major.** **Remediation:** AC already covers this ("chest.py imports from the shared location"), but should explicitly mention updating test imports.

3. **Story 10.1 — Logout while in combat behavior underspecified.** The AC says "treated as flee" but doesn't specify: does the player receive a `combat_fled` message before `logged_out`? Is combat state saved? What if the player is the last combat participant — does the mob reset? **Severity: Major.** **Remediation:** Add detailed combat-logout sequence to Story 10.1 ACs.

#### Minor Concerns

1. **Story 10.4 — `help_actions` action name inconsistent.** The server action is `help_actions` but the slash command is `/help`. This works (the parser maps `/help` → `help_actions`) but the naming inconsistency could confuse developers. Consider renaming the server action to `help` if it doesn't conflict. **Severity: Minor.**

2. **Story 10.8 — Stats HUD doesn't specify how stats update during combat.** The AC says "stats update in real-time" but doesn't specify the trigger — is it from `combat_turn` messages, a separate `stats_update` message, or the existing `combat_end`? During combat, HP changes are communicated via `combat_turn` — the HUD should parse those. **Severity: Minor.** **Remediation:** Clarify in AC that HUD reads HP from `combat_turn` messages during combat.

3. **Story 10.6 — No `/chat` command.** Regular chat is sent by typing without a `/` prefix, but there's no explicit `/chat` or `/say` command for consistency. This is fine for the prototype but may be expected by players familiar with MMO conventions. **Severity: Minor.**

## Summary and Recommendations

### Overall Readiness Status

**READY — with 3 major issues to address in story ACs before implementation.**

The epic structure is sound, FR coverage is 100%, dependencies are clean, and the architecture supports all planned features. The 3 major issues are AC gaps that should be fixed in the epics.md stories before creating detailed story files — they are not blockers but will cause rework if caught during code review instead.

### Critical Issues Requiring Immediate Action

None.

### Major Issues Requiring AC Updates

1. **Story 10.2** — Add AC for updating existing interact tests that assume no distance check
2. **Story 10.7** — Add AC for updating test imports after loot table relocation
3. **Story 10.1** — Clarify combat-logout sequence (message order, last-participant behavior)

### Minor Recommendations (address during implementation)

1. Consider renaming `help_actions` server action to `help` for consistency with `/help` command
2. Clarify in Story 10.8 that HUD reads HP from `combat_turn` messages during combat
3. Consider adding `/say` or `/chat` command for MMO convention consistency

### Architecture Update Required Post-Implementation

After Epic 10 is complete, update `architecture.md`:
- Section 8.2: Add `logout`, `look`, `who`, `stats`, `help_actions` to Client→Server actions table
- Section 8.3: Add `logged_out`, `look_result`, `who_result`, `stats_result`, `help_result` to Server→Client messages table
- Section 4.1: Update interactive objects walkability from "Varies" to "No (blocking)"

### Final Note

This assessment identified **3 major issues** and **3 minor concerns** across epic quality and UX alignment. All are AC refinement gaps — no structural, coverage, or dependency problems found. The epic is ready for implementation once the 3 major AC updates are applied to epics.md.
