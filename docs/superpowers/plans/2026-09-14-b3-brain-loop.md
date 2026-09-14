# B3 — Brain Loop + Auto-Treasure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A sparse thin-brain that periodically asks an LLM (OpenAI) to edit the tactics profile (occupy policy + army composition), validated and applied to the live profile; plus a deterministic rule that auto opens/claims earned treasures.

**Architecture:** Pure helpers (`policies`, `guard`, `digest`) + a provider-isolated `llm` (injectable `chat`, OpenAI via env key) + a `BrainService` that mutates the shared `Profile` in place and persists it. A `ClaimTreasures` hands rule closes the farming loop. Any LLM/network failure degrades to a no-op; hands keep running.

**Tech Stack:** Python 3.12 (`.venv/Scripts/python.exe`), pytest, ruff, stdlib `urllib` for OpenAI (no new dependency). Reuses `execution/profile.py`, `treasure_model.chest_budget`.

**Spec:** `docs/superpowers/specs/2026-09-14-b3-brain-loop-design.md`

## Global Constraints

- Lint `ruff check nta_agent tests`; test `.venv/Scripts/python.exe -m pytest -q`.
- **No live OpenAI in tests** — always inject a fake `chat`/`llm`.
- Never hardcode secrets: OpenAI key from `OPENAI_API_KEY`, model from `OPENAI_MODEL` (default `gpt-4o-mini`).
- Thin brain: LLM output = **profile edits only**, sanitized + clamped before apply.
- Loop never dies: missing key / network / parse / bad edit → no-op that tick.
- Brain mutates `profile.army`/`profile.occupy` dicts **in place** (rules share the object); also `save_profile`.
- Commit proactively per green task; finish flow = push → PR → merge.

---

### Task 1: `brain/policies.py` — call cadence + budget

**Files:** Create `nta_agent/brain/__init__.py` (empty), `nta_agent/brain/policies.py`; Test `tests/test_brain_policies.py`

**Interfaces:** Produces `BrainPolicy(every_ticks=60, max_calls=50)`; `should_call(tick:int, calls_made:int) -> bool`.

- [ ] **Step 1: Failing test**

```python
# tests/test_brain_policies.py
from nta_agent.brain.policies import BrainPolicy


def test_fires_on_cadence_until_budget():
    p = BrainPolicy(every_ticks=10, max_calls=2)
    assert p.should_call(10, 0) is True
    assert p.should_call(15, 0) is False   # not on cadence
    assert p.should_call(20, 1) is True
    assert p.should_call(30, 2) is False   # budget exhausted
    assert p.should_call(0, 0) is False    # tick 0 never fires
```

- [ ] **Step 2: Run** → FAIL (module missing).
- [ ] **Step 3: Implement**

```python
# nta_agent/brain/policies.py
"""When the brain may call the LLM: sparse cadence + hard budget."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class BrainPolicy:
    every_ticks: int = 60
    max_calls: int = 50

    def should_call(self, tick: int, calls_made: int) -> bool:
        return (calls_made < self.max_calls and tick > 0
                and tick % self.every_ticks == 0)
```

- [ ] **Step 4: Run** → PASS; `ruff check`.
- [ ] **Step 5: Commit** `git add nta_agent/brain/__init__.py nta_agent/brain/policies.py tests/test_brain_policies.py && git commit -m "brain: call policy (cadence + budget)"`

---

### Task 2: `brain/guard.py` — sanitize/clamp profile edits

**Files:** Create `nta_agent/brain/guard.py`; Test `tests/test_brain_guard.py`

**Interfaces:** Consumes `Profile`, a `set[str]` of valid army uids. Produces `sanitize_edits(edits: dict, profile, valid_army_uids) -> dict` returning only `{army?, occupy?}` with valid, clamped fields (drops unknown/out-of-range; fully-invalid → `{}`).

- [ ] **Step 1: Failing test**

