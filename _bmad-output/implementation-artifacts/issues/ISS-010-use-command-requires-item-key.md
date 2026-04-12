# Issue: /use command requires internal item_key instead of display name

**ID:** ISS-010
**Severity:** Low (UX)
**Status:** Fixed
**Delivery:** Post-Epic 10 (Gameplay Polish follow-up)
**Created:** 2026-04-10
**Assigned:** BMad Developer

## Description

The `/use` slash command requires the internal `item_key` (e.g., `healing_potion`) but the inventory panel displays the friendly name (e.g., "Healing Potion"). Players have no way to discover the correct key to type without inspecting the code or guessing.

## Expected

Players should be able to use items by their display name. Both `/use healing_potion` and `/use Healing Potion` should work.

## Fix Applied

1. **`/use` command now accepts display names:** The client-side handler matches input against both `item_key` and `name` (case-insensitive) from the player's inventory before sending to the server.
2. **Tooltip on inventory items:** Hovering over an item name in the inventory panel shows the exact `/use` command as a tooltip.

## Files Modified

- `web-demo/js/game.js` — `/use` handler resolves display name to item_key; inventory item name gets tooltip
