# Build-order in Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the building priority a profile field (`build.order` + `build.skip`) that the user, chat, and brain can all edit, driving BuildOrder's construct-first priority.

**Architecture:** Extend the tactics profile with `build`; `apply_edits` merges it; the guard validates it against real build ids; `BuildOrder` builds an effective sequence from `order` (+ sorted remainder) minus `skip`. Reuses B1/B4 machinery; deterministic hands.

**Tech Stack:** Python 3.12 (`.venv/Scripts/python.exe`), pytest, ruff. Touches profile, build_planner, heuristics, brain (guard/llm/digest), dashboard.

**Spec:** `docs/superpowers/specs/2026-09-16-build-order-profile-design.md`

## Global Constraints

- Lint `ruff check nta_agent tests`; test `.venv/Scripts/python.exe -m pytest -q`.
- `build.order` / `build.skip` = lists of ints (build ids). Replace-list semantics on edit (like `notes`).
- Construct-first preserved; `skip` ids never constructed or upgraded.
- Guard needs `valid_build_ids`; when absent, `build` edits are dropped (safe).
- No profile → BuildOrder unchanged (sorted default).
- Commit proactively per green task; finish flow = push → PR → merge.

---

### Task 1: Profile `build` field (order/skip) + apply_edits + defaults

**Files:** Modify `nta_agent/execution/profile.py`; Test `tests/test_profile.py` (extend)

**Interfaces:** `DEFAULT_PROFILE["build"] = {"order": [], "skip": []}`; `Profile` gains `build: dict`; `load_profile`/`save_profile` carry it; `apply_edits` merges `build.order`/`build.skip` (replace lists), returns changed.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_profile.py (add)
def test_defaults_have_build_order_skip():
    p = load_profile("none")
    assert p.build == {"order": [], "skip": []}


def test_apply_edits_merges_build_lists():
    p = load_profile("none")
    changed = apply_edits(p, {"build": {"order": [2002, 2004], "skip": [2000]}})
    assert changed is True
    assert p.build["order"] == [2002, 2004]
    assert p.build["skip"] == [2000]
    assert apply_edits(p, {"build": {"order": [2002, 2004], "skip": [2000]}}) is False
```

- [ ] **Step 2: Run** → FAIL (`.venv/Scripts/python.exe -m pytest tests/test_profile.py -q`).
- [ ] **Step 3: Implement**
  - `DEFAULT_PROFILE`: add top-level `"build": {"order": [], "skip": []}`.
  - `Profile` dataclass: add `build: dict`.
  - `load_profile`: `return Profile(army=..., occupy=..., notes=merged["notes"], build=merged["build"])`.
  - `save_profile`: include `"build": profile.build` in the written dict.
  - `apply_edits`: after the `notes` block, add:
```python
    if isinstance(clean.get("build"), dict):
        for k, v in clean["build"].items():
            if profile.build.get(k) != v:
                profile.build[k] = list(v)
                changed = True