```python
# tests/test_brain_guard.py
from nta_agent.brain.guard import sanitize_edits
from nta_agent.execution.profile import load_profile


def _prof():
    return load_profile("nonexistent")  # defaults


def test_clamps_occupy_and_drops_unknown():
    e = {"occupy": {"max_loss": 250, "max_march_ms": -5, "bogus": 1,
                    "loot": {"enabled": "yes", "min_reward_per_chest": -3}},
         "junk": 9}
    out = sanitize_edits(e, _prof(), set())
    assert out["occupy"]["max_loss"] == 100          # clamped to 100
    assert out["occupy"]["max_march_ms"] == 0        # clamped to >=0
    assert out["occupy"]["loot"]["enabled"] is True  # coerced bool
    assert out["occupy"]["loot"]["min_reward_per_chest"] == 0
    assert "bogus" not in out["occupy"] and "junk" not in out


def test_army_only_real_uids_and_nonneg_counts():
    e = {"army": {"group": ["A", "X"], "roles": {"A": "tank", "X": "archer", "A2": "bad"},
                  "onetile": 0, "composition": {"A": {"3101": -2, "3305": 3}, "X": {"3101": 1}}}}
    out = sanitize_edits(e, _prof(), {"A"})
    assert out["army"]["group"] == ["A"]             # X not real
    assert out["army"]["roles"] == {"A": "tank"}     # X not real, A2 not real
    assert out["army"]["onetile"] is False
    assert out["army"]["composition"] == {"A": {"3101": 0, "3305": 3}}  # X dropped, clamp >=0


def test_fully_invalid_is_empty():
    assert sanitize_edits({"nope": 1}, _prof(), set()) == {}
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**

```python
# nta_agent/brain/guard.py
"""Validate + clamp LLM-proposed profile edits before applying."""
from __future__ import annotations

_ROLES = {"archer", "tank"}


