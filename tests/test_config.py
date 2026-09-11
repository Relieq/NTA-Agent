"""Unit tests for config auto-detection (no device required)."""

from pathlib import Path

from nta_agent import config


def test_detect_adb_port_reads_status_port(tmp_path: Path):
    conf = tmp_path / "bluestacks.conf"
    conf.write_text(
        'bst.instance.Pie64.adb_port="5555"\n'
        'bst.instance.Pie64.status.adb_port="5565"\n',
        encoding="utf-8",
    )
    assert config._detect_adb_port(conf) == 5565


def test_detect_adb_port_falls_back_to_adb_port(tmp_path: Path):
    conf = tmp_path / "bluestacks.conf"
    conf.write_text('bst.instance.Nougat64.adb_port="5575"\n', encoding="utf-8")
    assert config._detect_adb_port(conf) == 5575


def test_detect_adb_port_missing_file(tmp_path: Path):
    assert config._detect_adb_port(tmp_path / "nope.conf") is None


def test_settings_detect_populates_adb_path():
    s = config.load_settings()
    assert s.adb_path
    assert s.game_package == "twgame.global.acers"
    assert (s.screen_w, s.screen_h) == (1600, 900)
