"""Build the portable Windows release (spec 2026-09-24-packaging-design.md).

    .venv/Scripts/python.exe tools/package.py --version 0.1.0 [--notes "..."]

Produces in ``dist/``:
    NTA-Agent-<v>-full.zip   NTA-Agent/{NTA-Agent.exe,.bat,VERSION,runtime/,app/}
    NTA-Agent-<v>-app.zip    app/ + VERSION (updates when runtimes are unchanged)
    manifest.json            version, runtimes, sha256 of each zip (updater input)

App files are the GIT-TRACKED files of an allow-list (so gitignored game data and
keys can't slip in), then every zip is re-scanned by ``leaks()`` before it is kept.
Downloads (embedded CPython, Node) are cached in ``build/pkgcache``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY_VERSION = "%d.%d.%d" % sys.version_info[:3]
NODE_VERSION = "22.11.0"
PY_URL = f"https://www.python.org/ftp/python/{PY_VERSION}/python-{PY_VERSION}-embed-amd64.zip"
NODE_BASE = f"https://nodejs.org/dist/v{NODE_VERSION}"
NODE_ZIP = f"node-v{NODE_VERSION}-win-x64.zip"
PIP_DEPS = ["paho-mqtt>=2.0", "pillow>=10.0"]

INCLUDE = ["nta_agent/", "tools/battlesim/", "tools/re/extract_config.py",
           "tools/re/decrypt_jsc.py", "README.md"]
EXCLUDE_PREFIX = ["tools/battlesim/test/"]


def leaks(names: list[str]) -> list[str]:
    """Zip member names that must never ship (game data, keys, dev state)."""
    bad_suffix = ("key.txt", ".env", ".jsc", ".apk", "settings.json", "token.txt")
    bad_part = ("tools/re/decrypted", "/.env", "/build/", "/tests/", "__pycache__")
    bad = []
    for n in names:
        p = "/" + n.replace("\\", "/")
        low = p.lower()
        game_data = "/data/config/" in p and not p.endswith(("/manifest.json", "/config/"))
        if game_data or low.endswith(bad_suffix) or any(s in p for s in bad_part):
            bad.append(n)
    return bad


def collect_app_files(repo: Path = REPO) -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-z", *INCLUDE], cwd=repo, capture_output=True,
                         check=True).stdout.decode("utf-8").split("\0")
    return sorted(Path(f) for f in out if f and not f.startswith(tuple(EXCLUDE_PREFIX))
                  and (repo / f).is_file())


def _download(url: str, dst: Path) -> Path:
    if not dst.exists():
        print(f"  downloading {url}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_suffix(".part")
        with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f, 1 << 20)
        tmp.replace(dst)
    return dst


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_runtime(stage: Path, cache: Path) -> dict:
    py_dir = stage / "runtime" / "python"
    with zipfile.ZipFile(_download(PY_URL, cache / Path(PY_URL).name)) as z:
        z.extractall(py_dir)
    tag = "python%d%d" % sys.version_info[:2]
    (py_dir / f"{tag}._pth").write_text(
        f"{tag}.zip\n.\nLib\\site-packages\n..\\..\\app\nimport site\n", encoding="utf-8")
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                    "--target", str(py_dir / "Lib" / "site-packages"), "--only-binary=:all:",
                    "--platform", "win_amd64", "--python-version", "%d.%d" % sys.version_info[:2],
                    *PIP_DEPS], check=True)

    sums = _download(f"{NODE_BASE}/SHASUMS256.txt", cache / f"node-{NODE_VERSION}-SHASUMS256.txt")
    nz = _download(f"{NODE_BASE}/{NODE_ZIP}", cache / NODE_ZIP)
    want = next(line.split()[0] for line in sums.read_text().splitlines()
                if line.endswith(" " + NODE_ZIP))
    if _sha256(nz) != want:
        nz.unlink()
        raise SystemExit("node zip sha256 mismatch — deleted, re-run")
    node_dir = stage / "runtime" / "node"
    node_dir.mkdir(parents=True)
    with zipfile.ZipFile(nz) as z:
        member = f"node-v{NODE_VERSION}-win-x64/node.exe"
        with z.open(member) as src, open(node_dir / "node.exe", "wb") as dst:
            shutil.copyfileobj(src, dst, 1 << 20)
    versions = {"python": PY_VERSION, "node": NODE_VERSION}
    (stage / "runtime" / "versions.json").write_text(json.dumps(versions), encoding="utf-8")
    return versions


def build_launcher(stage: Path, work: Path) -> bool:
    try:
        import PyInstaller.__main__ as pyi
    except ImportError:
        print("  PyInstaller not installed — shipping NTA-Agent.bat only")
        return False
    pyi.run([str(REPO / "packaging" / "launcher.py"), "--onefile", "--noconsole",
             "--name", "NTA-Agent", "--distpath", str(work / "exe"),
             "--workpath", str(work / "pyi"), "--specpath", str(work), "--log-level", "WARN"])
    shutil.copy2(work / "exe" / "NTA-Agent.exe", stage / "NTA-Agent.exe")
    return True


def _zip_dir(src: Path, dst: Path, prefix: str = "", only: list[str] | None = None) -> None:
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(src.rglob("*")):
            rel = p.relative_to(src).as_posix()
            if only and not any(rel == o or rel.startswith(o + "/") for o in only):
                continue
            if p.is_file():
                z.write(p, prefix + rel)


def build(version: str, out: Path, cache: Path, notes: str = "") -> dict:
    from nta_agent.version import GAME_VERSION
    work = REPO / "build" / "pkgwork"
    shutil.rmtree(work, ignore_errors=True)
    stage = work / "NTA-Agent"
    app = stage / "app"
    for rel in collect_app_files():
        (app / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / rel, app / rel)
    shutil.copy2(REPO / "README.md", stage / "README.md")
    shutil.copy2(REPO / "packaging" / "NTA-Agent.bat", stage / "NTA-Agent.bat")
    (stage / "VERSION").write_text(version, encoding="utf-8")
    runtime = build_runtime(stage, cache)
    build_launcher(stage, work)

    out.mkdir(parents=True, exist_ok=True)
    full = out / f"NTA-Agent-{version}-full.zip"
    appz = out / f"NTA-Agent-{version}-app.zip"
    _zip_dir(stage, full, prefix="NTA-Agent/")
    _zip_dir(stage, appz, only=["app", "VERSION"])
    for z in (full, appz):
        with zipfile.ZipFile(z) as zf:
            bad = leaks([n for n in zf.namelist() if "/runtime/" not in "/" + n])
        if bad:
            z.unlink()
            raise SystemExit(f"LEAK in {z.name}: {bad[:10]}")
    manifest = {"version": version, "game_version": GAME_VERSION, "runtime": runtime,
                "notes": notes,
                "assets": {"full": {"name": full.name, "sha256": _sha256(full),
                                    "size": full.stat().st_size},
                           "app": {"name": appz.name, "sha256": _sha256(appz),
                                   "size": appz.stat().st_size}}}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--notes", default="")
    ap.add_argument("--out", default=str(REPO / "dist"))
    ap.add_argument("--cache", default=str(REPO / "build" / "pkgcache"))
    a = ap.parse_args(argv)
    m = build(a.version, Path(a.out), Path(a.cache), a.notes)
    for k, v in m["assets"].items():
        print(f"[+] {k:4} {v['name']}  {v['size'] / 1e6:.1f} MB  sha256={v['sha256'][:12]}…")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(REPO))
    raise SystemExit(main())
