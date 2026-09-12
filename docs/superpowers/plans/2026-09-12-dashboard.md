# Web Dashboard (Chặng 2B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A dependency-free, read-only local web dashboard (`python -m nta_agent.dashboard`) that reads the 2A seam files and shows live agent status, resources, buildings (Vietnamese names), armies, tasks, and a recent-events feed, auto-refreshing.

**Architecture:** New `nta_agent/dashboard/` package: pure file-reading (`data.py`), config-driven name mapping (`names.py`), a static HTML page (`page.py`), a thin `http.server` layer (`server.py`), and a CLI (`__main__.py`). Separate process from the agent; reads `RuntimeConfig` paths only; binds `127.0.0.1`.

**Tech Stack:** Python 3.12 stdlib only (`http.server`, `json`, `urllib` for tests, `pathlib`), pytest, ruff. Venv at `.venv`.

**Spec:** `docs/superpowers/specs/2026-09-12-dashboard-design.md`

## Global Constraints

- Python 3.12; run via venv: `.venv/Scripts/python.exe -m pytest -q`, `.venv/Scripts/python.exe -m ruff check nta_agent tests`. All new code passes ruff clean.
- **stdlib only** — no Flask/FastAPI/etc. Dashboard is read-only in 2B (no POST/write).
- Reuse `nta_agent.runtime.config.RuntimeConfig` for seam-file paths (`snapshot_path`, `event_log_path`); do not duplicate path logic.
- Building names come from `nta_agent/data/config/buildText.json` (`.vi`, fallback `.en`, fallback `#<id>`); config is gitignored — code must work (unlabeled) when it is absent.
- Server binds `127.0.0.1` only. HTML page uses inline CSS/JS with no external assets.
- Seam-file reads must never raise: missing/corrupt files yield `{"ok": false}` / `[]`.
- Port from `--port` or env `NTA_DASHBOARD_PORT`, default `8787`.

---

### Task 1: Seam-file readers (`data.py`)

**Files:**
- Create: `nta_agent/dashboard/__init__.py`
- Create: `nta_agent/dashboard/data.py`
- Test: `tests/test_dashboard_data.py`

**Interfaces:**
- Produces:
  - `read_state(path: Path) -> dict` — `{"ok": True, **snapshot}` on success; `{"ok": False}` if missing or unparseable (never raises).
  - `tail_events(path: Path, n: int = 50) -> list[dict]` — last `n` parseable JSON lines (oldest→newest); skips blank/corrupt lines; `[]` if missing.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dashboard_data.py
import json
from nta_agent.dashboard.data import read_state, tail_events


def test_read_state_ok(tmp_path):
    p = tmp_path / "state.json"
    p.write_text(json.dumps({"main_city_index": 5, "resources": {"cereal": 9}}))
    d = read_state(p)
    assert d["ok"] is True and d["main_city_index"] == 5 and d["resources"]["cereal"] == 9


def test_read_state_missing(tmp_path):
    assert read_state(tmp_path / "nope.json") == {"ok": False}


def test_read_state_corrupt(tmp_path):
    p = tmp_path / "state.json"
    p.write_text('{"half wri')
    assert read_state(p) == {"ok": False}


def test_tail_events(tmp_path):
    p = tmp_path / "events.jsonl"
    p.write_text('\n'.join(json.dumps({"i": i}) for i in range(5)) + "\n")
    rows = tail_events(p, 2)
    assert [r["i"] for r in rows] == [3, 4]


def test_tail_events_skips_corrupt_and_missing(tmp_path):
    p = tmp_path / "events.jsonl"
    p.write_text('{"i":1}\nnot json\n\n{"i":2}\n')
    assert [r["i"] for r in tail_events(p, 50)] == [1, 2]
    assert tail_events(tmp_path / "none.jsonl") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_data.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

Create `nta_agent/dashboard/__init__.py` with a one-line docstring. Then `nta_agent/dashboard/data.py`:

```python
"""Pure readers for the operational-spine seam files (state.json, events.jsonl)."""
from __future__ import annotations

import json
from pathlib import Path


def read_state(path: Path) -> dict:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return {"ok": False}
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return {"ok": False}
    if not isinstance(data, dict):
        return {"ok": False}
    return {"ok": True, **data}


def tail_events(path: Path, n: int = 50) -> list[dict]:
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict] = []
    for line in lines[-n:] if n > 0 else []:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out
```

