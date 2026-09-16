# B4 — Chat-with-Brain + presets & notes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A dashboard chat box where the user's natural-language instruction becomes a guarded profile edit (applied live via the command channel), plus durable profile memory: named formation presets + free-form strategy notes.

**Architecture:** Extend the profile schema (active/presets/notes) with an `active_formation` resolver and a shared `apply_edits`. The dashboard `/api/chat` calls the brain LLM with the instruction, sanitizes, persists profile.json, and appends a `profile_edit` command; the running agent's DecisionService applies it to the live Profile. Rules read the active formation.

**Tech Stack:** Python 3.12 (`.venv/Scripts/python.exe`), pytest, ruff, stdlib http.server. Reuses `brain/llm.py`, `brain/guard.py`, `execution/profile.py`, the commands channel.

**Spec:** `docs/superpowers/specs/2026-09-16-b4-chat-with-brain-design.md`

## Global Constraints

- Lint `ruff check nta_agent tests`; test `.venv/Scripts/python.exe -m pytest -q`.
- **No live OpenAI in tests** — inject a fake `chat`/`propose`.
- Thin brain: chat output = **profile edits only**, sanitized/clamped before apply.
- Durable memory = profile (`army.presets`/`army.active`, `notes`); chat history is a short in-RAM window in the dashboard, not persisted.
- Loop/UI never dies: no key → `/api/chat` returns 503; agent unaffected.
- Deep-copy defaults (existing B3 fix in `load_profile`) — presets/notes are mutable.
- Commit proactively per green task; finish flow = push → PR → merge.

---

### Task 1: Profile schema (active/presets/notes) + `active_formation` + `apply_edits`

**Files:** Modify `nta_agent/execution/profile.py`; Test `tests/test_profile.py` (extend)

**Interfaces:**
- `DEFAULT_PROFILE` gains `army.active: ""`, `army.presets: {}`, top-level `notes: []`.
- `Profile` dataclass gains `notes: list` (default via load).
- `active_formation(profile) -> dict`: `presets[active]` if `active` names a real preset, else `{group,roles,onetile,composition}` from flat `army`.
- `apply_edits(profile, clean) -> bool`: merge `clean` (`occupy`/`army`/`notes`) into the profile in place; when `army.active` is set to a real preset, copy that preset's fields into the flat `army.*`; return whether anything changed.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_profile.py (add)
from nta_agent.execution.profile import active_formation, apply_edits


def test_defaults_have_presets_active_notes():
    p = load_profile("none")
    assert p.army["presets"] == {} and p.army["active"] == ""
    assert p.notes == []


def test_active_formation_prefers_active_preset():
    p = load_profile("none")
    p.army["presets"]["turtle"] = {"group": ["A"], "roles": {"A": "tank"},
                                   "onetile": False, "composition": {"A": {"3101": 5}}}
    assert active_formation(p)["group"] == p.army["group"]   # active "" -> flat
    p.army["active"] = "turtle"
    assert active_formation(p)["group"] == ["A"]
    assert active_formation(p)["onetile"] is False


def test_apply_edits_merges_and_activates(tmp_path):
    p = load_profile("none")
    changed = apply_edits(p, {"army": {"presets": {"turtle": {"group": ["A"], "roles": {},
                              "onetile": True, "composition": {}}}, "active": "turtle"},
                              "occupy": {"max_loss": 8}, "notes": ["early: timber"]})
    assert changed is True
    assert p.army["active"] == "turtle"
    assert p.army["group"] == ["A"]           # activated -> flat synced
    assert p.occupy["max_loss"] == 8
    assert p.notes == ["early: timber"]
    assert apply_edits(p, {}) is False        # no-op


def test_notes_edit_replaces_list():
    p = load_profile("none")
    apply_edits(p, {"notes": ["a"]})
    apply_edits(p, {"notes": ["a", "b"]})
    assert p.notes == ["a", "b"]
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**

