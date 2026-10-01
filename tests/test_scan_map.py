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


def test_allied_cells_are_not_enemies_nor_frontier():
    mine = {"indexs1": _rect_bytes(10, 10, 11, 11), "indexs2": b"", "cities": b""}
    ally = {"indexs1": _rect_bytes(12, 10, 12, 10), "indexs2": b"", "cities": b""}  # next to me
    enemy = {"indexs1": _rect_bytes(20, 20, 20, 20), "indexs2": b"", "cities": b""}
    acts = FakeActions({"57696053": mine, "777": ally, "999": enemy})
    m = scan_map(acts, main=_idx(10, 10), uid="57696053", map_width=600, allies={"777"})
    assert _idx(12, 10) in m["ally_cells"] and _idx(12, 10) not in m["enemy_cells"]
    assert _idx(20, 20) in m["enemy_cells"]
    assert _idx(12, 10) not in m["frontier"]          # can't occupy an ally's cell either


# ---- surrounded by allies: cells touching an ally's land are attackable too ---------------
def test_frontier_goes_through_allied_land_that_touches_ours():
    # the engine's checkCanOccupyCell: a cell is occupiable if ANY neighbour is ours or an ally's
    mine = {"indexs1": _rect_bytes(10, 10, 11, 11), "indexs2": b"", "cities": b""}
    ring = {"indexs1": _rect_bytes(12, 10, 12, 11), "indexs2": b"", "cities": b""}   # touches me
    far = {"indexs1": _rect_bytes(60, 60, 60, 60), "indexs2": b"", "cities": b""}    # does not
    m = scan_map(FakeActions({"57696053": mine, "777": ring, "888": far}), main=_idx(10, 10),
                 uid="57696053", map_width=600, allies={"777", "888"})
    fa = m["frontier_ally"]
    assert _idx(13, 10) in fa and _idx(13, 11) in fa                         # beyond the ally
    assert _idx(12, 9) in fa and _idx(12, 12) in fa                          # above/below it
    assert _idx(10, 9) in m["frontier"]                                      # next to us: as before
    assert _idx(12, 10) not in m["frontier"] | fa                            # the ally's own cell
    assert _idx(61, 60) not in fa and _idx(60, 61) not in fa                 # far ally land
    assert not (fa & m["frontier"])                                          # kept apart


def test_a_ring_of_allies_does_not_empty_the_frontier():
    # all four sides of our 2x2 block belong to allies: before, the frontier was EMPTY
    mine = {"indexs1": _rect_bytes(10, 10, 11, 11), "indexs2": b"", "cities": b""}
    rects = {"771": (9, 9, 12, 9), "772": (9, 12, 12, 12), "773": (9, 10, 9, 11),
             "774": (12, 10, 12, 11)}
    cells = {"57696053": mine}
    for u, r in rects.items():
        cells[u] = {"indexs1": _rect_bytes(*r), "indexs2": b"", "cities": b""}
    m = scan_map(FakeActions(cells), main=_idx(10, 10), uid="57696053", map_width=600,
                 allies=set(rects))
    assert m["frontier"] == set()                            # nothing touches us any more ...
    assert m["frontier_ally"], "surrounded by allies must not mean nothing to attack"
    for c in ((13, 10), (8, 10), (10, 13), (10, 8)):       # ... but the cells beyond the ring are
        assert _idx(*c) in m["frontier_ally"]
    assert not (m["frontier_ally"] & m["ally_cells"]) and not (m["frontier_ally"] & m["owned"])


def test_ally_reach_is_limited_to_a_few_layers_and_to_land_touching_us():
    from nta_agent.execution.territory import ALLY_DEPTH, ally_reach
    owned = {_idx(10, 10)}
    chain = {_idx(11 + k, 10) for k in range(ALLY_DEPTH + 5)}      # ally land running away from us
    got = ally_reach(owned, chain)
    assert _idx(11, 10) in got and _idx(10 + ALLY_DEPTH, 10) in got
    assert _idx(11 + ALLY_DEPTH, 10) not in got                    # deeper than the limit
    assert ally_reach(owned, {_idx(50, 50)}) == set() and ally_reach(owned, set()) == set()
