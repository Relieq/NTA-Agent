import json

import nta_agent.dashboard.supervisor as sup_mod
from nta_agent.dashboard.supervisor import AgentSupervisor
from nta_agent.runtime.config import RuntimeConfig
from nta_agent.runtime.control import read_mode


class FakeProc:
    def __init__(self, pid=4321): self.pid = pid; self._code = None
    def poll(self): return self._code
    def terminate(self): self._code = -15
    def kill(self): self._code = -9
    def wait(self, timeout=None): return self._code


def _cfg(tmp_path): return RuntimeConfig(distinct_id="x", log_dir=tmp_path)


def _patch_spawn(monkeypatch, proc):
    monkeypatch.setattr(sup_mod.subprocess, "Popen", lambda *a, **k: proc)


def test_start_then_running(tmp_path, monkeypatch):
    proc = FakeProc()
    _patch_spawn(monkeypatch, proc)
    monkeypatch.setattr(sup_mod, "pid_alive", lambda pid: proc.poll() is None)
    s = AgentSupervisor(_cfg(tmp_path))
    st = s.start()
    assert st["engine"] == "RUNNING" and st["pid"] == 4321
    assert read_mode(_cfg(tmp_path).control_path) == "run"   # reset on start
    assert json.loads((tmp_path / "agent.pid").read_text())["pid"] == 4321


def test_pause_resume(tmp_path, monkeypatch):
    proc = FakeProc(); _patch_spawn(monkeypatch, proc)
    monkeypatch.setattr(sup_mod, "pid_alive", lambda pid: proc.poll() is None)
    s = AgentSupervisor(_cfg(tmp_path)); s.start()
    assert s.pause()["engine"] == "PAUSED"
    assert read_mode(tmp_path / "control.json") == "pause"
    assert s.resume()["engine"] == "RUNNING"


def test_double_start_is_noop(tmp_path, monkeypatch):
    calls = []
    proc = FakeProc()
    monkeypatch.setattr(sup_mod.subprocess, "Popen",
                        lambda *a, **k: (calls.append(1), proc)[1])
    monkeypatch.setattr(sup_mod, "pid_alive", lambda pid: proc.poll() is None)
    s = AgentSupervisor(_cfg(tmp_path)); s.start(); s.start()
    assert len(calls) == 1


def test_stop_writes_flag_and_clears(tmp_path, monkeypatch):
    proc = FakeProc(); _patch_spawn(monkeypatch, proc)
    # the owned child honors the stop flag: poll() returns a code once stop is set
    monkeypatch.setattr(proc, "poll",
        lambda: 0 if read_mode(tmp_path / "control.json") == "stop" else None)
    s = AgentSupervisor(_cfg(tmp_path)); s.start()
    st = s.stop(timeout=1.0)
    assert st["engine"] == "STOPPED"
    assert read_mode(tmp_path / "control.json") == "stop"
    assert not (tmp_path / "agent.pid").exists()


def test_crashed_detection(tmp_path, monkeypatch):
    proc = FakeProc(); _patch_spawn(monkeypatch, proc)
    monkeypatch.setattr(sup_mod, "pid_alive", lambda pid: proc.poll() is None)
    s = AgentSupervisor(_cfg(tmp_path)); s.start()
    proc._code = 1  # exited nonzero without a user stop
    assert s.status()["engine"] == "CRASHED"


def test_adopt_live_pidfile(tmp_path, monkeypatch):
    (tmp_path / "agent.pid").write_text(json.dumps({"pid": 777, "started_at": 0}))
    monkeypatch.setattr(sup_mod, "pid_alive", lambda pid: pid == 777)
    s = AgentSupervisor(_cfg(tmp_path))
    assert s.status()["engine"] == "RUNNING" and s.status()["pid"] == 777


def test_adopt_stale_pidfile_deleted(tmp_path, monkeypatch):
    (tmp_path / "agent.pid").write_text(json.dumps({"pid": 777, "started_at": 0}))
    monkeypatch.setattr(sup_mod, "pid_alive", lambda pid: False)
    s = AgentSupervisor(_cfg(tmp_path))
    assert s.status()["engine"] == "STOPPED"
    assert not (tmp_path / "agent.pid").exists()
