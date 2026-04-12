# Story 16.12: Chat Markdown Support

Status: done

## Story

As a player,
I want to use markdown formatting in chat messages,
so that I can express myself more clearly in room chat, whispers, and party chat.

## Acceptance Criteria

1. Chat messages include `"format"` field from `settings.CHAT_FORMAT` (default `"markdown"`)
2. `CHAT_FORMAT` configurable — set to `"plain"` to disable markdown signaling
3. Server does NOT strip HTML tags or modify printable message content
4. Server strips control characters (null bytes, etc.) — content-neutral validation
5. Web-demo: HTML-escapes BEFORE markdown regex (XSS prevention)
6. Web-demo: code spans processed FIRST (prevents formatting inside code)
7. Web-demo: safe subset only — bold, italic, code, strikethrough. NO links, NO images
8. Clients that ignore `format` field see plain text (backward compatible)
9. All existing tests pass (updated 4 tests for new `format` field)

## Tasks / Subtasks

- [x] Task 1: Add `CHAT_FORMAT` setting to `server/core/config.py`
- [x] Task 2: Add control character stripping to `server/net/handlers/chat.py`
- [x] Task 3: Add `format` field to chat, party_chat, and announcement messages
- [x] Task 4: Update outbound schemas with `format` field
- [x] Task 5: Update web-demo client with safe markdown rendering
- [x] Task 6: Update tests for new `format` field
- [x] Task 7: Regenerate protocol-spec.md
- [x] Task 8: Run full test suite — all 959 pass

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Completion Notes List

- Added `CHAT_FORMAT: str = "markdown"` to Settings
- Control character stripping in chat handler (preserves \n, \r)
- `format` field added to chat (room + whisper), party_chat, and announcement messages
- Updated 3 outbound schemas: OutboundChatMessage, OutboundPartyChatMessage, AnnouncementMessage
- Web-demo `renderSafeMarkdown()`: HTML-escape first, code spans second, then bold/italic/strikethrough. No links/images.
- Updated `appendChat()` to accept `format` parameter and render markdown when `format === 'markdown'`
- Updated 4 tests: test_chat.py (2), test_events.py (1), test_party_chat.py (1)
- Regenerated protocol-spec.md to reflect schema changes
- All 959 tests pass

### File List

- **Modified**: `server/core/config.py` (add `CHAT_FORMAT`)
- **Modified**: `server/net/handlers/chat.py` (control char strip, `format` field)
- **Modified**: `server/net/handlers/party.py` (`format` field on party_chat)
- **Modified**: `server/app.py` (`format` field on announcement)
- **Modified**: `server/net/outbound_schemas.py` (`format` field on 3 schemas)
- **Modified**: `web-demo/js/game.js` (`renderSafeMarkdown`, updated `appendChat` + handlers)
- **Modified**: `tests/test_chat.py` (updated expected messages)
- **Modified**: `tests/test_events.py` (updated expected announcement)
- **Modified**: `tests/test_party_chat.py` (updated expected party_chat)
- **Modified**: `_bmad-output/planning-artifacts/protocol-spec.md` (regenerated)
