"""capped_storage_upgrade: raise the store cap when it can't hold a needed cost."""
from dataclasses import dataclass

from nta_agent.data.config import BuildUpgrade
from nta_agent.execution.build_planner import capped_storage_upgrade
from nta_agent.state.schema import Building, GameState


@dataclass
class FakeConfig:
    table: dict

    def build_upgrade(self, build_id, level):
        return self.table.get((build_id, level))


def _bu(bid, lv, cost):
    return BuildUpgrade(build_id=bid, level=lv, cost=cost, time=60, effects=[], prep_cond="")


def _state(builds, caps, cereal=9999, timber=9999, stone=9999):
    st = GameState(source="api")
    st.builds = [Building(index=i, id=bid, lv=lv, uid=f"u{bid}") for i, (bid, lv) in enumerate(builds)]
    st.granary_cap, st.warehouse_cap = caps
    st.resources.cereal, st.resources.timber, st.resources.stone = cereal, timber, stone
    return st


def test_upgrades_granary_when_cap_below_needed_cereal():
    # main hall lv5 -> lv6 needs 2000 cereal, but granary holds only 1000 -> upgrade Kho Lương.
    st = _state([(2001, 5), (2002, 1)], caps=(1000, 1000))
    cfg = FakeConfig({(2001, 6): _bu(2001, 6, {"cereal": 2000}),
                      (2002, 2): _bu(2002, 2, {"timber": 100})})
    act = capped_storage_upgrade(st, cfg)
    assert act is not None and act.build_id == 2002 and act.up.level == 2


def test_no_upgrade_when_cap_sufficient():
    st = _state([(2001, 5), (2002, 1)], caps=(5000, 5000))
    cfg = FakeConfig({(2001, 6): _bu(2001, 6, {"cereal": 2000}),
                      (2002, 2): _bu(2002, 2, {"timber": 100})})
    assert capped_storage_upgrade(st, cfg) is None


def test_warehouse_for_timber_stone_iron():
    st = _state([(2001, 5), (2003, 1)], caps=(9999, 500))
    cfg = FakeConfig({(2001, 6): _bu(2001, 6, {"stone": 1200}),
                      (2003, 2): _bu(2003, 2, {"cereal": 50})})
    act = capped_storage_upgrade(st, cfg)
    assert act is not None and act.build_id == 2003


def test_inert_when_no_cap_set():
    st = _state([(2001, 5), (2002, 1)], caps=(0, 0))
    cfg = FakeConfig({(2001, 6): _bu(2001, 6, {"cereal": 2000}), (2002, 2): _bu(2002, 2, {})})
    assert capped_storage_upgrade(st, cfg) is None


def test_no_upgrade_when_store_cannot_afford():
    st = _state([(2001, 5), (2002, 1)], caps=(1000, 1000), cereal=0, timber=0, stone=0)
    cfg = FakeConfig({(2001, 6): _bu(2001, 6, {"cereal": 2000}),
                      (2002, 2): _bu(2002, 2, {"timber": 100})})  # timber=0 -> can't afford
    assert capped_storage_upgrade(st, cfg) is None
