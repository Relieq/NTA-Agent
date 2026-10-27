"""Game 4.5.x builds its XXTEA key at runtime (no longer a string in libcocos2djs.so) and
kills the game when Frida attaches. The key is read instead from the running game's memory
over root ADB (/proc/<pid>/mem) — a libc++ short std::string in the library's data
segment (live 2026-10-27)."""
import zipfile

from nta_agent import gamedata
from nta_agent.io import keydump

KEY = b"0123456789abcdef"
PROBE = gamedata.xxtea_encrypt(b"(function r(e, n, t) {\nfunction i(u, f) {}\n})" * 4, KEY)

MAPS = """\
7e6abd60c000-7e6abf1ed000 r-xp 00000000 08:12 655490   /data/app/x/lib/x86_64/libcocos2djs.so
7e6abf1f0000-7e6abf2b0000 rw-p 00000000 00:00 0
7e6abf2b0000-7e6abf2b3000 r-xp 00000000 00:00 0
7e6abf3b5000-7e6abf9e1000 rw-p 01cad000 08:12 655490   /data/app/x/lib/x86_64/libcocos2djs.so
7e6abfa00000-7e6abfc00000 ---p 00000000 00:00 0
7e6abfcbb000-7e6abfcbc000 rw-p 0001d000 08:02 5830     /system/vendor/lib64/egl/libGLESv2_adreno.so
7e6ad0000000-7e6ad0100000 rw-p 00000000 00:00 0
"""


def test_reads_only_the_librarys_writable_ranges():
    got = keydump.rw_ranges(MAPS)
    assert got == [(0x7E6ABF1F0000, 0x7E6ABF2B0000), (0x7E6ABF3B5000, 0x7E6ABF9E1000)]
    assert keydump.rw_ranges("nothing here\n") == []


def test_finds_the_key_held_as_a_short_std_string():
    junk = bytes([0x20]) + b"not-the-key-zzzz" + b"\x00" * 7
    held = bytes([len(KEY) << 1]) + KEY + b"\x00" * 7       # libc++ short string layout
    mem = b"\x11" * 64 + junk + b"\x00" * 9 + held + b"\xff" * 32
    assert keydump.key_in_memory(mem, PROBE) == KEY.decode()
    assert keydump.key_in_memory(b"\x00" * 128, PROBE) is None


def _apk(tmp_path, with_probe=True):
    apk = tmp_path / "base.apk"
    with zipfile.ZipFile(apk, "w") as z:
        if with_probe:
            z.writestr(gamedata.PROBE_ENTRY, PROBE)
        z.writestr("lib/x86_64/libcocos2djs.so", b"\x00nothing\x00")
    return apk


def test_a_saved_key_is_used_only_while_it_still_decrypts_the_apk(tmp_path):
    apk = _apk(tmp_path)
    assert gamedata.resolve_key(apk, saved=KEY.decode()) == (KEY.decode(), "saved")
    # the game changed its key: the stale saved one is skipped, the device one is used
    asked = []
    dev = lambda probe: asked.append(probe) or KEY.decode()
    assert gamedata.resolve_key(apk, saved="ffffffffffffffff", device=dev) == (KEY.decode(), "device")
    assert asked == [PROBE]


def test_a_wrong_device_key_is_rejected(tmp_path):
    apk = _apk(tmp_path)
    assert gamedata.resolve_key(apk, device=lambda p: "ffffffffffffffff") == (None, None)
    assert gamedata.resolve_key(apk, device=lambda p: None) == (None, None)


def test_the_device_is_only_asked_when_the_apk_does_not_give_the_key(tmp_path, monkeypatch):
    apk = _apk(tmp_path)
    monkeypatch.setattr(gamedata, "find_xxtea_key", lambda a: KEY.decode())
    dev = lambda p: (_ for _ in ()).throw(AssertionError("device asked"))
    assert gamedata.resolve_key(apk, device=dev) == (KEY.decode(), "apk")


def test_a_device_failure_is_not_fatal(tmp_path):
    def boom(probe):
        raise OSError("adb not found")
    assert gamedata.resolve_key(_apk(tmp_path), device=boom) == (None, None)


class FakeAdb:
    """adb shell / exec-out stand-in for a rooted emulator running the game."""
    def __init__(self, mem: bytes, root=True, running=True):
        self.mem, self.root, self.running, self.cmds = mem, root, running, []

    def __call__(self, args, binary=False):
        cmd = args[-1]
        self.cmds.append(cmd)
        if cmd.startswith("su -c id"):
            return "uid=0(root)" if self.root else "Permission denied"
        if cmd.startswith("pidof"):
            return "4986\n" if self.running else ""
        if cmd.startswith("am start"):
            self.running = True
            return "Starting"
        if "cat /proc/4986/maps" in cmd:
            return MAPS
        if "toybox dd" in cmd:
            return self.mem if binary else ""
        return ""


def test_reads_the_key_from_the_running_game_over_root_adb():
    mem = b"\x00" * 40 + bytes([32]) + KEY + b"\x00" * 7
    adb = FakeAdb(mem)
    assert keydump.read_key(adb, PROBE, sleep=lambda s: None) == KEY.decode()
    assert any("toybox dd if=/proc/4986/mem" in c for c in adb.cmds)


def test_starts_the_game_when_it_is_not_running():
    mem = bytes([32]) + KEY
    adb = FakeAdb(mem, running=False)
    assert keydump.read_key(adb, PROBE, sleep=lambda s: None) == KEY.decode()
    assert any(c.startswith("am start") for c in adb.cmds)


def test_no_root_means_no_key_and_no_memory_read():
    adb = FakeAdb(b"", root=False)
    assert keydump.read_key(adb, PROBE, sleep=lambda s: None) is None
    assert not any("dd" in c for c in adb.cmds)
