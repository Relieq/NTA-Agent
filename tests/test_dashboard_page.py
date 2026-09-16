from nta_agent.dashboard.page import INDEX_HTML


def test_page_has_chat_panel_and_endpoint():
    assert "/api/chat" in INDEX_HTML
    assert "chat" in INDEX_HTML.lower()
    assert 'id="chatlog"' in INDEX_HTML


def test_page_has_build_order_widget():
    assert "/api/profile" in INDEX_HTML
    assert 'id="buildorder"' in INDEX_HTML
    assert "Thứ tự xây" in INDEX_HTML
