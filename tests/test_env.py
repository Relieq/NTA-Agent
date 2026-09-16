import os

from nta_agent.env import load_dotenv


def test_loads_keys_without_overriding_real_env(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text('FOO=bar\n# comment\nQUOTED="baz qux"\nPRESET=fromfile\n', encoding="utf-8")
    monkeypatch.delenv("FOO", raising=False)
    monkeypatch.setenv("PRESET", "fromenv")  # real env must win
    load_dotenv(f)
    assert os.environ["FOO"] == "bar"
    assert os.environ["QUOTED"] == "baz qux"
    assert os.environ["PRESET"] == "fromenv"


def test_missing_file_is_noop(tmp_path):
    load_dotenv(tmp_path / "nope.env")  # must not raise
