# Buffer Leveling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Level a chosen group's pawns inside agent-managed buffer armies and swap them into the main
armies on a cell next to them, so the main group keeps farming/digging.

**Architecture:** A pure planner (`buffer_plan.py`) computes demand per pawn type, exp-book/time costs from
`pawnAttr`, and a buffer proposal; the player confirms it on the dashboard. A deterministic rule
(`BufferLeveling`) executes: one-time setup (merge/rename/recruit/dismiss as approved), continuous
leveling at the city, rendezvous on an owned cell adjacent to the target main army, type-for-type
`ExchangePawnArmy`, return home. `OccupyCell` learns "a member is away swapping".

**Tech Stack:** Python 3.12 (venv `.venv`), pytest, ruff; Vue 3 no-build dashboard; game API via `Actions`.

**Spec:** `docs/superpowers/specs/2026-09-25-buffer-leveling-design.md`

## Global Constraints

- Start executing only after the current dig finishes and its run is checked for errors (user, 2026-09-25).
- Mode is chosen **per group** (`direct` | `buffer`), not per army.
- Swaps are **same pawn type**, weak (lv < target) ↔ ready (lv ≥ target); `ExchangePawnArmy` both armies on one cell, cell not in battle.
- `PawnLving` only at the main city, army not marching; queue ≤ 6 per city; keep it topped up (finish one → queue one).
- Costs from `pawnAttr[id*1000+lv]`: `lv_cost` CType 7 = exp books, `lv_time` seconds, `lv_cond` `4,2004,N` = Trại Lính ≥ N.
- A cell holds ≤ 5 armies; the buffer waits on an **owned** cell 4-adjacent to the main army's cell with room.
- `DismissArmy` loses pawns → only armies the player explicitly approved. No enemy-distance check for now.
- While one member is away swapping: the others attack only if the sim is clean (≤ `occupy.max_loss`), else wait; only the **whole** group may mark a dig cell hard.
- Proposal is computed deterministically (`buffer_plan.propose`), shown to the brain digest and the dashboard; the player confirms (no auto-apply).
- Every failed move/swap/level is logged with its ecode (`swap_error` / `rally_error` / rule error) — never swallowed.
- Commit per task on a branch; merge `--no-ff` to master after the task set is green. Commit trailer:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` + `Claude-Session: https://claude.ai/code/session_01BVFc86868epnzqCQQrn4yj`.

## File Structure

| File | Responsibility |
|---|---|
| `nta_agent/execution/buffer_plan.py` (new) | Pure: costs, demand, proposal, swap pairing, rendezvous cell |
| `nta_agent/runtime/buffers.py` (new) | `buffers.json` state (approved plan + per-buffer phase), atomic IO |
| `nta_agent/runtime/config.py` | `buffers_path` |
| `nta_agent/execution/profile.py` | `leveling.groups` schema/defaults |
| `nta_agent/execution/heuristics.py` | new `BufferLeveling` rule; `Leveling` only for `direct` groups; `OccupyCell` away-member rule |
| `nta_agent/runtime/runner.py` | wire the rule + sources |
| `nta_agent/brain/digest.py` | `leveling_needs` (demand + proposal) |
| `nta_agent/dashboard/server.py` | `GET /api/leveling`, `POST /api/leveling/confirm` |
| `nta_agent/dashboard/static/components/LevelingConfigPanel.js` | groups + mode + proposal + buffer status |
| `tests/test_buffer_plan.py`, `tests/test_buffers_state.py`, `tests/test_buffer_leveling_rule.py`, `tests/test_dig_select.py`, `tests/test_dashboard_leveling.py` | tests |

---

### Task 1: Costs and demand (`buffer_plan.py`)

**Files:** Create `nta_agent/execution/buffer_plan.py`; Test `tests/test_buffer_plan.py`

**Interfaces — Produces:**
- `level_step(attr_rows, pawn_id, lv) -> dict | None` → `{"books": int, "time_s": int, "barracks_lv": int}` (None when no next level)
- `pawn_cost(attr_rows, pawn_id, lv_from, lv_to, barracks_lv) -> dict` → `{"books", "time_s", "blocked_at": int|None}`
- `demand(armies, target_lv) -> dict[int, list[dict]]` → pawn type → weak pawns `{uid, army_uid, lv}`

- [ ] **Step 1: Write the failing tests**

