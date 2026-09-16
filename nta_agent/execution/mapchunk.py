"""Decode packed map-chunk cell data (Tier B territory).

`game/HD_GetMapChunk{chunkId}` returns `cells: map<playerUid, PlayerCellBytesInfo>`
where each `PlayerCellBytesInfo{indexs1, indexs2, cities}` holds a player's cells in
that chunk as packed bitstreams. This module reimplements the engine's decoders
(MSB-first bit reader) and maps decoded (x, y) back to global cell indices.

Map is ``map_width`` (default 600) square; chunks are ``CHUNK`` (100) square, so
there are ``ceil(map_width / CHUNK)`` chunks per row. ``chunk_id = cy*per_row + cx``
and a chunk's origin is ``(cx*CHUNK, cy*CHUNK)``. A cell index is ``y*map_width + x``.

Pure: no I/O. Robust to short/empty byte fields (returns empty results).
"""
from __future__ import annotations

CHUNK = 100


def _per_row(map_width: int, chunk: int = CHUNK) -> int:
    return -(-map_width // chunk)  # ceil


def chunk_id(index: int, map_width: int = 600, chunk: int = CHUNK) -> int:
    """Chunk id containing a global cell index."""
    x, y = index % map_width, index // map_width
    return (y // chunk) * _per_row(map_width, chunk) + (x // chunk)


def chunk_origin(cid: int, map_width: int = 600, chunk: int = CHUNK) -> tuple[int, int]:
    """Top-left (x, y) origin of a chunk id."""
    per = _per_row(map_width, chunk)
    cx, cy = cid % per, cid // per
    return cx * chunk, cy * chunk


class _BitReader:
    """MSB-first bit reader over a bytes buffer."""

    def __init__(self, data: bytes):
        self._d = data or b""
        self._byte = 0
        self._off = 0
        self._total = 8 * len(self._d)

    def read(self, n: int) -> int:
        val = 0
        while n > 0:
            if self._byte >= len(self._d):
                return val << n  # ran out; pad low bits with zero
            avail = 8 - self._off
            take = min(avail, n)
            shift = 8 - self._off - take
            bits = (self._d[self._byte] >> shift) & ((1 << take) - 1)
            val = (val << take) | bits
            self._off += take
            n -= take
            if self._off >= 8:
                self._off = 0
                self._byte += 1
        return val

    def has(self, n: int) -> bool:
        return 8 * self._byte + self._off + n <= self._total


def _pt2idx(x: int, y: int, map_width: int) -> int:
    if x < 0 or x >= map_width or y < 0 or y >= map_width:
        return -1
    return y * map_width + x


def _dec_indexs1(data: bytes, ox: int, oy: int, map_width: int) -> list[int]:
    """Run-length rectangles, delta-coded relative to chunk origin."""
    br = _BitReader(data)
    out: list[int] = []

    def span() -> int:
        if br.read(1) == 0:
            return br.read(3)
        if br.read(1) == 0:
            return 8 + br.read(5)
        return 32 + br.read(7)

    while br.has(18):
        x0 = ox + br.read(7)
        y0 = oy + br.read(7)
        x1 = x0 + span()
        y1 = y0 + span()
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                idx = _pt2idx(x, y, map_width)
                if idx >= 0:
                    out.append(idx)
    return out


def _dec_indexs2(data: bytes, ox: int, oy: int, map_width: int) -> list[int]:
    """Zig-zag delta-coded point list."""
    br = _BitReader(data)
    out: list[int] = []

    def delta() -> int:
        if br.read(1) == 0:
            e = br.read(4)
        elif br.read(1) == 0:
            e = 16 + br.read(6)
        else:
            e = 64 + br.read(8)
        val = e >> 1
        return -val - 1 if (e & 1) else val

    if not br.has(14):
        return out
    x = br.read(7)
    y = br.read(7)
    idx = _pt2idx(ox + x, oy + y, map_width)
    if idx >= 0:
        out.append(idx)
    while br.has(10):
        x += delta()
        y += delta()
        idx = _pt2idx(ox + x, oy + y, map_width)
        if idx >= 0:
            out.append(idx)
    return out


def _dec_cities(data: bytes, ox: int, oy: int, map_width: int) -> dict[int, int]:
    """Repeated (dx:7, dy:7, cityType:8) -> {index: cityType}."""
    br = _BitReader(data)
    out: dict[int, int] = {}
    while br.has(22):
        dx = br.read(7)
        dy = br.read(7)
        ctype = br.read(8)
        idx = _pt2idx(ox + dx, oy + dy, map_width)
        if idx >= 0:
            out[idx] = ctype
    return out


def decode_player_cells(
    info: dict, origin_x: int, origin_y: int, map_width: int = 600
) -> tuple[list[int], dict[int, int]]:
    """Decode one player's PlayerCellBytesInfo into (owned indices, cities map).

    ``info`` is ``{indexs1, indexs2, cities}`` with bytes values (any missing/empty
    field is treated as no data). Returns deduplicated owned cell indices and the
    cities map ``{index: cityType}`` (cityType 1 = main city).
    """
    i1 = info.get("indexs1") or b""
    i2 = info.get("indexs2") or b""
    ci = info.get("cities") or b""
    owned = _dec_indexs1(i1, origin_x, origin_y, map_width) + _dec_indexs2(
        i2, origin_x, origin_y, map_width
    )
    cities = _dec_cities(ci, origin_x, origin_y, map_width)
    return sorted(set(owned)), cities
