import json
from pathlib import Path

from nta_agent.dashboard.server import handle_profile_edit, read_profile_view
from nta_agent.runtime.config import RuntimeConfig


def _cfg(tmp_path):
    return RuntimeConfig(distinct_id="x", log_dir=tmp_path)


def test_read_profile_view_reports_build_and_names(tmp_path):
    cfg = _cfg(tmp_path)
    Path(cfg.profile_path).parent.mkdir(parents=True, exist_ok=True)
    Path(cfg.profile_path).write_text(json.dumps(
        {"build": {"order": [2016, 2006], "skip": [2000]}}), encoding="utf-8")
    view = read_profile_view(cfg)
    assert view["build"]["order"] == [2016, 2006]
    assert view["build"]["skip"] == [2000]
    # names map covers listed ids + offers the in-city catalogue for the editor
    assert view["names"]["2016"]  # Y Quán
    assert any(item["id"] == 2016 for item in view["catalogue"])


def test_handle_profile_edit_sets_build_order_directly(tmp_path):
    cfg = _cfg(tmp_path)
    Path(cfg.profile_path).parent.mkdir(parents=True, exist_ok=True)
    out = handle_profile_edit(cfg, {"build": {"order": [2016, 2006], "skip": [2000]}})
    assert out["ok"] is True
    assert out["applied"]["build"]["order"] == [2016, 2006]
    saved = json.loads(Path(cfg.profile_path).read_text(encoding="utf-8"))
    assert saved["build"]["order"] == [2016, 2006]
    cmds = Path(cfg.commands_path).read_text(encoding="utf-8").splitlines()
    assert any(json.loads(c)["action"] == "profile_edit" for c in cmds)


def test_handle_profile_edit_drops_invalid_ids(tmp_path):
    cfg = _cfg(tmp_path)
    Path(cfg.profile_path).parent.mkdir(parents=True, exist_ok=True)
    out = handle_profile_edit(cfg, {"build": {"order": [2016, 999999], "skip": []}})
    assert out["applied"]["build"]["order"] == [2016]  # unknown id dropped by guard


def test_profile_edit_sets_leveling(tmp_path):
    from nta_agent.dashboard.server import handle_profile_edit, read_profile_view
    from nta_agent.runtime.config import RuntimeConfig
    cfg = RuntimeConfig(distinct_id="x", log_dir=tmp_path)
    out = handle_profile_edit(cfg, {"leveling": {"enabled": True, "target_lv": 8,
                                                 "max_leveling": 2}})
    assert out["ok"] is True
    v = read_profile_view(cfg)
    assert v["leveling"] == {"enabled": True, "target_lv": 8, "max_leveling": 2}
