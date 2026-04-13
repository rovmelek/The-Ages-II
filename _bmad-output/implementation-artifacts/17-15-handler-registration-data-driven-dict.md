# Story 17.15: Handler Registration Data-Driven Dict

Status: done

## Story

As a developer maintaining the game server,
I want handler registration driven by a data dict instead of 23 imperative calls,
so that adding a new action requires only one dict entry instead of a new code block.

## Acceptance Criteria

1. A `HANDLERS` dict in `server/app.py` maps each action string to its handler function.

2. `_register_handlers()` iterates `HANDLERS` in a loop calling `self.router.register(action, lambda ...)` for each entry.

3. All 23 actions are registered with the same handler functions as before — no behavioral change.

4. The 23 individual `self.router.register()` calls are removed.

5. All existing tests pass (`make test`).

## Tasks / Subtasks

- [x] Task 1: Define `HANDLERS` dict in `server/app.py` (AC: #1)
  - [x] Create a module-level or method-level dict mapping action strings to handler functions
  - [x] Include all 23 actions with their corresponding handler functions
  - [x] Maintain existing import structure for handler functions

- [x] Task 2: Rewrite `_register_handlers()` to use loop (AC: #2, #3, #4)
  - [x] Replace 23 imperative register calls with a single loop over `HANDLERS`
  - [x] Each iteration: `self.router.register(action, lambda ws, d, h=handler: h(ws, d, game=self))`
  - [x] The `h=handler` default arg is CRITICAL to avoid late-binding closure issues

- [x] Task 3: Run tests (AC: #5)
  - [x] Run `make test` — all tests must pass
  - [x] No new tests needed — this is a pure refactor with identical behavior

## Dev Notes

### Current Registration Pattern (app.py `_register_handlers()`)

23 calls like:
```python
self.router.register(
    "login",
    lambda ws, d: handle_login(ws, d, game=self),
)
```

### Critical: Lambda Late-Binding

When using a loop, `lambda ws, d: handler(ws, d, game=self)` would capture the LOOP VARIABLE `handler` by reference, meaning all 23 lambdas would call the LAST handler. Use default argument binding:
```python
lambda ws, d, h=handler: h(ws, d, game=self)
```

### Architecture Decision

- **ADR-17-6**: Data-driven dict + loop for handler registration — no decorator auto-discovery. Simple, explicit, and easy to grep.

### Files to Modify

| File | Change |
|------|--------|
| `server/app.py` | Replace 23 register calls with HANDLERS dict + loop in `_register_handlers()` |

### All 23 Actions and Their Handlers

The handler imports are at the top of `_register_handlers()` (lines ~165-185). The dict should map:

| Action | Handler Function | Module |
|--------|-----------------|--------|
| `login` | `handle_login` | `server.net.handlers.auth` |
| `register` | `handle_register` | `server.net.handlers.auth` |
| `logout` | `handle_logout` | `server.net.handlers.auth` |
| `reconnect` | `handle_reconnect` | `server.net.handlers.auth` |
| `move` | `handle_move` | `server.net.handlers.movement` |
| `chat` | `handle_chat` | `server.net.handlers.chat` |
| `party_chat` | `handle_party_chat` | `server.net.handlers.party` |
| `interact` | `handle_interact` | `server.net.handlers.interact` |
| `play_card` | `handle_play_card` | `server.net.handlers.combat` |
| `pass_turn` | `handle_pass_turn` | `server.net.handlers.combat` |
| `flee` | `handle_flee` | `server.net.handlers.combat` |
| `use_item_combat` | `handle_use_item_combat` | `server.net.handlers.combat` |
| `inventory` | `handle_inventory` | `server.net.handlers.inventory` |
| `use_item` | `handle_use_item` | `server.net.handlers.inventory` |
| `look` | `handle_look` | `server.net.handlers.query` |
| `who` | `handle_who` | `server.net.handlers.query` |
| `stats` | `handle_stats` | `server.net.handlers.query` |
| `help_actions` | `handle_help_actions` | `server.net.handlers.query` |
| `map` | `handle_map` | `server.net.handlers.query` |
| `level_up` | `handle_level_up` | `server.net.handlers.levelup` |
| `trade` | `handle_trade` | `server.net.handlers.trade` |
| `party` | `handle_party` | `server.net.handlers.party` |
| `pong` | `handle_pong` | `server.net.handlers.auth` |

### What NOT to Do

- Do NOT use decorator-based auto-discovery (ADR-17-6)
- Do NOT change handler function signatures
- Do NOT move imports outside `_register_handlers()` (they're local to avoid circular imports)

### References

- [Source: _bmad-output/planning-artifacts/epics.md#FR147] — HANDLERS dict + loop replaces 23 lambdas
- [Source: CLAUDE.md#Epic 17 Key Decisions] — ADR-17-6

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6
### Debug Log References
### Completion Notes List
- Replaced 23 imperative router.register() calls with handlers dict + loop
- Used h=handler default arg to avoid late-binding closure issue
- Pure refactor — identical behavior, 1066 tests pass
### File List
- server/app.py (MODIFIED) — _register_handlers() rewritten with data-driven dict
