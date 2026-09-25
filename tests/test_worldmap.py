from nta_agent.execution.worldmap import WorldMap

LAND = [{"id": 0, "type": 3, "lv": 1, "occupy": 1}, {"id": 1, "type": 4, "lv": 3, "occupy": 1},
        {"id": 7, "type": 7, "lv": 0, "occupy": 0}]


def test_detect_picks_the_map_where_owned_cells_are_occupiable():
    maps = {"maps_13": [7, 7, 7, 0], "maps_15": [0, 1, 1, 7]}
    wm = WorldMap(maps, LAND)
    assert wm.detect(owned=[0, 1, 2]) == "maps_15"
    assert wm.passable(1) and not wm.passable(3)
    assert wm.lv(0) == 1 and wm.lv(1) == 3 and wm.land_id(3) == 7


def test_unknown_index_or_no_map_is_not_passable():
    wm = WorldMap({}, LAND)
    assert wm.detect(owned=[1]) is None and not wm.passable(5) and wm.lv(5) == 0


def test_load_from_config_dir(tmp_path):
    import json
    (tmp_path / "land.json").write_text(json.dumps(LAND), encoding="utf-8")
    (tmp_path / "maps_15.json").write_text(json.dumps([0, 1]), encoding="utf-8")
    wm = WorldMap.load(tmp_path)
    assert wm.detect(owned=[0]) == "maps_15" and wm.passable(0)
