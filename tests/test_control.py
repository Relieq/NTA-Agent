from nta_agent.runtime.config import RuntimeConfig
from nta_agent.runtime.control import read_mode, reset, write_control


def test_read_mode_missing_is_run(tmp_path):
    assert read_mode(tmp_path / "nope.json") == "run"


def test_write_and_read_pause_stop(tmp_path):
    p = tmp_path / "control.json"
    write_control(p, paused=True)
    assert read_mode(p) == "pause"
    write_control(p, stop=True)        # merge: stop wins over pause
    assert read_mode(p) == "stop"


def test_write_control_merges(tmp_path):
    p = tmp_path / "control.json"
    write_control(p, paused=True)
    write_control(p, stop=False)       # leaves paused untouched
    assert read_mode(p) == "pause"


def test_reset_clears_both(tmp_path):
    p = tmp_path / "control.json"
    write_control(p, paused=True, stop=True)
    reset(p)
    assert read_mode(p) == "run"


def test_corrupt_file_is_run(tmp_path):
    p = tmp_path / "control.json"
    p.write_text("{bad", encoding="utf-8")
    assert read_mode(p) == "run"


def test_config_paths():
    cfg = RuntimeConfig(distinct_id="x")
    assert cfg.control_path.name == "control.json"
    assert cfg.agent_pid_path.name == "agent.pid"
