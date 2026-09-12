"""Per-tick service: publish pending decisions + execute human commands."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from nta_agent.execution.decisions import pending_decisions
from nta_agent.execution.equipment import pawn_equipment
from nta_agent.runtime.commands import mark_done, read_pending

_TRACK_TP = {"pawn": 2, "policy": 1, "equip": 3}


class DecisionService:
    def __init__(self, actions, config, cfg, on_event=None):
        self.actions = actions
        self.config = config
        self.cfg = cfg
        self._on_event = on_event or (lambda *a: None)

    def _write_decisions(self, state) -> None:
        data = [asdict(d) for d in pending_decisions(state, self.config)]
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

    def _execute(self, cmd: dict) -> None:
        action = cmd.get("action")
        lv = int(cmd.get("lv", 0) or 0)
        if action == "equip":
            self.actions.change_pawn_equip(
                int(cmd["pawn_id"]), cmd["equip_uid"],
                int(cmd.get("skin_id", 0) or 0), int(cmd.get("attack_speed", 0) or 0))
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
        for cmd in read_pending(self.cfg.commands_path, self.cfg.commands_done_path):
            try:
                self._execute(cmd)
                self._on_event("decision_done", {"id": cmd["id"], "action": cmd.get("action")})
            except Exception as e:
                self._on_event("decision_error", {"id": cmd.get("id"), "error": str(e)})
            finally:
                mark_done(self.cfg.commands_done_path, cmd["id"])
