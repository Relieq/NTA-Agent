# Human-Decision Queue (Chặng 2C) — Design

Date: 2026-09-12
Status: Approved (brainstorming) → ready for implementation plan
Parent: Chặng 2, sub-project 2C (depends on 2A spine + 2B dashboard)

## 1. Problem

Some decisions are reserved for the human, not the rules or the LLM (see the
`nta-agent-human-in-loop` memory): which troop type to **unlock**, which
**policy** to research, and which **equipment type to unlock**. All three use the
same in-game "ceri" mechanic. The agent must **detect** a pending choice,
**surface** it on the dashboard, let the human **pick or reroll**, and then
**execute** their choice on the live session — never auto-deciding.

2A/2B connect agent→dashboard through files (agent writes, dashboard reads). 2C
adds the reverse direction (dashboard→agent) so a human click on one process
causes the agent process to act on its live MQTT session.

## 2. Game mechanic (RE, verified)

- `player.pawnSlots`, `policySlots`, `equipSlots` are each `map(CeriSlotInfo)`,
  `CeriSlotInfo = {selectIds: int[], id: int, resetCount: int, lv: int}`.
- A slot is **pending a human choice** iff `id <= 0 and selectIds` is non-empty
  (verified in client: `this.id <= 0 && this.selectIds.length > 0`). `selectIds`
  are the offered choices (ceri row ids); each `ceri.json` row has `value` (the
  thing unlocked) + `weight`/`cost`/`need_lv`.
- **Pick:** `GAME_HD_StudySelect{lv, id, tp}` → `{slots: map(CeriSlotInfo)}`.
- **Reroll:** `GAME_HD_CeriResetSelect{lv, tp}` → `{gold, selectIds:int[],
  resetCount, useGold}` — first reroll free, later costs gold.
- `tp` selects the track (pawn / policy / equip). Slots unlock sequentially and
  are gated by `lv`.
- **Known-unknown pinned in implementation (Task 1):** the integer `tp` per track.
  It will be read from the client's `StudySelectPnl` controller and/or confirmed
  live; the design isolates it in one `TRACKS` table.

Out of scope for 2C (→ sub-project 2E): assigning owned gear to soldiers
(`GAME_HD_ChangeConfigPawnEquip`) and forging (`FORGEEQUIP`/`LOCKEQUIPEFFECT`/
`SMELTINGEQUIP`) — a different mechanic (inventory + per-pawn UI), not a
pending-slot select.

## 3. Chosen approach (decisions locked)

- **Scope:** the ceri decision-queue over **three tracks** — pawn unlock, policy
  research, equipment-type unlock. All share the StudySelect/CeriResetSelect
  mechanic; they differ only by `tp` and by the config text table used for names.
- **Command channel:** **file-based** (consistent with the 2A/2B seam). The agent
  writes `decisions.json`; the dashboard appends to `commands.jsonl`; the agent
  records processed ids in `commands.done` for exactly-once execution across
  restarts (a select is one-shot; a reroll spends gold — never double-run).
- The agent **never auto-resolves** these decisions; it only surfaces and
  executes the human's command.

## 4. Architecture

### 4.1 `execution/decisions.py` (pure)
- `Decision` dataclass: `track: str` ("pawn"|"policy"|"equip"), `tp: int`,
  `slot_key: str`, `lv: int`, `reset_count: int`,
  `options: list[dict]` (`{"ceri_id", "value", "name"}`).
- `TRACKS: dict[str, tuple[int, str]]` — maps the player slot-map field
  (`"pawnSlots"`/`"policySlots"`/`"equipSlots"`) to `(tp, text_table)` where
  text_table is `"pawnText"`/`"policyText"`/`"equipText"`. (tp values pinned in
  Task 1.)
- `pending_decisions(state, config) -> list[Decision]` — for each track, scan the
  slot map for slots with `id <= 0 and selectIds`; resolve each selectId via
  `ceri.json` → `value`, then a Vietnamese `name` from the track's text table
  (`name_<value>` `.vi`, fallback `.en`, fallback `#<value>`). Pure; needs only a
  loaded config.

### 4.2 `execution/actions.py` (+2 hands methods)
- `study_select(lv, ceri_id, tp) -> dict` — `game/HD_StudySelect{lv, id, tp}`;
  apply the returned `slots` back into `state.raw["player"]` (per-track map).
