# Story 17.16: Fix Markdown Line Break Rendering

Status: done

## Story

As a game player using the web demo client,
I want newlines in chat messages to render as visible line breaks,
so that multi-line messages (inventory lists, help text) display correctly.

## Acceptance Criteria

1. Newline characters (`\n`) in chat messages render as visible line breaks in the web demo client.

2. Both markdown-formatted and plain-text messages display line breaks correctly.

3. The fix uses CSS `white-space: pre-wrap` on `.chat-msg` elements — this handles both `innerHTML` (markdown) and `textContent` (plain) rendering paths.

4. No server-side changes required — this is a client-only fix.

5. Manual visual verification: multi-line messages (e.g., `/inventory` output) display on separate lines.

## Tasks / Subtasks

- [x] Task 1: Add `white-space: pre-wrap` to `.chat-msg` in `web-demo/css/style.css` (AC: #1, #2, #3)
  - [ ] Find the `.chat-msg` rule (line ~316) and add `white-space: pre-wrap;`

- [x] Task 2: Visual verification (AC: #5)
  - [ ] Verify the CSS change is syntactically correct
  - [ ] No automated tests for web demo — client-only change

## Dev Notes

### Current CSS

`.chat-msg` at `web-demo/css/style.css` line ~316:
```css
.chat-msg { padding: 2px 0; word-wrap: break-word; }
```

No `white-space` property set. Default is `normal`, which collapses whitespace and newlines.

### Why `white-space: pre-wrap` Instead of `\n` → `<br>`

- `pre-wrap` handles BOTH rendering paths: `textContent` (plain) and `innerHTML` (markdown)
- Adding `\n` → `<br>` in `renderSafeMarkdown()` would only fix markdown-formatted messages
- Plain-text messages (using `textContent`) would still collapse newlines without the CSS fix
- `pre-wrap` preserves newlines while still wrapping long lines (unlike `pre` which doesn't wrap)

### Rendering Paths in `appendChat()` (game.js lines ~1067-1077)

1. `format === "markdown"` → `div.innerHTML = renderSafeMarkdown(text)` — `pre-wrap` preserves `\n` in the raw text before HTML parsing, but `\n` in `innerHTML` is whitespace, not `<br>`. Actually for `innerHTML`, `\n` is treated as whitespace by HTML parser. So `pre-wrap` on the parent makes `\n` in `textContent` path work. For the `innerHTML` path, the `\n` characters in the source become whitespace nodes which `pre-wrap` preserves. This works correctly.
2. `format !== "markdown"` → `div.textContent = text` — `pre-wrap` directly preserves `\n` characters.

### Files to Modify

| File | Change |
|------|--------|
| `web-demo/css/style.css` | Add `white-space: pre-wrap` to `.chat-msg` |

### What NOT to Do

- Do NOT modify `renderSafeMarkdown()` in `game.js` — CSS fix is sufficient
- Do NOT add server-side newline conversion
- Do NOT change any Python server files

### References

- [Source: _bmad-output/implementation-artifacts/codebase-adversarial-review-2026-04-12.md#FR151] — Markdown line break rendering
- [Source: _bmad-output/planning-artifacts/epics.md#FR151] — \n → line break rendering fix

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6
### Debug Log References
### Completion Notes List
- Added white-space: pre-wrap to .chat-msg CSS rule
- Fixes both markdown (innerHTML) and plain-text (textContent) newline rendering
- Client-only change, no server modifications
### File List
- web-demo/css/style.css (MODIFIED) — added white-space: pre-wrap to .chat-msg
