from types import SimpleNamespace
from typing import ClassVar

from nta_agent.execution.caps import army_pawn_cap, next_cap_level
from nta_agent.state.schema import Building


class Cfg:
    ROWS: ClassVar[dict] = {2001001: {"effects": "11,2|63,3"}, 2001002: {"effects": "11,3|63,5"},
            2001004: {"effects": "11,4|63,5"}, 2001005: {"effects": "11,4|63,7"},
            2001006: {"effects": "11,5|63,9"}}

    def table(self, name):
        return self.ROWS if name == "buildAttr" else {}


def _st(lv):
    return SimpleNamespace(main_city_index=5, builds=[Building(index=5, id=2001, lv=lv, uid="m")])


def test_pawn_cap_follows_the_main_city_level():
    assert army_pawn_cap(_st(1), Cfg()) == 3
    assert army_pawn_cap(_st(4), Cfg()) == 5
    assert army_pawn_cap(_st(6), Cfg()) == 9
    assert army_pawn_cap(SimpleNamespace(main_city_index=5, builds=[]), Cfg()) == 9  # unknown
    assert next_cap_level(Cfg(), 4, 5) == (5, 7)


def test_real_config_matches_issue_83():
    import pytest
    try:
        from nta_agent.data.config import GameConfig
        cfg = GameConfig.load()
    except Exception:
        pytest.skip("no game config")
    assert [army_pawn_cap(_st(lv), cfg) for lv in (1, 2, 4, 5, 6)] == [3, 5, 5, 7, 9]