- `ceri_reset(lv, tp) -> dict` — `game/HD_CeriResetSelect{lv, tp}`; update the
  affected slot's `selectIds`/`resetCount` in state from the reply.

### 4.3 `runtime/commands.py` (file command channel)
- `append_command(path, cmd: dict) -> str` — assign a unique `id` (uuid4 hex),
  write one JSON line, return the id. Used by the dashboard.
- `read_pending(commands_path, done_path) -> list[dict]` — parse `commands.jsonl`,
  drop malformed lines and ids already in `done_path`.
- `mark_done(done_path, cmd_id)` — append an id to `commands.done`.

### 4.4 `runtime/decision_service.py`
- `DecisionService(actions, config, cfg)` with `tick(state) -> None`:
  1. write `pending_decisions(state, config)` (as dicts) atomically to
     `cfg.log_dir/"decisions.json"` (guarded — never raise into the loop);
  2. for each `read_pending(...)` command: dispatch `select` →
     `actions.study_select(lv, ceri_id, tp)` or `reroll` →
     `actions.ceri_reset(lv, tp)`; log an event (ok/err with reason); `mark_done`
     regardless of ok/err (a failed pick is not retried forever; the human can
     re-issue). Malformed/unknown-action commands are logged and marked done.
- Wired into `runner.run`'s `on_tick` (after the snapshot/eventlog step). The
  service loads `GameConfig` once; if config is absent, decisions are empty and
  commands still execute (names just missing).

### 4.5 `dashboard` (extend 2B)
- `GET /api/decisions` → read `decisions.json` (`[]` when missing).
- `POST /api/command` → parse a JSON body `{action, track, lv, ceri_id?}`,
  validate (`action` in {select, reroll}; `select` needs `ceri_id`), then
  `append_command(cfg.commands_path, ...)`; return `{"ok": true, "id": ...}` (400
  on bad body). This makes the dashboard no longer read-only; it still binds
  `127.0.0.1` only.
- Page: a "Quyết định đang chờ" panel polling `/api/decisions` — each decision
  shows its track + options as buttons (name) and a "Làm mới (reroll)" button
  (labeled free/gold from `reset_count`); a click POSTs the command and shows
  "đã gửi · chờ agent". Existing monitoring stays.
- `RuntimeConfig` gains `commands_path` (`log_dir/"commands.jsonl"`),
  `commands_done_path` (`log_dir/"commands.done"`), `decisions_path`
  (`log_dir/"decisions.json"`).

## 5. Data flow

```
agent tick (DecisionService.tick):
  pending_decisions(state, config) → write decisions.json
  read_pending(commands.jsonl, commands.done) → for each:
     select → actions.study_select(lv, id, tp)   |  reroll → actions.ceri_reset(lv, tp)
     → event log + mark_done
dashboard:
  GET /api/decisions → render pending panel
  human clicks → POST /api/command → append_command(commands.jsonl)
```
One-tick latency; state.json + decisions.json reflect the result next tick.

## 6. Error handling

- StudySelect/CeriReset server error (e.g. insufficient gold) → caught, logged as
  a `decision_error` event with the ecode/message, command marked done (surfaced
  to the human via the event feed; they can retry).
- Malformed command lines / unknown actions → skipped/marked done, logged.
- `decisions.json` write failure → guarded, logged, loop continues.
- `commands.done` guarantees exactly-once even across agent restarts.
- POST body validation returns 400 without appending.

## 7. Testing

- **decisions.py:** `pending_decisions` finds only `id<=0 && selectIds` slots
  across the three tracks, resolves option names via ceri+text (fake config),
  ignores chosen/empty slots; unknown value → `#<value>`.
- **actions:** `study_select`/`ceri_reset` send the right route+params (fake
  session) and update `state.raw.player` slots from the reply.
- **commands.py:** `append_command` writes a line with a unique id; `read_pending`
  skips malformed lines and already-done ids; `mark_done` appends.
- **decision_service:** `tick` writes decisions.json, executes a queued `select`
  (calls `study_select` once) and a `reroll`, marks them done, and does not
  reprocess on the next tick; a raising action is caught + marked done.
- **dashboard:** `GET /api/decisions` returns the file; `POST /api/command`
  appends a command and returns its id; bad body → 400. (threaded server + urllib)

## 8. Out of scope (2E and later)

- Gear assignment (`ChangeConfigPawnEquip`) and forging — sub-project 2E.
- LLM/brain involvement — these decisions are human-reserved by design.
- Captcha (2D).
