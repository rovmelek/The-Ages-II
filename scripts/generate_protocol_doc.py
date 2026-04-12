#!/usr/bin/env python3
"""Generate protocol-spec.md from Pydantic schemas (Stories 16.1 + 16.2).

Usage:
    python scripts/generate_protocol_doc.py > _bmad-output/planning-artifacts/protocol-spec.md
"""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path
from typing import Any

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import BaseModel

from server.net.schemas import ACTION_SCHEMAS
from server.net import outbound_schemas as _out
from server.room.tile import TileType


def _get_outbound_classes() -> list[tuple[str, type[BaseModel]]]:
    """Discover all outbound message classes (those with a 'type' default)."""
    classes = []
    for name, obj in inspect.getmembers(_out, inspect.isclass):
        if not issubclass(obj, BaseModel) or obj is BaseModel:
            continue
        fields = obj.model_fields
        if "type" in fields and fields["type"].default is not None:
            classes.append((name, obj))
    classes.sort(key=lambda x: x[0])
    return classes


def _schema_fields_table(cls: type[BaseModel]) -> str:
    """Generate a Markdown table of fields for a schema class."""
    lines = ["| Field | Type | Required | Default |", "|-------|------|----------|---------|"]
    for name, info in cls.model_fields.items():
        annotation = info.annotation
        type_str = getattr(annotation, "__name__", str(annotation))
        # Simplify common types
        type_str = type_str.replace("typing.", "").replace("server.net.outbound_schemas.", "")
        required = "Yes" if info.is_required() else "No"
        default = info.default if info.default is not None else "—"
        if isinstance(default, str):
            default = f'`"{default}"`'
        lines.append(f"| `{name}` | `{type_str}` | {required} | {default} |")
    return "\n".join(lines)