Note: reading the last `n` from `lines[-n:]` keeps at most `n` candidates; corrupt lines are dropped, so the result may be fewer than `n`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_data.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add nta_agent/dashboard/__init__.py nta_agent/dashboard/data.py tests/test_dashboard_data.py
git commit -m "dashboard: pure seam-file readers (read_state/tail_events)"
```

---

### Task 2: Building name mapping (`names.py`)

**Files:**
- Create: `nta_agent/dashboard/names.py`
- Test: `tests/test_dashboard_names.py`

**Interfaces:**
- Produces:
  - `load_build_names(config_dir: Path | None = None) -> dict[int, str]` — read
    `<config_dir>/buildText.json` (default `nta_agent/data/config`), return
    `{build_id: name}` from rows whose `id` looks like `name_<digits>`, using `.vi`
    or (if empty) `.en`. Returns `{}` if the file is missing/unreadable.
  - `build_label(names: dict[int, str], build_id: int) -> str` — `names.get(id)` or `f"#{id}"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dashboard_names.py
from pathlib import Path
import pytest
from nta_agent.dashboard.names import build_label, load_build_names

_CONFIG = Path("nta_agent/data/config/buildText.json")


def test_build_label_fallback():
    assert build_label({}, 2001) == "#2001"
    assert build_label({2001: "Thành Chính"}, 2001) == "Thành Chính"
    assert build_label({2001: "Thành Chính"}, 9999) == "#9999"


def test_load_missing_config_returns_empty(tmp_path):
    assert load_build_names(tmp_path) == {}


@pytest.mark.skipif(not _CONFIG.exists(), reason="config not extracted")
def test_load_build_names_vietnamese():
    names = load_build_names()
    assert names[2001] == "Thành Chính"
    assert names[2004] == "Binh Doanh"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_names.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

```python
# nta_agent/dashboard/names.py
"""Map building ids to Vietnamese display names from config (buildText.json)."""
from __future__ import annotations

import json
import re
from pathlib import Path

_DEFAULT_CONFIG = Path("nta_agent/data/config")
_NAME_KEY = re.compile(r"^name_(\d+)$")


def load_build_names(config_dir: Path | None = None) -> dict[int, str]:
    path = Path(config_dir or _DEFAULT_CONFIG) / "buildText.json"
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    names: dict[int, str] = {}
    for r in rows if isinstance(rows, list) else []:
        m = _NAME_KEY.match(str(r.get("id", "")))
        if not m:
            continue
        label = (r.get("vi") or r.get("en") or "").strip()
        if label:
            names[int(m.group(1))] = label
    return names


def build_label(names: dict[int, str], build_id: int) -> str:
    return names.get(build_id, f"#{build_id}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_names.py -q`
Expected: PASS (3 tests; the config one may PASS or SKIP).

- [ ] **Step 5: Commit**

```bash
git add nta_agent/dashboard/names.py tests/test_dashboard_names.py
git commit -m "dashboard: Vietnamese building-name mapping from config"
```

---

### Task 3: Static page (`page.py`)

**Files:**
- Create: `nta_agent/dashboard/page.py`
- Test: `tests/test_dashboard_page.py`

**Interfaces:**
- Produces: `INDEX_HTML: str` — a self-contained HTML page (inline CSS + JS, no external assets) that polls `/api/state` and `/api/events?n=50` every 2s and renders status/resources/buildings/armies/tasks/events; shows "Đang chờ agent…" when state is `{"ok": false}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dashboard_page.py
from nta_agent.dashboard.page import INDEX_HTML


def test_index_html_is_self_contained():
    assert "NTA Agent" in INDEX_HTML
    assert "/api/state" in INDEX_HTML and "/api/events" in INDEX_HTML
    # no external assets (CSP-safe): no http(s) src/href
    assert "http://" not in INDEX_HTML and "https://" not in INDEX_HTML
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_page.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

```python
# nta_agent/dashboard/page.py
"""The single, self-contained dashboard HTML page (inline CSS + JS)."""