```

- [ ] **Step 4: Run** → PASS; `ruff check`. Existing profile tests still pass (Profile now needs `build=` in any direct constructors — grep tests for `Profile(army=` and add `build={"order":[],"skip":[]}` where missing).
- [ ] **Step 5: Commit** `git add nta_agent/execution/profile.py tests/test_profile.py [any test files with Profile()] && git commit -m "profile: build.order/skip field + apply_edits merge"`

---

### Task 2: `next_build_action` honors `skip`

**Files:** Modify `nta_agent/execution/build_planner.py`; Test `tests/test_build_planner_construct.py` (extend)

**Interfaces:** `next_build_action(state, config, sequence=None, blocked=None, skip=None)` — ids in `skip` (a set/list of build ids) are excluded from both the construct and upgrade passes.

- [ ] **Step 1: Write failing test**

```python
# tests/test_build_planner_construct.py (add)
def test_skip_excludes_from_construct_and_upgrade():
    c = GameConfig.load()
    # only candidates are 2000 (upgrade) and 2002 (construct); skip both -> None
    st = _state([_b(2001, 10), _b(2000, 5)])
    assert next_build_action(st, c, sequence=[2000, 2002], skip={2000, 2002}) is None
    # skip only 2002 -> falls back to upgrading 2000
    act = next_build_action(st, c, sequence=[2000, 2002], skip={2002})
    assert act.kind == "upgrade" and act.build_id == 2000
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** — add `skip=None` param; `skip = set(skip or ())`; at the top of both the construct loop and the upgrade loop, `if build_id in skip: continue`.

- [ ] **Step 4: Run** → PASS; `ruff check`; run all build tests (`pytest -k build -q`).
- [ ] **Step 5: Commit** `git add nta_agent/execution/build_planner.py tests/test_build_planner_construct.py && git commit -m "build_planner: next_build_action honors skip set"`

---

### Task 3: BuildOrder uses profile order/skip

**Files:** Modify `nta_agent/execution/heuristics.py` (`BuildOrder`, `RuleEngine.default`); Test `tests/test_build_order.py` (extend)

**Interfaces:** `BuildOrder` gains `profile: object = None`. `applies` builds the effective sequence: `profile.build["order"]` followed by the remaining in-city+existing ids sorted, and passes `skip=profile.build["skip"]`. `RuleEngine.default(profile)` passes it to `BuildOrder`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_build_order.py (add)
from nta_agent.execution.profile import Profile


def _profile(order, skip):
    return Profile(army={"group": [], "roles": {}, "onetile": True, "composition": {},
                         "active": "", "presets": {}},
                   occupy={}, notes=[], build={"order": order, "skip": skip})


def test_build_order_skips_wall_via_profile():
    # main hall lv10, wall lv5 (upgradeable) — but skip 2000 -> constructs instead.
    st = _state([Building(id=2001, lv=10, uid="m", index=109726),
                 Building(id=2000, lv=5, uid="w", index=109726)])
    act = Acts()
    rule = BuildOrder(profile=_profile(order=[], skip=[2000]), config=GameConfig.load())
    assert rule.applies(st, act) is True
    rule.act(act)
    assert act.calls and act.calls[0][0] == "add"      # a construct, not wall upgrade


def test_build_order_prioritizes_profile_order():
    st = _state([Building(id=2001, lv=10, uid="m", index=109726)])
    act = Acts()
    # order puts 2016 (Y Quán) first -> it is constructed first
    rule = BuildOrder(profile=_profile(order=[2016], skip=[]), config=GameConfig.load())
    assert rule.applies(st, act) is True
    rule.act(act)
    assert act.calls == [("add", 109726, 2016)]
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**
  - Add `profile: object = None` to `BuildOrder`.
  - In `applies`, after getting `cfg`:
```python
        seq, skip = self.sequence, None
        if self.profile is not None:
            b = self.profile.build
            skip = b.get("skip") or []
            order = list(b.get("order") or [])
            rest = sorted(set(cfg.in_city_build_ids()) | {x.id for x in state.builds})
            seq = order + [i for i in rest if i not in order]
        self._pending = next_build_action(state, cfg, seq, self._blocked, skip=skip)
```
  (keep the sig/retry-clear logic above it unchanged.)
  - `RuleEngine.default`: `BuildOrder(profile=profile)`.

- [ ] **Step 4: Run** `pytest tests/test_build_order.py -q` → PASS; full suite + ruff.
- [ ] **Step 5: Commit** `git add nta_agent/execution/heuristics.py tests/test_build_order.py && git commit -m "build: BuildOrder follows profile build.order/skip"`

---

### Task 4: Guard validates `build` edits; brain/chat can author them

**Files:** Modify `nta_agent/brain/guard.py`, `nta_agent/brain/llm.py`, `nta_agent/brain/digest.py`, `nta_agent/runtime/brain_service.py`, `nta_agent/dashboard/server.py`; Test `tests/test_brain_guard.py`, `tests/test_brain_digest.py` (extend)

**Interfaces:** `sanitize_edits(edits, profile, valid_army_uids, valid_build_ids=None)` — keeps `build.order`/`build.skip` as int lists filtered to `valid_build_ids`; drops `build` entirely when `valid_build_ids` is None. BrainService + handle_chat pass `set(config.in_city_build_ids())`. Digest includes `profile.build`. `_SYSTEM` documents `build`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_brain_guard.py (add)
def test_build_edits_filtered_to_valid_ids():
    out = sanitize_edits({"build": {"order": [2002, 999999, "x"], "skip": [2000]}},
                         _prof(), set(), valid_build_ids={2000, 2002})
    assert out["build"]["order"] == [2002]     # 999999/"x" dropped
    assert out["build"]["skip"] == [2000]


def test_build_edits_dropped_without_valid_ids():
    out = sanitize_edits({"build": {"order": [2002]}}, _prof(), set())
    assert "build" not in out

# tests/test_brain_digest.py (add)
def test_digest_includes_build():
    from types import SimpleNamespace
    from nta_agent.brain.digest import digest
    from nta_agent.execution.profile import load_profile
    p = load_profile("none"); p.build["order"] = [2002]
    st = SimpleNamespace(main_city_index=1,
        resources=SimpleNamespace(**{k: 0 for k in
            ("cereal","timber","stone","iron","gold","stamina","exp_book","up_scroll","fixator")}),
        raw={})
    assert digest(st, p, [])["profile"]["build"]["order"] == [2002]
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**
  - `guard.sanitize_edits`: add param `valid_build_ids=None`; after the notes block:
```python
    build_in = edits.get("build") if isinstance(edits, dict) else None
    if isinstance(build_in, dict) and valid_build_ids is not None:
        valid_b = {int(x) for x in valid_build_ids}
        b = {}
        for key in ("order", "skip"):
            if isinstance(build_in.get(key), list):
                b[key] = [int(x) for x in build_in[key]
                          if isinstance(x, int) and int(x) in valid_b]
        if b:
            out["build"] = b
```
  - `digest`: add `profile.build` to the `profile` dict it emits (it passes `profile.army`/`occupy`; add `"build": profile.build`).
  - `llm._SYSTEM`: document `build.order` (priority) / `build.skip` (ids to leave alone).
  - `brain_service`: compute `valid_build_ids` from a config (load `GameConfig` lazily) and pass to `sanitize_edits`. If config is unavailable, pass None (build edits skipped — safe).
  - `dashboard.server.handle_chat`: `from nta_agent.data.config import GameConfig`; pass `valid_build_ids=set(GameConfig.load().in_city_build_ids())` to `sanitize_edits` (guard against load failure → None).

- [ ] **Step 4: Run** the two test files → PASS; then full suite + ruff.
- [ ] **Step 5: Commit** `git add nta_agent/brain/guard.py nta_agent/brain/llm.py nta_agent/brain/digest.py nta_agent/runtime/brain_service.py nta_agent/dashboard/server.py tests/test_brain_guard.py tests/test_brain_digest.py && git commit -m "brain/chat: author build.order/skip (guarded by valid build ids)"`

---

## Self-Review

**Spec coverage:** §2/§4 profile field → Task 1; skip in planner → Task 2; BuildOrder effective sequence + skip + RuleEngine wiring → Task 3; guard/llm/digest/brain/chat authoring → Task 4. §6 edge (no profile / empty order / skip existing) → Task 3 tests + unchanged default path. §8 tests → each task. Covered.

**Placeholder scan:** No TBD. Task 1 Step 4 flags updating direct `Profile(...)` constructors in tests (add `build=`). Task 4 gives exact guard/digest/wiring edits.

**Type consistency:** `Profile` now `(army, occupy, notes, build)` — all direct constructors updated (Task 1). `apply_edits` handles `build` (Task 1) — used by BrainService/handle_chat/decision_service already. `next_build_action(..., skip=)` (Task 2) called by BuildOrder (Task 3). `sanitize_edits(..., valid_build_ids=)` (Task 4) called by BrainService + handle_chat with `in_city_build_ids()`. `build.order/skip` = int lists throughout.
