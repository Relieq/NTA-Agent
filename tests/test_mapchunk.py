import base64
import json
from pathlib import Path

from nta_agent.execution.mapchunk import chunk_id, chunk_origin, decode_player_cells

FX = json.loads(Path("tests/fixtures/mapchunk_real.json").read_text(encoding="utf-8"))


def test_chunk_id_and_origin_for_main_city():
    assert chunk_id(109726) == FX["chunk_id"] == 11
    assert chunk_origin(11) == tuple(FX["origin"]) == (500, 100)


def test_decode_real_chunk_matches_land_count():
    info = {k: base64.b64decode(FX[k]) for k in ("indexs1", "indexs2", "cities")}
    ox, oy = FX["origin"]
    owned, cities = decode_player_cells(info, ox, oy)
    assert len(owned) == FX["land_count"] == 23
    assert FX["main_city"] in owned
    assert cities.get(FX["main_city"]) == 1