INDEX_HTML = """<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NTA Agent</title>
<style>
 body{margin:0;font:14px system-ui,Segoe UI,Arial;background:#0f1216;color:#e6e6e6}
 header{display:flex;justify-content:space-between;align-items:center;padding:12px 16px;background:#171b21;border-bottom:1px solid #262c34}
 h1{font-size:16px;margin:0}
 .dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;background:#666}
 .dot.on{background:#3fb950}.dot.wait{background:#d29922}
 main{padding:16px;display:grid;gap:12px;grid-template-columns:1fr 1fr;max-width:960px}
 .card{background:#171b21;border:1px solid #262c34;border-radius:8px;padding:12px}
 .card h2{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:#8b949e;margin:0 0 8px}
 .kv{display:flex;flex-wrap:wrap;gap:8px 16px}.kv b{color:#fff}
 .full{grid-column:1/-1}
 ul{list-style:none;margin:0;padding:0}li{padding:3px 0;border-bottom:1px solid #21262d}
 .feed{max-height:320px;overflow:auto;font-family:ui-monospace,Consolas,monospace;font-size:12px}
 .muted{color:#8b949e}
</style></head><body>
<header><h1>NTA Agent</h1><div id="status"><span class="dot"></span><span id="statusText">…</span></div></header>
<main>
 <div class="card"><h2>Tài nguyên</h2><div id="res" class="kv"></div></div>
 <div class="card"><h2>Thành chính &amp; công trình</h2><div id="city"></div></div>
 <div class="card"><h2>Quân &amp; nhiệm vụ</h2><div id="misc"></div></div>
 <div class="card full"><h2>Sự kiện gần đây</h2><ul id="feed" class="feed"></ul></div>
</main>
<script>
const RES=[["cereal","Lương"],["timber","Gỗ"],["stone","Đá"],["iron","Sắt"],["gold","Vàng"],["stamina","Thể lực"]];
function ago(ts){if(!ts)return"";const s=Math.max(0,Math.round(Date.now()/1000-ts));return s+"s trước";}
function hms(ts){const d=new Date((ts||0)*1000);return d.toLocaleTimeString();}
async function j(u){try{const r=await fetch(u);return await r.json();}catch(e){return null;}}
async function refresh(){
 const s=await j("/api/state");
 const dot=document.querySelector("#status .dot"),txt=document.getElementById("statusText");
 if(!s||!s.ok){dot.className="dot wait";txt.textContent="Đang chờ agent…";
   document.getElementById("res").innerHTML="";document.getElementById("city").innerHTML="";document.getElementById("misc").innerHTML="";}
 else{
   dot.className="dot on";txt.textContent="đang chạy · "+ago(s.updated_at);
   const r=s.resources||{};
   document.getElementById("res").innerHTML=RES.map(([k,l])=>`${l} <b>${r[k]??0}</b>`).join("");
   const builds=(s.builds||[]).map(b=>`<li>${b.name||("#"+b.id)} <b>Lv${b.lv}</b></li>`).join("")||"<li class=muted>—</li>";
   const q=s.build_queue?s.build_queue.length:0;
   document.getElementById("city").innerHTML=`<div class=muted>@${s.main_city_index||"?"} · hàng đợi ${q}/${s.build_queue_slots||0}</div><ul>${builds}</ul>`;
   const p=s.player||{};
   document.getElementById("misc").innerHTML=`<div class=kv>Đội hành quân <b>${s.marches??0}</b> · Ô đã biết <b>${s.areas??0}</b></div>`+
     `<div class=kv style=margin-top:8px>Guide <b>${p.guide_tasks??0}</b> · Other <b>${p.other_tasks??0}</b> · Today <b>${p.today_tasks??0}</b></div>`;
 }
 const ev=await j("/api/events?n=50")||[];
 document.getElementById("feed").innerHTML=ev.slice().reverse().map(e=>{
   const extra=e.kind==="tick"?("tick "+e.i+" · "+((e.fired||[]).join(", ")||"—")):(e.kind+(e.detail?(" · "+e.detail):""));
   return `<li><span class=muted>${hms(e.ts)}</span> ${extra}</li>`;}).join("")||"<li class=muted>—</li>";
}
refresh();setInterval(refresh,2000);
</script></body></html>"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_page.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nta_agent/dashboard/page.py tests/test_dashboard_page.py
git commit -m "dashboard: self-contained HTML page"
```

---

### Task 4: HTTP server (`server.py`)

**Files:**
- Create: `nta_agent/dashboard/server.py`
- Test: `tests/test_dashboard_server.py`

**Interfaces:**
- Consumes: `read_state`/`tail_events` (Task 1), `load_build_names`/`build_label` (Task 2), `INDEX_HTML` (Task 3), `RuntimeConfig` (`nta_agent.runtime.config`).
- Produces:
  - `serve(cfg: RuntimeConfig, port: int, *, host: str = "127.0.0.1") -> DashboardServer` — a `ThreadingHTTPServer` subclass holding `cfg` + a preloaded build-names map, not yet serving (caller runs `serve_forever()` or, in tests, drives it in a thread). `server_address[1]` is the bound port (use `port=0` for ephemeral).
  - Routes: `GET /`→HTML; `GET /api/state`→`read_state` enriched with build `name`; `GET /api/events`→`tail_events` (query `n`, default 50, clamped 1..500); else 404.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dashboard_server.py
import json
import threading
import urllib.request
from nta_agent.dashboard.server import serve
from nta_agent.runtime.config import RuntimeConfig


def _cfg(tmp_path):
    return RuntimeConfig.from_env({"NTA_DISTINCT_ID": "x", "NTA_LOG_DIR": str(tmp_path)})


def _run(srv):
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return t


def _get(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
        return r.status, r.read().decode("utf-8")


def test_index_and_apis(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.snapshot_path.write_text(json.dumps(
        {"main_city_index": 5, "resources": {"cereal": 9},
         "builds": [{"index": 5, "id": 2001, "lv": 2, "uid": "b1"}]}))
    cfg.event_log_path.write_text(json.dumps({"kind": "tick", "i": 0}) + "\n")
    srv = serve(cfg, 0)
    port = srv.server_address[1]
    _run(srv)
    try:
        st, body = _get(port, "/")
        assert st == 200 and "NTA Agent" in body
        st, body = _get(port, "/api/state")
        d = json.loads(body)
        assert st == 200 and d["ok"] is True
        assert d["builds"][0]["name"]  # enriched with a name (VN or #id)
        st, body = _get(port, "/api/events?n=2")
        assert st == 200 and isinstance(json.loads(body), list)
    finally:
        srv.shutdown()


def test_state_waiting_when_missing(tmp_path):
    cfg = _cfg(tmp_path)
    srv = serve(cfg, 0)
    port = srv.server_address[1]
    _run(srv)
    try:
        _, body = _get(port, "/api/state")
        assert json.loads(body) == {"ok": False}
    finally:
        srv.shutdown()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_server.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

```python
# nta_agent/dashboard/server.py
"""Thin stdlib HTTP layer serving the dashboard page + read-only JSON APIs."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from nta_agent.dashboard.data import read_state, tail_events
from nta_agent.dashboard.names import build_label, load_build_names
from nta_agent.dashboard.page import INDEX_HTML
from nta_agent.runtime.config import RuntimeConfig


