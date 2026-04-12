"""NPC entity and template loading."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from server.core.config import settings


@dataclass
class NpcEntity:
    """In-memory representation of an NPC on the tile grid."""

    id: str
    npc_key: str
    name: str
    x: int
    y: int
    behavior_type: str  # "hostile", "merchant", "quest_giver"
    stats: dict = field(default_factory=dict)
    loot_table: str = ""
    is_alive: bool = True
    in_combat: bool = False
    spawn_config: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize for room_state broadcast."""
        return {
            "id": self.id,
            "npc_key": self.npc_key,
            "name": self.name,
            "x": self.x,
            "y": self.y,
            "is_alive": self.is_alive,
        }


# ---------------------------------------------------------------------------
# Template loading
# ---------------------------------------------------------------------------

_NPC_TEMPLATES: dict[str, dict] = {}


def load_npc_templates(npcs_dir: Path) -> dict[str, dict]:
    """Load all NPC templates from JSON files in the given directory."""
    global _NPC_TEMPLATES
    if not npcs_dir.exists():
        return _NPC_TEMPLATES
    for json_file in sorted(npcs_dir.glob("*.json")):
        with open(json_file) as f:
            data = json.load(f)
        if isinstance(data, list):
            for tmpl in data:
                _NPC_TEMPLATES[tmpl["npc_key"]] = tmpl
        elif isinstance(data, dict) and "npc_key" in data:
            _NPC_TEMPLATES[data["npc_key"]] = data
    return _NPC_TEMPLATES


def get_npc_template(npc_key: str) -> dict | None:
    """Look up an NPC template by key."""
    return _NPC_TEMPLATES.get(npc_key)


def _derive_stats_from_hit_dice(tmpl: dict) -> dict:
    """Derive full stat block from hit_dice + hp_multiplier template fields.

    Falls back to legacy flat ``stats`` dict if ``hit_dice`` is absent.
    """
    hit_dice = tmpl.get("hit_dice")
    if hit_dice is None:
        # Legacy format — use flat stats dict
        return dict(tmpl.get("stats", {}))
    hp_multiplier = tmpl.get("hp_multiplier", settings.NPC_DEFAULT_HP_MULTIPLIER)
    max_hp = hit_dice * hp_multiplier
    return {
        "hp": max_hp,
        "max_hp": max_hp,
        "attack": hit_dice * settings.NPC_ATTACK_DICE_MULTIPLIER,
        "strength": hit_dice,
        "dexterity": hit_dice,
        "constitution": hit_dice,
        "intelligence": hit_dice,
        "wisdom": hit_dice,
        "charisma": hit_dice,
    }


def create_npc_from_template(npc_key: str, npc_id: str, x: int, y: int) -> NpcEntity | None:
    """Create an NpcEntity from a template."""
    tmpl = get_npc_template(npc_key)
    if tmpl is None:
        return None
    return NpcEntity(
        id=npc_id,
        npc_key=npc_key,
        name=tmpl.get("name", npc_key),
        x=x,
        y=y,
        behavior_type=tmpl.get("behavior_type", "hostile"),
        stats=_derive_stats_from_hit_dice(tmpl),
        loot_table=tmpl.get("loot_table", ""),
        spawn_config=dict(tmpl.get("spawn_config", {})),
    )
