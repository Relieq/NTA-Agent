"""Intelligence & advisory report (Phase I) — aggregate what the agent knows into
a compact brief the human reads to decide. Pure over the on-disk snapshot +
forts.json (threats/enemy/frontier/fort recs); no I/O, no LLM.

The agent is a co-pilot: this surfaces threats, opportunities and recommendations
with reasons; the human makes the competitive/strategic calls.
"""
from __future__ import annotations

# cereal is stored in the granary; timber/stone in the warehouse.
_CAP_OF = {"cereal": "granary", "timber": "warehouse", "stone": "warehouse"}


def _time_to_full(cur: int, cap: int, rate: float):
    """Hours until a resource hits its cap at ``rate``/hour, or None."""
    if rate <= 0 or cap <= 0 or cur >= cap:
        return None
    return round((cap - cur) / rate, 1)


def build_report(snapshot: dict, forts: dict, config=None) -> dict:
    """Assemble the advisory report from a snapshot dict + a forts.json dict."""
    snapshot = snapshot or {}
    forts = forts or {}
    res = snapshot.get("resources", {}) or {}
    prod = snapshot.get("production", {}) or {}
    caps = {"granary": int(snapshot.get("granary_cap", 0) or 0),
            "warehouse": int(snapshot.get("warehouse_cap", 0) or 0)}

    recs: list[dict] = []
    warnings: list[str] = []
    forecasts: dict[str, float] = {}

    # Economy: cap-fill forecasts + overflow warnings.
    for r, cap_key in _CAP_OF.items():
        t = _time_to_full(int(res.get(r, 0) or 0), caps[cap_key], float(prod.get(r, 0) or 0))
        if t is None:
            continue
        forecasts[r] = t
        if t <= 2.0:
            warnings.append(f"{r} sắp đầy kho (~{t}h)")
            recs.append({"type": "economy", "text": f"Thu/tiêu {r} để tránh tràn kho",
                         "why": f"còn ~{t}h là đầy"})

    # Defense: threats touching our border (from Phase P).
    tsum = forts.get("threat_summary") or {"count": 0}
    threats = forts.get("threats") or []
    if tsum.get("count"):
        why = f"{tsum['count']} điểm địch chạm biên"
        if tsum.get("has_enemy_city"):
            why += " (có thành địch)"
        if tsum.get("inside_count"):
            why += f", {tsum['inside_count']} đã lọt vào trong"
        recs.append({"type": "defense", "text": "Địch áp sát biên — cân nhắc phòng thủ/đánh trả", "why": why})

    # Fort placement suggestions (already threat-aware from C1).
    for r in (forts.get("recommendations") or [])[:3]:
        recs.append({"type": "fort", "text": f"Đặt Cứ Điểm tại ({r.get('x')},{r.get('y')})",
                     "why": r.get("reason", "")})

    # Expansion posture advice.
    if tsum.get("count"):
        recs.append({"type": "expansion", "text": "Lối mở rộng: xoắn ốc (phòng thủ)",
                     "why": "địch đang áp sát biên"})
    else:
        recs.append({"type": "expansion", "text": "Lối mở rộng: bạch tuộc (mở rộng nhanh)",
                     "why": "biên hiện an toàn"})

    status = (f"{tsum.get('count', 0)} đe dọa · {len(recs)} khuyến nghị · "
              f"{snapshot.get('main_city_index', 0) and 'đang chạy'}").strip(" ·")

    return {
        "status": status,
        "economy": {"resources": res, "caps": caps,
                    "forecasts_hours": forecasts, "warnings": warnings},
        "threats": {"summary": tsum, "top": threats[:5]},
        "opportunities": {"open_frontier": len(forts.get("frontier") or []),
                          "enemy_nearby": len(forts.get("enemy_cells") or [])},
        "recommendations": recs,
    }