class DashboardServer(ThreadingHTTPServer):
    def __init__(self, addr, handler, cfg: RuntimeConfig):
        super().__init__(addr, handler)
        self.cfg = cfg
        self.build_names = load_build_names()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence stderr access logs
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self):
        parsed = urlparse(self.path)
        cfg = self.server.cfg
        if parsed.path == "/":
            self._send(200, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
        elif parsed.path == "/api/state":
            state = read_state(cfg.snapshot_path)
            if state.get("ok"):
                for b in state.get("builds", []):
                    b["name"] = build_label(self.server.build_names, b.get("id", 0))
            self._json(200, state)
        elif parsed.path == "/api/events":
            q = parse_qs(parsed.query)
            try:
                n = int(q.get("n", ["50"])[0])
            except ValueError:
                n = 50
            n = max(1, min(n, 500))
            self._json(200, tail_events(cfg.event_log_path, n))
        else:
            self._json(404, {"error": "not found"})


def serve(cfg: RuntimeConfig, port: int, *, host: str = "127.0.0.1") -> DashboardServer:
    return DashboardServer((host, port), Handler, cfg)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_server.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add nta_agent/dashboard/server.py tests/test_dashboard_server.py
git commit -m "dashboard: stdlib http.server (page + /api/state + /api/events)"
```

---

### Task 5: CLI entrypoint (`python -m nta_agent.dashboard`)

**Files:**
- Create: `nta_agent/dashboard/__main__.py`
- Test: `tests/test_dashboard_cli.py`

**Interfaces:**
- Consumes: `serve` (Task 4), `RuntimeConfig.from_env`/`ConfigError` (`nta_agent.runtime.config`).
- Produces: `main(argv: list[str] | None = None) -> int` — `--port` (default env `NTA_DASHBOARD_PORT` or 8787); load config; `srv = serve(cfg, port)`; print `http://127.0.0.1:<bound port>`; `srv.serve_forever()` until `KeyboardInterrupt` (returns 0); `ConfigError` → message + return 2. Module runs `raise SystemExit(main())`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dashboard_cli.py
from nta_agent.dashboard import __main__ as cli
from nta_agent.runtime.config import ConfigError


class FakeSrv:
    server_address = ("127.0.0.1", 8787)
    def serve_forever(self): raise KeyboardInterrupt()
    def server_close(self): pass


def test_main_config_error_returns_2(monkeypatch, capsys):
    monkeypatch.setattr(cli.RuntimeConfig, "from_env", staticmethod(
        lambda *a, **k: (_ for _ in ()).throw(ConfigError("NTA_DISTINCT_ID is required"))))
    assert cli.main(["--port", "0"]) == 2
    assert "NTA_DISTINCT_ID" in capsys.readouterr().err


def test_main_serves_and_returns_0(monkeypatch):
    calls = {}
    monkeypatch.setattr(cli.RuntimeConfig, "from_env", staticmethod(lambda *a, **k: "CFG"))
    monkeypatch.setattr(cli, "serve", lambda cfg, port: calls.setdefault("args", (cfg, port)) or FakeSrv())
    assert cli.main(["--port", "9000"]) == 0
    assert calls["args"] == ("CFG", 9000)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_cli.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

```python
# nta_agent/dashboard/__main__.py
"""CLI: `python -m nta_agent.dashboard` serves the monitoring dashboard."""
from __future__ import annotations

import argparse
import os
import sys

from nta_agent.dashboard.server import serve
from nta_agent.runtime.config import ConfigError, RuntimeConfig


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="nta_agent.dashboard", description="NTA monitoring dashboard.")
    ap.add_argument("--port", type=int, default=int(os.environ.get("NTA_DASHBOARD_PORT", "8787")))
    args = ap.parse_args(argv)
    try:
        cfg = RuntimeConfig.from_env()
    except ConfigError as e:
        sys.stderr.write(f"config error: {e}\n")
        return 2
    srv = serve(cfg, args.port)
    port = srv.server_address[1]
    sys.stdout.write(f"dashboard on http://127.0.0.1:{port}\n")
    sys.stdout.flush()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_cli.py -q`
Expected: PASS.

- [ ] **Step 5: Full verification + commit**

Run: `.venv/Scripts/python.exe -m pytest -q` (all pass) and `.venv/Scripts/python.exe -m ruff check nta_agent tests` (clean).

```bash
git add nta_agent/dashboard/__main__.py tests/test_dashboard_cli.py
git commit -m "dashboard: python -m nta_agent.dashboard CLI"
```

---

## Self-Review

**Spec coverage:**
- §3.1 data.py → Task 1. §3.2 names.py → Task 2. §3.3 page.py → Task 3. §3.4 server.py → Task 4. §3.5 __main__ → Task 5. ✓
- §2 stdlib http.server, read-only, 127.0.0.1 → Task 4 (`serve` binds host default 127.0.0.1). ✓
- §2 Vietnamese names from buildText.vi, presentation in 2B, fallback → Task 2 + enrichment in Task 4. ✓
- §5 error handling: missing/corrupt → `{"ok":false}`/`[]` (Task 1), config absent → `{}`/`#id` (Task 2), 404 else (Task 4), ConfigError→exit 2 (Task 5). ✓
- §6 testing: data/names/page/server(threaded urllib)/CLI(fake serve) all covered. ✓
- §7 out of scope (POST/interaction, auth, charts) — not in any task. ✓

**Placeholder scan:** No TBD/TODO; `INDEX_HTML` is provided in full; every code step complete.

**Type consistency:** `read_state(path)->dict{"ok":..}`, `tail_events(path,n)->list`, `load_build_names(dir)->dict[int,str]`, `build_label(names,id)->str`, `serve(cfg,port,*,host)->DashboardServer`, `main(argv)->int` are used identically across tasks. Server enriches builds with `name` matching what `page.py` reads (`b.name`). `/api/state` returns `{"ok":False}` (Task 1) consumed by page's waiting state (Task 3). `RuntimeConfig.snapshot_path`/`event_log_path` (from 2A) are the fields used in Task 4.
