# Epic 16 Gap Analysis: Evaluation Against 7 Criteria

**Date**: 2026-04-12
**Evaluating**: `_bmad-output/planning-artifacts/epic-16-tech-spec.md` (14 stories)

---

## Evaluation Summary

| # | Criterion | Addressed by Epic 16? | Verdict |
|---|-----------|----------------------|---------|
| 1 | Web UX is PoC only, no game logic | Not in scope (already passing) | **PASS** — no changes needed |
| 2 | Server codebase well organized | Stories 16.4, 16.5, 16.6 | **ADDRESSED** |
| 3 | Easy to add features/plugins | Stories 16.1, 16.2, 16.4 | **PARTIALLY ADDRESSED** |
| 4 | Easy DB migration to PostgreSQL | Not in scope (already passing) | **PASS** — no changes needed |
| 5 | Easy integration with Godot/Unity/Unreal | Stories 16.3, 16.7, 16.8, 16.9, 16.10 | **ADDRESSED** |
| 6 | Protocol well defined, easy to extend | Stories 16.1, 16.2, 16.3, 16.7, 16.11 | **ADDRESSED** |
| 7 | Chat supports markdown text | **NOT ADDRESSED** | **GAP** |

---

## Detailed Analysis

### Criterion 1: Web UX — PoC, No Game Logic

**Status: Already passing. No epic work needed.**

The codebase review (`_bmad-output/implementation-artifacts/codebase-review-2026-04-12.md`, Section 1) confirmed the web-demo is a clean thin client. All 1900 lines of `web-demo/js/game.js` are state management, message dispatch, and DOM rendering. Zero game logic. ISS-021 through ISS-028 (completed in prior epics) already cleaned up all game logic leaks.

Epic 16 does not introduce any game logic into the web-demo. Story 16.8 (Heartbeat) adds a `ping`→`pong` handler in the web-demo client, which is networking infrastructure, not game logic.

**No gap.**

### Criterion 2: Server Organization and Structure

**Status: Addressed by Stories 16.4, 16.5, 16.6.**

- **Story 16.4** (Combat Service Layer): Moves 230 lines of business logic from `server/net/handlers/combat.py` (lines 22-251) into `server/combat/service.py`. This cleanly separates the handler layer (input parsing, WebSocket I/O) from the business logic layer (XP distribution, loot rolling, combat end orchestration).
- **Story 16.5** (Login Decompose): Breaks the 167-line `handle_login` (`server/net/handlers/auth.py:112-278`) into 4-5 focused helper functions. Eliminates variable shadowing (`session` at line 274), promotes `_DEFAULT_STATS` to module-level constant.
- **Story 16.6** (Trade DI): Replaces `TradeManager.set_connection_manager()` setter injection (`server/trade/manager.py:28-30`) with constructor injection, matching `PartyManager` pattern (`server/app.py:45`). Eliminates the DI inconsistency.

**No gap.**

### Criterion 3: Easy to Add Features and Plugins

**Status: Partially addressed.**

- **Story 16.1** (Inbound Schemas): Defines Pydantic models for all 21 actions with an `ACTION_SCHEMAS` mapping. Adding a new action requires adding a schema class + one `register()` call. This is more structured than the current ad-hoc `data.get()` approach.
- **Story 16.2** (Outbound Schemas): Documents all 38 outbound message types as Pydantic models. New message types follow the same pattern.
- **Story 16.4** (Combat Service): The `EffectRegistry` pattern already allows adding new combat effects. Extracting the service layer makes the combat system more composable.

**Remaining gap**: The epic does not add auto-discovery or a plugin loading mechanism. All handler registration is still explicit in `Game._register_handlers()` (`server/app.py:142-232`). This was noted in the codebase review as acceptable at current scale. No story addresses this, which is the right call — adding a plugin system would be premature abstraction.

**Acceptable gap — no change needed.**

### Criterion 4: Database Migration to PostgreSQL

**Status: Already passing. No epic work needed.**

The codebase review confirmed:
- `DATABASE_URL` is configurable via environment variable (`server/core/config.py:79`)
- `ALEMBIC_DATABASE_URL` property handles driver stripping (`server/core/config.py:86-92`)
- Connection pooling conditionally applied for non-SQLite (`server/core/database.py:10-14`)
- All queries use SQLAlchemy ORM constructs — no raw SQL, no SQLite-specific functions
- Alembic migrations in place

Epic 16 does not introduce any SQLite-specific code. Story 16.9 (Session Tokens) uses an in-memory `TokenStore`, not a DB table, which is appropriate for short-lived tokens.

