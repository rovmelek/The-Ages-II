---
name: Document before fixing
description: Always create an issue/enhancement doc before making code changes, even for small fixes
type: feedback
---

Always document bugs and UX issues as ISS-NNN files before making code changes. Follow the project's issue tracking workflow even for small fixes.

**Why:** Kevin called this out when I jumped straight to fixing a UX issue without documenting it first. The project uses a structured issue tracking process (ISS-NNN files in `_bmad-output/implementation-artifacts/issues/` + sprint-status.yaml entries).

**How to apply:** Before touching code for any bug/enhancement not covered by an existing story, create the issue file and sprint status entry first, then implement the fix.