Extend `DEFAULT_PROFILE`:
```python
DEFAULT_PROFILE = {
    "army": {"group": [], "roles": {}, "onetile": True, "composition": {},
             "active": "", "presets": {}},
    "occupy": {"max_loss": 0.0, "max_march_ms": 0,
               "loot": {"enabled": True, "min_reward_per_chest": 0.0}},
    "notes": [],
}
```
`Profile` + `load_profile` carry `notes`:
```python
@dataclass
class Profile:
    army: dict
    occupy: dict
    notes: list

# in load_profile: return Profile(army=merged["army"], occupy=merged["occupy"],
#                                 notes=merged["notes"])
```
`save_profile` writes `notes` too. Add:
```python
def active_formation(profile) -> dict:
    name = (profile.army or {}).get("active") or ""
    preset = (profile.army.get("presets") or {}).get(name)
    if preset:
        return {"group": preset.get("group", []), "roles": preset.get("roles", {}),
                "onetile": preset.get("onetile", True),
                "composition": preset.get("composition", {})}
    a = profile.army
    return {"group": a.get("group", []), "roles": a.get("roles", {}),
            "onetile": a.get("onetile", True), "composition": a.get("composition", {})}


def apply_edits(profile, clean: dict) -> bool:
    changed = False
    if isinstance(clean.get("occupy"), dict):
        for k, v in clean["occupy"].items():
            if profile.occupy.get(k) != v:
                profile.occupy[k] = v; changed = True
    if isinstance(clean.get("army"), dict):
        for k, v in clean["army"].items():
            if k == "presets" and isinstance(v, dict):
                for name, preset in v.items():
                    if profile.army["presets"].get(name) != preset:
                        profile.army["presets"][name] = preset; changed = True
            elif profile.army.get(k) != v:
                profile.army[k] = v; changed = True
    if "notes" in clean and clean["notes"] != profile.notes:
        profile.notes = list(clean["notes"]); changed = True
    # activating a preset syncs it into the flat army.* fields
    active = profile.army.get("active") or ""
    preset = (profile.army.get("presets") or {}).get(active)
    if preset:
        for k in ("group", "roles", "onetile", "composition"):
            if k in preset and profile.army.get(k) != preset[k]:
                profile.army[k] = preset[k]; changed = True
    return changed
```

- [ ] **Step 4: Run** → PASS; `ruff check`. Existing profile tests still pass.
- [ ] **Step 5: Commit** `git add nta_agent/execution/profile.py tests/test_profile.py && git commit -m "profile: presets/active/notes + active_formation + apply_edits"`

---

### Task 2: BrainService uses shared `apply_edits`

**Files:** Modify `nta_agent/runtime/brain_service.py`; Test `tests/test_brain_service.py` (already covers apply; keep green)

**Interfaces:** BrainService replaces its private `_apply` with `profile.apply_edits`.

- [ ] **Step 1: Replace** `self._apply(clean)` usage and delete the private `_apply`:

```python
from nta_agent.execution.profile import apply_edits, save_profile
# ...
changed = apply_edits(self.profile, clean)
```

- [ ] **Step 2: Run** `pytest tests/test_brain_service.py -q` → PASS (behavior identical for occupy/army fields).
- [ ] **Step 3: `ruff check`; Commit** `git add nta_agent/runtime/brain_service.py && git commit -m "brain: use shared profile.apply_edits"`

---

### Task 3: Guard sanitizes presets/active/notes

**Files:** Modify `nta_agent/brain/guard.py`; Test `tests/test_brain_guard.py` (extend)

**Interfaces:** `sanitize_edits(edits, profile, valid_army_uids)` also accepts `army.presets` (each preset validated like a formation: group/roles filtered to real uids, composition counts ≥0, onetile bool), `army.active` (str; kept only if it names a preset present in the edit or already in the profile), and top-level `notes` (list of ≤20 strings, each trimmed to ≤200 chars).

- [ ] **Step 1: Write failing tests**

