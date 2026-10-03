"""Keep the PC from going to sleep while the agent runs.

Live 2026-10-03: the laptop entered Modern Standby for 63 minutes in the middle of a dig and the
agent (loop, session, dig) stood still. Windows only: a daemon thread holds
``SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)`` (the display may still turn off)
and a ``PowerRequest`` (system + execution required — what lets a desktop process keep running
under Modern Standby). Both are released on ``stop()`` and by Windows if the process dies.
It cannot stop a lid-close / power-button sleep set by the user: say so in the UI/README.
"""
from __future__ import annotations

import sys
import threading

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
_POWER_REQUEST_SYSTEM_REQUIRED = 1
_POWER_REQUEST_EXECUTION_REQUIRED = 3
_REASON = "NTA-Agent is running"


def _kernel32():
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        return ctypes.windll.kernel32
    except Exception:
        return None


class KeepAwake:
    def __init__(self, enabled: bool = True, kernel=..., renew_s: float = 60.0):
        self.enabled = enabled
        self.kernel = _kernel32() if kernel is ... else kernel
        self.renew_s = renew_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._handle = None
        self.active = False

    def _create_request(self):
        """A PowerRequest handle (None when the API is missing or refuses)."""
        try:
            import ctypes

            class _Reason(ctypes.Structure):   # REASON_CONTEXT, simple-string form
                _fields_ = [("Version", ctypes.c_ulong), ("Flags", ctypes.c_ulong),
                            ("Reason", ctypes.c_wchar_p), ("_pad", ctypes.c_void_p)]
            ctx = _Reason(0, 1, _REASON, None)
            h = self.kernel.PowerCreateRequest(ctypes.byref(ctx))
            if not h or h == -1:
                return None
            for kind in (_POWER_REQUEST_SYSTEM_REQUIRED, _POWER_REQUEST_EXECUTION_REQUIRED):
                try:
                    self.kernel.PowerSetRequest(h, kind)
                except Exception:
                    pass
            return h
        except Exception:
            return None

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.kernel.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
            except Exception:
                pass
            self._stop.wait(self.renew_s)
        try:
            self.kernel.SetThreadExecutionState(ES_CONTINUOUS)
        except Exception:
            pass

    def start(self) -> bool:
        if not self.enabled or self.kernel is None or self._thread is not None:
            return False
        self._handle = self._create_request()
        self._thread = threading.Thread(target=self._run, name="keep-awake", daemon=True)
        self._thread.start()
        self.active = True
        return True

    def stop(self) -> None:
        if self._thread is None:
            return
        self._stop.set()
        self._thread.join(timeout=2.0)
        self._thread = None
        if self._handle is not None:
            for kind in (_POWER_REQUEST_SYSTEM_REQUIRED, _POWER_REQUEST_EXECUTION_REQUIRED):
                try:
                    self.kernel.PowerClearRequest(self._handle, kind)
                except Exception:
                    pass
            try:
                self.kernel.CloseHandle(self._handle)
            except Exception:
                pass
            self._handle = None
        self.active = False
