from nta_agent import paths


def test_runtime_config_defaults_follow_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("NTA_DATA_DIR", str(tmp_path))
    from nta_agent.runtime.config import RuntimeConfig
    cfg = RuntimeConfig.from_env({"NTA_DISTINCT_ID": "x"})
    assert cfg.log_dir == tmp_path / "run"
    assert cfg.token_path == tmp_path / "nta_token.txt"


def test_game_config_dir_follows_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "config_dir", lambda: tmp_path)
    from nta_agent.data.config import GameConfig
    assert GameConfig().config_dir == tmp_path


def test_bridge_env_points_sidecar_at_paths(monkeypatch, tmp_path):
    from nta_agent.execution.predictors import sim_bridge
    monkeypatch.setattr(sim_bridge, "_bridge", None)
    monkeypatch.setattr(paths, "engine_js", lambda: tmp_path / "e.js")
    monkeypatch.setattr(paths, "config_dir", lambda: tmp_path / "cfg")
    b = sim_bridge.get_bridge()
    assert b.env["NTA_ENGINE_JS"] == str(tmp_path / "e.js")
    assert b.env["NTA_CONFIG_DIR"] == str(tmp_path / "cfg")
    assert b.node == paths.node_exe()
    monkeypatch.setattr(sim_bridge, "_bridge", None)
