from nta_agent.dashboard import __main__ as cli
from nta_agent.runtime.config import ConfigError


class FakeSrv:
    server_address = ("127.0.0.1", 8787)

    def serve_forever(self):
        raise KeyboardInterrupt()

    def server_close(self):
        pass


def test_main_config_error_returns_2(monkeypatch, capsys):
    monkeypatch.setattr(cli.RuntimeConfig, "from_env", staticmethod(
        lambda *a, **k: (_ for _ in ()).throw(ConfigError("NTA_DISTINCT_ID is required"))))
    assert cli.main(["--port", "0"]) == 2
    assert "NTA_DISTINCT_ID" in capsys.readouterr().err


def test_main_serves_and_returns_0(monkeypatch):
    calls = {}

    def fake_serve(cfg, port):
        calls["args"] = (cfg, port)
        return FakeSrv()

    monkeypatch.setattr(cli.RuntimeConfig, "from_env", staticmethod(lambda *a, **k: "CFG"))
    monkeypatch.setattr(cli, "serve", fake_serve)
    assert cli.main(["--port", "9000"]) == 0
    assert calls["args"] == ("CFG", 9000)