def _num(v, lo, hi, default):
    try:
        n = float(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def sanitize_edits(edits: dict, profile, valid_army_uids) -> dict:
    valid = {str(u) for u in (valid_army_uids or ())}
    out: dict = {}

    occ_in = edits.get("occupy") if isinstance(edits, dict) else None
    if isinstance(occ_in, dict):
        occ: dict = {}
        if "max_loss" in occ_in:
            occ["max_loss"] = _num(occ_in["max_loss"], 0, 100, profile.occupy["max_loss"])
        if "max_march_ms" in occ_in:
            occ["max_march_ms"] = int(_num(occ_in["max_march_ms"], 0, 10 ** 9, 0))
        loot_in = occ_in.get("loot")
        if isinstance(loot_in, dict):
            loot: dict = {}
            if "enabled" in loot_in:
                loot["enabled"] = bool(loot_in["enabled"] if not isinstance(loot_in["enabled"], str)
                                       else loot_in["enabled"].lower() in ("1", "true", "yes"))
            if "min_reward_per_chest" in loot_in:
                loot["min_reward_per_chest"] = _num(loot_in["min_reward_per_chest"], 0, 10 ** 9, 0)
            if loot:
                occ["loot"] = loot
        if occ:
            out["occupy"] = occ

    army_in = edits.get("army") if isinstance(edits, dict) else None
    if isinstance(army_in, dict):
        army: dict = {}
        if isinstance(army_in.get("group"), list):
            army["group"] = [str(u) for u in army_in["group"] if str(u) in valid]
        if isinstance(army_in.get("roles"), dict):
            army["roles"] = {str(u): r for u, r in army_in["roles"].items()
                             if str(u) in valid and r in _ROLES}
        if "onetile" in army_in:
            army["onetile"] = bool(army_in["onetile"])
        if isinstance(army_in.get("composition"), dict):
            comp: dict = {}
            for u, targets in army_in["composition"].items():
                if str(u) in valid and isinstance(targets, dict):
                    comp[str(u)] = {str(pid): int(_num(c, 0, 10 ** 6, 0)) for pid, c in targets.items()}
            if comp:
                army["composition"] = comp
        if army:
            out["army"] = army
    return out
```

- [ ] **Step 4: Run** → PASS; `ruff check`.
- [ ] **Step 5: Commit** `git add nta_agent/brain/guard.py tests/test_brain_guard.py && git commit -m "brain: sanitize/clamp profile edits"`

---

### Task 3: `brain/digest.py` — compact state summary

**Files:** Create `nta_agent/brain/digest.py`; Test `tests/test_brain_digest.py`

**Interfaces:** Produces `digest(state, profile, armies=None) -> dict` — small dict: resources, main_city_index, per-army `{uid,name,pawns,composition}`, and the current profile. Pure.

- [ ] **Step 1: Failing test**

```python
# tests/test_brain_digest.py
from types import SimpleNamespace
from nta_agent.brain.digest import digest
from nta_agent.execution.profile import load_profile


def test_digest_is_compact_and_has_armies_and_profile():
    st = SimpleNamespace(
        main_city_index=7,
        resources=SimpleNamespace(cereal=10, timber=20, stone=30, iron=0, gold=1,
                                  stamina=50, exp_book=0, up_scroll=0, fixator=0),
        raw={})
    armies = [{"uid": "A", "name": "Đội 1", "pawns": [{"id": 3101}, {"id": 3101}, {"id": 3305}]}]
    d = digest(st, load_profile("none"), armies)
    assert d["main_city_index"] == 7
    assert d["resources"]["cereal"] == 10
    assert d["armies"][0]["uid"] == "A"
    assert d["armies"][0]["composition"] == {"3101": 2, "3305": 1}
    assert "occupy" in d["profile"] and "army" in d["profile"]
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**

```python
# nta_agent/brain/digest.py
"""Compact, token-cheap game summary for the brain prompt."""
from __future__ import annotations
from collections import Counter


def digest(state, profile, armies=None) -> dict:
    r = state.resources
    res = {k: getattr(r, k, 0) for k in
           ("cereal", "timber", "stone", "iron", "gold", "stamina",
            "exp_book", "up_scroll", "fixator")}
    army_rows = []
    for a in (armies or []):
        comp = Counter(str(p.get("id")) for p in (a.get("pawns") or []))
        army_rows.append({"uid": str(a.get("uid")), "name": a.get("name"),
                          "pawns": len(a.get("pawns") or []), "composition": dict(comp)})
    return {
        "main_city_index": getattr(state, "main_city_index", 0),
        "resources": res,
        "armies": army_rows,
        "profile": {"army": profile.army, "occupy": profile.occupy},
    }
```

- [ ] **Step 4: Run** → PASS; `ruff check`.
- [ ] **Step 5: Commit** `git add nta_agent/brain/digest.py tests/test_brain_digest.py && git commit -m "brain: compact state digest"`

---

### Task 4: `brain/llm.py` — OpenAI-isolated proposer

**Files:** Create `nta_agent/brain/llm.py`; Test `tests/test_brain_llm.py`

**Interfaces:** Produces `BrainUnavailable(Exception)`; `propose(digest: dict, profile, chat=None) -> dict` (parsed edits incl. optional `rationale`); `default_chat() -> callable` (OpenAI via env; raises `BrainUnavailable` with no key). `chat(messages: list[dict]) -> str`.

- [ ] **Step 1: Failing test** (fake chat; no network)

```python
# tests/test_brain_llm.py
import json
from nta_agent.brain.llm import propose, BrainUnavailable, default_chat
from nta_agent.execution.profile import load_profile


def test_propose_builds_messages_and_parses_json():
    seen = {}
    def fake_chat(messages):
        seen["messages"] = messages
        return "```json\n" + json.dumps({"occupy": {"max_loss": 5}, "rationale": "safer"}) + "\n```"
    out = propose({"resources": {"cereal": 1}}, load_profile("none"), chat=fake_chat)
    assert out["occupy"]["max_loss"] == 5 and out["rationale"] == "safer"
    blob = " ".join(m["content"] for m in seen["messages"])
    assert "max_loss" in blob and "cereal" in blob   # schema + digest present


def test_malformed_response_is_empty():
    assert propose({}, load_profile("none"), chat=lambda m: "not json at all") == {}


def test_default_chat_without_key_raises(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    try:
        default_chat()
        assert False, "expected BrainUnavailable"
    except BrainUnavailable:
        pass
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**

```python
# nta_agent/brain/llm.py
"""The only module that talks to OpenAI. Injectable `chat` for tests."""
from __future__ import annotations
import json
import os
import urllib.request


class BrainUnavailable(Exception):
    """No API key / provider unreachable — the brain is skipped this tick."""


_SYSTEM = (
    "You tune a strategy game agent by editing its tactics PROFILE. You never "
    "control the game directly. Return ONLY a JSON object with the profile fields "
    "to change and a short 'rationale'. Schema:\n"
    '{"army":{"group":[armyUid],"roles":{armyUid:"archer|tank"},"onetile":bool,'
    '"composition":{armyUid:{pawnId:count}}},'
    '"occupy":{"max_loss":0-100,"max_march_ms":int>=0,'
    '"loot":{"enabled":bool,"min_reward_per_chest":number>=0}}}\n'
    "Only include fields you want to change. max_loss is the max acceptable "
    "predicted troop-loss %% for occupying a cell (0 = never lose troops)."
)


def _parse_json(text: str) -> dict:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1] if "```" in t[3:] else t[3:]
        t = t[4:] if t.lower().startswith("json") else t
        t = t.strip().rstrip("`").strip()
    try:
        obj = json.loads(t)
        return obj if isinstance(obj, dict) else {}
    except (ValueError, TypeError):
        return {}