**No gap.**

### Criterion 5: Engine Integration (Godot, Unity, Unreal)

**Status: Addressed by Stories 16.3, 16.7, 16.8, 16.9, 16.10.**

- **Story 16.3** (Protocol Doc): Generates a protocol specification from schemas. This is the primary deliverable for engine client developers — they can implement a client from the spec without reading server code.
- **Story 16.7** (Request ID): Adds optional `request_id` echo for async client networking. Essential for Godot/Unity/Unreal async patterns.
- **Story 16.8** (Heartbeat): Adds ping/pong for connection health detection. Essential for mobile (iOS/Android kill background WebSocket connections).
- **Story 16.9** (Session Tokens): Token-based reconnection without re-sending credentials. Essential for mobile where OS backgrounding kills connections.
- **Story 16.10** (Grace Period): Keeps player state during brief disconnects. Prevents "check a text message → lose your combat" on mobile.

**No gap.**

### Criterion 6: Protocol Well Defined and Extensible

**Status: Addressed by Stories 16.1, 16.2, 16.3, 16.7, 16.11.**

- **Stories 16.1/16.2**: Machine-readable schemas for all inbound and outbound messages.
- **Story 16.3**: Human-readable protocol spec document.
- **Story 16.7**: Request-response correlation mechanism.
- **Story 16.11**: Message acknowledgment for reliable delivery across reconnections.

The protocol is naturally extensible — new `action`/`type` values don't break existing clients.

**No gap.**

### Criterion 7: Chat Supports Markdown Text

**Status: NOT ADDRESSED. This is a gap.**

#### Current State

**Server** (`server/net/handlers/chat.py:17-63`):
- Receives `message` string from client
- Validates length against `settings.MAX_CHAT_MESSAGE_LENGTH` (500 chars, `server/core/config.py:70`)
- Broadcasts raw `message` string as-is: `{"type": "chat", "sender": "...", "message": "...", "whisper": false}`
- No markdown parsing, validation, or sanitization
- Same applies to party chat (`server/net/handlers/party.py`, `party_chat` type)

**Web-demo client** (`web-demo/js/game.js:1023-1029`):
- `appendChat()` function creates a `<div>` and sets `div.textContent = text` (line 1026)
- `textContent` renders as **plain text** — no HTML interpretation, no markdown rendering
- This is currently safe (no XSS) but means markdown syntax would display as raw characters

#### What's Needed

A new story to add markdown support to the chat system. The server should remain transport-agnostic (pass markdown text through as-is), and rendering should be a client concern. However, the server needs input validation to prevent malicious content.

**This gap requires a new Story 16.12.**

---

## Story 16.12: Chat Markdown Support

**Goal**: Enable markdown-formatted text in chat messages (room chat, whisper, party chat, announcements). The server remains **fully client-agnostic** — it passes message content through as-is. Rendering and sanitization are client concerns.

### Design Principles

1. **Server is markdown-agnostic** — it treats chat messages as opaque strings. It does not parse, transform, or sanitize markdown. It does not strip HTML tags. This is consistent with the client-agnostic architecture: a Godot client uses BBCode (not HTML), a Unity client uses TextMeshPro tags, a web client uses HTML. Server-side HTML stripping would be an HTML-specific defense that corrupts legitimate messages (e.g., `x < y` becomes `x  y`) and provides no protection for non-HTML clients.

2. **Each client owns its rendering security** — The web-demo must HTML-escape content before any markdown-to-HTML conversion. Godot must escape BBCode. Unity must escape TMP tags. This is the only architecture that is truly client-agnostic.

3. **Server adds a `format` metadata field** — signals to clients that markdown rendering is appropriate, read from a configurable setting. Clients that don't support markdown ignore this field and render as plain text.

4. **Server does content-neutral validation only** — maximum length (existing `MAX_CHAT_MESSAGE_LENGTH: 500` at `server/core/config.py:70`), strip control characters (null bytes, etc.). These are game rules, not rendering rules.

### Why NOT sanitize on the server

The adversarial review identified that server-side HTML stripping:
- **Corrupts legitimate messages** — `I think x < y and a > b` gets mangled
- **Is HTML-specific** — useless for Godot (BBCode) or CLI clients
- **Misses markdown-based XSS** — `[click](javascript:alert(1))` contains no HTML tags but is dangerous if a client ever adds link markdown. The server regex provides no protection.
- **Creates false confidence** — developers assume the server has handled XSS, then add `.innerHTML` in the client without proper escaping

