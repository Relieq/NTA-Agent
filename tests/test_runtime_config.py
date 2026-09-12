from pathlib import Path

import pytest

from nta_agent.runtime.config import ConfigError, RuntimeConfig


def test_from_env_defaults():
    cfg = RuntimeConfig.from_env({"NTA_DISTINCT_ID": "abc"})
    assert cfg.distinct_id == "abc"
    assert cfg.host == "nine-hk.twomiles.cn"
    assert cfg.interval == 5.0
    assert cfg.max_backoff == 60.0
    assert cfg.token_path == Path("build/nta_token.txt")
    assert cfg.log_dir == Path("build/run")
    assert cfg.snapshot_path == Path("build/run/state.json")
    assert cfg.event_log_path == Path("build/run/events.jsonl")


def test_from_env_overrides():
    cfg = RuntimeConfig.from_env({
        "NTA_DISTINCT_ID": "x", "NTA_SERVER_HOST": "h", "NTA_TICK_INTERVAL": "2.5",
        "NTA_MAX_BACKOFF": "10", "NTA_TOKEN_PATH": "/t/tok.txt", "NTA_LOG_DIR": "/l",
    })
    assert (cfg.host, cfg.interval, cfg.max_backoff) == ("h", 2.5, 10.0)
    assert cfg.token_path == Path("/t/tok.txt")
    assert cfg.snapshot_path == Path("/l/state.json")


def test_missing_distinct_id_raises():
    with pytest.raises(ConfigError):
        RuntimeConfig.from_env({})


def test_decision_queue_paths():
    cfg = RuntimeConfig.from_env({"NTA_DISTINCT_ID": "x", "NTA_LOG_DIR": "/l"})
    assert cfg.decisions_path == Path("/l/decisions.json")
    assert cfg.commands_path == Path("/l/commands.jsonl")
    assert cfg.commands_done_path == Path("/l/commands.done")
