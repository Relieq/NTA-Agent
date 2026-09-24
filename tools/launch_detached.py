"""Launch the dashboard (or agent) as a DETACHED OS process — reaper-proof.

Processes started via Claude Code's background shells get killed under host
memory pressure. Running the dashboard detached (not as a Claude bg-shell) keeps
it alive across that; the agent it then spawns (via the dashboard Start button)
inherits that independence too.

Usage:
    python tools/launch_detached.py dashboard   # start the dashboard detached
    python tools/launch_detached.py agent       # start the agent directly (rare)
    python tools/launch_detached.py stop dashboard   # stop a launched process
    python tools/launch_detached.py status           # show what's running

Writes <target>.pid in the runtime log dir; `stop` reads it.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nta_agent import paths
from nta_agent.env import load_dotenv
from nta_agent.runtime.config import RuntimeConfig
from nta_agent.runtime.proc import hard_kill, pid_alive

TARGETS = {"dashboard": ["-m", "nta_agent.dashboard"], "agent": ["-m", "nta_agent"]}
_REPO = str(paths.app_dir())


def _pidfile(cfg, target):
    return cfg.log_dir / f"{target}.pid"


def _detached_popen(args):
    kw = dict(cwd=_REPO, stdin=subprocess.DEVNULL,
              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if os.name == "nt":  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        kw["creationflags"] = 0x00000008 | 0x00000200
    else:
        kw["start_new_session"] = True
    return subprocess.Popen(args, **kw)


def launch(cfg, target):
    pf = _pidfile(cfg, target)
    try:  # don't double-launch
        old = json.loads(pf.read_text(encoding="utf-8")).get("pid")
        if old and pid_alive(old):
            print(f"{target} already running (pid {old})")
            return 0
    except (OSError, ValueError):
        pass
    p = _detached_popen([sys.executable, *TARGETS[target]])
    pf.parent.mkdir(parents=True, exist_ok=True)
    pf.write_text(json.dumps({"pid": p.pid, "started_at": time.time()}), encoding="utf-8")
    time.sleep(1.5)
    ok = pid_alive(p.pid)
    print(f"{target} detached pid={p.pid} alive={ok} pidfile={pf}")
    if target == "dashboard" and ok:
        print("dashboard on http://127.0.0.1:8787")
    return 0 if ok else 1


def stop(cfg, target):
    pf = _pidfile(cfg, target)
    try:
        pid = json.loads(pf.read_text(encoding="utf-8")).get("pid")
    except (OSError, ValueError):
        print(f"{target}: no pidfile"); return 0
    if pid and pid_alive(pid):
        hard_kill(pid)
        print(f"{target}: killed pid {pid}")
    else:
        print(f"{target}: not running")
    pf.unlink(missing_ok=True)
    return 0


def status(cfg):
    for t in TARGETS:
        try:
            pid = json.loads(_pidfile(cfg, t).read_text(encoding="utf-8")).get("pid")
            print(f"  {t}: pid {pid} alive={pid_alive(pid) if pid else False}")
        except (OSError, ValueError):
            print(f"  {t}: not launched")


def main(argv):
    load_dotenv()
    cfg = RuntimeConfig.from_env()
    cmd = argv[0] if argv else "dashboard"
    if cmd == "stop":
        return stop(cfg, argv[1] if len(argv) > 1 else "dashboard")
    if cmd == "status":
        status(cfg); return 0
    if cmd in TARGETS:
        return launch(cfg, cmd)
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
