# Army/Squad Detail View + Dashboard Polish (Chặng A1) — Design

Date: 2026-09-12
Status: Approved (brainstorming) → ready for implementation plan
Parent: Track A (rich army/troop controls). A1 = read-only detail view; editing = A2. Depends on 2A/2B/2C/2E-1.

## 1. Problem

The dashboard shows aggregate counts but not the armies themselves. The user
needs a detailed per-army / per-troop view (squad order, level, attack speed,
equipped gear, state) — the foundation for later editing (A2) and for the
battle-sim advisor. This work also folds in three pieces of dashboard feedback:
wrong resource labels, missing option descriptions, and a monotone UI.

## 2. Game mechanic (RE, verified)

- `game/HD_GetPlayerArmys{}` → `{list: AreaArmyInfo[]}`.
- `AreaArmyInfo = {index, uid, name, pawns: AreaPawnInfo[], drillPawns[], state,
  enterDir, owner, marchSpeed, curingPawns[]}`. `pawns` order = the squad order.
- `AreaPawnInfo = {index, uid, point, id, lv, skinId, curAnger, attackSpeed,
  equip: EquipInfo, treasures[], buffs[], hp, armyUid, ..., isFight}`.
- Resource VN names (from `ui.json`, verified): `cereal`→"L.Thực", `timber`→"Gỗ",
  `stone`→"Đá", `iron`→"Sắt", `gold`→"Vàng", `exp_book`→"Sách EXP",
  `up_scroll`→"Quyển Trục", `fixator`→"Máy Cố Định". `stamina` has no resource
  label (it is a battle stat, not a stored currency) → not shown as a resource.
- Option descriptions: `policyText["desc_<id>"]`, `equipText["effect_<id>"]`
  (both `.vi`); `pawnText` has only names.

## 3. Chosen approach (decisions locked)

- **A1 is read-only.** Editing army/troop settings (attack speed, composition,
  grouping) is A2. This view is the shared foundation for A2 and the sim-advisor.
- **Throttled fetch.** Unlike `decisions.json`/`equipment.json` (derived locally
  from state each tick), the army list needs a network request
  (`GetPlayerArmys`). `DecisionService` fetches it on a throttle (`armies_every`
  ticks, default 6), guarded so a failure never kills the loop, and writes
  `armies.json` for the dashboard.
- **Fold the polish** into this dashboard pass: correct resource labels, per-
  option descriptions, and light restyling for section clarity.

## 4. Architecture

### 4.1 `execution/armies.py` (pure)
- `STATE_LABELS = {0: "rảnh", 1: "hành quân", 2: "đang đánh"}` (best-effort;
  unknown → `str(state)`).
- `army_view(armys: list[dict], config) -> list[dict]` — per `AreaArmyInfo`:
  `{uid, name, index, state, state_label, march_speed,
    pawns: [{uid, id, name, lv, attack_speed, equip_name}]}`.
  `name` from `pawnText["name_<id>"].vi` (fallback en/`#id`); `equip_name` from
  the pawn's `equip.id` via `equipText["name_<id>"].vi` (empty if no equip). Pawn
  order preserved from `pawns`.

### 4.2 `execution/actions.py` (+1 method)
- `get_player_armys() -> list[dict]` — `game/HD_GetPlayerArmys{}`; return
  `reply.get("list", []) or []`.

### 4.3 `execution/decisions.py` (option descriptions — polish)
- Each option in `pending_decisions` gains `"desc"`: for the `policy` track,
  `policyText["desc_<value>"].vi`; for `equip`, `equipText["effect_<value>"].vi`;
  for `pawn`, `""`. Fallback `""`. (Name behavior unchanged.)

### 4.4 `runtime/config.py` (+1 path)
- `RuntimeConfig.armies_path` → `log_dir/"armies.json"`.

### 4.5 `runtime/decision_service.py` (throttled army fetch)
- Add `armies_every: int = 6` and an internal tick counter. In `tick(state)`:
  when the counter hits the interval, `try: army_view(self.actions.
  get_player_armys(), self.config)` → write `armies.json` atomically; guard with
  try/except (it makes a network call) → on error log to stderr, never raise.
  decisions.json/equipment.json writes and command processing are unchanged.

### 4.6 `dashboard` (view + polish)
- `server.py`: `GET /api/armies` → `read_json_array(cfg.armies_path)`.
- `page.py`:
  - **Resources:** replace the label list with the correct VN names and the right
    fields — `cereal`→"L.Thực", `timber`→"Gỗ", `stone`→"Đá", `iron`→"Sắt",
    `gold`→"Vàng", `exp_book`→"Sách EXP", `up_scroll`→"Quyển Trục",
    `fixator`→"Máy Cố Định" (drop "Thể lực"/stamina).
  - **Decisions:** render each option's `desc` (a small muted line under the
    option buttons) when present.
  - **Đội quân section:** a card polling `/api/armies`; per army show name +
    state_label + march_speed, then its pawns in order as
    `name Lv<lv> · tốc <attack_speed> · <equip_name or "—">`.
  - **Restyle:** clearer section headers/spacing/accent so sections (esp. the new
    army + existing "Trang bị lính") are easy to distinguish. Inline CSS only.

## 5. Data flow

```
agent tick (DecisionService.tick):
  every armies_every ticks: get_player_armys() → army_view → write armies.json (guarded)
  (decisions.json + equipment.json each tick as before)
dashboard: GET /api/armies → render "Đội quân"; resources + decision descs updated
```

## 6. Error handling

- `GetPlayerArmys` request error → caught, logged to stderr; `armies.json` keeps
  its last content; loop continues.
- Missing config → names fall back to `#id`; view still lists armies.
- `armies.json` write failure → guarded, logged, loop continues.
- Missing `armies.json` on the dashboard → `[]` (empty section).

## 7. Testing

- **armies.py:** `army_view` builds a row per army with ordered pawns, resolved
  names, attack speed, equip name; unknown ids fall back; `state_label` maps
  known states and falls back for unknown.
- **actions:** `get_player_armys` sends the right route and returns `list`.
- **decisions.py:** options now carry `desc` — policy uses `desc_`, equip uses
  `effect_`, pawn is `""`; existing name/detection tests still pass.
- **decision_service:** on the throttled tick it writes `armies.json` from a fake
  `get_player_armys`; off-throttle ticks do not call it; a failing
  `get_player_armys` is swallowed (loop continues, other writes still happen).
- **dashboard:** `GET /api/armies` returns the file; the page contains the "Đội
  quân" section and uses the corrected resource labels; decision descs render.

## 8. Out of scope (A2 and later)

- Editing: `SetArmySpeed`, `ChangePawnArmy`/`ExchangePawnArmy`, army grouping /
  joint-march (`armyDists`/`GetBattleDist`, `isSameSpeed`), fort auto-support — A2.
- Battle-sim advisor (evaluate/search arrangements) — separate step.
- Pawn skill descriptions in decisions (pawn→skill chain) — later refinement.
