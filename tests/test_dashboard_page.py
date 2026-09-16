from nta_agent.dashboard.page import INDEX_HTML


def test_page_has_chat_panel_and_endpoint():
    assert "/api/chat" in INDEX_HTML
    assert "chat" in INDEX_HTML.lower()
    assert 'id="chatlog"' in INDEX_HTML


def test_page_has_build_order_widget():
    assert "/api/profile" in INDEX_HTML
    assert 'id="buildorder"' in INDEX_HTML
    assert "Thứ tự xây" in INDEX_HTML


def test_page_has_territory_panel():
    assert "/api/territory" in INDEX_HTML
    assert 'id="territory"' in INDEX_HTML
    assert "Lãnh thổ" in INDEX_HTML


def test_page_has_forts_panel():
    assert "/api/forts" in INDEX_HTML
    assert 'id="forts"' in INDEX_HTML
    assert "Cứ Điểm" in INDEX_HTML


def test_page_has_territory_map_canvas():
    assert 'id="terrmap"' in INDEX_HTML
    assert "renderTerritoryMap" in INDEX_HTML
    assert "owned_cells" in INDEX_HTML  # map reads owned cell coords


def test_event_detail_object_is_formatted_not_stringified():
    # brain_plan detail is an object; must not render as "[object Object]"
    assert "[object Object]" not in INDEX_HTML  # no literal accidental output
    assert "rationale" in INDEX_HTML  # fmt helper reads .rationale
    assert "JSON.stringify" in INDEX_HTML  # fallback for other objects
