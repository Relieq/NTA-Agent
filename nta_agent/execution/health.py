"""Connection health for unattended runs (F1).

The agent's recovery is otherwise purely reactive (it recovers on an exception).
A silent half-open connection throws nothing but stops delivering pushes, so state
goes stale without ever triggering recovery. HealthMonitor tracks staleness and
recovery telemetry; the agent uses it to PROACTIVELY probe + recover, and the
dashboard reads its status to watch a long run.
"""
from __future__ import annotations

import time


class HealthMonitor:
    def __init__(self, stale_after: float = 90.0, degrade_after: int = 3,
                 clock=time.time) -> None:
        self.stale_after = float(stale_after)
        self.degrade_after = int(degrade_after)
        self._clock = clock
        self.recover_count = 0
        self.last_recover_ts = 0.0
        self.consecutive_fail = 0
        self.degraded = False

    def is_stale(self, last_activity: float) -> bool:
        """True when no server activity has been seen for longer than stale_after."""
        return (self._clock() - float(last_activity)) > self.stale_after

    def note_recover_ok(self) -> None:
        self.recover_count += 1
        self.last_recover_ts = self._clock()
        self.consecutive_fail = 0
        self.degraded = False

    def note_recover_fail(self) -> None:
        self.consecutive_fail += 1
        if self.consecutive_fail >= self.degrade_after:
            self.degraded = True

    def status(self, last_activity: float, connected: bool = True) -> dict:
        return {
            "connected": bool(connected),
            "last_activity_age": round(self._clock() - float(last_activity), 1),
            "recover_count": self.recover_count,
            "last_recover_ts": self.last_recover_ts,
            "consecutive_fail": self.consecutive_fail,
            "degraded": self.degraded,
        }