```python
from nta_agent.execution.buffer_plan import demand, level_step, pawn_cost

ROWS = {  # pawnAttr subset (live values 2026-09-25)
    3305001: {"lv_cost": "1,0,346|7,0,1", "lv_time": 488, "lv_cond": "4,2004,1"},
    3305002: {"lv_cost": "1,0,554|7,0,1", "lv_time": 732, "lv_cond": "4,2004,5"},
    3305003: {"lv_cost": "1,0,886|7,0,2", "lv_time": 1098, "lv_cond": "4,2004,10"},
    3202002: {"lv_cost": "1,0,461|7,0,2", "lv_time": 698, "lv_cond": "4,2004,5"},
}

def test_level_step_reads_books_time_and_barracks():
    assert level_step(ROWS, 3305, 1) == {"books": 1, "time_s": 488, "barracks_lv": 1}
    assert level_step(ROWS, 3202, 2) == {"books": 2, "time_s": 698, "barracks_lv": 5}
    assert level_step(ROWS, 3305, 9) is None

def test_pawn_cost_sums_steps_and_stops_at_the_barracks_gate():
    assert pawn_cost(ROWS, 3305, 1, 3, barracks_lv=13) == {"books": 2, "time_s": 1220, "blocked_at": None}
    assert pawn_cost(ROWS, 3305, 1, 4, barracks_lv=6) == {"books": 2, "time_s": 1220, "blocked_at": 3}

def test_demand_groups_weak_pawns_by_type():
    armies = [{"uid": "A", "pawns": [{"uid": "a1", "id": 3305, "lv": 1}, {"uid": "a2", "id": 3305, "lv": 3}]},
              {"uid": "B", "pawns": [{"uid": "b1", "id": 3202, "lv": 2}]}]
    d = demand(armies, target_lv=3)
    assert d == {3305: [{"uid": "a1", "army_uid": "A", "lv": 1}],
                 3202: [{"uid": "b1", "army_uid": "B", "lv": 2}]}
```

- [ ] **Step 2:** Run `.venv/Scripts/python.exe -m pytest tests/test_buffer_plan.py -q` → FAIL (module missing).
- [ ] **Step 3: Implement**

```python
"""Leveling via buffer armies — pure planning (no I/O). See the spec."""
from __future__ import annotations

EXP_BOOK = 7  # CType


def _types(s: str) -> dict[int, int]:
    out: dict[int, int] = {}
    for part in (s or "").split("|"):
        bits = part.split(",")
        if len(bits) == 3 and bits[0].strip():
            out[int(bits[0])] = out.get(int(bits[0]), 0) + int(bits[2])
    return out


def level_step(rows, pawn_id: int, lv: int) -> dict | None:
    row = rows.get(int(pawn_id) * 1000 + int(lv))
    if not row or not row.get("lv_cost"):
        return None
    cond = [int(x) for x in str(row.get("lv_cond") or "0,0,0").split(",")]
    return {"books": _types(row["lv_cost"]).get(EXP_BOOK, 0), "time_s": int(row.get("lv_time") or 0),
            "barracks_lv": cond[2] if len(cond) == 3 and cond[1] == 2004 else 0}


def pawn_cost(rows, pawn_id, lv_from, lv_to, barracks_lv) -> dict:
    books = time_s = 0
    for lv in range(int(lv_from), int(lv_to)):
        step = level_step(rows, pawn_id, lv)
        if step is None or step["barracks_lv"] > barracks_lv:
            return {"books": books, "time_s": time_s, "blocked_at": lv}
        books += step["books"]
        time_s += step["time_s"]
    return {"books": books, "time_s": time_s, "blocked_at": None}


def demand(armies, target_lv: int) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for a in armies:
        for p in a.get("pawns") or []:
            if int(p.get("lv", 0) or 0) < target_lv:
                out.setdefault(int(p["id"]), []).append(
                    {"uid": str(p["uid"]), "army_uid": str(a["uid"]), "lv": int(p.get("lv", 0) or 0)})
    return out
```

- [ ] **Step 4:** Tests PASS; `ruff check`.
- [ ] **Step 5:** Commit `feat(leveling): buffer planner — costs from pawnAttr, demand by pawn type`.

### Task 2: Proposal (`propose`)

**Files:** Modify `nta_agent/execution/buffer_plan.py`; Test `tests/test_buffer_plan.py`

