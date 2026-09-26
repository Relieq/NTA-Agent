"""Can the spare armies (together, any attack order) win a frontier cell cleanly?

Used by the SpareArmies rule to decide whether to warn the player. Defenders are
the engine's generated ones (landId from the world map) — a screen, like the dig
planner; the real attack decision stays with OccupyCell (real defenders).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)


def make_spare_predict(cfg, profile, *, max_cells: int = 20):
    def predict(state, armies):
        from nta_agent import paths
        from nta_agent.execution.occupy_planner import full_hp_pawns
        from nta_agent.execution.order_strategies import colocated_orders
        from nta_agent.execution.predictors.sim_bridge import get_bridge
        from nta_agent.execution.predictors.sim_predictor import SimBattlePredictor
        from nta_agent.execution.worldmap import WorldMap
        from nta_agent.runtime.dig_service import dist_to_block
        if not armies or not get_bridge().available():
            return None
        try:
            f = json.loads(Path(cfg.forts_path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        W = 600
        main = int(state.main_city_index)
        owned = {y * W + x for x, y in f.get("owned_cells") or []}
        world = WorldMap.load(paths.config_dir())
        world.detect(owned)
        cells = [y * W + x for x, y in f.get("frontier") or []]
        cells = sorted((c for c in cells if world.passable(c)),
                       key=lambda c: dist_to_block(c, main))[:max_cells]
        max_loss = float((getattr(profile, "occupy", {}) or {}).get("max_loss", 0) or 0)
        sim = SimBattlePredictor()
        healed = [{**a, "pawns": full_hp_pawns(a.get("pawns") or [])} for a in armies]
        for c in cells:
            for _label, order in colocated_orders(healed, "auto"):
                try:
                    p = sim.predict_armies(state, order, target_index=c,
                                           land_id=world.land_id(c),
                                           distance=dist_to_block(c, main))
                except Exception as e:  # one sim failing must not end the screen
                    log.debug("spare predict failed at %s: %s", c, e)
                    continue
                if p.win and p.loss_percent <= max_loss:
                    return {"target": c, "loss": p.loss_percent,
                            "armies": [a.get("name") for a in order]}
        return None
    return predict
