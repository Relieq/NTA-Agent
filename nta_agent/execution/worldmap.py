"""The world map's static land layout: per-cell landId -> land row (type, lv, occupy).

The APK ships a few world maps (``tmp/json/maps/maps_<n>``, 360 000 landIds, index =
y*600+x); which one a server uses isn't sent to us, so :meth:`WorldMap.detect` picks the
map on which every owned cell is occupiable land (live 2026-09-25: maps_15 matched
152/152 owned + 865/865 enemy cells, the others didn't). Land ``type`` 3/4/5 is
resource land with ``lv`` 1..5 (``occupy == 1``); anything else is an obstacle.
"""
from __future__ import annotations

import json
from pathlib import Path


class WorldMap:
    def __init__(self, maps: dict[str, list[int]], land_rows: list[dict]):
        self.maps = maps
        self.land_by_id = {int(r["id"]): r for r in land_rows if isinstance(r, dict) and "id" in r}
        self.name: str | None = None
        self.cells: list[int] = []

    @classmethod
    def load(cls, config_dir) -> WorldMap:
        d = Path(config_dir)
        maps = {}
        for p in sorted(d.glob("maps_*.json")):
            try:
                arr = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(arr, list) and arr:
                maps[p.stem] = arr
        try:
            land = json.loads((d / "land.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            land = []
        return cls(maps, land)

    def detect(self, owned) -> str | None:
        """Select (and return) the map where the most owned cells are occupiable land."""
        owned = [int(i) for i in owned or ()]
        best, best_score = None, -1
        for name, cells in self.maps.items():
            score = sum(1 for i in owned
                        if 0 <= i < len(cells)
                        and self.land_by_id.get(int(cells[i]), {}).get("occupy") == 1)
            if score > best_score:
                best, best_score = name, score
        if best is not None and best_score > 0:
            self.name, self.cells = best, self.maps[best]
            return best
        return None

    def land_id(self, idx: int) -> int:
        return int(self.cells[idx]) if 0 <= idx < len(self.cells) else -1

    def land(self, idx: int) -> dict:
        return self.land_by_id.get(self.land_id(idx), {})

    def passable(self, idx: int) -> bool:
        """Occupiable land (resource cells); mountains, water, decor are obstacles."""
        return self.land(idx).get("occupy") == 1

    def lv(self, idx: int) -> int:
        return int(self.land(idx).get("lv", 0) or 0)