**Interfaces — Produces:** `propose(group_armies, spare_armies, target_lv, *, rows, barracks_lv, exp_book, army_count, army_cap, buffer_size=9) -> dict` →
```
{"buffers": [{"name": "Nâng Cấp 1", "base_uid": str|"", "types": {pawn_id: n},
              "merge": [{"from_uid", "pawn_uid", "pawn_id"}], "recruit": {pawn_id: n}}],
 "dismiss": [army_uid],          # only suggested; never executed without approval
 "books_needed": int, "books_have": int, "time_s": int, "blocked": [pawn_id], "notes": [str]}
```
Rules: one buffer per **dominant weak pawn type** (types covering ≥ 1 weak pawn), sized `min(buffer_size, weak count of that type)`;
reuse the spare army holding the most pawns of that type as `base_uid` (renamed), fill from other spares
(`merge`), recruit the rest; if new buffers exceed `army_cap - army_count`, suggest dismissing spare armies
with the fewest pawns not used by `merge`. `books_needed` = cost to target for every weak group pawn **plus** the
buffer's own pawns; `time_s` = total leveling seconds / 6 (queue kept full).

- [ ] **Step 1: Failing test (live example)**

```python
def test_propose_live_example_one_imp_buffer_from_spares():
    imp = lambda u, lv=1: {"uid": u, "id": 3305, "lv": lv}
    group = [{"uid": f"G{i}", "pawns": [imp(f"g{i}{k}") for k in range(9)]} for i in range(4)]
    spares = [{"uid": "D5", "name": "D5", "pawns": [imp(f"d5{k}") for k in range(6)] +
               [{"uid": f"d5c{k}", "id": 3201, "lv": 1} for k in range(3)]},
              {"uid": "D1", "name": "D1", "pawns": [imp(f"d1{k}") for k in range(4)]}]
    p = propose(group, spares, 3, rows=ROWS, barracks_lv=13, exp_book=49, army_count=9, army_cap=9)
    (b,) = p["buffers"]
    assert b["base_uid"] == "D5" and b["types"] == {3305: 9}
    assert len(b["merge"]) == 3 and all(m["from_uid"] == "D1" for m in b["merge"])
    assert b["recruit"] == {}
    assert p["books_needed"] == 2 * 36 + 2 * 9 and p["books_have"] == 49
    assert p["dismiss"] == []          # D5 reused: no new army slot needed
```

- [ ] **Step 2:** FAIL. **Step 3:** implement `propose` per the rules above (sort spares by count of the type desc,
  then uid). **Step 4:** PASS + ruff. **Step 5:** Commit `feat(leveling): buffer proposal from spare armies`.

### Task 3: Swap pairing and rendezvous cell

**Files:** Modify `buffer_plan.py`; Test `tests/test_buffer_plan.py`

**Interfaces — Produces:**
- `swap_pairs(main_army, buffer_army, target_lv) -> list[tuple[str, str]]` → `(weak_uid, ready_uid)` same type, weakest first
- `pick_target(group_armies, buffer_army, target_lv) -> str | None` → main army uid with most pairs (ties: lowest total lv)
- `meeting_cell(main_index, owned, occupancy, cap=5, width=600) -> int | None` → owned 4-neighbour with `occupancy < cap`, lowest index on ties

- [ ] **Step 1: Failing tests**

```python
def test_swap_pairs_same_type_weakest_first():
    main = {"uid": "M", "pawns": [{"uid": "m1", "id": 3305, "lv": 2}, {"uid": "m2", "id": 3305, "lv": 1},
                                  {"uid": "m3", "id": 3202, "lv": 1}]}
    buf = {"uid": "B", "pawns": [{"uid": "b1", "id": 3305, "lv": 3}, {"uid": "b2", "id": 3305, "lv": 3},
                                 {"uid": "b3", "id": 3305, "lv": 2}]}
    assert swap_pairs(main, buf, 3) == [("m2", "b1"), ("m1", "b2")]   # no 3202 in buffer; b3 not ready

def test_meeting_cell_is_owned_adjacent_with_room():
    W = 600; c = 10 * W + 10
    owned = {c - 1, c + 1, c + W}
    assert meeting_cell(c, owned, {c - 1: 5, c + 1: 2}) == c + 1
    assert meeting_cell(c, set(), {}) is None
```

- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** Commit `feat(leveling): swap pairing, target choice, meeting cell`.

### Task 4: Buffer state + profile groups

**Files:** Create `nta_agent/runtime/buffers.py`; Modify `runtime/config.py` (`buffers_path` → `log_dir/"buffers.json"`),
`execution/profile.py` (default `leveling.groups = []`); Test `tests/test_buffers_state.py`

