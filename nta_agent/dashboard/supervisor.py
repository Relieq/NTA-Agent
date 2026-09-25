"""Supervise the agent as a child process (spawn or adopt), thread-safe."""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

from nta_agent import paths
from nta_agent.runtime.control import read_mode, reset, write_control
from nta_agent.runtime.proc import hard_kill, pid_alive


class AgentSupervisor:
    def __init__(self, cfg):
        self.cfg = cfg
        self._lock = threading.Lock()
        self._proc = None            # Popen when we spawned it; None when adopted
        self._pid = 0
        self._started_at = 0.0
        self._user_stopped = False
        self._last_exit = None
        self._adopt()

    # ---- helpers -------------------------------------------------------- #
    def _adopt(self):
        try:
            d = json.loads(Path(self.cfg.agent_pid_path).read_text(encoding="utf-8"))
            pid = int(d.get("pid", 0))
        except (OSError, ValueError):
            return
        if pid and pid_alive(pid):
            self._pid = pid
            self._started_at = float(d.get("started_at") or time.time())
        else:
            self._clear_pidfile()

    def _write_pidfile(self):
        Path(self.cfg.agent_pid_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.cfg.agent_pid_path).write_text(
            json.dumps({"pid": self._pid, "started_at": self._started_at}),
            encoding="utf-8")

    def _clear_pidfile(self):
        try:
            Path(self.cfg.agent_pid_path).unlink()
        except OSError:
            pass

    def _alive(self) -> bool:
        if self._proc is not None:
            return self._proc.poll() is None
        if self._pid:
            return pid_alive(self._pid)
        return False

    def _reap_if_exited(self):
        """If an owned child exited on its own, record it and clear handles."""
        if self._proc is not None and self._proc.poll() is not None:
            self._last_exit = self._proc.poll()
            self._proc = None
            self._pid = 0
            self._clear_pidfile()

    # ---- API ------------------------------------------------------------ #
    def start(self) -> dict:
        with self._lock:
            self._reap_if_exited()
            if self._alive():
                return self._status()
            from nta_agent.setup import steps
            if not steps.ready():
                return {**self._status(),
                        "error": "Chưa hoàn tất Thiết lập — mở tab Thiết lập."}
            reset(self.cfg.control_path)
            # No console window: the packaged dashboard itself runs windowless.
            flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
            # Keep the agent's stdout/stderr: a crash before its first tick (e.g. login
            # failing) never reaches errors.jsonl, so this log is the only trace.
            log = self._open_agent_log()
            try:
                self._proc = subprocess.Popen([sys.executable, "-m", "nta_agent"],
                                              cwd=str(paths.app_dir()), creationflags=flags,
                                              stdin=subprocess.DEVNULL, stdout=log,
                                              stderr=subprocess.STDOUT)
            finally:
                log.close()  # the child holds its own handle
            self._pid = self._proc.pid
            self._started_at = time.time()
            self._user_stopped = False
            self._last_exit = None
            self._write_pidfile()
            return self._status()

    def stop(self, timeout: float = 10.0) -> dict:
        with self._lock:
            if not self._alive():
                self._proc = None
                self._pid = 0
                self._clear_pidfile()
                self._user_stopped = True
                return self._status()
            write_control(self.cfg.control_path, stop=True)
            deadline = time.time() + timeout
            while time.time() < deadline and self._alive():
                time.sleep(0.1)
            if self._alive():
                if self._proc is not None:
                    self._proc.terminate()
                    try:
                        self._proc.wait(timeout=3)
                    except Exception:
                        self._proc.kill()
                else:
                    hard_kill(self._pid)
            self._user_stopped = True
            self._proc = None
            self._pid = 0
            self._clear_pidfile()
            return self._status()

    def pause(self) -> dict:
        with self._lock:
            write_control(self.cfg.control_path, paused=True)
            return self._status()

    def resume(self) -> dict:
        with self._lock:
            write_control(self.cfg.control_path, paused=False)
            return self._status()

    def status(self) -> dict:
        with self._lock:
            self._reap_if_exited()
            return self._status()

    # ---- internal status (assumes lock held) ---------------------------- #
    def _agent_log_path(self) -> Path:
        return Path(self.cfg.log_dir) / "agent.log"

    def _open_agent_log(self):
        p = self._agent_log_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            if p.stat().st_size > 5_000_000:
                p.replace(p.with_suffix(".log.1"))
        except OSError:
            pass
        f = open(p, "ab")  # noqa: SIM115 — closed by the caller after the spawn
        f.write(time.strftime("\n=== agent start %Y-%m-%d %H:%M:%S ===\n").encode())
        f.flush()
        return f

    def _log_tail(self, n: int = 15) -> list[str]:
        try:
            text = self._agent_log_path().read_bytes()[-20000:].decode("utf-8", "replace")
        except OSError:
            return []
        run = text.rsplit("=== agent start", 1)[-1]  # only the last run's output
        return [ln for ln in run.splitlines()[1:] if ln.strip()][-n:]

    def _status(self) -> dict:
        if self._alive():
            engine = "PAUSED" if read_mode(self.cfg.control_path) == "pause" else "RUNNING"
            return {"engine": engine, "pid": self._pid,
                    "uptime": max(0.0, time.time() - self._started_at)}
        if self._last_exit not in (None, 0) and not self._user_stopped:
            return {"engine": "CRASHED", "pid": None, "uptime": 0.0,
                    "exit_code": self._last_exit, "log_tail": self._log_tail()}
        return {"engine": "STOPPED", "pid": None, "uptime": 0.0}