def propose(digest: dict, profile, chat=None) -> dict:
    chat = chat or default_chat()
    user = ("CURRENT PROFILE:\n" + json.dumps({"army": profile.army, "occupy": profile.occupy})
            + "\n\nGAME STATE:\n" + json.dumps(digest))
    messages = [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}]
    return _parse_json(chat(messages))


def default_chat():
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise BrainUnavailable("OPENAI_API_KEY not set")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    def chat(messages):
        body = json.dumps({"model": model, "messages": messages, "temperature": 0.2,
                           "response_format": {"type": "json_object"}}).encode("utf-8")
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions", data=body,
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]

    return chat
```

- [ ] **Step 4: Run** → PASS; `ruff check`.
- [ ] **Step 5: Commit** `git add nta_agent/brain/llm.py tests/test_brain_llm.py && git commit -m "brain: OpenAI-isolated proposer (injectable chat)"`

---

### Task 5: `BrainService` + config + runner wiring

**Files:** Create `nta_agent/runtime/brain_service.py`; Modify `nta_agent/runtime/config.py`, `nta_agent/runtime/runner.py`; Test `tests/test_brain_service.py`

**Interfaces:** `BrainService(profile, cfg, on_event=None, actions=None, llm_propose=None, policy=None)`; `tick(state)` — gate → digest → propose → sanitize → apply in place + save + emit `brain_plan`. `llm_propose(digest, profile) -> dict` injectable (default wraps `brain.llm.propose`). Config: `brain_every_ticks`, `brain_max_calls`.

- [ ] **Step 1: Failing test** (fake llm_propose; no network)

```python
# tests/test_brain_service.py
from types import SimpleNamespace
from nta_agent.execution.profile import load_profile
from nta_agent.brain.policies import BrainPolicy
from nta_agent.runtime.brain_service import BrainService


def _cfg(tmp_path):
    return SimpleNamespace(profile_path=tmp_path / "profile.json")


def test_applies_sanitized_edits_in_place_and_emits(tmp_path):
    prof = load_profile("none")
    events = []
    actions = SimpleNamespace(get_player_armys=lambda: [{"uid": "A", "name": "D1", "pawns": []}])
    svc = BrainService(prof, _cfg(tmp_path), on_event=lambda k, d: events.append((k, d)),
                       actions=actions, policy=BrainPolicy(every_ticks=1, max_calls=5),
                       llm_propose=lambda dg, p: {"occupy": {"max_loss": 12}, "army": {"group": ["A"]},
                                                  "rationale": "tune"})
    st = SimpleNamespace(main_city_index=7,
                         resources=SimpleNamespace(**{k: 0 for k in
                             ("cereal","timber","stone","iron","gold","stamina","exp_book","up_scroll","fixator")}),
                         raw={})
    svc.tick(st)
    assert prof.occupy["max_loss"] == 12       # mutated in place
    assert prof.army["group"] == ["A"]
    assert any(k == "brain_plan" for k, d in events)
    assert (tmp_path / "profile.json").exists()  # persisted


def test_skips_off_cadence_and_survives_unavailable(tmp_path):
    from nta_agent.brain.llm import BrainUnavailable
    prof = load_profile("none")
    def boom(dg, p):
        raise BrainUnavailable("no key")
    svc = BrainService(prof, _cfg(tmp_path), actions=SimpleNamespace(get_player_armys=lambda: []),
                       policy=BrainPolicy(every_ticks=10, max_calls=5), llm_propose=boom)
    st = SimpleNamespace(main_city_index=0,
                         resources=SimpleNamespace(**{k: 0 for k in
                             ("cereal","timber","stone","iron","gold","stamina","exp_book","up_scroll","fixator")}),
                         raw={})
    svc.tick(st)          # tick 1: off cadence -> no call, no raise
    for _ in range(9):
        svc.tick(st)      # tick 10: fires but BrainUnavailable -> swallowed
    assert prof.occupy["max_loss"] == 0.0   # unchanged
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `brain_service.py`

