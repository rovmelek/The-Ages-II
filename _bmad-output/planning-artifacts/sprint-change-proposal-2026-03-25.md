# Sprint Change Proposal — 2026-03-25

## 1. Issue Summary

During Epic 7 (Server Hardening) review, we identified that `Game.shutdown()` saves all player states and disconnects cleanly, but can only be triggered by process termination (Ctrl+C / SIGINT). No remote admin capability exists for graceful shutdown or restart without SSH access to kill the process.

**Discovery context**: Epic 7 Stories 7.7 (Graceful Server Shutdown) and 7.8 (Client Disconnect Login Screen) implemented the mechanics but not the trigger mechanism.

## 2. Impact Analysis

- **Epic Impact**: No existing epics affected. New Epic 9 created for server administration.
- **Story Impact**: No existing stories modified.
- **Artifact Conflicts**: `architecture.md` needs minor updates (new REST endpoints, admin auth) — to be updated after implementation.
- **Technical Impact**: Additive only — new REST endpoints, new config setting (`ADMIN_SECRET`), process re-execution for restart. Builds on existing `Game.shutdown()`.

## 3. Recommended Approach

**Direct Adjustment** — Add Epic 9 (Server Administration) with 3 new stories. Zero risk to existing functionality.

- **Effort**: Low-Medium
- **Risk**: Low
- **Dependencies**: 9.1 (auth) must come before 9.2 (shutdown) and 9.3 (restart)

**Alternatives considered**:
- Adding to Epic 8: Rejected — Epic 8 is "World Expansion" (gameplay features), admin ops is a different concern
- Rollback: Not applicable
- MVP scope change: Not applicable

## 4. Detailed Changes

### 4.1 New Functional Requirements (added to `epics.md`)

| FR | Epic | Description |
|----|------|-------------|
| FR59 | Epic 9 | Admin authentication (shared secret) |
| FR60 | Epic 9 | Admin-triggered graceful shutdown |
| FR61 | Epic 9 | Admin-triggered server restart |

### 4.2 New Epic 9: Server Administration (added to `epics.md`)

3 stories:
- **9.1 Admin Authentication**: `ADMIN_SECRET` config, 403 rejection, auth middleware for admin endpoints
- **9.2 Admin Shutdown Command**: `POST /admin/shutdown`, triggers `Game.shutdown()`, exits uvicorn
- **9.3 Server Restart Mechanism**: `POST /admin/restart`, shutdown + `os.execv()` re-execution

### 4.3 Sprint Status (updated `sprint-status.yaml`)

- Added Epic 8 entries (were missing from tracking): `backlog`
- Added Epic 9 entries: `backlog`

## 5. Implementation Handoff

- **Scope**: Minor — direct implementation by dev team
- **Sequence**: 9.1 → 9.2 → 9.3
- **Workflow**: `/gds-create-story` for each story, then `/gds-dev-story` to implement
- **Post-implementation**: Update `architecture.md`, `CLAUDE.md`, `project-context.md`

## Approval

- **Approved by**: Kevin
- **Date**: 2026-03-25
- **Mode**: Incremental review
