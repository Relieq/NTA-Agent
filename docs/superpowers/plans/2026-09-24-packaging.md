# Portable App Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship NTA-Agent as a Windows portable zip (embedded Python + Node + code) with a first-run
Setup page, encrypted user settings, and a GitHub-Releases updater.

**Architecture:** One path authority (`nta_agent/paths.py`) separates the replaceable app folder
from the per-user data dir; `nta_agent/settings.py` stores DPAPI-encrypted secrets with env/.env
precedence; `nta_agent/setup/` runs self-checking first-run steps (ADB, root, game, game-data
extraction, distinct id, token); `nta_agent/updater.py` swaps the `app\` folder with backup/rollback;
`tools/package.py` builds the zips + manifest. Dev behaviour (repo, `.env`, `build\`) is unchanged.

**Tech Stack:** Python 3.12 (stdlib + ctypes DPAPI), embedded CPython 3.12 amd64, Node portable,
existing stdlib HTTP dashboard + Vue 3 no-build components, pytest, ruff, PyInstaller (launcher only).

**Spec:** `docs/superpowers/specs/2026-09-24-packaging-design.md`

## Global Constraints

- Windows only. Python 3.12. Node >= 18 in the bundle.
- Release zips contain NO game data (`nta_agent/data/config/*.json` except `manifest.json`,
  `tools/re/decrypted`), NO `KEY.txt`, NO `.env`, NO `build/`, NO `tests/`.
- Secrets (`openai_api_key`, `xxtea_key`) never in the app folder, logs, events or API responses
  (masked `sk-…a1b2`). Dashboard binds 127.0.0.1 only.
- Precedence: real env / `.env` > `settings.json` > default.
- Dev mode (running from the repo) keeps today's paths: `build/run`, `build/nta_token.txt`,
  `nta_agent/data/config`, `tools/re/decrypted/index.js`, `node` on PATH.
- User data dir when packaged: `%LOCALAPPDATA%\NTA-Agent` (override `NTA_DATA_DIR`).
- Updates: GitHub `Relieq/NTA-Agent` releases over HTTPS, sha256-verified; keep 2 backups.
- `SUPPORTED_GAME_VERSION` = `nta_agent.version.GAME_VERSION`.
- Commit messages end with the session's attribution lines; branch per task, merge to master.

---

## File structure

| File | Responsibility |
|---|---|
| `nta_agent/paths.py` (new) | Every filesystem location; dev vs packaged |
| `nta_agent/settings.py` (new) | settings.json load/save, env precedence, DPAPI secrets, masking |
| `nta_agent/gamedata.py` (new) | APK → config tables + decrypted engine (moved from tools/re) |
| `nta_agent/setup/__init__.py`, `nta_agent/setup/steps.py` (new) | First-run steps + status |
| `nta_agent/updater.py` (new) | semver, GitHub check, download/verify, swap/backup/rollback |
| `nta_agent/app.py` (new) | Launcher entry: start dashboard detached or open browser |
| `packaging/launcher.py`, `packaging/NTA-Agent.bat` (new) | exe stub + bat fallback |
| `tools/package.py` (new) | Build dist zips + manifest |
| `README.md` (rewrite user section) | Human setup steps + troubleshooting |
| Modified: `data/config.py`, `dashboard/names.py`, `runtime/config.py`, `config.py` (adb), `execution/predictors/sim_bridge.py`, `brain/llm.py`, `dashboard/server.py`, `dashboard/supervisor.py`, `dashboard/__main__.py`, `tools/launch_detached.py`, `tools/re/extract_config.py`, `tools/re/decrypt_jsc.py`, dashboard components |

---

### Task 1: Path authority (`paths.py`)

**Files:** Create `nta_agent/paths.py`; Test `tests/test_paths.py`

**Interfaces — Produces:** `app_dir() -> Path`, `root_dir() -> Path`, `is_packaged() -> bool`,
`data_dir() -> Path`, `run_dir()`, `token_path()`, `config_dir()`, `engine_js()`, `settings_path()`,
`backups_dir()`, `gamedata_dir()`, `node_exe() -> str`, `app_version() -> str`.

- [ ] **Step 1: failing tests**

```python
# tests/test_paths.py
from pathlib import Path

from nta_agent import paths


def test_dev_mode_keeps_todays_locations(monkeypatch):
    monkeypatch.delenv("NTA_DATA_DIR", raising=False)
    monkeypatch.setattr(paths, "is_packaged", lambda: False)
    app = paths.app_dir()
    assert (app / "nta_agent").is_dir()                       # repo root in dev
    assert paths.run_dir() == app / "build" / "run"
    assert paths.token_path() == app / "build" / "nta_token.txt"
    assert paths.config_dir() == app / "nta_agent" / "data" / "config"
    assert paths.engine_js() == app / "tools" / "re" / "decrypted" / "index.js"
    assert paths.node_exe() == "node"
    assert paths.app_version() == "dev"


def test_packaged_mode_uses_localappdata(monkeypatch, tmp_path):
    monkeypatch.delenv("NTA_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(paths, "is_packaged", lambda: True)
    d = tmp_path / "NTA-Agent"
    assert paths.data_dir() == d
    assert paths.run_dir() == d / "run"
    assert paths.token_path() == d / "token.txt"
    assert paths.config_dir() == d / "gamedata" / "config"
    assert paths.engine_js() == d / "gamedata" / "engine" / "index.js"
    assert paths.settings_path() == d / "settings.json"
    assert paths.node_exe().endswith(str(Path("runtime") / "node" / "node.exe"))


def test_env_override_and_detection(monkeypatch, tmp_path):
    monkeypatch.setenv("NTA_DATA_DIR", str(tmp_path / "x"))
    assert paths.data_dir() == tmp_path / "x"
    root = tmp_path / "pkg"
    (root / "runtime").mkdir(parents=True)
    (root / "VERSION").write_text("0.1.0", encoding="utf-8")
    assert paths.is_packaged(root) is True
    assert paths.is_packaged(tmp_path) is False
```

- [ ] **Step 2:** `.venv/Scripts/python.exe -m pytest tests/test_paths.py -q` → FAIL (no module).

- [ ] **Step 3: implement**

```python
# nta_agent/paths.py
"""Single authority for every filesystem location (dev repo vs packaged app).

Packaged layout (spec 2026-09-24-packaging-design.md §2):
    <root>\\VERSION, <root>\\runtime\\{python,node}, <root>\\app\\nta_agent  (replaced by updates)
    %LOCALAPPDATA%\\NTA-Agent\\...                                         (user data, kept)
Dev (running from the repo): today's paths under the repo (build/, nta_agent/data/config, ...).
"""
from __future__ import annotations

import os
from pathlib import Path

_APP = Path(__file__).resolve().parents[1]          # repo root (dev) or <root>\app (packaged)


def app_dir() -> Path:
    return _APP


def root_dir() -> Path:
    return _APP.parent


def is_packaged(root: Path | None = None) -> bool:
    r = root if root is not None else root_dir()
    return (r / "runtime").is_dir() and (r / "VERSION").is_file()


def data_dir() -> Path:
    env = os.environ.get("NTA_DATA_DIR")
    if env:
        return Path(env)
    if is_packaged():
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "NTA-Agent"
    return _APP / "build"


def run_dir() -> Path:
    return data_dir() / "run"


def token_path() -> Path:
    return data_dir() / ("token.txt" if is_packaged() else "nta_token.txt")


def gamedata_dir() -> Path:
    return data_dir() / "gamedata"


def config_dir() -> Path:
    return gamedata_dir() / "config" if is_packaged() else _APP / "nta_agent" / "data" / "config"


def engine_js() -> Path:
    if is_packaged():
        return gamedata_dir() / "engine" / "index.js"
    return _APP / "tools" / "re" / "decrypted" / "index.js"


def settings_path() -> Path:
    return data_dir() / "settings.json"


def backups_dir() -> Path:
    return data_dir() / "backups"


def node_exe() -> str:
    return str(root_dir() / "runtime" / "node" / "node.exe") if is_packaged() else "node"


def app_version() -> str:
    try:
        return (root_dir() / "VERSION").read_text(encoding="utf-8").strip() if is_packaged() else "dev"
    except OSError:
        return "dev"
```

Note: `token_path()` in dev must equal `build/nta_token.txt` (data_dir()=`<repo>/build`). ✓

- [ ] **Step 4:** run tests → PASS; `ruff check nta_agent tests`.
- [ ] **Step 5:** commit `feat(paths): single path authority for dev vs packaged app`.

---

### Task 2: Wire paths into existing code (dev unchanged)

**Files:** Modify `nta_agent/data/config.py:18`, `nta_agent/dashboard/names.py:8`,
`nta_agent/runtime/config.py:18,21,127,130`, `nta_agent/execution/predictors/sim_bridge.py:16-19,151-156`,
`nta_agent/dashboard/supervisor.py:73`, `tools/launch_detached.py:30,40`; Test `tests/test_paths_wiring.py`

**Interfaces — Consumes:** Task 1 getters. **Produces:** `get_bridge()` spawns `paths.node_exe()`
with env `NTA_ENGINE_JS`/`NTA_CONFIG_DIR`; `RuntimeConfig` defaults = `paths.token_path()`/`paths.run_dir()`.

- [ ] **Step 1: failing tests**

```python
# tests/test_paths_wiring.py
from nta_agent import paths


def test_runtime_config_defaults_follow_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("NTA_DATA_DIR", str(tmp_path))
    from nta_agent.runtime.config import RuntimeConfig
    cfg = RuntimeConfig.from_env({"NTA_DISTINCT_ID": "x"})
    assert cfg.log_dir == paths.run_dir()
    assert cfg.token_path == paths.token_path()


def test_game_config_dir_follows_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "config_dir", lambda: tmp_path)
    from nta_agent.data.config import GameConfig
    assert GameConfig().config_dir == tmp_path


def test_bridge_env_points_sidecar_at_paths(monkeypatch, tmp_path):
    from nta_agent.execution.predictors import sim_bridge
    monkeypatch.setattr(sim_bridge, "_bridge", None)
    monkeypatch.setattr(paths, "engine_js", lambda: tmp_path / "e.js")
    monkeypatch.setattr(paths, "config_dir", lambda: tmp_path / "cfg")
    b = sim_bridge.get_bridge()
    assert b.env["NTA_ENGINE_JS"] == str(tmp_path / "e.js")
    assert b.env["NTA_CONFIG_DIR"] == str(tmp_path / "cfg")
    assert b.node == paths.node_exe()
    monkeypatch.setattr(sim_bridge, "_bridge", None)
```

- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: implement**
  - `data/config.py`: replace `_CONFIG_DIR = Path(__file__).with_name("config")` by a lazy default:
    `config_dir: Path = field(default_factory=lambda: _paths.config_dir())` in `GameConfig`, and in
    `load()` use `Path(config_dir) if config_dir else _paths.config_dir()` (import `from nta_agent import paths as _paths`).
    Keep `_CONFIG_DIR` name as `_paths.config_dir()` call sites only (grep `_CONFIG_DIR` and replace).
  - `dashboard/names.py`: `_DEFAULT_CONFIG` → `Path(config_dir or paths.config_dir())`.
  - `runtime/config.py`: `token_path: Path = field(default_factory=paths.token_path)`,
    `log_dir: Path = field(default_factory=paths.run_dir)`; in `from_env` use
    `Path(env["NTA_TOKEN_PATH"]) if env.get("NTA_TOKEN_PATH") else paths.token_path()` and the same for
    `NTA_LOG_DIR`/`paths.run_dir()`.
  - `sim_bridge.py`: `_DEFAULT_SERVER = paths.app_dir() / "tools" / "battlesim" / "server.js"`;
    `get_bridge()` builds `env = {**os.environ, "NTA_ENGINE_JS": str(paths.engine_js()), "NTA_CONFIG_DIR": str(paths.config_dir())}`
    and `SimBridge(node=paths.node_exe(), env=env)`.
  - `supervisor.py:73`: `subprocess.Popen([sys.executable, "-m", "nta_agent"], cwd=str(paths.app_dir()))`.
  - `tools/launch_detached.py`: `_REPO = str(paths.app_dir())`.
- [ ] **Step 4:** full suite `pytest -q` (all 744+ must pass — dev paths unchanged) + ruff.
- [ ] **Step 5:** commit `refactor(paths): route config/run/token/sim paths through nta_agent.paths`.

---

### Task 3: Settings store with DPAPI secrets (`settings.py`)

**Files:** Create `nta_agent/settings.py`; Test `tests/test_settings.py`

**Interfaces — Produces:** `get(key, default=None) -> str|None`, `set_values(dict) -> None`,
`view() -> dict` (masked), `KEYS`, `SECRETS`, `mask(str) -> str`.

- [ ] **Step 1: failing tests**

```python
# tests/test_settings.py
import json

import pytest

from nta_agent import settings


@pytest.fixture
def store(monkeypatch, tmp_path):
    p = tmp_path / "settings.json"
    monkeypatch.setattr(settings, "_path", lambda: p)
    for env in settings.KEYS.values():
        monkeypatch.delenv(env, raising=False)
    return p


def test_env_wins_over_file(store, monkeypatch):
    settings.set_values({"openai_model": "gpt-x"})
    assert settings.get("openai_model") == "gpt-x"
    monkeypatch.setenv("OPENAI_MODEL", "gpt-env")
    assert settings.get("openai_model") == "gpt-env"


def test_secret_is_encrypted_on_disk_and_masked_in_view(store):
    settings.set_values({"openai_api_key": "sk-test-1234567890abcd"})
    raw = store.read_text(encoding="utf-8")
    assert "sk-test-1234567890abcd" not in raw                 # never plaintext on disk
    assert settings.get("openai_api_key") == "sk-test-1234567890abcd"
    v = settings.view()
    assert v["openai_api_key"] == {"set": True, "value": "sk-…abcd"}
    assert v["openai_model"] == {"set": False, "value": ""}


def test_blank_clears_and_unknown_rejected(store):
    settings.set_values({"openai_api_key": "sk-abc12345"})
    settings.set_values({"openai_api_key": ""})
    assert settings.get("openai_api_key") is None
    with pytest.raises(KeyError):
        settings.set_values({"evil": "x"})


def test_corrupt_file_is_empty(store):
    store.write_text("{not json", encoding="utf-8")
    assert settings.get("distinct_id") is None
```

- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: implement**

```python
# nta_agent/settings.py
"""User settings (%LOCALAPPDATA%\\NTA-Agent\\settings.json in the packaged app).

Precedence: real env / .env  >  settings.json  >  default. Secrets are stored with Windows
DPAPI (user scope) so the file is useless on another machine/user; never logged or returned
unmasked (spec §4)."""
from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

from nta_agent import paths

KEYS = {  # setting -> env var that overrides it
    "openai_api_key": "OPENAI_API_KEY", "openai_model": "OPENAI_MODEL",
    "brain_max_calls": "NTA_BRAIN_MAX_CALLS", "distinct_id": "NTA_DISTINCT_ID",
    "adb_path": "NTA_ADB_PATH", "adb_serial": "NTA_ADB_SERIAL",
    "xxtea_key": "NTA_XXTEA_KEY", "dashboard_port": "NTA_DASHBOARD_PORT",
}
SECRETS = {"openai_api_key", "xxtea_key"}


def _path() -> Path:
    return paths.settings_path()


def _dpapi(data: bytes, protect: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
    buf = ctypes.create_string_buffer(data, len(data))
    inp, out = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), BLOB()
    fn = (ctypes.windll.crypt32.CryptProtectData if protect
          else ctypes.windll.crypt32.CryptUnprotectData)
    if not fn(ctypes.byref(inp), None, None, None, None, 0, ctypes.byref(out)):
        raise OSError("DPAPI failed")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def _enc(v: str) -> dict:
    if sys.platform == "win32":
        return {"dpapi": base64.b64encode(_dpapi(v.encode("utf-8"), True)).decode()}
    return {"plain": v}  # non-Windows = tests/CI only


def _dec(v) -> str | None:
    if isinstance(v, dict):
        if "dpapi" in v:
            try:
                return _dpapi(base64.b64decode(v["dpapi"]), False).decode("utf-8")
            except (OSError, ValueError):
                return None  # copied from another machine/user
        return v.get("plain")
    return v


def _load() -> dict:
    try:
        d = json.loads(_path().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def get(key: str, default=None):
    env = os.environ.get(KEYS.get(key, ""), "")
    if env:
        return env
    v = _dec(_load().get(key))
    return v if v not in (None, "") else default


def set_values(values: dict) -> None:
    d = _load()
    for k, v in values.items():
        if k not in KEYS:
            raise KeyError(k)
        v = "" if v is None else str(v).strip()
        if not v:
            d.pop(k, None)
        else:
            d[k] = _enc(v) if k in SECRETS else v
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def mask(v: str) -> str:
    return f"{v[:3]}…{v[-4:]}" if len(v) > 8 else "…"


def view() -> dict:
    out = {}
    for k in KEYS:
        v = get(k)
        out[k] = {"set": bool(v), "value": (mask(v) if k in SECRETS else v) if v else ""}
    return out
```

- [ ] **Step 4:** tests PASS (Windows: real DPAPI round-trip) + ruff.
- [ ] **Step 5:** commit `feat(settings): per-user settings with DPAPI-encrypted secrets`.

---

### Task 4: Consume settings (brain key, distinct id, ADB, XXTEA key)

**Files:** Modify `nta_agent/brain/llm.py:149-153`, `nta_agent/runtime/config.py` (`from_env`),
`nta_agent/config.py:32-40,69-76`, `nta_agent/dashboard/__main__.py`; Test `tests/test_settings_wiring.py`

**Interfaces — Consumes:** `settings.get`. **Produces:** `RuntimeConfig.from_env(env=None, require_distinct=True)`.

- [ ] **Step 1: failing tests**

```python
# tests/test_settings_wiring.py
import pytest

from nta_agent import settings


@pytest.fixture(autouse=True)
def iso(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "_path", lambda: tmp_path / "s.json")
    for env in settings.KEYS.values():
        monkeypatch.delenv(env, raising=False)


def test_brain_reads_key_from_settings_each_call():
    from nta_agent.brain import llm
    with pytest.raises(llm.BrainUnavailable):
        llm.default_chat()
    settings.set_values({"openai_api_key": "sk-abc12345"})
    assert callable(llm.default_chat())          # no restart needed


def test_distinct_id_from_settings_and_optional_for_dashboard():
    from nta_agent.runtime.config import ConfigError, RuntimeConfig
    with pytest.raises(ConfigError):
        RuntimeConfig.from_env({})
    assert RuntimeConfig.from_env({}, require_distinct=False).distinct_id == ""
    settings.set_values({"distinct_id": "abc"})
    assert RuntimeConfig.from_env({}).distinct_id == "abc"


def test_adb_settings_used():
    from nta_agent import config
    settings.set_values({"adb_path": r"X:\adb.exe", "adb_serial": "emulator-5556"})
    s = config.Settings.detect()
    assert s.adb_path == r"X:\adb.exe" and s.serial == "emulator-5556"
```

- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: implement**
  - `llm.default_chat`: `key = settings.get("openai_api_key")`, `model = settings.get("openai_model", "gpt-4o-mini")`.
  - `RuntimeConfig.from_env(cls, env=None, require_distinct=True)`: `distinct = (env.get("NTA_DISTINCT_ID","") or (settings.get("distinct_id") or "") if env is os.environ or env == {} ... )`
    — concretely: `distinct = env.get("NTA_DISTINCT_ID", "").strip() or (settings.get("distinct_id") or "").strip()`;
    `if not distinct and require_distinct: raise ConfigError(...)`; brain max calls:
    `int(env.get("NTA_BRAIN_MAX_CALLS") or settings.get("brain_max_calls") or 50)`.
  - `config._find_adb`: first `settings.get("adb_path")`; `Settings.detect`: serial = `settings.get("adb_serial")` before `_detect_adb_port`.
  - `dashboard/__main__.py`: `RuntimeConfig.from_env(require_distinct=False)`; port default
    `int(settings.get("dashboard_port") or 8787)`.
- [ ] **Step 4:** full suite + ruff (existing tests setting env vars still pass: env wins).
- [ ] **Step 5:** commit `feat(settings): brain key, distinct id, ADB read from user settings`.

---

### Task 5: Game-data extraction into the package (`gamedata.py`)

**Files:** Create `nta_agent/gamedata.py`; Modify `tools/re/extract_config.py`, `tools/re/decrypt_jsc.py`
to delegate; Test `tests/test_gamedata.py`

**Interfaces — Produces:** `extract_config_tables(apk: Path, out_dir: Path) -> int` (tables written),
`find_engine_entry(names: list[str]) -> str|None`, `decrypt_engine(apk: Path, out_js: Path, key: bytes) -> None`,
`xxtea_decrypt(data: bytes, key: bytes) -> bytes`, `maybe_decompress(b) -> bytes`.

- [ ] **Step 1:** read `tools/re/extract_config.py` + `tools/re/decrypt_jsc.py` fully; move
  `decode_uuid`, `unwrap_jsonasset`, the table loop (from `main`) into `extract_config_tables`, and
  `_to_uint32_list`, `_to_bytes`, `xxtea_decrypt`, `maybe_decompress` into `gamedata.py` verbatim.
- [ ] **Step 2: failing tests**

```python
# tests/test_gamedata.py
import zipfile

from nta_agent import gamedata


def test_find_engine_entry_prefers_main_index_jsc():
    names = ["assets/src/assets/app/proto/msg.jsc", "assets/assets/main/index.jsc",
             "assets/assets/resources/index.jsc"]
    assert gamedata.find_engine_entry(names) == "assets/assets/main/index.jsc"
    assert gamedata.find_engine_entry(["x.png"]) is None


def test_xxtea_roundtrip_via_encrypt_helper():
    key = b"0123456789abcdef"
    plain = b"hello engine" * 10
    enc = gamedata.xxtea_encrypt(plain, key)        # test helper exposed for round-trip
    assert gamedata.maybe_decompress(gamedata.xxtea_decrypt(enc, key)) == plain


def test_decrypt_engine_writes_js(tmp_path):
    key = b"0123456789abcdef"
    apk = tmp_path / "base.apk"
    with zipfile.ZipFile(apk, "w") as z:
        z.writestr("assets/assets/main/index.jsc", gamedata.xxtea_encrypt(b"var x=1;", key))
    out = tmp_path / "engine" / "index.js"
    gamedata.decrypt_engine(apk, out, key)
    assert out.read_bytes() == b"var x=1;"
```

  (Add a small `xxtea_encrypt` — the inverse of `xxtea_decrypt`, standard XXTEA encrypt with length
  word — used only for tests.)
- [ ] **Step 3:** implement; `decrypt_engine` writes to `out_js.with_suffix(".tmp")` then replaces.
  `extract_config_tables` writes into a temp dir then renames onto `out_dir` (atomic swap).
  `tools/re/*.py` `main()` now call these (keep CLI flags).
- [ ] **Step 4:** tests + ruff. **Live check (manual, agent stopped):** pull `base.apk` via
  `adb shell pm path twgame.global.acers`, run `extract_config_tables` into a temp dir and diff table
  names/count against `nta_agent/data/config` (expect equal); `decrypt_engine` with `KEY.txt` → size
  ≈ current `tools/re/decrypted/index.js` and same first 200 bytes. Record the real engine entry path.
- [ ] **Step 5:** commit `refactor(gamedata): APK extraction/decryption as importable package code`.

---

### Task 6: First-run setup steps (`nta_agent/setup/`)

**Files:** Create `nta_agent/setup/__init__.py`, `nta_agent/setup/steps.py`; Test `tests/test_setup_steps.py`

**Interfaces — Consumes:** `settings`, `paths`, `gamedata`, `DeviceManager`, `bootstrap.read_account_token`,
`version.GAME_VERSION`. **Produces:** `STEPS: list[str]`, `run_step(name, dm_factory=None) -> dict`
(`{ok, detail, hint, doc}`), `status() -> dict` (`{steps: [{name, ok, detail, hint, doc}], ready: bool}`
from a cached `setup_status.json` in `run_dir()`), `ready() -> bool`.

Steps (names): `adb`, `device`, `root`, `game`, `gamedata`, `distinct_id`, `token`.

- [ ] **Step 1: failing tests** (fake device object with `shell`, `su`, `pull`)

```python
# tests/test_setup_steps.py
import pytest

from nta_agent import paths, settings
from nta_agent.setup import steps


class FakeDM:
    def __init__(self, version="4.4.4", root=True, token="tok", rid="rid-1"):
        self.version, self.root, self.token, self.rid = version, root, token, rid
        self.serial = "emulator-5554"
    def shell(self, cmd, timeout=30):
        if "dumpsys package" in cmd:
            return f"    versionName={self.version}\n"
        if "pm path" in cmd:
            return "package:/data/app/x/base.apk\n"
        return ""
    def su(self, cmd, timeout=30):
        if "id" == cmd.strip():
            return "uid=0(root)" if self.root else "uid=2000(shell)"
        if "thinkingdata" in cmd:
            return f'<string name="randomID">{self.rid}</string>'
        return ""


@pytest.fixture(autouse=True)
def iso(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "_path", lambda: tmp_path / "s.json")
    monkeypatch.setenv("NTA_DATA_DIR", str(tmp_path))
    for env in settings.KEYS.values():
        monkeypatch.delenv(env, raising=False)


def test_root_and_game_version_steps():
    assert steps.run_step("root", dm_factory=lambda: FakeDM())["ok"] is True
    r = steps.run_step("root", dm_factory=lambda: FakeDM(root=False))
    assert r["ok"] is False and "Root" in r["hint"] and r["doc"].startswith("README.md#")
    assert steps.run_step("game", dm_factory=lambda: FakeDM())["ok"] is True
    bad = steps.run_step("game", dm_factory=lambda: FakeDM(version="4.5.0"))
    assert bad["ok"] is False and "4.5.0" in bad["detail"]


def test_distinct_id_saved_to_settings():
    assert steps.run_step("distinct_id", dm_factory=lambda: FakeDM(rid="abc-123"))["ok"] is True
    assert settings.get("distinct_id") == "abc-123"


def test_token_step_writes_token(monkeypatch):
    monkeypatch.setattr(steps, "read_account_token", lambda dm: "TOKEN123")
    assert steps.run_step("token", dm_factory=lambda: FakeDM())["ok"] is True
    assert paths.token_path().read_text(encoding="utf-8") == "TOKEN123"
    monkeypatch.setattr(steps, "read_account_token", lambda dm: "")
    r = steps.run_step("token", dm_factory=lambda: FakeDM())
    assert r["ok"] is False and "Google" in r["hint"]


def test_status_ready_only_when_all_required_ok(monkeypatch):
    for n in steps.STEPS:
        monkeypatch.setitem(steps._RUNNERS, n, lambda dm: {"ok": True, "detail": ""})
    for n in steps.STEPS:
        steps.run_step(n, dm_factory=lambda: FakeDM())
    assert steps.status()["ready"] is True
    monkeypatch.setitem(steps._RUNNERS, "token", lambda dm: {"ok": False, "detail": "x"})
    steps.run_step("token", dm_factory=lambda: FakeDM())
    assert steps.status()["ready"] is False
```

- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: implement** `steps.py`:
  - `_RUNNERS = {"adb": _adb, "device": _device, "root": _root, "game": _game, "gamedata": _gamedata, "distinct_id": _distinct, "token": _token}`; `STEPS = list(_RUNNERS)`.
  - `_HINTS[name]` Vietnamese fix text + `doc` anchors `README.md#buoc-1-adb` … `#buoc-7-token`.
  - `_adb(dm)`: `config._find_adb()` exists → save `adb_path`; `_device(dm)`: `dm.serial` non-empty → save `adb_serial`;
    `_root(dm)`: `"uid=0" in dm.su("id")`; `_game(dm)`: parse `versionName=(\S+)` from `dumpsys package twgame.global.acers`, ok iff `== GAME_VERSION` (detail includes found version);
    `_gamedata(dm)`: skip (ok) when `gamedata/meta.json.game_version == installed version` and config dir has `buildBase.json`; else `pm path` → `dm.pull(remote, tmp/base.apk)` → `gamedata.extract_config_tables(apk, paths.config_dir())` → if `settings.get("xxtea_key")`: `decrypt_engine(apk, paths.engine_js(), key.encode())` → write meta → delete apk; ok iff tables > 0 (engine optional, detail says whether battle sim is on);
    `_distinct(dm)`: `dm.su("cat /data/data/twgame.global.acers/shared_prefs/com.thinkingdata.analyse.xml")`, regex `name="randomID">([^<]+)<` → `settings.set_values({"distinct_id": v})`;
    `_token(dm)`: `read_account_token(dm)` → write `paths.token_path()`.
  - `run_step(name, dm_factory=None)`: `dm_factory` defaults to `lambda: DeviceManager.connect()`; any exception → `{ok: False, detail: str(e)}`; merge hint/doc; persist into `run_dir()/setup_status.json` `{name: result}`.
  - `status()`: read that file, fill missing steps as not-run; `ready = all(ok)`.
  - `ready()`: `status()["ready"]` in packaged mode; **always True in dev** (don't gate your own workflow).
- [ ] **Step 4:** tests + ruff.
- [ ] **Step 5:** commit `feat(setup): self-checking first-run steps (adb/root/game/gamedata/id/token)`.

---

### Task 7: Dashboard — Setup + Settings pages, Start gate

**Files:** Modify `nta_agent/dashboard/server.py` (routes), `nta_agent/dashboard/supervisor.py` (`start`),
`static/components/App.js`, `Sidebar` tabs; Create `static/components/SetupPanel.js`,
`static/components/SettingsPanel.js`; Test `tests/test_dashboard_setup_settings.py`

**Interfaces — Consumes:** `setup.steps.status/run_step/ready`, `settings.view/set_values/get`.
**Produces:** `GET /api/setup`, `POST /api/setup/run {step}`, `GET /api/settings`,
`POST /api/settings {key: value}`, `POST /api/settings/test-key`, `/api/agent/start` → 409 `{error}` when not ready.

- [ ] **Step 1: failing tests** (call pure helpers, like existing dashboard tests)

```python
# tests/test_dashboard_setup_settings.py
from nta_agent import settings
from nta_agent.dashboard import server


def test_settings_view_masks_and_update(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "_path", lambda: tmp_path / "s.json")
    for env in settings.KEYS.values():
        monkeypatch.delenv(env, raising=False)
    r = server.update_settings({"openai_api_key": "sk-abcdefgh1234"})
    assert r["ok"] is True
    v = server.read_settings()
    assert v["openai_api_key"]["value"] == "sk-…1234"
    assert server.update_settings({"nope": 1})["ok"] is False


def test_start_blocked_until_setup_ready(monkeypatch):
    from nta_agent.dashboard.supervisor import AgentSupervisor
    from nta_agent.setup import steps
    monkeypatch.setattr(steps, "ready", lambda: False)
    sup = AgentSupervisor.__new__(AgentSupervisor)
    sup._proc = None
    r = sup.start()
    assert r.get("error") and "Thiết lập" in r["error"]
```

- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: implement**
  - `server.read_settings() -> settings.view()`; `server.update_settings(body)` → `set_values` (KeyError → `{ok: False}`);
    `server.test_openai_key()` → GET `https://api.openai.com/v1/models` with the stored key, 8s timeout → `{ok, error}` (never echo key).
  - Routes in the GET/POST dispatch next to `/api/health`.
  - `supervisor.start()`: first `from nta_agent.setup import steps; if not steps.ready(): return {"error": "Chưa hoàn tất Thiết lập — mở trang Thiết lập."}`.
  - `SetupPanel.js`: table of steps (✓/✗, detail, hint, link `doc`), "Chạy" per step, "Chạy tất cả" (sequential POSTs), banner warning on account-ban risk + single-session.
  - `SettingsPanel.js`: masked fields (OpenAI key, XXTEA key), model, brain max calls, ADB path/serial; "Lưu", "Kiểm tra key"; never pre-fill secrets (placeholder shows mask).
  - `App.js`: new tabs "Thiết lập", "Cài đặt"; on load, if `/api/setup` → `ready:false` (packaged) select "Thiết lập".
- [ ] **Step 4:** tests + full suite + ruff; add component test asserting routes present in JS.
- [ ] **Step 5:** commit `feat(dashboard): setup + settings pages; gate Start on setup`.

---

### Task 8: Updater

**Files:** Create `nta_agent/updater.py`; Modify `dashboard/server.py` (routes), `StatusHeader.js` (banner),
`SettingsPanel.js` (rollback button); Test `tests/test_updater.py`

**Interfaces — Produces:** `parse_version(s) -> tuple`, `newer(a, b) -> bool`,
`check(fetch=None) -> dict|None` (`{version, notes, manifest_url, assets}`),
`plan(manifest, current_runtime) -> str` (`"app"`|`"full"`), `verify(path, sha256) -> bool`,
`apply(zip_path, root, backups, kind) -> Path` (returns backup dir), `rollback(root, backup) -> None`,
`prune(backups, keep=2)`, `main(argv)` (standalone process entry).

- [ ] **Step 1: failing tests**

```python
# tests/test_updater.py
import hashlib
import zipfile

from nta_agent import updater


def test_semver():
    assert updater.newer("0.2.0", "0.1.9") and not updater.newer("0.1.0", "0.1.0")
    assert updater.newer("1.0.0", "dev") is True


def test_verify_sha(tmp_path):
    f = tmp_path / "a.zip"; f.write_bytes(b"abc")
    assert updater.verify(f, hashlib.sha256(b"abc").hexdigest())
    assert not updater.verify(f, "0" * 64)


def _mk(root, ver):
    (root / "app" / "nta_agent").mkdir(parents=True)
    (root / "app" / "nta_agent" / "__init__.py").write_text(ver, encoding="utf-8")
    (root / "VERSION").write_text(ver, encoding="utf-8")


def test_apply_swaps_app_and_rollback_restores(tmp_path):
    root, backups = tmp_path / "NTA-Agent", tmp_path / "backups"
    _mk(root, "0.1.0")
    z = tmp_path / "new.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("app/nta_agent/__init__.py", "0.2.0")
        zf.writestr("VERSION", "0.2.0")
    bk = updater.apply(z, root, backups, "app")
    assert (root / "app" / "nta_agent" / "__init__.py").read_text(encoding="utf-8") == "0.2.0"
    assert (root / "VERSION").read_text(encoding="utf-8") == "0.2.0"
    updater.rollback(root, bk)
    assert (root / "app" / "nta_agent" / "__init__.py").read_text(encoding="utf-8") == "0.1.0"
    assert (root / "VERSION").read_text(encoding="utf-8") == "0.1.0"


def test_plan_full_when_runtime_changes():
    m = {"runtime": {"python": "3.12.10", "node": "20.18.0"}}
    assert updater.plan(m, {"python": "3.12.10", "node": "20.18.0"}) == "app"
    assert updater.plan(m, {"python": "3.12.9", "node": "20.18.0"}) == "full"


def test_check_reads_latest_release():
    rel = {"tag_name": "v0.2.0", "body": "notes",
           "assets": [{"name": "manifest.json", "browser_download_url": "https://x/manifest.json"}]}
    r = updater.check(fetch=lambda url: rel, current="0.1.0")
    assert r["version"] == "0.2.0" and r["manifest_url"] == "https://x/manifest.json"
    assert updater.check(fetch=lambda url: rel, current="0.2.0") is None
```

- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: implement** (`REPO = "Relieq/NTA-Agent"`, API `https://api.github.com/repos/{REPO}/releases/latest`,
  urllib with `User-Agent`, only `https://github.com/`/`objects.githubusercontent.com` URLs accepted):
  - `apply`: extract zip to `root/"app.new"` (+ `runtime.new` when kind=="full"), move `root/"app"` (+ runtime, VERSION)
    into `backups/f"app-{old_version}"`, rename `.new` → live, write VERSION; on any exception before the
    rename → delete `.new`, re-raise (nothing changed).
  - `rollback`: move current `app` aside to a temp name, move backup `app` (+ runtime/VERSION) back, delete temp.
  - `main(argv)`: `--pid <dashboard pid> --manifest-url U --root R --data D`: wait pid exit (30s), download
    manifest → pick asset by `plan` → download to temp → `verify` → `apply` → `prune(keep=2)` → launch
    `root/"NTA-Agent.exe"` (or `.bat`) → poll `http://127.0.0.1:<port>/api/agent/status` 30s → on failure
    `rollback` + relaunch. Log to `run_dir()/updater.log`.
  - Dashboard: `GET /api/update/check` (cache 6h in `run_dir()/update_check.json`), `POST /api/update/apply`
    (stop agent, copy `updater.py` to temp, spawn detached with runtime python, then `os._exit(0)` after
    responding), `POST /api/update/rollback` (same pattern with `--rollback`). Banner in `StatusHeader.js`
    when a newer version exists; disabled in dev (`paths.is_packaged()` False → check returns `{dev: true}`).
- [ ] **Step 4:** tests + ruff.
- [ ] **Step 5:** commit `feat(updater): GitHub-release updater with sha256 check, backup and rollback`.

---

### Task 9: Launcher + packaging script

**Files:** Create `nta_agent/app.py`, `packaging/launcher.py`, `packaging/NTA-Agent.bat`, `tools/package.py`,
`VERSION` (repo root, `0.1.0`); Test `tests/test_app_launcher.py`, `tests/test_package.py`

**Interfaces — Produces:** `app.main()`; `package.collect_app_files(repo) -> list[Path]`,
`package.build(version, out_dir, cache_dir, offline_runtime=None) -> dict` (manifest).

- [ ] **Step 1: failing tests**

```python
# tests/test_package.py
from pathlib import Path

from tools import package  # add tools/__init__.py if missing


def test_collect_excludes_game_data_and_secrets():
    files = {p.as_posix() for p in package.collect_app_files(Path("."))}
    assert "nta_agent/paths.py" in files
    assert "tools/battlesim/server.js" in files
    assert "tools/re/extract_config.py" in files and "tools/re/decrypt_jsc.py" in files
    bad = [f for f in files if f.startswith(("tests/", "build/", "tools/re/decrypted/"))
           or f.endswith(("KEY.txt", ".env"))
           or (f.startswith("nta_agent/data/config/") and not f.endswith("manifest.json"))]
    assert bad == []
```

```python
# tests/test_app_launcher.py
from nta_agent import app


def test_running_dashboard_only_opens_browser(monkeypatch):
    opened, started = [], []
    monkeypatch.setattr(app, "_alive", lambda port: True)
    monkeypatch.setattr(app, "_open", lambda url: opened.append(url))
    monkeypatch.setattr(app, "_start_dashboard", lambda port: started.append(port))
    app.main(port=8787)
    assert opened == ["http://127.0.0.1:8787"] and started == []
```

- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: implement**
  - `app.py`: `_alive(port)` = GET `/api/agent/status` ok; `_start_dashboard(port)` = detached Popen
    `[sys.executable, "-m", "nta_agent.dashboard", "--port", str(port)]` cwd `paths.app_dir()`, pidfile in
    `run_dir()`; pick first free port from `settings.get("dashboard_port") or 8787` upward (save it);
    wait up to 15s for `_alive`; `_open(url)` = `webbrowser.open`.
  - `packaging/launcher.py` (stdlib only): resolve exe dir, `Popen([root/"runtime/python/pythonw.exe", "-m", "nta_agent.app"], cwd=root/"app", creationflags=0x08|0x200)`.
  - `packaging/NTA-Agent.bat`: `@start "" "%~dp0runtime\python\pythonw.exe" -m nta_agent.app` with `cd /d "%~dp0app"`.
  - `tools/package.py`:
    - `PY_VERSION` = the venv's `sys.version_info` (3.12.x), `NODE_VERSION = "20.18.0"`.
    - download (cached in `build/pkgcache`) `https://www.python.org/ftp/python/{v}/python-{v}-embed-amd64.zip`
      and `https://nodejs.org/dist/v{n}/node-v{n}-win-x64.zip`; verify node against `SHASUMS256.txt`.
    - unpack python → `stage/runtime/python`; write `python312._pth`:
      `python312.zip`, `.`, `Lib\site-packages`, `..\..\app`, `import site`.
    - `pip install --target stage/runtime/python/Lib/site-packages paho-mqtt numpy pillow --only-binary=:all:`.
    - copy only `node.exe` → `stage/runtime/node/`.
    - `collect_app_files`: include `nta_agent/**` (exclude `__pycache__`, `data/config/*.json` except
      `manifest.json`), `tools/battlesim/**` (exclude `test/`, `node_modules/`), `tools/re/extract_config.py`,
      `tools/re/decrypt_jsc.py`, `tools/launch_detached.py`, `README.md`, `LICENSE` if present.
    - launcher: `pyinstaller --onefile --noconsole packaging/launcher.py -n NTA-Agent` if PyInstaller is
      importable, else skip (bat only) with a warning.
    - write `VERSION`; zip `full` (stage) and `app` (`app/` + `VERSION`); `manifest.json` with sha256 of
      each zip, `game_version`, `runtime`, `notes` (from `--notes`).
    - leak check: re-open both zips and assert no forbidden member (same rules as the test).
- [ ] **Step 4:** tests + ruff; then run `python tools/package.py --version 0.1.0` for real and inspect
  `dist/` sizes + manifest.
- [ ] **Step 5:** commit `feat(package): portable launcher + dist builder with leak check`.

---

### Task 10: README user guide + end-to-end verification

**Files:** Modify `README.md` (user section first, dev section kept below)

- [ ] **Step 1:** Write Vietnamese user guide with anchors used by the setup steps:
  `#buoc-1-adb`, `#buoc-2-gia-lap`, `#buoc-3-root`, `#buoc-4-game`, `#buoc-5-du-lieu-game`,
  `#buoc-6-distinct-id`, `#buoc-7-token`, plus: install/unzip, SmartScreen, antivirus → `.bat`,
  OpenAI key (optional, cost), XXTEA key (optional, battle sim), single-session rule, account-ban
  warning, update/rollback, where data lives, uninstall (delete folder + `%LOCALAPPDATA%\NTA-Agent`).
- [ ] **Step 2:** test asserting README contains every `doc` anchor referenced by `setup.steps`.
- [ ] **Step 3: E2E (manual, on this machine):** stop agent + dashboard; unzip `dist/NTA-Agent-0.1.0-full.zip`
  to `D:\NTA-test\`; set `NTA_DATA_DIR=D:\NTA-test-data` for the session; run launcher → dashboard opens on
  Setup → run all steps with LDPlayer → enter keys → Start agent → verify ticks/events in the test data dir.
  Then build `0.1.1` locally, publish as a **draft** release, point updater at it (env `NTA_UPDATE_REPO`
  optional override), apply update, verify VERSION, then rollback.
- [ ] **Step 4:** restore normal dev dashboard/agent; commit `docs(readme): user setup guide for the portable app`.
- [ ] **Step 5:** update memory (project status) with packaging done + how to release.