```python
# nta_agent/runtime/brain_service.py
"""Sparse thin-brain: periodically ask the LLM to edit the live profile."""
from __future__ import annotations
import sys

from nta_agent.brain.digest import digest
from nta_agent.brain.guard import sanitize_edits
from nta_agent.brain.llm import BrainUnavailable
from nta_agent.brain.policies import BrainPolicy
from nta_agent.execution.profile import save_profile


class BrainService:
    def __init__(self, profile, cfg, on_event=None, actions=None,
                 llm_propose=None, policy=None):
        self.profile = profile
        self.cfg = cfg
        self._on_event = on_event or (lambda *a: None)
        self.actions = actions
        self.policy = policy or BrainPolicy(
            every_ticks=getattr(cfg, "brain_every_ticks", 60),
            max_calls=getattr(cfg, "brain_max_calls", 50))
        if llm_propose is None:
            from nta_agent.brain import llm as _llm
            llm_propose = lambda dg, p: _llm.propose(dg, p)  # noqa: E731
        self._propose = llm_propose
        self._tick = 0
        self._calls = 0
        self._off = False

    def _apply(self, clean: dict) -> bool:
        changed = False
        for domain in ("army", "occupy"):
            for k, v in (clean.get(domain) or {}).items():
                target = getattr(self.profile, domain)
                if target.get(k) != v:
                    target[k] = v
                    changed = True
        return changed

    def tick(self, state) -> None:
        self._tick += 1
        if self._off or not self.policy.should_call(self._tick, self._calls):
            return
        try:
            armies = self.actions.get_player_armys() if self.actions else []
            dg = digest(state, self.profile, armies)
            edits = self._propose(dg, self.profile)
            valid = {str(a.get("uid")) for a in armies}
            clean = sanitize_edits(edits, self.profile, valid)
            changed = self._apply(clean)
            if changed:
                save_profile(self.profile, self.cfg.profile_path)
            self._calls += 1
            self._on_event("brain_plan", {"changed": changed,
                                          "rationale": (edits or {}).get("rationale", "")})
        except BrainUnavailable as e:
            self._off = True  # stop retrying this run
            sys.stderr.write(f"[brain] disabled: {e}\n")
        except Exception as e:  # never kill the loop
            sys.stderr.write(f"[brain] tick failed: {e}\n")
```

- [ ] **Step 4: config + runner**

`config.py`: add
```python
    brain_every_ticks: int = 60
    brain_max_calls: int = 50
```
and in `from_env`: `brain_every_ticks=int(env.get("NTA_BRAIN_EVERY","60")), brain_max_calls=int(env.get("NTA_BRAIN_MAX_CALLS","50"))`.

`runner.py`: after building `service` (DecisionService) and the profile, create
`brain = BrainService(profile, cfg, on_event=log.append, actions=agent.actions)`
using the same `profile` object passed to `RuleEngine.default`, and in `on_tick`
call `_safe(brain.tick, state)` after `service.tick`. (Refactor the profile load
so both `RuleEngine.default(profile=…)` and `BrainService(profile,…)` share it.)

- [ ] **Step 5: Run** `pytest tests/test_brain_service.py -q` → PASS; full suite + ruff.
- [ ] **Step 6: Commit** `git add nta_agent/runtime/brain_service.py nta_agent/runtime/config.py nta_agent/runtime/runner.py tests/test_brain_service.py && git commit -m "brain: BrainService (sparse profile edits) + wiring"`

---

### Task 6: Auto open/claim treasures (deterministic rule)

**Files:** Modify `nta_agent/execution/actions.py` (batch treasure actions), `nta_agent/execution/heuristics.py` (`ClaimTreasures` + `RuleEngine.default`); Test `tests/test_claim_treasures.py`

**Interfaces:** `Actions.open_armys_treasure(targets)` / `claim_armys_treasure(targets)` where `targets = [{"index":int,"auid":str}]` → routes `game/HD_OpenArmysTreasure` / `game/HD_ClaimArmysTreasure`. `ClaimTreasures` rule: `applies` when any army has a pawn with non-empty `treasures`; `act` opens+claims those armies (batch), budget-capped, best-effort.

- [ ] **Step 1: Failing test**

