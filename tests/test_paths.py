from pathlib import Path

from nta_agent import paths


def test_dev_mode_keeps_todays_locations(monkeypatch):
    monkeypatch.delenv("NTA_DATA_DIR", raising=False)
    monkeypatch.setattr(paths, "is_packaged", lambda root=None: False)
    app = paths.app_dir()
    assert (app / "nta_agent").is_dir()
    assert paths.run_dir() == app / "build" / "run"
    assert paths.token_path() == app / "build" / "nta_token.txt"
    assert paths.config_dir() == app / "nta_agent" / "data" / "config"
    assert paths.engine_js() == app / "tools" / "re" / "decrypted" / "index.js"
    assert paths.node_exe() == "node"
    assert paths.app_version() == "dev"


def test_packaged_mode_uses_localappdata(monkeypatch, tmp_path):
    monkeypatch.delenv("NTA_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(paths, "is_packaged", lambda root=None: True)
    d = tmp_path / "NTA-Agent"
    assert paths.data_dir() == d
    assert paths.run_dir() == d / "run"
    assert paths.token_path() == d / "token.txt"
    assert paths.config_dir() == d / "gamedata" / "config"
    assert paths.engine_js() == d / "gamedata" / "engine" / "index.js"
    assert paths.settings_path() == d / "settings.json"
    assert paths.node_exe().endswith(str(Path("runtime") / "node" / "node.exe"))


def test_env_override_and_detection(monkeypatch, tmp_path):
    monkeypatch.setenv("NTA_DATA_DIR", str(tmp_path / "x"))
    assert paths.data_dir() == tmp_path / "x"
    root = tmp_path / "pkg"
    (root / "runtime").mkdir(parents=True)
    (root / "VERSION").write_text("0.1.0", encoding="utf-8")
    assert paths.is_packaged(root) is True
    assert paths.is_packaged(tmp_path) is False
    assert paths.is_packaged() is False  # the repo itself is dev
