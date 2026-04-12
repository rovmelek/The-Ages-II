# Issue: /inventory command has no chat output

**ID:** ISS-011
**Severity:** Low (UX)
**Status:** Fixed
**Delivery:** Post-Epic 10 (Gameplay Polish follow-up)
**Created:** 2026-04-10
**Assigned:** BMad Developer

## Description

The `/inventory` slash command updates the inventory panel in the sidebar but produces no feedback in the chat area. Players expect chat-based commands to produce chat-based output. The command should also display item keys so players know what to type for `/use`.

## Expected

When a player types `/inventory`, a formatted list of items with their keys and quantities should appear in the chat log, in addition to updating the sidebar panel.

## Fix Applied

Added chat output to `handleInventory()` in `game.js` that lists each item with its key and quantity, or shows "Inventory is empty" if no items.

## Files Modified

- `web-demo/js/game.js` — `handleInventory()` now appends item list to chat
