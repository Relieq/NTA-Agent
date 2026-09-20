from nta_agent.state.schema import GameState
from nta_agent.state.store import accrue_output, apply_update_output


def _state(stone=0, cereal=0, timber=0, cap=7400):
    st = GameState(source="api")
    st.resources.stone = stone; st.resources.cereal = cereal; st.resources.timber = timber
    st.production = {"cereal": 360, "timber": 360, "stone": 720}  # per hour
    st.granary_cap = cap; st.warehouse_cap = cap
    return st


def test_accrue_grows_stock_by_production():
    st = _state(stone=0, cereal=100)
    accrue_output(st, now=1000.0)          # first call sets the base, no growth
    accrue_output(st, now=1000.0 + 3600)   # +1 hour
    assert st.resources.stone == 720       # 0 + 720/hr * 1h
    assert st.resources.cereal == 460      # 100 + 360


def test_accrue_caps_at_storage():
    st = _state(stone=7300, cap=7400)
    accrue_output(st, now=0.0)
    accrue_output(st, now=3600.0)          # would add 720 -> capped at 7400
    assert st.resources.stone == 7400


def test_accrue_no_growth_without_elapsed_or_rate():
    st = _state(stone=50); st.production = {}
    accrue_output(st, now=0.0); accrue_output(st, now=3600.0)
    assert st.resources.stone == 50        # no opHour -> no growth


def test_push_resets_accrual_base_no_double_count():
    st = _state(stone=0)
    accrue_output(st, now=0.0)
    # a server push arrives at t=1800 with the authoritative value
    apply_update_output(st, {"stone": {"value": 5000, "opHour": 720}})
    # the push set _output_at to ~now; accruing at that same instant adds nothing
    accrue_output(st, now=st._output_at)
    assert st.resources.stone == 5000
