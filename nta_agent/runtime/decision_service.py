"""Per-tick service: publish pending decisions + execute human commands."""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import asdict
from pathlib import Path

from nta_agent.execution.armies import army_view
from nta_agent.execution.decisions import pending_decisions
from nta_agent.execution.equipment import pawn_equipment
from nta_agent.runtime.commands import mark_done, read_pending

_TRACK_TP = {"pawn": 2, "policy": 1, "equip": 3}
_ECODE_RE = re.compile(r"ecode\.(\d+)")


def ecode_reason(config, err: str) -> str:
    """Human-readable meaning of an ecode.NNN inside an error string ('' if none)."""
    m = _ECODE_RE.search(err or "")
    if not m or config is None:
        return ""
    code = int(m.group(1))
    try:
        tbl = config.table("ecode")
    except Exception:
        return ""
    row = tbl.get(code) or tbl.get(str(code)) or {}
    return row.get("vi") or row.get("en") or ""


class DecisionService:
    def __init__(self, actions, config, cfg, on_event=None, armies_every=6, profile=None):
        self.actions = actions
        self.config = config
        self.cfg = cfg
        self._on_event = on_event or (lambda *a: None)
        self.armies_every = armies_every
        self._armies_counter = 0
        self.profile = profile  # shared live Profile for profile_edit commands
        from nta_agent.runtime.rename_queue import RenameQueue
        self.renames = RenameQueue(getattr(cfg, "pending_renames_path", None)
                                   or Path(cfg.commands_path).with_name("pending_renames.json"))
        from nta_agent.runtime.dismiss_queue import DismissQueue
        self.dismissals = DismissQueue(Path(cfg.commands_path).with_name("pending_dismissals.json"))
        # {pawn_id: equip_uid} the player chose on the dashboard: kept so armies that
        # were marching (the game only equips idle armies) get it once they are idle
        self._equip_sync_path = Path(cfg.commands_path).with_name("equip_sync.json")

    def _equip_choices(self) -> dict:
        try:
            return {str(k): str(v) for k, v in
                    json.loads(self._equip_sync_path.read_text(encoding="utf-8")).items()}
        except (OSError, ValueError, AttributeError):
            return {}

    def _sync_equips(self, armies) -> None:
        """Equip every IDLE army's pawns of a chosen type that still wear something
        else: one ChangePawnAttr per army (syncEquip 2 = that army), keeping the
        pawn's own attack speed (the engine sets it from the request)."""
        choices = self._equip_choices()
        if not choices:
            return
        for a in armies or []:
            if int(a.get("state", 0) or 0) != 0:
                continue  # marching / fighting: the game would skip or refuse it
            for pid, uid in choices.items():
                p = next((q for q in a.get("pawns") or []
                          if str(int(q.get("id", 0) or 0)) == pid
                          and str(((q.get("equip") or {}) if isinstance(q.get("equip"), dict)
                                   else {}).get("uid") or "") != uid), None)
                if p is None:
                    continue
                try:
                    self.actions.change_pawn_attr(
                        int(a.get("index", 0) or 0), str(a.get("uid")), str(p.get("uid")), uid,
                        sync_equip=2, skin_id=0, attack_speed=int(p.get("attackSpeed", 0) or 0))
                    self._on_event("equip_sync", {"army": a.get("name") or a.get("uid"),
                                                  "pawn_id": int(pid), "equip_uid": uid})
                except Exception as e:  # e.g. the army started a battle meanwhile
                    self._on_event("equip_sync_error", {"army": a.get("name") or a.get("uid"),
                                                        "error": str(e)[:160]})

    def _write_decisions(self, state) -> None:
        from nta_agent.runtime import world_random
        pools = world_random.load(self.cfg.world_random_path)             if hasattr(self.cfg, "world_random_path") else {}
        data = [asdict(d) for d in pending_decisions(state, self.config, pools=pools)]
        path = Path(self.cfg.decisions_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)

    def _write_equipment(self, state) -> None:
        data = pawn_equipment(state, self.config)
        path = Path(self.cfg.equipment_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)

    def _write_armies(self) -> None:
        armies = self.actions.get_player_armys()
        self._sync_equips(armies)
        data = army_view(armies, self.config)
        path = Path(self.cfg.armies_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)

    def _execute(self, cmd: dict) -> None:
        action = cmd.get("action")
        lv = int(cmd.get("lv", 0) or 0)
        if action == "profile_edit":
            if self.profile is not None:
                from nta_agent.execution.profile import apply_edits
                apply_edits(self.profile, cmd.get("edits") or {})
            return
        if action == "equip":
            pawn_id = int(cmd["pawn_id"])
            equip_uid = cmd["equip_uid"]
            skin_id = int(cmd.get("skin_id", 0) or 0)
            atk = int(cmd.get("attack_speed", 0) or 0)
            # 1) config = default for pawns drilled later
            self.actions.change_pawn_equip(pawn_id, equip_uid, skin_id, atk)
            # 2) remember the choice, then equip the pawns already on the field. The
            # game only equips idle armies (and syncEquip 1 only those in the SAME
            # cell), so each idle army is done now and the rest when they are idle.
            choices = self._equip_choices()
            choices[str(pawn_id)] = str(equip_uid)
            self._equip_sync_path.parent.mkdir(parents=True, exist_ok=True)
            self._equip_sync_path.write_text(json.dumps(choices), encoding="utf-8")
            self._sync_equips(self.actions.get_player_armys())
            return
        if action == "build_fort":
            # User picked an owned cell in the fort zone -> build a Cứ Điểm there.
            # A fort is a city-type structure (ui=BuildCity): use CreateCity, NOT
            # AddAreaBuild (which rejects it with ecode.500009).
            from nta_agent.runtime.fort_service import FORT_BUILD_ID
            self.actions.create_city(int(cmd["index"]), FORT_BUILD_ID)
            return
        if action == "smelt":
            # confirmed by the player on the dashboard (never on the agent's own)
            self.actions.smelting_equip(str(cmd["main_uid"]),
                                        [int(i) for i in cmd.get("vice_ids") or []])
            return
        if action == "restore_smelt":
            self.actions.restore_smelt_equip(str(cmd["main_uid"]))
            return
        if action == "dismiss":
            # the player CONFIRMED this on the dashboard; the queue waits for an idle army
            self.dismissals.add(str(cmd["uid"]), str(cmd.get("scope", "army")),
                                cmd.get("pawn_uids") or [])
            return
        if action == "rename_army":
            # Chat/dashboard rename: queued until the army is idle, then sent with its
            # current index (a one-shot send failed on busy/marching armies).
            self.renames.add(str(cmd["uid"]), str(cmd["name"]))
            return
        track = cmd.get("track")
        tp = _TRACK_TP.get(track)
        if tp is None:
            raise ValueError(f"unknown track {track!r}")
        if action == "select":
            self.actions.study_select(lv, int(cmd["ceri_id"]), tp)
        elif action == "reroll":
            self.actions.ceri_reset(lv, tp)
        else:
            raise ValueError(f"unknown action {action!r}")

    def tick(self, state) -> None:
        try:
            self._write_decisions(state)
        except Exception as e:  # observability must not kill the loop
            sys.stderr.write(f"[decisions] write failed: {e}\n")
        try:
            self._write_equipment(state)
        except Exception as e:
            sys.stderr.write(f"[equipment] write failed: {e}\n")
        if self._armies_counter <= 0:
            self._armies_counter = self.armies_every - 1
            try:
                self._write_armies()  # network call — never kill the loop
            except Exception as e:
                sys.stderr.write(f"[armies] fetch failed: {e}\n")
        else:
            self._armies_counter -= 1
        for cmd in read_pending(self.cfg.commands_path, self.cfg.commands_done_path):
            try:
                self._execute(cmd)
                self._on_event("decision_done", {"id": cmd["id"], "action": cmd.get("action")})
            except Exception as e:
                detail = {"id": cmd.get("id"), "action": cmd.get("action"),
                          "track": cmd.get("track"), "lv": cmd.get("lv"),
                          "ceri_id": cmd.get("ceri_id"), "equip_uid": cmd.get("equip_uid"),
                          "pawn_id": cmd.get("pawn_id"), "main_uid": cmd.get("main_uid"),
                          "error": str(e), "reason": ecode_reason(self.config, str(e))}
                detail = {k: v for k, v in detail.items() if v is not None and v != ""}
                self._on_event("decision_error", detail)
                sys.stderr.write(f"[decision] {cmd.get('action')} failed: {e}\n")
            finally:
                mark_done(self.cfg.commands_done_path, cmd["id"])
        try:
            self.dismissals.process(self.actions, self._on_event)
        except Exception as e:  # a network hiccup must not kill the loop
            sys.stderr.write(f"[dismissals] process failed: {e}\n")
        try:
            self.renames.process(self.actions, self._on_event)
        except Exception as e:  # a network hiccup must not kill the loop
            sys.stderr.write(f"[renames] process failed: {e}\n")
