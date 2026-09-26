"""Runtime configuration for the operational spine (env NTA_* -> RuntimeConfig)."""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from nta_agent import paths, settings


class ConfigError(Exception):
    """A required runtime configuration value is missing or invalid."""


@dataclass
class RuntimeConfig:
    distinct_id: str
    host: str = "nine-hk.twomiles.cn"
    token_path: Path = field(default_factory=lambda: paths.token_path())
    interval: float = 5.0
    max_backoff: float = 60.0
    log_dir: Path = field(default_factory=lambda: paths.run_dir())
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
    def forge_targets_path(self) -> Path:
        return self.log_dir / "forge_targets.json"   # {equip_uid: {threshold, budget}}

    @property
    def forge_view_path(self) -> Path:
        return self.log_dir / "forge.json"           # recast panel rows (dashboard)

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
    def pending_renames_path(self) -> Path:
        return self.log_dir / "pending_renames.json"   # renames waiting for an idle army

    @property
    def dig_request_path(self) -> Path:
        return self.log_dir / "dig_request.json"      # dashboard -> agent (request/confirm/cancel)

    @property
    def dig_state_path(self) -> Path:
        return self.log_dir / "dig.json"              # agent -> dashboard (preview/active/...)

    @property
    def spare_advice_path(self) -> Path:
        return self.log_dir / "spare_advice.json"     # spare armies: ok / stuck warning

    @property
    def buffers_path(self) -> Path:
        return self.log_dir / "buffers.json"          # buffer-leveling proposal + phases

    @property
    def fort_decisions_path(self) -> Path:
        return self.log_dir / "fort_decisions.json"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None,
                 require_distinct: bool = True) -> RuntimeConfig:
        """Env first, then the user's settings.json (packaged app). The dashboard
        passes ``require_distinct=False`` so it can run the first-time Setup."""
        env = os.environ if env is None else env
        distinct = (env.get("NTA_DISTINCT_ID", "").strip()
                    or (settings.get("distinct_id") or "").strip())
        if not distinct and require_distinct:
            raise ConfigError("NTA_DISTINCT_ID is required")
        return cls(
            distinct_id=distinct,
            host=env.get("NTA_SERVER_HOST", "nine-hk.twomiles.cn"),
            token_path=Path(env.get("NTA_TOKEN_PATH") or paths.token_path()),
            interval=float(env.get("NTA_TICK_INTERVAL", "5.0")),
            max_backoff=float(env.get("NTA_MAX_BACKOFF", "60.0")),
            log_dir=Path(env.get("NTA_LOG_DIR") or paths.run_dir()),
            brain_every_ticks=int(env.get("NTA_BRAIN_EVERY", "60")),
            brain_max_calls=int(env.get("NTA_BRAIN_MAX_CALLS")
                                or settings.get("brain_max_calls") or 50),
        )
