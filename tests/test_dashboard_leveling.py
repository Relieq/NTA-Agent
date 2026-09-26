"""Buffer leveling on the dashboard: read proposal/phases, confirm."""
import json
from types import SimpleNamespace

from nta_agent.brain.digest import digest
from nta_agent.dashboard.server import confirm_leveling, read_leveling
from nta_agent.runtime import buffers
from nta_agent.runtime.config import RuntimeConfig


def _cfg(tmp_path):
    return RuntimeConfig(distinct_id="x", log_dir=tmp_path)


def test_read_leveling_defaults(tmp_path):
    v = read_leveling(_cfg(tmp_path))
    assert v["proposal"] is None and v["approved"] is False and v["buffers"] == {}
    assert v["groups"] == []


def test_read_and_confirm(tmp_path):
    cfg = _cfg(tmp_path)
    buffers.set_proposal(cfg.buffers_path, {"buffers": [{"name": "Nâng Cấp 1"}],
                                             "books_needed": 90, "books_have": 49})
    cfg.profile_path.write_text(json.dumps({"leveling": {"groups": [
        {"armies": ["A"], "mode": "buffer", "target_lv": 3}]}}), encoding="utf-8")
    v = read_leveling(cfg)
    assert v["proposal"]["books_needed"] == 90 and v["approved"] is False
    assert v["groups"] == [{"armies": ["A"], "mode": "buffer", "target_lv": 3}]
    r = confirm_leveling(cfg)
    assert r["ok"] is True and read_leveling(cfg)["approved"] is True


def test_confirm_needs_a_proposal(tmp_path):
    assert confirm_leveling(_cfg(tmp_path))["ok"] is False


def test_digest_carries_leveling_needs():
    st = SimpleNamespace(resources=SimpleNamespace(cereal=0, timber=0, stone=0, iron=0, gold=0,
                                                   stamina=0, exp_book=49, up_scroll=0, fixator=0),
                         main_city_index=0, raw={})
    prof = SimpleNamespace(army={"group": []}, occupy={}, logistics={}, notes=[],
                           leveling={"groups": []}, build={}, revive={}, forge={})
    dg = digest(st, prof, [], leveling={"proposal": {"books_needed": 90}, "approved": False})
    assert dg["leveling"]["proposal"]["books_needed"] == 90


def test_intel_carries_the_spare_armies_warning(tmp_path):
    from nta_agent.dashboard.server import read_intel
    cfg = _cfg(tmp_path)
    assert read_intel(cfg)["spares"] is None
    cfg.spare_advice_path.write_text(json.dumps({"status": "stuck", "armies": ["D6", "D7"],
                                                 "composition": {"3201@lv1": 18}}), encoding="utf-8")
    assert read_intel(cfg)["spares"]["status"] == "stuck"


def test_digest_carries_spares():
    st = SimpleNamespace(resources=SimpleNamespace(cereal=0, timber=0, stone=0, iron=0, gold=0,
                                                   stamina=0, exp_book=0, up_scroll=0, fixator=0),
                         main_city_index=0, raw={})
    prof = SimpleNamespace(army={"group": []}, occupy={}, logistics={}, notes=[],
                           leveling={"groups": []}, build={}, revive={}, forge={})
    dg = digest(st, prof, [], spares={"status": "stuck", "armies": ["D6"]})
    assert dg["spares"]["armies"] == ["D6"]
