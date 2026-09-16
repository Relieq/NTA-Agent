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
    main = 100 * W + 100
    t = Territory(main_city=main, forts=[], garrisons=[], map_width=W)
    assert t.pos(main) == (100, 100)
    other = (103) * W + 105  # +5 x, +3 y -> Chebyshev 5
    assert t.dist(main, other) == 5
    assert t.near_main(other, radius=6) is True
    far = (110) * W + 100  # +10 y -> dist 10
    assert t.near_main(far, radius=6) is False


def test_empty_player_builds_empty_territory():
    t = build_territory(_state({}), map_width=600)
    assert t.forts == [] and t.garrisons == [] and t.main_city == 0
