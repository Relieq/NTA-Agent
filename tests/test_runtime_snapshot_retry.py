"""write_snapshot survives a brief Windows file lock (WinError 5 seen live)."""
import os

from nta_agent.runtime import snapshot
from nta_agent.state.schema import GameState


def test_replace_is_retried_on_a_transient_lock(tmp_path, monkeypatch):
    calls = {"n": 0}
    real = os.replace

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError(5, "Access is denied")
        return real(src, dst)
    monkeypatch.setattr(snapshot.os, "replace", flaky)
    monkeypatch.setattr(snapshot.time, "sleep", lambda s: None)
    snapshot.write_snapshot(GameState(source="api"), tmp_path / "state.json")
    assert (tmp_path / "state.json").exists() and calls["n"] == 3
