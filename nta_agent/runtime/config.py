"""Runtime configuration for the operational spine (env NTA_* -> RuntimeConfig)."""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


class ConfigError(Exception):
    """A required runtime configuration value is missing or invalid."""


@dataclass
class RuntimeConfig:
    distinct_id: str
    host: str = "nine-hk.twomiles.cn"
    token_path: Path = Path("build/nta_token.txt")
    interval: float = 5.0
    max_backoff: float = 60.0
    log_dir: Path = Path("build/run")

    @property
    def snapshot_path(self) -> Path:
        return self.log_dir / "state.json"

    @property
    def event_log_path(self) -> Path:
        return self.log_dir / "events.jsonl"

    @property
    def decisions_path(self) -> Path:
        return self.log_dir / "decisions.json"

    @property
    def commands_path(self) -> Path:
        return self.log_dir / "commands.jsonl"

    @property
    def commands_done_path(self) -> Path:
        return self.log_dir / "commands.done"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> RuntimeConfig:
        env = os.environ if env is None else env
        distinct = env.get("NTA_DISTINCT_ID", "").strip()
        if not distinct:
            raise ConfigError("NTA_DISTINCT_ID is required")
        return cls(
            distinct_id=distinct,
            host=env.get("NTA_SERVER_HOST", "nine-hk.twomiles.cn"),
            token_path=Path(env.get("NTA_TOKEN_PATH", "build/nta_token.txt")),
            interval=float(env.get("NTA_TICK_INTERVAL", "5.0")),
            max_backoff=float(env.get("NTA_MAX_BACKOFF", "60.0")),
            log_dir=Path(env.get("NTA_LOG_DIR", "build/run")),
        )
