from nta_agent.execution.territory import scan_map


def _idx(x, y, mw=600): return y * mw + x


class FakeActions:
    """One chunk id 0 (origin 0,0) with my cells + an enemy's cells."""
    def __init__(self, cells): self._cells = cells; self.requested = []
    def get_map_chunk(self, cid):
        self.requested.append(cid)
        return {"cells": self._cells} if cid == 0 else {"cells": {}}


def _rect_bytes(x0, y0, x1, y1):
    # encode a run-length rect via indexs1 (same bit layout mapchunk decodes)
    bits = []
    def put(v, n):
        for i in range(n - 1, -1, -1): bits.append((v >> i) & 1)
    put(x0, 7); put(y0, 7)
    def span(d):  # d in 0..7 uses the 4-bit short form (flag 0 + 3 bits)
        put(0, 1); put(d, 3)
    span(x1 - x0); span(y1 - y0)
    while len(bits) % 8: bits.append(0)
    out = bytearray()
    for i in range(0, len(bits), 8):
        b = 0
        for j in range(8): b = (b << 1) | bits[i + j]
        out.append(b)
    return bytes(out)


def test_scan_map_splits_mine_and_enemy_and_frontier():
    mine = {"indexs1": _rect_bytes(10, 10, 11, 11), "indexs2": b"", "cities": b""}   # 2x2 at (10,10)
    enemy = {"indexs1": _rect_bytes(20, 20, 20, 20), "indexs2": b"", "cities": b""}  # 1 cell (20,20)
    acts = FakeActions({"57696053": mine, "999": enemy})
    m = scan_map(acts, main=_idx(10, 10), uid="57696053", map_width=600)
    assert _idx(10, 10) in m["owned"] and _idx(11, 11) in m["owned"]
    assert _idx(20, 20) in m["enemy_cells"] and _idx(20, 20) not in m["owned"]
    # frontier: unowned 4-neighbours of my 2x2 block, excluding owned + enemy
    assert _idx(9, 10) in m["frontier"] and _idx(12, 10) in m["frontier"]
    assert _idx(10, 10) not in m["frontier"]        # owned is not frontier
    assert _idx(20, 20) not in m["frontier"]         # enemy is not frontier