def generate() -> str:
    """Generate the full protocol specification document."""
    sections = []

    # --- Header ---
    sections.append("# The Ages II — WebSocket Protocol Specification\n")
    sections.append("> **Auto-generated** from Pydantic schemas by `scripts/generate_protocol_doc.py`.")
    sections.append("> Do not edit manually — run `make protocol-doc` to regenerate.\n")

    # --- Transport ---
    sections.append("## 1. Transport\n")
    sections.append("- **Protocol**: WebSocket (RFC 6455)")
    sections.append("- **Endpoint**: `ws://<host>:<port>/ws/game`")
    sections.append("- **Frame type**: Text (JSON)")
    sections.append("- **Encoding**: UTF-8")
    sections.append("- **Default port**: 8000\n")

    # --- Connection Lifecycle ---
    sections.append("## 2. Connection Lifecycle\n")
    sections.append("### Initial Connection Sequence\n")
    sections.append("1. Client opens WebSocket to `/ws/game`")
    sections.append("2. Client sends `login` or `register` message")
    sections.append("3. Server responds with `login_success` (includes player stats)")
    sections.append("4. Server sends `room_state` (full room snapshot)")
    sections.append("5. Client begins rendering\n")
    sections.append("### Reconnect Sequence (Story 16.9)\n")
    sections.append("1. Client opens WebSocket to `/ws/game`")
    sections.append("2. Client sends `reconnect` with `session_token`")
    sections.append("3. Server responds with `login_success` + `room_state` + combat state if applicable\n")

    # --- Inbound Messages ---
    sections.append("## 3. Inbound Messages (Client → Server)\n")
    sections.append(f"**{len(ACTION_SCHEMAS)} actions** defined.\n")

    for action, cls in sorted(ACTION_SCHEMAS.items()):
        sections.append(f"### `{action}`\n")
        sections.append(_schema_fields_table(cls))
        sections.append("")

    # --- Outbound Messages ---
    outbound = _get_outbound_classes()
    sections.append(f"## 4. Outbound Messages (Server → Client)\n")
    sections.append(f"**{len(outbound)} message types** defined.\n")

    for name, cls in outbound:
        type_field = cls.model_fields.get("type")
        type_val = type_field.default if type_field else name
        sections.append(f"### `{type_val}` ({name})\n")
        sections.append(_schema_fields_table(cls))
        sections.append("")

    # --- Delivery Scopes ---
    sections.append("## 5. Delivery Scopes\n")
    sections.append("| Scope | Description |")
    sections.append("|-------|-------------|")
    sections.append("| **single** | Sent only to the requesting player |")
    sections.append("| **room** | Broadcast to all players in the same room |")
    sections.append("| **room-exclude** | Broadcast to room, excluding the acting player |")
    sections.append("| **combat** | Sent to all combat participants |")
    sections.append("| **party** | Sent to all party members |")
    sections.append("| **trade** | Sent to both trade participants |")
    sections.append("| **all** | Broadcast to all connected players |")
    sections.append("")

    # --- Error Handling ---
    sections.append("## 6. Error Handling\n")
    sections.append("All errors use the same format: `{\"type\": \"error\", \"detail\": \"<message>\"}`\n")
    sections.append("| Error | Trigger |")
    sections.append("|-------|---------|")
    sections.append("| Invalid JSON | Client sends non-JSON text |")
    sections.append("| Missing action field | JSON object without `action` key |")
    sections.append("| Unknown action | `action` value not in registered handlers |")
    sections.append("| Validation error | Message fields fail Pydantic schema validation |")
    sections.append("| Not logged in | Action requires auth but player not authenticated |")
    sections.append("")

    # --- Tile Types ---
    sections.append("## 7. Tile Type Enum\n")
    sections.append("| Name | Value | Walkable |")
    sections.append("|------|-------|----------|")
    walkable = {TileType.FLOOR, TileType.EXIT, TileType.MOB_SPAWN, TileType.STAIRS_UP, TileType.STAIRS_DOWN}
    for t in TileType:
        sections.append(f"| `{t.name}` | {t.value} | {'Yes' if t in walkable else 'No'} |")
    sections.append("")

    # --- Movement Directions ---
    sections.append("## 8. Movement Directions\n")
    sections.append("Player movement uses four directions: `up`, `down`, `left`, `right`.\n")
    sections.append("Vertical transitions (`ascend`/`descend`) are **exit-triggered** — they fire")
    sections.append("automatically when a player steps onto `STAIRS_UP` or `STAIRS_DOWN` tiles.")
    sections.append("They are NOT player-input directions.\n")

    # --- Combat Flow ---
    sections.append("## 9. Combat Flow\n")
    sections.append("```")
    sections.append("Player steps on MOB_SPAWN with alive NPC")
    sections.append("  → Server sends combat_start to all participants")
    sections.append("  → Turn loop:")
    sections.append("      Current player sends: play_card / pass_turn / use_item_combat / flee")
    sections.append("      Server broadcasts: combat_turn (with result + updated state)")
    sections.append("  → Combat ends:")
    sections.append("      Victory/Defeat → combat_end (per-player, with rewards/loot)")
    sections.append("      Flee → combat_fled (to fleeing player) + combat_update (to remaining)")
    sections.append("```\n")

    # --- Trade Flow ---
    sections.append("## 10. Trade Flow\n")
    sections.append("```")
    sections.append("Player A: trade @PlayerB  → trade_request to B, trade_result(request_sent) to A")
    sections.append("Player B: trade accept    → trade_update to both (negotiating)")
    sections.append("Either:   trade offer X N → trade_update to both")
    sections.append("Either:   trade ready     → trade_update to both")
    sections.append("Both ready:               → trade_result(success) + inventory to both")
    sections.append("Either:   trade cancel    → trade_result(cancelled) to both")
    sections.append("Player B: trade reject    → trade_result(rejected) to both")
    sections.append("Timeout:                  → trade_result(timeout) to both")
    sections.append("```\n")

    # --- Party Flow ---
    sections.append("## 11. Party Flow\n")
    sections.append("```")
    sections.append("Player A: party invite B  → party_invite to B, party_invite_response(sent) to A")
    sections.append("Player B: party accept    → party_update(member_joined) to all members")
    sections.append("Player B: party reject    → party_invite_response(rejected) to A")
    sections.append("Member:   party leave     → party_update(member_left) to remaining")
    sections.append("Leader:   party kick X    → party_update(member_kicked) to all")
    sections.append("Leader:   party disband   → party_update(disbanded) to all")
    sections.append("Any:      party           → party_status (current state)")
    sections.append("```\n")

    return "\n".join(sections)


if __name__ == "__main__":
    print(generate())
