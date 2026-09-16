"""Game config tables (buildings, pawns, ...) extracted from the client.

The client's static data lives in ``common/json/*`` tables; ``tools/re/extract_config.py``
dumps them to ``nta_agent/data/config/<name>.json`` (a list of rows). This loader
indexes them by id and parses the game's terse encodings so predictors and rules
can reason about costs, build times, and pawn stats without re-parsing strings.

Cost/effect encoding: ``"type,x,amount|type,x,amount"`` where type is a resource
(1=cereal, 2=timber, 3=stone) and amount is the quantity; effects use ``"key,val|..."``.
IDs are ``base*1000 + level`` for the per-level attribute tables.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

_CONFIG_DIR = Path(__file__).with_name("config")

# Resource type codes used across cost strings.
RESOURCE_BY_TYPE = {1: "cereal", 2: "timber", 3: "stone"}


def parse_cost(s: str) -> dict[str, int]:
    """"2,0,178|3,0,178" -> {'timber': 178, 'stone': 178}."""
    out: dict[str, int] = {}
    for part in (s or "").split("|"):
        part = part.strip()
        if not part:
            continue
        fields = part.split(",")
        if len(fields) >= 3:
            rtype, amount = int(fields[0]), int(fields[-1])
            name = RESOURCE_BY_TYPE.get(rtype, f"res{rtype}")
            out[name] = out.get(name, 0) + amount
    return out


def parse_effects(s: str) -> list[tuple[int, int]]:
    """"11,2|63,3" -> [(11, 2), (63, 3)]."""
    out: list[tuple[int, int]] = []
    for part in (s or "").split("|"):
        part = part.strip()
        if not part:
            continue
        f = part.split(",")
        if len(f) >= 2:
            out.append((int(f[0]), int(f[1])))
    return out


@dataclass
class BuildUpgrade:
    build_id: int
    level: int
    cost: dict[str, int]
    time: int              # seconds
    effects: list[tuple[int, int]]
    prep_cond: str


@dataclass
class GameConfig:
    config_dir: Path = _CONFIG_DIR
    _tables: dict[str, dict[int, dict]] = field(default_factory=dict)

    @classmethod
    def load(cls, config_dir: Path | str | None = None) -> GameConfig:
        gc = cls(config_dir=Path(config_dir) if config_dir else _CONFIG_DIR)
        if not gc.config_dir.exists():
            raise FileNotFoundError(
                "config tables not found at %s — run tools/re/extract_config.py" % gc.config_dir
            )
        return gc

    @staticmethod
    def _key(raw):
        # Numeric tables key by int id; text tables (e.g. "name_3101") keep the str.
        try:
            return int(raw)
        except (ValueError, TypeError):
            return raw

    def table(self, name: str) -> dict:
        """Return {id: row} for a config table, loaded and cached on first use.

        Ids are int for numeric tables and left as-is for text tables whose id is
        a string key like ``"name_3101"``.
        """
        if name not in self._tables:
            rows = json.loads((self.config_dir / f"{name}.json").read_text(encoding="utf-8"))
            self._tables[name] = {self._key(r["id"]): r for r in rows if "id" in r}
        return self._tables[name]

    # ---- buildings ------------------------------------------------------- #
    def build_upgrade(self, build_id: int, level: int) -> BuildUpgrade | None:
        """Cost/time/effects to reach ``level`` for a building (buildAttr row)."""
        row = self.table("buildAttr").get(build_id * 1000 + level)
        if not row:
            return None
        return BuildUpgrade(
            build_id=build_id,
            level=level,
            cost=parse_cost(row.get("up_cost", "")),
            time=int(row.get("bt_time", 0) or 0),
            effects=parse_effects(row.get("effects", "")),
            prep_cond=str(row.get("prep_cond", "")),
        )

    def build_base(self, build_id: int) -> dict | None:
        """A buildBase row (id, type, bt_count, prep_cond, ui, size…)."""
        return self.table("buildBase").get(build_id)

    def max_count(self, build_id: int) -> int:
        """Max instances allowed of a building (abs(bt_count); 0/unknown → 1)."""
        row = self.build_base(build_id)
        n = abs(int(row.get("bt_count", 0))) if row else 0
        return n or 1

    @staticmethod
    def _build_in_mode(row: dict, room_type: int | None) -> bool:
        """A building's ``server`` field gates it by room type: "" = all modes,
        else a comma list of room types (e.g. 0 = free, "1,2" = newbie+ranked)."""
        if room_type is None:
            return True
        sv = row.get("server", "")
        if sv == "" or sv is None:
            return True
        modes = {int(x) for x in str(sv).split(",") if str(x).strip() != ""}
        return int(room_type) in modes

    def in_city_build_ids(self, room_type: int | None = None) -> list[int]:
        """In-city building ids (buildBase type == 1), sorted; filtered to the
        given room type when provided (mode-gated buildings via ``server``)."""
        return sorted(bid for bid, r in self.table("buildBase").items()
                      if r.get("type") == 1 and self._build_in_mode(r, room_type))

    # ---- pawns ----------------------------------------------------------- #
    def pawn_base(self, pawn_id: int) -> dict | None:
        return self.table("pawnBase").get(pawn_id)

    def pawn_recruit_cost(self, pawn_id: int) -> dict[str, int]:
        base = self.pawn_base(pawn_id) or {}
        return parse_cost(base.get("drill_cost", ""))
