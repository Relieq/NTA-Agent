# Gear Assignment (Chặng 2E-1) — Design

Date: 2026-09-12
Status: Approved (brainstorming) → ready for implementation plan
Parent: Chặng 2E (gear assignment + forge), sub-project 2E-1 (assignment). Depends on 2A/2B/2C.

## 1. Problem

Choosing which equipment a soldier wears is a taste-driven, human-reserved
decision (like unlock/policy). 2E-1 surfaces each pawn-type's current gear plus
the compatible owned equipment on the dashboard, lets the human assign, and has
the agent execute it on the live session. Forging (recast/lock/smelt) is a
separate, more interactive mechanic deferred to 2E-2.

## 2. Game mechanic (RE, verified)

- `player.configPawnMap: map(PawnConfigInfo)` keyed by pawn id (string);
  `PawnConfigInfo = {equipUid: string, skinId: int, attackSpeed: int}` — the
  current gear/skin/attack-speed config of each pawn type.
- `player.equips: EquipInfo[]` — owned equipment; `EquipInfo = {uid, id, attrs[],
  lastAttrs[], recastCount, nextForgeFree, lockEffect}`. `id` → `equipBase`/
  `equipText`.
- `equipBase[id].exclusive_pawn` — empty ⇒ usable by any player pawn; otherwise a
  restriction string listing the pawn(s) it is exclusive to.
- **Assign:** `game/HD_ChangeConfigPawnEquip{id: pawnId, equipUid, skinId,
  attackSpeed}` (S2C empty). To change only the equip, resend the pawn's current
  `skinId`/`attackSpeed` alongside the new `equipUid`.

## 3. Chosen approach (decisions locked)

- **Scope: gear assignment only.** Forge (`ForgeEquip`/`LockEquipEffect`/
  `InDoneForge`/`SmeltingEquip`) is deferred to 2E-2 — it is an iterative
  reroll loop that suits the game client better than a 1-tick file channel.
- **Human-reserved, proactive.** Unlike a ceri "pending slot", assignment is a
  choice the human makes anytime. It is a dedicated dashboard section, reusing the
  existing 2C file command channel (`commands.jsonl` + `commands.done`) with a new
  `equip` action. The command carries the current `skin_id`/`attack_speed` (echoed
  from the equipment view) so only the equip changes.
- **One command consumer.** `DecisionService` remains the single reader of
  `commands.jsonl`; it gains the `equip` dispatch and writes the equipment view —
  avoiding two services fighting over the same command file.

## 4. Architecture

### 4.1 `execution/equipment.py` (pure)
- `pawn_equipment(state, config) -> list[dict]` — for each entry of
  `player.configPawnMap`, produce:
  `{"pawn_id": int, "pawn_name": str, "current_equip_uid": str,
    "current_equip_name": str, "skin_id": int, "attack_speed": int,
    "options": [{"uid": str, "id": int, "name": str}]}`.
  Options = `player.equips` compatible with that pawn (see below). Names:
  `pawn_name` from `pawnText["name_<pawnId>"].vi`; equip name from
  `equipText["name_<equipId>"].vi` (fallback `.en`, then `#<id>`). Current equip
  name resolved by finding the owned equip whose `uid == equipUid`.
- `equip_name(config, equip_id) -> str` and `pawn_name(config, pawn_id) -> str`
  helpers.
- `_compatible(config, equip_id, pawn_id) -> bool`: `ex = equipBase[equip_id].
  exclusive_pawn`; return True if `ex` is empty/falsey, else `str(pawn_id)` appears
  among `ex` split on `,`/`|`. Unknown equip id → treated as compatible (server
  validates).

### 4.2 `execution/actions.py` (+1 method)
- `change_pawn_equip(pawn_id, equip_uid, skin_id=0, attack_speed=0) -> dict` —
  `game/HD_ChangeConfigPawnEquip{id, equipUid, skinId, attackSpeed}`.

### 4.3 `runtime/config.py` (+1 path)
- `RuntimeConfig.equipment_path` → `log_dir/"equipment.json"`.

### 4.4 `runtime/decision_service.py` (extend)
- In `tick(state)`: additionally write `pawn_equipment(state, config)` atomically
  to `cfg.equipment_path` (guarded, never raises into the loop).
- In `_execute(cmd)`: add `action == "equip"` →
  `actions.change_pawn_equip(int(cmd["pawn_id"]), cmd["equip_uid"],
  int(cmd.get("skin_id", 0) or 0), int(cmd.get("attack_speed", 0) or 0))`.
  Existing `select`/`reroll` unchanged; unknown actions still error + mark done.

### 4.5 `dashboard` (extend 2B/2C)
- `GET /api/equipment` → read `equipment.json` (`[]` when missing) via the
  existing `read_json_array`.
- `POST /api/command` accepts `action == "equip"` with `{pawn_id, equip_uid,
  skin_id?, attack_speed?}`; validates `pawn_id` and `equip_uid` present; appends
  a command carrying those fields (skin/attack default 0).
- Page: a "Trang bị lính" card polling `/api/equipment` — each pawn row shows its
  name + current equip and its compatible options as buttons; a click POSTs
  `{action:"equip", pawn_id, equip_uid, skin_id, attack_speed}` (skin/attack from
  the row) and shows "đã gửi · chờ agent".

## 5. Data flow

```
agent tick (DecisionService.tick):
  write decisions.json (2C)  +  write equipment.json (pawn_equipment)
  read_pending(commands.jsonl) → dispatch select/reroll/equip → mark_done
dashboard:
  GET /api/equipment → render "Trang bị lính"
  human clicks → POST /api/command {action:"equip", pawn_id, equip_uid, skin_id, attack_speed}
  → commands.jsonl → agent change_pawn_equip → next tick equipment.json reflects it
```

## 6. Error handling

- `ChangeConfigPawnEquip` server error → caught in `_execute`, logged
  `decision_error`, command marked done (human can retry).
- Incompatible/invalid choice → server rejects; surfaced via event feed.
- `equipment.json` write failure → guarded, logged, loop continues.
- Missing config → equipment view empty (names/options unavailable), consistent
  with the decisions path.
- POST validation: missing `pawn_id`/`equip_uid` → 400, nothing appended.

## 7. Testing

- **equipment.py:** `pawn_equipment` builds a row per configPawnMap entry with
  resolved names, current equip, and only compatible options; `_compatible`
  honors empty vs restricted `exclusive_pawn`; unknown ids fall back gracefully.
- **actions:** `change_pawn_equip` sends the right route+params (fake session).
- **decision_service:** `tick` writes `equipment.json`; an `equip` command calls
  `change_pawn_equip` with the echoed skin/attack and is marked done (not
  reprocessed); `select`/`reroll` still work.
- **dashboard:** `GET /api/equipment` returns the file; `POST` with
  `action:"equip"` appends a command with `pawn_id`/`equip_uid`; bad body → 400;
  the page contains the "Trang bị lính" section.

## 8. Out of scope (2E-2 and later)

- Forge / recast / lock-effect / smelt (`ForgeEquip`, `LockEquipEffect`,
  `InDoneForge`, `SmeltingEquip`) — 2E-2.
- Skin selection and attack-speed tuning as first-class choices (only preserved
  here, not changed).
- Auto-assignment heuristics (which gear is "best") — human-reserved by design;
  a future brain-layer concern.