```python
# tests/test_brain_guard.py (add)
def test_presets_validated_like_formation():
    e = {"army": {"presets": {"turtle": {"group": ["A", "X"], "roles": {"A": "tank", "X": "archer"},
                  "onetile": 1, "composition": {"A": {"3101": -1}, "X": {"3305": 2}}}},
                  "active": "turtle"}}
    out = sanitize_edits(e, _prof(), {"A"})
    t = out["army"]["presets"]["turtle"]
    assert t["group"] == ["A"] and t["roles"] == {"A": "tank"}
    assert t["onetile"] is True and t["composition"] == {"A": {"3101": 0}}
    assert out["army"]["active"] == "turtle"   # names a preset in the edit


def test_active_dropped_when_unknown():
    out = sanitize_edits({"army": {"active": "ghost"}}, _prof(), {"A"})
    assert "active" not in out.get("army", {})


def test_notes_capped_and_stringified():
    e = {"notes": ["ok note", 123, "x" * 500] + ["n"] * 30}
    out = sanitize_edits(e, _prof(), set())
    assert len(out["notes"]) <= 20
    assert all(isinstance(s, str) and len(s) <= 200 for s in out["notes"])
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** — add to `sanitize_edits`, factoring a helper for one formation:

```python
def _formation(f: dict, valid: set) -> dict:
    out = {}
    if isinstance(f.get("group"), list):
        out["group"] = [str(u) for u in f["group"] if str(u) in valid]
    if isinstance(f.get("roles"), dict):
        out["roles"] = {str(u): r for u, r in f["roles"].items() if str(u) in valid and r in _ROLES}
    if "onetile" in f:
        out["onetile"] = bool(f["onetile"])
    if isinstance(f.get("composition"), dict):
        comp = {}
        for u, targets in f["composition"].items():
            if str(u) in valid and isinstance(targets, dict):
                comp[str(u)] = {str(pid): int(_num(c, 0, 10 ** 6, 0)) for pid, c in targets.items()}
        out["composition"] = comp
    return out
```
In the `army_in` block, after the existing group/roles/onetile/composition handling, add presets/active; and after the occupy block add notes:
```python
        if isinstance(army_in.get("presets"), dict):
            presets = {str(n): _formation(f, valid) for n, f in army_in["presets"].items()
                       if isinstance(f, dict)}
            if presets:
                army["presets"] = presets
        if "active" in army_in:
            name = str(army_in["active"])
            known = set((army.get("presets") or {})) | set((profile.army.get("presets") or {}))
            if name in known or name == "":
                army["active"] = name
    # ... (after building `army`, keep existing `if army: out["army"] = army`)

    if isinstance(edits.get("notes"), list):
        notes = [str(s).strip()[:200] for s in edits["notes"] if str(s).strip()][:20]
        out["notes"] = notes
