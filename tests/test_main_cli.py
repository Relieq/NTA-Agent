from nta_agent import __main__ as cli
from nta_agent.runtime.config import ConfigError


def test_main_missing_config_returns_2(monkeypatch, capsys):
    monkeypatch.setattr(cli.RuntimeConfig, "from_env", staticmethod(
        lambda *a, **k: (_ for _ in ()).throw(ConfigError("NTA_DISTINCT_ID is required"))))
    assert cli.main([]) == 2
    assert "NTA_DISTINCT_ID" in capsys.readouterr().err


def test_main_once_calls_runner_with_ticks_1(monkeypatch):
    calls = {}
    monkeypatch.setattr(cli.RuntimeConfig, "from_env", staticmethod(lambda *a, **k: "CFG"))
    monkeypatch.setattr(cli.runner, "run", lambda cfg, *, ticks: calls.update(cfg=cfg, ticks=ticks))
    assert cli.main(["--once"]) == 0
    assert calls == {"cfg": "CFG", "ticks": 1}
