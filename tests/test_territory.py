from nta_agent.execution.territory import Fort, Territory, build_territory
from nta_agent.state.schema import GameState


def _state(player):
    st = GameState(source="api")
    st.raw = {"player": player}
    st.main_city_index = player.get("mainCityIndex", 0)
    return st


def test_build_territory_from_player_fields():
    W = 600
    main = 100 * W + 100
    st = _state({
        "mainCityIndex": main,
        "fortAutoSupports": [{"index": main + 10, "val": True},
                             {"index": main + 20, "val": False}],
        "armyDists": [{"index": main, "armys": []},
                      {"index": main + 10, "armys": [{"uid": "a"}]}],
        "buildCitys": {str(main): {}},
    })
    t = build_territory(st, map_width=W)
    assert t.main_city == main and t.map_width == W
    assert Fort(index=main + 10, auto_support=True) in t.forts
    assert Fort(index=main + 20, auto_support=False) in t.forts
    assert main in t.garrisons and (main + 10) in t.garrisons
    assert set(t.nodes()) == {main, main + 10, main + 20}


def test_geometry_pos_dist_near_main():
    W = 600
    main = 100 * W + 100  # 2x2 block corner (100,100)..(101,101)
    t = Territory(main_city=main, forts=[], garrisons=[], map_width=W)
    assert t.pos(main) == (100, 100)
    other = (103) * W + 105  # (x=105, y=103)
    assert t.dist(main, other) == 8          # Manhattan cell-to-cell |5|+|3|
    assert t.dist_to_main(other) == 6        # Manhattan to the 2x2 block (4+2)
    assert t.near_main(other, radius=6) is True
    far = (110) * W + 100  # (x=100, y=110) -> 9 below the block
    assert t.dist_to_main(far) == 9
    assert t.near_main(far, radius=6) is False
    # diagonal cell: Chebyshev would be 5 (inside), Manhattan-to-block is 8 (outside)
    diag = (105) * W + 105  # (x=105, y=105)
    assert t.dist_to_main(diag) == 8
    assert t.near_main(diag, radius=6) is False


def test_empty_player_builds_empty_territory():
    t = build_territory(_state({}), map_width=600)
    assert t.forts == [] and t.garrisons == [] and t.main_city == 0