```
(Reuse the existing group/roles/onetile/composition inline code by delegating to `_formation` for the flat army too, to stay DRY.)

- [ ] **Step 4: Run** → PASS (new + existing guard tests); `ruff check`.
- [ ] **Step 5: Commit** `git add nta_agent/brain/guard.py tests/test_brain_guard.py && git commit -m "brain: guard validates presets/active/notes"`

---

### Task 4: LLM prompt carries instruction + history + new schema; digest carries memory

**Files:** Modify `nta_agent/brain/llm.py`, `nta_agent/brain/digest.py`; Test `tests/test_brain_llm.py`, `tests/test_brain_digest.py` (extend)

**Interfaces:**
- `propose(digest, profile, chat=None, instruction=None, history=None) -> dict` — when `instruction` is set, add a user message with it; `history` (list of `{role,content}`) is inserted before it. `_SYSTEM` documents presets/active/notes.
- `digest(state, profile, armies=None)` — include `presets` (names), `active`, `notes`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_brain_llm.py (add)
def test_instruction_and_history_reach_prompt():
    seen = {}
    def fake_chat(messages):
        seen["m"] = messages
        return "{}"
    propose({"x": 1}, load_profile("none"), chat=fake_chat,
            instruction="create formation turtle", history=[{"role": "user", "content": "hi earlier"}])
    blob = " ".join(m["content"] for m in seen["m"])
    assert "create formation turtle" in blob and "hi earlier" in blob
    assert "presets" in seen["m"][0]["content"]  # schema documents presets

# tests/test_brain_digest.py (add)
def test_digest_includes_presets_active_notes():
    from types import SimpleNamespace
    from nta_agent.brain.digest import digest
    from nta_agent.execution.profile import load_profile
    p = load_profile("none"); p.army["presets"]["turtle"] = {"group": ["A"]}
    p.army["active"] = "turtle"; p.notes = ["early: timber"]
    st = SimpleNamespace(main_city_index=1,
        resources=SimpleNamespace(**{k: 0 for k in
            ("cereal","timber","stone","iron","gold","stamina","exp_book","up_scroll","fixator")}),
        raw={})
    d = digest(st, p, [])
    assert "turtle" in d["profile"]["army"]["presets"]
    assert d["profile"]["army"]["active"] == "turtle"
    assert d["notes"] == ["early: timber"]
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** — `llm.propose`:
```python
def propose(digest: dict, profile, chat=None, instruction=None, history=None) -> dict:
    chat = chat or default_chat()
    user = ("CURRENT PROFILE:\n"
            + json.dumps({"army": profile.army, "occupy": profile.occupy, "notes": profile.notes})
            + "\n\nGAME STATE:\n" + json.dumps(digest))
    messages = [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}]
    for h in (history or []):
        if isinstance(h, dict) and h.get("role") and h.get("content"):
            messages.append({"role": h["role"], "content": str(h["content"])})
    if instruction:
        messages.append({"role": "user", "content": "INSTRUCTION: " + str(instruction)})
    return _parse_json(chat(messages))
```
Extend `_SYSTEM` to document `army.presets` (named formations), `army.active`, and `notes` (durable free-form guidance you may add/update). `digest`: add
```python
        "notes": list(profile.notes),
```
and in the returned `profile` include `army` as-is (already carries presets/active). Ensure digest's `profile.army` includes presets/active (it passes `profile.army` whole — already does).

- [ ] **Step 4: Run** → PASS; `ruff check`.
- [ ] **Step 5: Commit** `git add nta_agent/brain/llm.py nta_agent/brain/digest.py tests/test_brain_llm.py tests/test_brain_digest.py && git commit -m "brain: chat instruction+history in prompt; digest carries presets/notes"`

---

### Task 5: DecisionService applies `profile_edit` commands to the live Profile

**Files:** Modify `nta_agent/runtime/decision_service.py`, `nta_agent/runtime/runner.py`; Test `tests/test_decision_service.py` (extend)

**Interfaces:** `DecisionService(actions, config, cfg, on_event=None, armies_every=6, profile=None)`; `_execute` handles `{"action":"profile_edit","edits":{...}}` → `apply_edits(self.profile, edits)` (no-op if `profile` is None). Runner passes the shared `profile`.

- [ ] **Step 1: Write failing test**

```python
# tests/test_decision_service.py (add)
def test_profile_edit_command_applies_to_live_profile(tmp_path):
    from nta_agent.execution.profile import load_profile
    from nta_agent.runtime.decision_service import DecisionService
    from types import SimpleNamespace
    prof = load_profile("none")
    cfg = SimpleNamespace(
        decisions_path=tmp_path / "d.json", equipment_path=tmp_path / "e.json",
        armies_path=tmp_path / "a.json", commands_path=tmp_path / "c.jsonl",
        commands_done_path=tmp_path / "c.done")
    svc = DecisionService(actions=SimpleNamespace(get_player_armys=list),
                          config=None, cfg=cfg, profile=prof)
    svc._execute({"action": "profile_edit", "edits": {"occupy": {"max_loss": 9}}})
    assert prof.occupy["max_loss"] == 9
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** — add `profile=None` to `__init__` (store `self.profile`); in `_execute`, before the existing dispatch:
```python
        if action == "profile_edit":
            if self.profile is not None:
                from nta_agent.execution.profile import apply_edits
                apply_edits(self.profile, cmd.get("edits") or {})
            return
```
Runner: pass `profile=profile` when constructing `DecisionService`.

