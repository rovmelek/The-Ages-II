# ISS-022: Room Chat Missing Message Length Enforcement

**Severity:** Medium
**Component:** server/net/handlers/chat.py
**Found during:** Codebase review (adversarial analysis)

## Description

The `handle_chat` function in `server/net/handlers/chat.py` does not enforce `settings.MAX_CHAT_MESSAGE_LENGTH` on room chat or whisper messages. By contrast, `handle_party_chat` in `server/net/handlers/party.py` (line 590) properly checks:

```python
if len(message) > settings.MAX_CHAT_MESSAGE_LENGTH:
```

This inconsistency allows a malicious client to send arbitrarily long messages via room chat, which could flood other players' chat windows.

## Root Cause

The length check was added to party chat (Epic 12) but was never back-ported to the original room chat handler (Epic 2).

## Proposed Fix

Add the same `MAX_CHAT_MESSAGE_LENGTH` check to `handle_chat` after the empty-message check, before processing whisper/broadcast logic.

## Impact

- Allows chat abuse via arbitrarily long messages
- Inconsistent validation between room chat and party chat
