"""Economy predictor tests (live-data driven, no static config)."""

from nta_agent.execution.predictors.economy import EconomyPredictor
from nta_agent.state.schema import GameState


def _state(cereal, timber, stone, gc, wc, prod):
    st = GameState(source="api")
    st.resources.cereal, st.resources.timber, st.resources.stone = cereal, timber, stone
    st.granary_cap, st.warehouse_cap = gc, wc
    st.production = prod
    return st


def test_forecast_fraction_and_hours_to_cap():
    st = _state(500, 900, 0, gc=1000, wc=1000, prod={"cereal": 100, "timber": 50, "stone": 0})
    eco = EconomyPredictor(st)
    f = {x.name: x for x in eco.forecasts()}
    assert f["cereal"].fraction == 0.5
    assert f["cereal"].hours_to_cap == 5.0        # (1000-500)/100
    assert f["timber"].hours_to_cap == 2.0        # (1000-900)/50
    assert f["stone"].hours_to_cap == float("inf")  # no production


def test_should_collect_gate():
    near = _state(900, 0, 0, gc=1000, wc=1000, prod={})
    assert EconomyPredictor(near).should_collect(0.85) is True
    low = _state(100, 100, 100, gc=1000, wc=1000, prod={})
    assert EconomyPredictor(low).should_collect(0.85) is False


def test_wasting_lists_capped_producers():
    st = _state(1000, 100, 1000, gc=1000, wc=1000, prod={"cereal": 100, "stone": 0})
    # cereal at cap and producing -> wasting; stone at cap but no production -> not
    assert EconomyPredictor(st).wasting() == ["cereal"]


def test_soonest_to_cap_picks_min():
    st = _state(500, 990, 0, gc=1000, wc=1000, prod={"cereal": 100, "timber": 50})
    assert EconomyPredictor(st).soonest_to_cap().name == "timber"  # 0.2h vs 5h