**Interfaces — Produces:**
- `profile.leveling["groups"]`: `[{"armies": [uid], "mode": "direct"|"buffer", "target_lv": int}]`
  (legacy: no groups ⇒ one `direct` group = active formation, current behaviour)
- `buffers.load(path) -> dict` / `buffers.save(path, data)` atomic; shape
  `{"proposal": dict|None, "approved": bool, "setup_done": bool,
    "buffers": {uid: {"name", "phase": "leveling"|"travel"|"wait"|"swap"|"home", "target": uid|None, "cell": int|None}}}`
- `buffers.approve(path)` sets `approved=True` (dashboard)

- [ ] Tests: round-trip, atomic write (tmp + `os.replace`), missing file → defaults, legacy profile ⇒ `groups == []`.
- [ ] Implement, PASS, commit `feat(leveling): buffer state file + leveling groups in profile`.

### Task 5: `BufferLeveling` rule — setup + continuous leveling

**Files:** Modify `nta_agent/execution/heuristics.py` (new dataclass rule after `Leveling`), `RuleEngine.default`
(insert `BufferLeveling(profile=profile)` right after `Leveling`); Test `tests/test_buffer_leveling_rule.py`

**Interfaces:**
- Consumes: Task 1–4 functions; `actions.change_pawn_army(index, army_uid, pawn_uid, new_army_uid)`,
  `actions.rename_army(index, uid, name)`, `actions.drill_pawn(bu, pawn_id, army_uid=…, army_name=…)`,
  `actions.dismiss_army(index, uid)`, `actions.pawn_lving(index, army_uid, pawn_uid)`,
  `army_health.leveling_pawn_uids(state)`, `is_idle`.
- Produces: rule attrs `state_path`, `on_event`; events `buffer_setup`, `buffer_level`.

Behaviour per tick (one game action per tick, like `Leveling`):
1. No `buffer` group or not `approved` → inert.
2. Setup (until `setup_done`): bring each spare named in the proposal to the city (`move_cell_army`), then at the
   city: `change_pawn_army` merges, `rename_army` base → buffer name, `drill_pawn` recruits (into the buffer by uid,
   or `army_name` when the buffer is new), `dismiss_army` **only** uids in the approved `dismiss` list.
3. Leveling: for buffers at the city and idle, queue the lowest-lv pawn `< target` not already queued while the
   city queue has `< 6` entries (count from `pawnLevelingQueues` at `index == main`). Books/`lv_cond` checked with
   `pawn_cost`; skip blocked.

- [ ] Tests (FakeActions like `tests/test_leveling_rule.py`): inert until approved; setup order (merge before rename,
  rename before level); dismiss only approved; tops up the queue to 6, never 7; skips queued pawns.
- [ ] Implement, PASS, ruff, commit `feat(leveling): BufferLeveling setup + continuous leveling`.

### Task 6: `BufferLeveling` — rendezvous and swap

**Files:** Modify `heuristics.py` (`BufferLeveling`); Test `tests/test_buffer_leveling_rule.py`

Behaviour:
1. `phase == leveling` and `swap_pairs(pick_target(...))` non-empty with ≥ `min_pairs` (default = all ready pawns
   of that type, ≥ 1) → `phase = travel`, `target = main uid`.
2. `travel`: `cell = meeting_cell(main.index, owned, occupancy)`; if buffer idle and `buffer.index != cell` →
   `move_cell_army([buffer], cell)`; main army moved to another cell ⇒ recompute `cell` next tick (approach).
3. Buffer on `cell` and main army **idle** → `move_cell_army([main], cell)`; `phase = swap`.
4. `swap`: both on `cell`, idle → one `exchange_pawn_army(cell, main_uid, weak, ready, army_uid2=buffer_uid)` per tick
   until pairs exhausted → `phase = home`, main army released (OccupyCell gathers it back via `dig_gather`/rally).
5. `home`: `move_cell_army([buffer], main_city)` → `phase = leveling` on arrival.
6. Every exception → event `swap_error {ecode, stage, armies}` + cooldown; 500080/500020 = busy, retry later.
- Exposes `away_uids() -> set[str]` (main armies currently in `swap`/walking to the meeting cell) and
  `buffer_uids() -> set[str]`.

- [ ] Tests: target choice; approach re-targets when main moves; main walks only when idle; one exchange per tick with
  the right `(index, uid1, uid2, army_uid2)`; errors logged with ecode; completes to `home` → `leveling`.
- [ ] Implement, PASS, commit `feat(leveling): buffer rendezvous next to the main army + same-type swaps`.

