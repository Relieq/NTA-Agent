"""territory.scan_owned: fetch chunk(s) via actions, decode owned cells."""
import base64
import json
from pathlib import Path

from nta_agent.execution.territory import scan_owned

FX = json.loads(Path("tests/fixtures/mapchunk_real.json").read_text(encoding="utf-8"))


class FakeActions:
    def __init__(self, chunks):
        self.chunks = chunks  # {chunk_id: {"cells": {uid: info}}}
        self.requested = []

    def get_map_chunk(self, chunk_id):
        self.requested.append(chunk_id)
        return self.chunks.get(chunk_id, {"cells": {}})


def _real_cells():
    return {k: base64.b64decode(FX[k]) for k in ("indexs1", "indexs2", "cities")}


def test_scan_owned_decodes_main_chunk():
    uid = FX["uid"]
    acts = FakeActions({FX["chunk_id"]: {"cells": {uid: _real_cells()}}})
    owned, cities = scan_owned(acts, FX["main_city"], uid)
    assert len(owned) == FX["land_count"] == 23
    assert FX["main_city"] in owned
    assert cities.get(FX["main_city"]) == 1
    assert acts.requested == [FX["chunk_id"]]  # no border fetch (cells interior here)


def test_scan_owned_fetches_border_adjacent_when_cells_touch_edge():
    uid = "u1"
    # a cell on the right edge of chunk 0 (x=99) -> should fetch chunk 1 too
    import nta_agent.execution.mapchunk as mc

    def cell_at(x, y):
        # build a 1x1 rect via indexs1: x0(7) y0(7) span0(=0) span0(=0)
        # span encoding: read(1)==0 then read(3)==0  -> value 0 (single cell)
        bits = []

        def put(v, n):
            for i in range(n - 1, -1, -1):
                bits.append((v >> i) & 1)

        put(x, 7)
        put(y, 7)
        put(0, 1)
        put(0, 3)  # span x = 0
        put(0, 1)
        put(0, 3)  # span y = 0
        while len(bits) % 8:
            bits.append(0)
        out = bytearray()
        for i in range(0, len(bits), 8):
            b = 0
            for j in range(8):
                b = (b << 1) | bits[i + j]
            out.append(b)
        return bytes(out)

    # cell at global (99, 5) is in chunk 0, on its right edge
    info0 = {"indexs1": cell_at(99, 5), "indexs2": b"", "cities": b""}
    acts = FakeActions({0: {"cells": {uid: info0}}, 1: {"cells": {}}})
    owned, _ = scan_owned(acts, mc._pt2idx(50, 5, 600), uid)
    assert mc._pt2idx(99, 5, 600) in owned
    assert 1 in acts.requested  # border-adjacent chunk fetched
