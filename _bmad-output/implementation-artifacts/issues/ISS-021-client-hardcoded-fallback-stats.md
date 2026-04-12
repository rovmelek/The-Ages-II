# ISS-021: Client Hardcoded Fallback Stats (hp: 105)

**Severity:** Medium
**Component:** web-demo/js/game.js
**Found during:** Codebase review (adversarial analysis)

## Description

The web demo client has hardcoded fallback player stats at line 522-523:

```js
stats: data.stats || { hp: 105, max_hp: 105, attack: 10, xp: 0, level: 1,
  strength: 1, dexterity: 1, constitution: 1, intelligence: 1, wisdom: 1, charisma: 1 },
```

The `hp: 105` / `max_hp: 105` values do **not match** the server's `DEFAULT_BASE_HP = 100` in `server/core/config.py`. This is stale data that would display incorrect HP if the fallback ever fires.

## Root Cause

The web demo is a proof-of-concept thin client and should not contain any game balance values. The server always sends `stats` in the login success response, making the fallback unnecessary.

## Proposed Fix

Remove the fallback object entirely. Use `data.stats` directly — it is always provided by the server on successful login. If defensively coding, use an empty object `{}` rather than fabricating game values.

## Impact

- If the fallback fires, player sees `105/105 HP` instead of the correct value
- Maintenance hazard: any config change to `DEFAULT_BASE_HP` silently drifts from client
