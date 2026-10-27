"""Read the game's XXTEA key from the running game over root ADB.

Since game 4.5.x the key is built at runtime — it is no longer a string in
``libcocos2djs.so`` (``gamedata.find_xxtea_key`` finds nothing) — and the game kills itself
when Frida attaches. It still sits in the library's data segment as a libc++ *short*
``std::string`` (first byte = length << 1, then the 16 characters), so with root we read
the library's writable ranges from ``/proc/<pid>/mem`` and test each such string against an
encrypted file of the APK (live 2026-10-27: 7.5 MB read in under a second, game unharmed).

``/system/bin/dd`` on LDPlayer 14 points at ``toolbox`` (no dd there), hence ``toybox dd``.
"""
from __future__ import annotations

import re
import subprocess
import time

PACKAGE = "twgame.global.acers"
ACTIVITY = "twgame.global.acers/org.cocos2dx.javascript.AppActivity"
LIB = "libcocos2djs.so"
PAGE = 4096
_MAP_RE = re.compile(r"^([0-9a-f]+)-([0-9a-f]+) (\S+) \S+ \S+ \S+\s*(.*)$")


def rw_ranges(maps: str, lib: str = LIB, margin: int = 0x200000) -> list[tuple[int, int]]:
    """Writable ranges of ``lib`` plus the anonymous ones (its .bss) inside its span."""
    rows = []
    for ln in maps.splitlines():
        m = _MAP_RE.match(ln.strip())
        if m:
            rows.append((int(m[1], 16), int(m[2], 16), m[3], m[4].strip()))
    mine = [r for r in rows if r[3].endswith("/" + lib)]
    if not mine:
        return []
    lo, hi = min(r[0] for r in mine), max(r[1] for r in mine) + margin
    return [(a, b) for a, b, perm, path in rows
            if perm.startswith("rw") and lo <= a < hi
            and (path.endswith("/" + lib) or path == "" or path.startswith("[anon"))]


def key_in_memory(data: bytes, probe: bytes) -> str | None:
    """The 16-char short std::string in ``data`` that decrypts ``probe`` into JavaScript."""
    from nta_agent import gamedata
    seen = set()
    for m in re.finditer(rb"[\x20-\x2c]", data):
        i = m.start()
        b = data[i]
        if b & 1:
            continue
        n = b >> 1
        s = data[i + 1:i + 1 + n]
        if not (16 <= n <= 22 and len(s) == n and all(0x21 <= c <= 0x7E for c in s)):
            continue
        cand = s[:16]
        if cand in seen:
            continue
        seen.add(cand)
        if gamedata._looks_like_js(gamedata.decrypt_bytes(probe, cand)):
            return cand.decode("ascii")
    return None


def adb_runner(adb_path: str, serial: str | None):
    """``run(args, binary=False)`` over ``adb [-s serial] shell|exec-out``."""
    base = [adb_path] + (["-s", serial] if serial else [])

    def run(args, binary=False):
        cmd = base + (["exec-out"] if binary else ["shell"]) + list(args)
        r = subprocess.run(cmd, capture_output=True, timeout=120,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.stdout if binary else r.stdout.decode("utf-8", "replace")
    return run


def _dd(pid: str, a: int, b: int) -> str:
    return (f"su -c 'toybox dd if=/proc/{pid}/mem bs={PAGE} skip={a // PAGE} "
            f"count={(b - a) // PAGE} 2>/dev/null'")


def read_key(run, probe: bytes, *, wait_s: float = 60, sleep=time.sleep) -> str | None:
    """Key from the running game (started if needed), or None without root / game."""
    if "uid=0" not in run(["su -c id"]):
        return None
    pid = run([f"pidof {PACKAGE}"]).strip().split()
    if not pid:
        run([f"am start -n {ACTIVITY}"])
    ranges = []
    waited = 0.0
    while waited <= wait_s:  # the library loads (and sets the key) a few seconds in
        pid = run([f"pidof {PACKAGE}"]).strip().split()
        if pid:
            ranges = rw_ranges(run([f"su -c 'cat /proc/{pid[0]}/maps'"]))
            if ranges:
                break
        sleep(3)
        waited += 3
    if not ranges:
        return None
    for _ in range(5):  # the key is set at boot: retry a little while the game starts up
        data = b"".join(run([_dd(pid[0], a, b)], binary=True) for a, b in ranges)
        key = key_in_memory(data, probe)
        if key:
            return key
        sleep(5)
    return None


def device_reader():
    """``probe -> key`` over the configured emulator (adb path/serial from Settings)."""
    def read(probe: bytes) -> str | None:
        from nta_agent.config import Settings
        s = Settings.detect()
        return read_key(adb_runner(s.adb_path, s.serial), probe)
    return read