### Task 7: OccupyCell — member away swapping; Leveling only for `direct`

**Files:** Modify `heuristics.py` (`OccupyCell._dig_select`, `applies`; `Leveling.applies`), `runtime/runner.py`;
Test `tests/test_dig_select.py`, `tests/test_leveling_rule.py`

**Interfaces:** `OccupyCell.away_source` (callable → set of uids away swapping), `OccupyCell.buffer_source`
(callable → buffer uids, never used for occupy); runner wires both from the `BufferLeveling` rule instance.

Rule change in `_dig_select` (and the farm/expansion group path):
- members away (in `away_source()`) are excluded from `members`; if the remaining members are idle + co-located and a
  plan with **all present members** is clean → attack; else wait (return None, **no** hard report);
- hard report only when **no member is away** (existing whole-group rule).
- `Leveling.applies`: only groups with `mode == "direct"` (legacy: no groups ⇒ direct, unchanged).

- [ ] Tests: away member + clean with 4 → plan with 4; away member + lossy → None and `hard == []`; no away → unchanged
  behaviour (existing tests stay green); Leveling inert for a `buffer` group.
- [ ] Implement, PASS, commit `feat(leveling): group attacks without the member that is swapping when clean`.

### Task 8: Brain digest + dashboard (proposal, confirm, status)

**Files:** Modify `brain/digest.py` (`leveling_needs`: per group `{mode, target_lv, weak_by_type, books_needed,
books_have, time_s, proposal}`), `dashboard/server.py` (`read_leveling(cfg)`, `confirm_leveling(cfg)`; routes
`GET /api/leveling`, `POST /api/leveling/confirm`), `LevelingConfigPanel.js`; Test `tests/test_dashboard_leveling.py`,
`tests/test_dashboard_components.py`

- The agent writes the proposal into `buffers.json` each time demand changes (BufferLeveling, no game action);
  the dashboard shows: groups (armies checkboxes from `/api/armies`, mode radio, target lv), the proposal
  (buffers + merges + recruits + **dismiss in red** + books needed/have + ETA), **Xác nhận** → `approved=True`,
  and per-buffer status (phase, target, ready pawns).
- [ ] Tests: `read_leveling` defaults/file; confirm sets approved; component strings (`/api/leveling`, `Xác nhận`,
  `Nâng bằng đội dư`, `Nâng trực tiếp`); digest contains `leveling_needs`.
- [ ] Implement, PASS, commit `feat(leveling): proposal + confirm + buffer status on the dashboard`.

### Task 9: Flexible types with spare armies at the city (P2)

**Files:** `buffer_plan.py` (`reshape(buffer, target_main, spares_at_city) -> list[(buffer_pawn_uid, spare_uid, spare_pawn_uid)]`),
`BufferLeveling` (before `travel`, at the city: exchange buffer pawns of an unneeded type for spare pawns of the
needed type, same lv or higher, one per tick); Test `tests/test_buffer_plan.py`, rule test.

- [ ] Test: IMP buffer serving an 8 IMP + 1 hunter army swaps one ready IMP for a hunter from a spare at the city.
- [ ] Implement, PASS, commit `feat(leveling): reshape the buffer's types with spare armies at the city`.

### Task 10: Verify + docs

- [ ] Full suite + ruff; restart dashboard (server.py changed) and agent via the dashboard API.
- [ ] **Live check with the player's go:** one `ExchangePawnArmy` between two armies on the same non-city owned cell
  (the engine read is the client's server mirror) — record the result in `docs/re/game-api.md`.
- [ ] Preview-only: the proposal for the live group (Đội 1–5, spares D1/D5/D6/D7) — no approve by the agent.
- [ ] README feature blurb (VI/EN/ZH), memory `nta-agent-forge-leveling` updated (buffer mode, costs, rules).
- [ ] Merge `--no-ff` to master; report to the user in Vietnamese.

## Self-review

- Spec coverage: modes per group (T4/T7/T8), brain proposes + user confirms (T2/T8 — deterministic proposal surfaced to
  brain + dashboard), book/time estimate (T1/T2), continuous queue (T5), rendezvous/approach/swap (T3/T6), 4-of-5 rule
  (T7), flexible types (T9), live check + errors logged (T6/T10), twin groups = out of scope (spec P3).
- Types: `swap_pairs`/`pick_target`/`meeting_cell` names reused verbatim in T6; `away_source`/`buffer_source` in T7.
