from nta_agent.execution.intel import build_report


def test_economy_forecast_and_overflow_warning():
    snap = {"main_city_index": 7, "granary_cap": 1000, "warehouse_cap": 1000,
            "resources": {"cereal": 950, "timber": 100, "stone": 100},
            "production": {"cereal": 100, "timber": 100, "stone": 100}}  # cereal ~0.5h to full
    r = build_report(snap, {})
    assert r["economy"]["forecasts_hours"]["cereal"] == 0.5
    assert any("cereal" in w for w in r["economy"]["warnings"])
    assert any(x["type"] == "economy" for x in r["recommendations"])


def test_threats_surface_defense_recommendation():
    forts = {"threat_summary": {"count": 3, "has_enemy_city": True, "inside_count": 1},
             "threats": [{"x": 1, "y": 2}], "frontier": [[9, 9]], "enemy_cells": [[9, 9]]}
    r = build_report({}, forts)
    assert r["threats"]["summary"]["count"] == 3
    dref = [x for x in r["recommendations"] if x["type"] == "defense"]
    assert dref and "thành địch" in dref[0]["why"]


def test_expansion_posture_switches_with_threats():
    safe = build_report({}, {"threat_summary": {"count": 0}})
    war = build_report({}, {"threat_summary": {"count": 2}})
    exp_safe = next(x for x in safe["recommendations"] if x["type"] == "expansion")
    exp_war = next(x for x in war["recommendations"] if x["type"] == "expansion")
    assert "bạch tuộc" in exp_safe["text"]     # safe -> expand fast
    assert "xoắn ốc" in exp_war["text"]        # threatened -> defensive


def test_fort_recs_included():
    forts = {"recommendations": [{"x": 5, "y": 6, "reason": "biên giới"}],
             "threat_summary": {"count": 0}}
    r = build_report({}, forts)
    assert any(x["type"] == "fort" and "(5,6)" in x["text"] for x in r["recommendations"])


def test_brain_advice_included():
    advice = [{"text": "Chọn Cung", "why": "tầm xa mạnh"}]
    r = build_report({}, {}, brain_advice=advice)
    assert r["brain_advice"] == advice
