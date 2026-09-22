"""Ground failures in the engine: summarize a lost battle + test alternate orders.

Hands call these on a real battle record (Cách A — the brain never runs the sim).
Every function is best-effort: if the sidecar is unavailable it returns ``None`` so
the loss is still recorded, just without engine-grounded enrichment.
"""
from __future__ import annotations

from nta_agent.execution.predictors.sim_bridge import SimUnavailable

_ORDERS = ["tank_first", "dps_first", "auto"]


def summarize_record(bridge, record) -> dict | None:
    """Replay a record → {summary, hits, enemy_ids, self_ids, aoe}. None if no sim."""
    try:
        out = bridge.replay(record)
    except SimUnavailable:
        return None
    if not isinstance(out, dict):
        return None
    out["aoe"] = detect_aoe(out.get("hits") or [])
    return out


def detect_aoe(hits) -> bool:
    """True if any single attacker hit more than one target on the same frame."""
    seen: dict = {}
    for h in hits or []:
        key = (h.get("by"), h.get("frame"))
        seen.setdefault(key, set()).add(h.get("target"))
    return any(len(targets) > 1 for targets in seen.values())


def best_counterfactual_order(bridge, record) -> dict | None:
    """Which army order loses the fewest troops. {"best_order","self_dead"} or None."""
    try:
        out = bridge.counterfactual(record, _ORDERS)
    except SimUnavailable:
        return None
    by = (out or {}).get("by_order") or {}
    if not by:
        return None
    best_order, best = min(by.items(), key=lambda kv: kv[1].get("self_dead", 10 ** 9))
    return {"best_order": best_order, "self_dead": int(best.get("self_dead", 0))}
