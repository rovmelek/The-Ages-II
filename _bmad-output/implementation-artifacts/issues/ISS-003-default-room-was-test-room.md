# Issue: Default player spawn room was test_room instead of town_square

**ID:** ISS-003
**Severity:** Medium
**Status:** Fixed
**Delivery:** Epic 1 (Player Login and Room Entry)
**Test:** Manual — register new account, observe spawn location
**Created:** 2026-03-25
**Assigned:** BMad Developer

## Description

New players logging in for the first time were placed in `test_room` (a 5x5 debug room) instead of `town_square` (the intended 100x100 starting area). The default room was hardcoded to `"test_room"` in the login handler.

## Expected

New players should spawn in `town_square`, the main hub area designed as the starting zone with trees, fountains, chests, and a welcoming environment.

## Actual

New players spawned in `test_room`, a tiny 5x5 debug room with minimal objects (a rock, flower, and chest). This gave a poor first impression and didn't represent the intended game world.

## Impact

Poor first-time player experience. The test_room was designed for development debugging, not as a player-facing starting area.

## Design Reference

- Epic 1 Story 1.7: Player Login and Room Entry
- Auth handler: `server/net/handlers/auth.py`
- Room topology: town_square ↔ test_room ↔ other_room ↔ dark_cave ↔ town_square

## Steps to Reproduce

1. Register a new account via WebSocket
2. Login with the new account
3. Observe `room_state` response shows `room_key: "test_room"`

## Screenshot/Video

N/A — verified via WebSocket JSON responses.

## Fix Applied

Changed default room from `"test_room"` to `"town_square"` in `server/net/handlers/auth.py` line 86:
```python
room_key = player.current_room_id or "town_square"
```

Updated test assertions in `tests/test_login.py` and `tests/test_integration.py` to expect `"town_square"`.

## Verification

New player login now returns `room_state` with `room_key: "town_square"`.

## Related Issues

- None

---

**Priority for fix:** This release
