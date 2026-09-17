"""Own-territory model (main city, forts, garrisons) + geometry — Tier A.

Built cheaply from player state fields (no packed-chunk decode). Foundation for
the fort-placement advisor (C2).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .mapchunk import CHUNK, chunk_id, chunk_origin, decode_player_cells


@dataclass(frozen=True)
class Fort:
    index: int
    auto_support: bool


@dataclass
class Territory:
    main_city: int
    forts: list = field(default_factory=list)
    garrisons: list = field(default_factory=list)
    owned_cells: set = field(default_factory=set)
    map_width: int = 600

    def pos(self, index: int) -> tuple[int, int]:
        return (index % self.map_width, index // self.map_width)

    def dist(self, a: int, b: int) -> int:
        # In-game movement is 4-directional: a diagonal step costs 2, so distance
        # is Manhattan (|dx|+|dy|), not Chebyshev.
        ax, ay = self.pos(a)
        bx, by = self.pos(b)
        return abs(ax - bx) + abs(ay - by)

    def dist_to_main(self, index: int) -> int:
        """Manhattan distance from a cell to the 2x2 main-city block.

        ``main_city`` is the block's corner (min x, min y); the block spans
        [mx, mx+1] x [my, my+1]. Cells orthogonally adjacent to it are distance 1.
        """
        mx, my = self.pos(self.main_city)
        x, y = self.pos(index)
        dx = max(mx - x, 0, x - (mx + 1))
        dy = max(my - y, 0, y - (my + 1))
        return dx + dy

    def near_main(self, index: int, radius: int = 6) -> bool:
        return self.dist_to_main(index) <= radius

    def nodes(self) -> list:
        return [self.main_city] + [f.index for f in self.forts]


def build_territory(state, map_width: int = 600) -> Territory:
    player = (getattr(state, "raw", None) or {}).get("player", {}) or {}
    main = int(player.get("mainCityIndex", 0) or 0)
    forts = [Fort(index=int(f.get("index", 0)), auto_support=bool(f.get("val")))
             for f in (player.get("fortAutoSupports") or []) if isinstance(f, dict)]
    garrisons = [int(d.get("index", 0)) for d in (player.get("armyDists") or [])
                 if isinstance(d, dict)]
    return Territory(main_city=main, forts=forts, garrisons=garrisons, map_width=map_width)


def _neighbor_chunks(owned: list[int], cid: int, map_width: int) -> set[int]:
    """Chunk ids adjacent to any owned cell that sits on this chunk's border."""
    ox, oy = chunk_origin(cid, map_width)
    per = -(-map_width // CHUNK)
    cols = per
    rows = -(-map_width // CHUNK)
    cx, cy = cid % per, cid // per
    out: set[int] = set()
    for idx in owned:
        x, y = idx % map_width, idx // map_width
        if x == ox and cx > 0:
            out.add(cid - 1)
        if x == ox + CHUNK - 1 and cx < cols - 1:
            out.add(cid + 1)
        if y == oy and cy > 0:
            out.add(cid - per)
        if y == oy + CHUNK - 1 and cy < rows - 1:
            out.add(cid + per)
    out.discard(cid)
    return out


def scan_owned(actions, main: int, uid, map_width: int = 600, focus=None):
    """Fetch the main-city chunk (+ border-adjacent + focus chunks) and decode.

    Returns ``(owned: set[int], cities: dict[int, int])`` unioned across the
    fetched chunks. ``uid`` selects this player's PlayerCellBytesInfo entry.
    """
    uid = str(uid)
    owned: set[int] = set()
    cities: dict[int, int] = {}
    seen: set[int] = set()

    def fetch(cid: int) -> list[int]:
        """Decode one chunk into the accumulators; return its owned cells."""
        if cid in seen:
            return []
        seen.add(cid)
        reply = actions.get_map_chunk(int(cid)) or {}
        info = (reply.get("cells") or {}).get(uid)
        if not info:
            return []
        ox, oy = chunk_origin(int(cid), map_width)
        cells, cmap = decode_player_cells(info, ox, oy, map_width)
        owned.update(cells)
        cities.update(cmap)
        return cells

    start = chunk_id(int(main), map_width)
    start_cells = fetch(start)
    for cid in _neighbor_chunks(start_cells, start, map_width):
        fetch(cid)
    for cid in (focus or []):
        fetch(int(cid))

    return owned, cities


def scan_map(actions, main: int, uid, map_width: int = 600, focus=None) -> dict:
    """Fetch the near chunks and decode EVERY player in them.

    Returns owned/cities (mine), enemy_cells/enemy_cities (all other players),
    and frontier (in-bounds 4-neighbours of my cells owned by nobody in view).
    Fetches the same chunks as ``scan_owned`` — no extra requests.
    """
    uid = str(uid)
    owned: set[int] = set()
    cities: dict[int, int] = {}
    enemy_cells: set[int] = set()
    enemy_cities: dict[int, int] = {}
    seen: set[int] = set()

    def fetch(cid: int) -> list[int]:
        if cid in seen:
            return []
        seen.add(cid)
        reply = actions.get_map_chunk(int(cid)) or {}
        cells_map = reply.get("cells") or {}
        ox, oy = chunk_origin(int(cid), map_width)
        mine_here: list[int] = []
        for u, info in cells_map.items():
            if not info:
                continue
            cells, cmap = decode_player_cells(info, ox, oy, map_width)
            if str(u) == uid:
                owned.update(cells)
                cities.update(cmap)
                mine_here = cells
            else:
                enemy_cells.update(cells)
                enemy_cities.update(cmap)
        return mine_here

    start = chunk_id(int(main), map_width)
    start_cells = fetch(start)
    for cid in _neighbor_chunks(start_cells, start, map_width):
        fetch(cid)
    for cid in (focus or []):
        fetch(int(cid))

    frontier: set[int] = set()
    for c in owned:
        x, y = c % map_width, c // map_width
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < map_width and 0 <= ny < map_width:
                n = ny * map_width + nx
                if n not in owned and n not in enemy_cells:
                    frontier.add(n)
    return {"owned": owned, "cities": cities, "enemy_cells": enemy_cells,
            "enemy_cities": enemy_cities, "frontier": frontier}