- [ ] **Step 4: Run** `pytest tests/test_decision_service.py -q` → PASS; `ruff check`.
- [ ] **Step 5: Commit** `git add nta_agent/runtime/decision_service.py nta_agent/runtime/runner.py tests/test_decision_service.py && git commit -m "runtime: apply profile_edit commands to the live profile"`

---

### Task 6: Consumers read the active formation

**Files:** Modify `nta_agent/execution/heuristics.py`; Test `tests/test_occupy_rule.py` (extend)

**Interfaces:** `OccupyCell.applies` builds candidate groups from `active_formation(profile)["group"]` (not `profile.army["group"]`); `Recruit` uses `active_formation(profile)["composition"]` via `composition_target`.

- [ ] **Step 1: Write failing test**

```python
# tests/test_occupy_rule.py (add)
def test_occupy_uses_active_preset_group(monkeypatch):
    from nta_agent.execution.profile import Profile
    center = 182 * W + 526
    st = GameState(source="api"); st.user.uid = "me"; st.main_city_index = center
    st.resources.stamina = 10
    areas = {center: _cell(owner="me", city=1001), center - 1: _cell(owner="", pawns=[50])}
    cung = {"index": center, "uid": "cung", "pawns": [{"id": 3305}, {"id": 3305}]}
    tank = {"index": center, "uid": "tank", "pawns": [{"id": 3101}, {"id": 3101}]}
    act = FakeActions(areas=areas, armies=[cung, tank])
    prof = Profile(army={"group": [], "roles": {}, "onetile": True, "composition": {},
                         "active": "duo", "presets": {"duo": {"group": ["cung", "tank"],
                         "roles": {}, "onetile": True, "composition": {}}}},
                   occupy={"max_loss": 100, "max_march_ms": 0,
                           "loot": {"enabled": False, "min_reward_per_chest": 0}},
                   notes=[])
    calls = []
    class Sim:
        def predict_armies(self, state, armies, **kw):
            from nta_agent.execution.predictors.battle import BattlePrediction
            return BattlePrediction(win=True, my_power=1, enemy_power=1, ratio=1,
                                    loss_percent=0, loss_lv=0)
    rule = OccupyCell(radius=1, use_sim=True, sim=Sim(), predictor=BattlePredictor(), profile=prof)
    assert rule.applies(st, act) is True
    rule.act(act)
    assert act.calls and act.calls[0][0] == "occupy"   # used the preset group -> found a plan
```

- [ ] **Step 2: Run** → FAIL (OccupyCell reads flat group, which is empty here).
- [ ] **Step 3: Implement** — in `OccupyCell.plans_for`, replace the group source:
```python
            from nta_agent.execution.profile import active_formation
            grp = (active_formation(self.profile)["group"] if self.profile else None) or []
```
In `Recruit.applies`, resolve composition via `active_formation` (build a temp profile-like view): change `composition_target(self.profile, armys, unlocked)` to use the active composition — pass a shallow profile whose `army["composition"]` is `active_formation(self.profile)["composition"]`, e.g. add an overload `composition_target(profile, armys, unlocked, composition=None)` that uses `composition` when given; call with `composition=active_formation(self.profile)["composition"]`.

- [ ] **Step 4: Run** `pytest tests/test_occupy_rule.py tests/test_recruit_composition.py -q` → PASS; `ruff check`.
- [ ] **Step 5: Commit** `git add nta_agent/execution/heuristics.py tests/test_occupy_rule.py && git commit -m "rules: read the active formation preset"`