```python
# tests/test_claim_treasures.py
from types import SimpleNamespace
from nta_agent.execution.heuristics import ClaimTreasures
from nta_agent.state.schema import GameState


def _actions(armies, calls):
    return SimpleNamespace(
        get_player_armys=lambda: armies,
        open_armys_treasure=lambda targets: calls.append(("open", targets)),
        claim_armys_treasure=lambda targets: calls.append(("claim", targets)))


def test_opens_and_claims_armies_with_pending_treasures():
    st = GameState(source="api"); st.raw = {"player": {}}
    armies = [{"uid": "A", "index": 5, "pawns": [{"id": 3101, "treasures": [{"id": 1}]}]},
              {"uid": "B", "index": 6, "pawns": [{"id": 3101, "treasures": []}]}]
    calls = []
    rule = ClaimTreasures()
    act = _actions(armies, calls)
    assert rule.applies(st, act) is True
    rule.act(act)
    kinds = {k for k, _ in calls}
    assert "open" in kinds and "claim" in kinds
    opened = next(t for k, t in calls if k == "open")
    assert opened == [{"index": 5, "auid": "A"}]     # only army A had pending


def test_no_pending_does_not_apply():
    st = GameState(source="api"); st.raw = {"player": {}}
    armies = [{"uid": "A", "index": 5, "pawns": [{"id": 3101, "treasures": []}]}]
    assert ClaimTreasures().applies(st, _actions(armies, [])) is False
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** — actions:

```python
    def open_armys_treasure(self, targets: list[dict]) -> dict:
        """Batch-open earned treasures (GAME_HD_OpenArmysTreasure)."""
        return self.session.request("game/HD_OpenArmysTreasure", {"targets": targets})

    def claim_armys_treasure(self, targets: list[dict]) -> dict:
        """Batch-claim opened treasures (GAME_HD_ClaimArmysTreasure)."""
        return self.session.request("game/HD_ClaimArmysTreasure", {"targets": targets})
```

`ClaimTreasures` rule (dataclass, like others), budget from `treasure_model.chest_budget`:

```python
@dataclass
class ClaimTreasures:
    name: str = "claim_treasures"
    _targets: object = None

    @staticmethod
    def _pending(armies):
        out = []
        for a in armies or []:
            if any((p.get("treasures") or []) for p in (a.get("pawns") or [])):
                out.append({"index": int(a.get("index", 0)), "auid": str(a.get("uid"))})
        return out

    def applies(self, state: GameState, actions: Actions) -> bool:
        try:
            armies = actions.get_player_armys()
        except Exception:
            return False
        self._targets = self._pending(armies)
        return bool(self._targets)

    def act(self, actions: Actions) -> None:
        targets, self._targets = self._targets, None
        if not targets:
            return
        from nta_agent.execution.treasure_model import chest_budget
        budget = chest_budget(state=SimpleNamespaceState())  # see note
        try:
            actions.open_armys_treasure(targets[:budget] if budget < 10_000 else targets)
            actions.claim_armys_treasure(targets)
        except Exception:
            pass  # best-effort; never block the loop
```

Note: the rule has no `state` in `act`; budget-capping needs the tick state. Simplest: cap in `applies` (which has `state`) — store `self._targets = pending[:budget]` there using `chest_budget(state)`, and drop the `act` budget import. Implement that way (compute budget + slice in `applies`).

- [ ] **Step 4: Wire** into `RuleEngine.default` (add `ClaimTreasures()` after `OccupyCell`). Run `pytest tests/test_claim_treasures.py -q` → PASS.
- [ ] **Step 5: Full verify** `pytest -q && ruff check nta_agent tests && node --test --test-force-exit tools/battlesim/test/golden.test.js` → all green.
- [ ] **Step 6: Commit** `git add nta_agent/execution/actions.py nta_agent/execution/heuristics.py tests/test_claim_treasures.py && git commit -m "occupy: auto open/claim earned treasures (ClaimTreasures rule)"`

---

## Self-Review

**Spec coverage:** §3/§4 components → Tasks 1–4; §4 BrainService + §6 wiring/config → Task 5; §5 LLM contract → Task 4 (prompt+parse); §7 auto-treasure → Task 6; §9 tests → each task's tests. Error handling (§6) → Task 5 `BrainUnavailable`/except + Task 4 malformed→{}. Covered.

**Placeholder scan:** No TBD. Task 6 Step 3 flags the budget-cap belongs in `applies` (has `state`) not `act` — implement there; the illustrative `SimpleNamespaceState()` is called out to replace, not left as code. Task 5 Step 4 describes the runner refactor concretely (share one profile object).

**Type consistency:** `sanitize_edits(edits, profile, valid_army_uids)` (T2) used in T5. `digest(state, profile, armies)` (T3) used in T5. `propose(digest, profile, chat)` (T4) wrapped by T5 `llm_propose`. `BrainPolicy.should_call` (T1) used in T5. `targets=[{index,auid}]` (T6 actions) matches the rule. Profile mutated in place via `profile.army`/`profile.occupy` dicts (consistent with B1).
