from nta_agent.dashboard.page import INDEX_HTML


def test_page_has_chat_panel_and_endpoint():
    assert "/api/chat" in INDEX_HTML
    assert "chat" in INDEX_HTML.lower()
    assert 'id="chatlog"' in INDEX_HTML