The correct security boundary is the client's rendering layer, not the server's transport layer.

### Implementation

**1. Config** — Add to `server/core/config.py`:
```python
CHAT_FORMAT: str = "markdown"  # "plain" or "markdown" — signals client rendering mode
```

**2. Server-side: content-neutral validation** — Add control character stripping to `server/net/handlers/chat.py` (before the existing length check at line 29):
```python
# Strip null bytes and control characters (content-neutral, not rendering-specific)
message = message.translate({i: None for i in range(32) if i not in (10, 13)})  # keep \n, \r
```

This removes null bytes, backspace, escape sequences, and other control characters that could cause issues in any rendering technology. It does NOT touch `<`, `>`, `&`, or any printable characters.

**3. Protocol change** — Add `format` field to outbound chat messages, read from `settings.CHAT_FORMAT`:

```python
# server/net/handlers/chat.py — modified whisper msg (lines 47-52):
msg = {
    "type": "chat",
    "sender": entity.name,
    "message": message,
    "format": settings.CHAT_FORMAT,
    "whisper": True,
}

# server/net/handlers/chat.py — modified room broadcast msg (lines 57-62):
msg = {
    "type": "chat",
    "sender": entity.name,
    "message": message,
    "format": settings.CHAT_FORMAT,
    "whisper": False,
}
```

Same change for:
- `party_chat` messages in `server/net/handlers/party.py` (line 497, add `"format": settings.CHAT_FORMAT`)
- `announcement` messages in `server/app.py:238-242` (add `"format": settings.CHAT_FORMAT`)

**4. Outbound schema update** (Story 16.2 dependency) — Update schemas in `server/net/outbound_schemas.py`:
```python
class ChatOutboundMessage(BaseModel):
    type: str = "chat"
    sender: str
    message: str
    format: str = "markdown"  # "plain" or "markdown"
    whisper: bool

class PartyChatOutboundMessage(BaseModel):
    type: str = "party_chat"
    from_: str = Field(alias="from")
    message: str
    format: str = "markdown"

class AnnouncementOutboundMessage(BaseModel):
    type: str = "announcement"
    message: str
    format: str = "markdown"
```

**5. Web-demo client** — Update `appendChat()` in `web-demo/js/game.js:1023-1029`. The web-demo is responsible for its own XSS prevention:

```javascript
function appendChat(text, type = 'chat', format = 'plain') {
  const div = document.createElement('div');
  div.className = `chat-msg chat-${type}`;
  if (format === 'markdown') {
    // SECURITY: HTML-escape FIRST, then apply safe markdown subset.
    // This order ensures no user content becomes executable HTML.
    // Only bold/italic/code/strikethrough — NO links, NO images (XSS vectors).
    let safe = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
    // Process code spans FIRST (protect contents from further markdown processing)
    const codeSpans = [];
    safe = safe.replace(/`(.+?)`/g, (_, code) => {
      codeSpans.push(`<code>${code}</code>`);
      return `\x00CODE${codeSpans.length - 1}\x00`;
    });
    // Then bold, italic, strikethrough
    safe = safe
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/~~(.+?)~~/g, '<del>$1</del>');
    // Reinsert code spans
    safe = safe.replace(/\x00CODE(\d+)\x00/g, (_, i) => codeSpans[parseInt(i)]);
    div.innerHTML = safe;
  } else {
    div.textContent = text;
  }
  $chatLog.appendChild(div);
  $chatLog.scrollTop = $chatLog.scrollHeight;
}
```

Key security properties:
- HTML-escaping happens **before** any markdown substitution → user content can never become executable HTML
- Code spans processed **first** and replaced with placeholders → markdown inside code blocks is preserved literally
- **No link or image markdown** → eliminates `javascript:` URI and `onerror` XSS vectors entirely
- Only 4 safe formatting patterns: `**bold**`, `*italic*`, `` `code` ``, `~~strikethrough~~`

Update `handleChat` to pass format:
```javascript
function handleChat(data) {
  const cls = data.whisper ? 'chat-whisper' : '';
  const prefix = data.whisper ? '[whisper] ' : '';
  appendChat(`${prefix}${data.sender}: ${data.message}`, cls || 'chat', data.format || 'plain');
}
```

Same pattern for `handlePartyChat` and `handleAnnouncement`.

