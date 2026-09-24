"""Launcher entry (``NTA-Agent.exe`` / ``.bat`` → ``python -m nta_agent.app``).

If the dashboard is already up, just open the browser; otherwise start it as a
windowless background process (on the saved port, or the next free one), wait
until it answers, then open the browser. Never prints: it may run under pythonw.
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

from nta_agent import paths, settings

CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200


def _alive(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/app", timeout=2) as r:
            return "version" in json.loads(r.read().decode("utf-8"))
    except (OSError, ValueError):
        return False


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _pick_port(start: int) -> int:
    for p in range(start, start + 20):
        if _port_free(p):
            return p
    return start


def _python() -> str:
    """Console python (hidden window) so the dashboard/agent always have stdout."""
    exe = sys.executable
    if exe.lower().endswith("pythonw.exe"):
        exe = exe[: -len("pythonw.exe")] + "python.exe"
    return exe


def _start_dashboard(port: int) -> None:
    run = paths.run_dir()
    run.mkdir(parents=True, exist_ok=True)
    log = open(run / "dashboard.log", "ab")  # noqa: SIM115 — handed to the child
    p = subprocess.Popen([_python(), "-m", "nta_agent.dashboard", "--port", str(port)],
                         cwd=str(paths.app_dir()), stdin=subprocess.DEVNULL, stdout=log,
                         stderr=subprocess.STDOUT,
                         creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP)
    (run / "dashboard.pid").write_text(f"{p.pid} {time.time():.0f}", encoding="utf-8")


def _open(url: str) -> None:
    webbrowser.open(url)


def main(port: int | None = None, wait_s: float = 20.0) -> int:
    port = port or int(settings.get("dashboard_port") or 8787)
    if not _alive(port):
        if not _port_free(port):          # something else holds it → move on
            port = _pick_port(port + 1)
            settings.set_values({"dashboard_port": str(port)})
        _start_dashboard(port)
        end = time.time() + wait_s
        while time.time() < end and not _alive(port):
            time.sleep(0.5)
    _open(f"http://127.0.0.1:{port}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
