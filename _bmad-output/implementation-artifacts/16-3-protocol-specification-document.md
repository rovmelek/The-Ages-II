# Story 16.3: Protocol Specification Document

Status: done

## Story

As a Godot client developer,
I want a comprehensive protocol specification document,
so that I can implement a game client without reading server source code.

## Acceptance Criteria

1. Protocol spec covers all 21 inbound + 38 outbound message types
2. Each message type lists: fields, types, required/optional, delivery scope
3. Tile type enum documented with all 7 values (FLOOR=0 through STAIRS_DOWN=6)
4. Combat, trade, and party state machines documented
5. Script generates the doc from schema imports (not hand-written)
6. `make protocol-doc` target regenerates protocol-spec.md from current schemas
7. `make check-protocol` target compares generated doc with committed version, fails if out of date
8. Document is sufficient for a Godot developer to implement a client without reading server code
9. Initial connection sequence documented step-by-step with exact message shapes
10. Movement directions documented as up/down/left/right only; vertical transitions are exit-triggered

## Tasks / Subtasks

- [x] Task 1: Create `scripts/generate_protocol_doc.py` (AC: 5)
- [x] Task 2: Generate `_bmad-output/planning-artifacts/protocol-spec.md` (AC: 1, 2, 3, 4, 8, 9, 10)
- [x] Task 3: Add Makefile targets (AC: 6, 7)
- [x] Task 4: Run full test suite — all 959 pass

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Completion Notes List

- Created `scripts/generate_protocol_doc.py` (~170 lines) — auto-generates protocol spec from schema imports
- Generated `_bmad-output/planning-artifacts/protocol-spec.md` (617 lines)
- Added `protocol-doc` and `check-protocol` Makefile targets
- `check-protocol` diffs generated output against committed file, exits non-zero if stale
- All 959 tests pass unchanged

### File List

- **New**: `scripts/generate_protocol_doc.py`
- **New**: `_bmad-output/planning-artifacts/protocol-spec.md`
- **Modified**: `Makefile` (added protocol-doc and check-protocol targets)
