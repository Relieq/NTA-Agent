"""Cross-platform process liveness + force-kill (no third-party deps)."""
from __future__ import annotations

import os
import signal
import subprocess

_STILL_ACTIVE = 259


def pid_alive(pid: int) -> bool:
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        PROCESS_QUERY_LIMITED = 0x1000
        k = ctypes.windll.kernel32
        h = k.OpenProcess(PROCESS_QUERY_LIMITED, False, int(pid))
        if not h:
            return False
        try:
            code = ctypes.c_ulong()
            if not k.GetExitCodeProcess(h, ctypes.byref(code)):
                return False
            return code.value == _STILL_ACTIVE
        finally:
            k.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def hard_kill(pid: int) -> None:
    if not pid or pid <= 0:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/PID", str(int(pid))],
                       capture_output=True, check=False)
        return
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
