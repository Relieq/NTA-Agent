from nta_agent.dashboard.page import INDEX_HTML


def test_index_html_is_self_contained():
    assert "NTA Agent" in INDEX_HTML
    assert "/api/state" in INDEX_HTML and "/api/events" in INDEX_HTML
    # no external assets (CSP-safe): no http(s) src/href
    assert "http://" not in INDEX_HTML and "https://" not in INDEX_HTML


def test_index_html_has_decisions_panel():
    assert "/api/decisions" in INDEX_HTML
    assert "/api/command" in INDEX_HTML
    assert "Quyết định đang chờ" in INDEX_HTML


def test_index_html_has_equipment_panel():
    assert "/api/equipment" in INDEX_HTML
    assert "Trang bị lính" in INDEX_HTML


def test_index_html_has_army_section_and_labels():
    assert "/api/armies" in INDEX_HTML
    assert "Đội quân" in INDEX_HTML
    assert "Sách EXP" in INDEX_HTML          # corrected resource label
    assert "Thể lực" not in INDEX_HTML       # dropped
