"""Spawn the game under Frida, load a hook script, print its output, detach.

Usage: python tools/re/run_hook.py tools/re/hook_xxtea.js [seconds]
"""
import sys
import time

import frida

PKG = "twgame.global.acers"

def main():
    script_path = sys.argv[1]
    wait_s = int(sys.argv[2]) if len(sys.argv) > 2 else 15
    with open(script_path, encoding="utf-8") as _f:
        src = _f.read()

    dev = frida.get_usb_device(timeout=10)
    print(f"[*] device: {dev.name}")
    pid = dev.spawn([PKG])
    print(f"[*] spawned {PKG} pid={pid}")
    session = dev.attach(pid)
    script = session.create_script(src)
    script.on("message", lambda m, d: print("[msg]", m.get("payload") or m))
    script.load()
    dev.resume(pid)
    print(f"[*] resumed; capturing {wait_s}s ...")
    time.sleep(wait_s)
    try:
        session.detach()
    except Exception:
        pass
    print("[*] done")

if __name__ == "__main__":
    main()
