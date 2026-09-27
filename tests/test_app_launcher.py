from nta_agent import app, settings


def _stub(monkeypatch, alive_seq, free=True):
    opened, started = [], []
    seq = iter(alive_seq)
    monkeypatch.setattr(app, "_alive", lambda port: next(seq, True))
    monkeypatch.setattr(app, "_port_free", lambda port: free if port == 8787 else True)
    monkeypatch.setattr(app, "_open", lambda url: opened.append(url))
    monkeypatch.setattr(app, "_start_dashboard", lambda port: started.append(port))
    return opened, started


def test_running_dashboard_only_opens_browser(monkeypatch):
    opened, started = _stub(monkeypatch, [True])
    app.main(port=8787)
    assert opened == ["http://127.0.0.1:8787"] and started == []


def test_starts_dashboard_then_opens(monkeypatch):
    opened, started = _stub(monkeypatch, [False, False, True])
    app.main(port=8787, wait_s=5)
    assert started == [8787] and opened == ["http://127.0.0.1:8787"]


def test_busy_port_moves_and_is_remembered(monkeypatch):
    _opened, started = _stub(monkeypatch, [False, True], free=False)
    app.main(port=8787, wait_s=5)
    assert started == [8788] and settings.get("dashboard_port") == "8788"


def test_python_prefers_console_interpreter(monkeypatch):
    monkeypatch.setattr(app.sys, "executable", r"C:\x\runtime\python\pythonw.exe")
    assert app._python() == r"C:\x\runtime\python\python.exe"


def test_fresh_env_reloads_our_vars_from_the_registry():
    # issue #81: a restart from the dashboard must see env changes made in Windows
    # since the app started (the process env is a stale copy)
    from nta_agent import app
    reg = {"OPENAI_API_KEY": "sk-new-from-registry"}           # NTA_ADB_SERIAL was deleted
    env = app.fresh_env({"OPENAI_API_KEY": "sk-old", "NTA_ADB_SERIAL": "5555", "PATH": "x"},
                        reader=reg.get)
    assert env["OPENAI_API_KEY"] == "sk-new-from-registry"
    assert "NTA_ADB_SERIAL" not in env and env["PATH"] == "x"   # others untouched


def test_restart_waits_for_the_old_dashboard_to_exit(monkeypatch):
    from nta_agent import app
    alive = iter([True, True, False, False, False])
    calls = []
    monkeypatch.setattr(app, "_alive", lambda port: next(alive))
    monkeypatch.setattr(app, "_port_free", lambda port: True)
    monkeypatch.setattr(app, "_start_dashboard", lambda port: calls.append(("start", port)))
    monkeypatch.setattr(app, "_open", lambda url: calls.append(("open", url)))
    monkeypatch.setattr(app.time, "sleep", lambda s: None)
    app.main(port=8787, wait_s=0, after_exit=8787)
    assert calls[0] == ("start", 8787)                           # not just "open" the old one
