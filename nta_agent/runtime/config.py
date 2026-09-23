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
    brain_every_ticks: int = 60
    brain_max_calls: int = 50
    res_pressure_window_s: float = 3600.0
    ledger_cap: int = 100
    lessons_cap: int = 50
    stale_after: float = 90.0   # F1: seconds of silence before a health probe
    march_poll_every: int = 6   # ticks between HD_GetMarchs resyncs (siege early warning)

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
    def brain_advice_path(self) -> Path:
        return self.log_dir / "brain_advice.json"

    @property
    def composition_status_path(self) -> Path:
        return self.log_dir / "composition_status.json"

    @property
    def failures_path(self) -> Path:
        return self.log_dir / "failures.json"

    @property
    def lessons_path(self) -> Path:
        return self.log_dir / "lessons.json"

    @property
    def health_path(self) -> Path:
        return self.log_dir / "health.json"

    @property
    def alerts_path(self) -> Path:
        return self.log_dir / "alerts.json"

    @property
    def pending_forts_path(self) -> Path:
        return self.log_dir / "pending_forts.json"

    @property
    def errors_path(self) -> Path:
        return self.log_dir / "errors.jsonl"

    @property
    def commands_done_path(self) -> Path:
        return self.log_dir / "commands.done"

    @property
    def equipment_path(self) -> Path:
        return self.log_dir / "equipment.json"

    @property
    def armies_path(self) -> Path:
        return self.log_dir / "armies.json"

    @property
    def profile_path(self) -> Path:
        return self.log_dir / "profile.json"

    @property
    def forts_path(self) -> Path:
        return self.log_dir / "forts.json"

    @property
    def control_path(self) -> Path:
        return self.log_dir / "control.json"

    @property
    def agent_pid_path(self) -> Path:
        return self.log_dir / "agent.pid"

    @property
    def fort_decisions_path(self) -> Path:
        return self.log_dir / "fort_decisions.json"

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
            brain_every_ticks=int(env.get("NTA_BRAIN_EVERY", "60")),
            brain_max_calls=int(env.get("NTA_BRAIN_MAX_CALLS", "50")),
        )