---

### Task 7: Dashboard `/api/chat` endpoint

**Files:** Modify `nta_agent/dashboard/server.py`; Test `tests/test_dashboard_chat.py` (create)

**Interfaces:** `POST /api/chat {message}` → `{ok, applied, rationale, active, presets, notes}` on success; `{ok:False,error}` + 503 when no key. Uses an injectable proposer so tests avoid OpenAI. The server keeps a short in-RAM history (`self.server.chat_history`, last 6 messages).

- [ ] **Step 1: Write failing test** (drive the handler logic through a small helper to avoid a live socket)

```python
# tests/test_dashboard_chat.py
import json
from pathlib import Path
from nta_agent.dashboard.server import handle_chat
from nta_agent.runtime.config import RuntimeConfig


def _cfg(tmp_path):
    return RuntimeConfig(distinct_id="x", log_dir=tmp_path)


def test_handle_chat_applies_edit_and_writes_command(tmp_path):
    cfg = _cfg(tmp_path)
    Path(cfg.profile_path).parent.mkdir(parents=True, exist_ok=True)
    Path(cfg.armies_path).write_text(json.dumps([{"uid": "A", "name": "D1", "pawns": []}]), encoding="utf-8")
    fake_propose = lambda digest, profile, instruction=None, history=None: {
        "occupy": {"max_loss": 6}, "rationale": "safer"}
    out = handle_chat(cfg, "play safer", history=[], propose=fake_propose)
    assert out["ok"] is True and out["applied"]["occupy"]["max_loss"] == 6
    # profile.json persisted
    saved = json.loads(Path(cfg.profile_path).read_text(encoding="utf-8"))
    assert saved["occupy"]["max_loss"] == 6
    # a profile_edit command was queued
    cmds = Path(cfg.commands_path).read_text(encoding="utf-8").splitlines()
    assert any(json.loads(c)["action"] == "profile_edit" for c in cmds)


def test_handle_chat_no_key_returns_unavailable(tmp_path):
    from nta_agent.brain.llm import BrainUnavailable
    cfg = _cfg(tmp_path)
    def boom(*a, **k):
        raise BrainUnavailable("no key")
    out = handle_chat(cfg, "hi", history=[], propose=boom)
    assert out["ok"] is False and "unavailable" in out["error"].lower()
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `handle_chat` (module function, testable) + wire the route. In `server.py`:
```python
def handle_chat(cfg, message, *, history=None, propose=None):
    from nta_agent.brain import llm as _llm
    from nta_agent.brain.digest import digest
    from nta_agent.brain.guard import sanitize_edits
    from nta_agent.brain.llm import BrainUnavailable
    from nta_agent.execution.profile import apply_edits, load_profile, save_profile
    from nta_agent.runtime.commands import append_command
    propose = propose or _llm.propose
    profile = load_profile(cfg.profile_path)
    try:
        armies = json.loads(Path(cfg.armies_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        armies = []
    valid = {str(a.get("uid")) for a in armies}
    dg = digest(_ChatState(), profile, armies)  # minimal state (resources 0s ok for chat)
    try:
        edits = propose(dg, profile, instruction=message, history=history or [])
    except BrainUnavailable as e:
        return {"ok": False, "error": "brain unavailable: %s" % e}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    clean = sanitize_edits(edits, profile, valid)
    apply_edits(profile, clean)
    save_profile(profile, cfg.profile_path)
    append_command(cfg.commands_path, {"action": "profile_edit", "edits": clean})
    return {"ok": True, "applied": clean, "rationale": (edits or {}).get("rationale", ""),
            "active": profile.army.get("active", ""), "presets": list(profile.army.get("presets") or {}),
            "notes": profile.notes}
```
Add a tiny `_ChatState` with a zeroed `resources` namespace + `main_city_index=0`, `raw={}` (digest needs those attrs). In `do_POST`, add before the `/api/command` check:
```python
        if parsed.path == "/api/chat":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, TypeError):
                self._json(400, {"ok": False, "error": "bad json"}); return
            msg = str(body.get("message", "")).strip()
            if not msg:
                self._json(400, {"ok": False, "error": "empty message"}); return
            hist = getattr(self.server, "chat_history", [])
            out = handle_chat(self.server.cfg, msg, history=hist)
            hist = (hist + [{"role": "user", "content": msg}])[-6:]
            self.server.chat_history = hist
            self._json(200 if out.get("ok") else 503, out); return
```
Init `self.chat_history = []` in `DashboardServer.__init__`.

- [ ] **Step 4: Run** `pytest tests/test_dashboard_chat.py -q` → PASS; `ruff check`.
- [ ] **Step 5: Commit** `git add nta_agent/dashboard/server.py tests/test_dashboard_chat.py && git commit -m "dashboard: /api/chat -> guarded profile edit via brain"`

---

### Task 8: Dashboard chat UI panel

**Files:** Modify `nta_agent/dashboard/page.py`; Test `tests/test_dashboard_page.py` (extend or create — assert markup/endpoint present)

**Interfaces:** The page HTML includes a chat panel (input + send + a short log) that POSTs `/api/chat` and renders `applied`/`rationale`, plus a read-only "Chiến thuật" area showing `active`/`presets`/`notes` (from `/api/state` or the chat response).

- [ ] **Step 1: Write failing test**

```python
# tests/test_dashboard_page.py (add or create)
from nta_agent.dashboard.page import INDEX_HTML


def test_page_has_chat_panel_and_endpoint():
    assert "/api/chat" in INDEX_HTML
    assert "chat" in INDEX_HTML.lower()
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** — add a chat panel section to `INDEX_HTML` and JS: a text input + button that `fetch("/api/chat",{method:"POST",body:JSON.stringify({message})})`, appends the user line + the returned `rationale`/`applied` summary to a log div, and shows `active`/`presets`/`notes`. Keep the existing dark/blue styling. (Static markup + inline JS; no framework.)

- [ ] **Step 4: Run** → PASS; smoke-load the page via `serve` in a throwaway check if desired. `ruff` not applicable to the HTML string but run it on the file.
- [ ] **Step 5: Full verify** `pytest -q && ruff check nta_agent tests && node --test --test-force-exit tools/battlesim/test/golden.test.js` → all green.
- [ ] **Step 6: Commit** `git add nta_agent/dashboard/page.py tests/test_dashboard_page.py && git commit -m "dashboard: chat panel + tactics (active/presets/notes) view"`

---

## Self-Review

**Spec coverage:** §3 schema/active_formation/apply_edits → Task 1; BrainService reuse → Task 2; §4 guard → Task 3; llm/digest → Task 4; command handler → Task 5; consumers read active → Task 6; `/api/chat` → Task 7; chat UI → Task 8. Error handling (§6) → Task 7 (503/parse) + guard drops (Task 3). Non-goals respected (no Q&A/streaming/persisted history/occupy-presets). Covered.

**Placeholder scan:** No TBD. Task 3 reuses a `_formation` helper for DRY (flat + presets share it); Task 7 defines `_ChatState` concretely. Task 6 extends `composition_target` with an optional `composition` arg (defined there). Task 8's HTML is described as concrete markup+JS, tested by presence assertions.

**Type consistency:** `active_formation(profile)->dict{group,roles,onetile,composition}` (T1) used in T6. `apply_edits(profile,clean)->bool` (T1) used in T2/T5/T7. `sanitize_edits(...,valid)` extended fields (T3) consumed in T7. `propose(digest,profile,chat,instruction,history)` (T4) used in T7 (via injectable). `handle_chat(cfg,message,history,propose)->dict` (T7) used in T8's endpoint. Command `{"action":"profile_edit","edits":...}` consistent T5/T7.