**Note on criterion 1 compliance**: The web-demo markdown renderer is purely **display logic** (string → styled HTML rendering), not game logic. It does not compute damage, resolve effects, validate moves, or make gameplay decisions. This is the same category as `tileClass()` (mapping tile types to CSS classes) and `setHpBarColor()` (HP bar color thresholds), which the codebase review already classified as acceptable display-only logic.

**6. Game engine clients** — Each engine has its own rich text system. The `format: "markdown"` field signals clients to apply their engine-specific markdown → native rendering conversion:
- **Godot 4.x**: `RichTextLabel` with BBCode. Client converts `**bold**` → `[b]bold[/b]`, `*italic*` → `[i]italic[/i]`, etc. Must escape `[` to prevent BBCode injection.
- **Unity**: `TextMeshPro` with rich text tags. Client converts `**bold**` → `<b>bold</b>`. Must escape `<` to prevent TMP tag injection.
- **Unreal**: `URichTextBlock` with decorator subsystem. Client converts to UE rich text markup.

Clients that don't support markdown ignore the `format` field and render as plain text (backward compatible).

### Files Changed
- **Modified**: `server/core/config.py` (add `CHAT_FORMAT` setting)
- **Modified**: `server/net/handlers/chat.py` (add control char stripping, add `"format": settings.CHAT_FORMAT` to chat messages)
- **Modified**: `server/net/handlers/party.py` (add `"format": settings.CHAT_FORMAT` to `party_chat` messages)
- **Modified**: `server/app.py` (add `"format": settings.CHAT_FORMAT` to `announcement` messages)
- **Modified**: `server/net/outbound_schemas.py` (update chat/party_chat/announcement schemas with `format` field)
- **Modified**: `web-demo/js/game.js` (update `appendChat()` with safe markdown rendering, update chat/party_chat/announcement handlers to pass format)

### Acceptance Criteria
- [ ] All chat-type outbound messages (`chat`, `party_chat`, `announcement`) include `"format"` field from `settings.CHAT_FORMAT`
- [ ] `CHAT_FORMAT` setting in `server/core/config.py` (default `"markdown"`, can be set to `"plain"` to disable)
- [ ] Server does NOT strip HTML tags or modify printable message content (client-agnostic)
- [ ] Server strips control characters (null bytes, etc.) from chat messages (content-neutral validation)
- [ ] `MAX_CHAT_MESSAGE_LENGTH: 500` still enforced (no change)
- [ ] Web-demo: HTML-escapes content BEFORE markdown regex substitution (XSS prevention)
- [ ] Web-demo: code spans processed FIRST (prevents markdown formatting inside code)
- [ ] Web-demo: only supports safe subset — bold, italic, code, strikethrough. NO links, NO images.
- [ ] Clients that ignore the `format` field see plain text (backward compatible)
- [ ] All 808+ existing tests pass unchanged

### Test Plan
- Unit test: control character stripping removes null bytes but preserves `\n`
- Unit test: chat message with `<script>` passes through server unmodified (server is client-agnostic)
- Integration test: send markdown chat → verify `format` field matches `settings.CHAT_FORMAT` in broadcast
- Integration test: set `CHAT_FORMAT=plain` → verify `"format": "plain"` in broadcast
- Web-demo manual test: verify **bold**, *italic*, `code`, ~~strikethrough~~ render correctly
- Web-demo manual test: verify `<script>alert(1)</script>` in chat renders as escaped text, not executed
- Web-demo manual test: verify `` `**not bold**` `` renders as literal `**not bold**` in code span

---

## Updated Epic 16 Scope

With Stories 16.4a, 16.10a, and 16.12, the epic now has **14 stories** covering all 7 criteria:

| Story | Criterion(s) | Summary |
|-------|-------------|---------|
| 16.1 | 3, 6 | Inbound Pydantic schemas |
| 16.2 | 3, 6 | Outbound Pydantic schemas |
| 16.3 | 5, 6 | Protocol specification document |
| 16.4a | 2 | Refactor grant_xp (apply_xp + notify_xp) |
| 16.4 | 2 | Combat service layer extraction |
| 16.5 | 2 | Login handler decomposition |
| 16.6 | 2 | TradeManager constructor injection |
| 16.7 | 5, 6 | Request-response correlation |
| 16.8 | 5 | Heartbeat / connection health |
| 16.9 | 5 | Session tokens for reconnection |
| 16.10a | 5 | Combat turn timeout enforcement |
| 16.10 | 5 | Disconnected player grace period |
| 16.11 | 6 | Message acknowledgment IDs |
| 16.12 | 7 | Chat markdown support |

Criteria 1 and 4 are already passing and require no new stories.
