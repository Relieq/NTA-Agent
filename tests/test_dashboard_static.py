from nta_agent.dashboard.server import serve_static


def test_serve_static_returns_js_and_type():
    code, ctype, body = serve_static("vendor/vue.global.prod.js")
    assert code == 200
    assert ctype.startswith("text/javascript")
    assert b"Vue" in body


def test_serve_static_blocks_traversal():
    for p in ("../server.py", "..%2fserver.py", "vendor/../../server.py", "/etc/passwd"):
        code, _ctype, _body = serve_static(p)
        assert code == 404


def test_serve_static_rejects_unknown_extension():
    code, _ctype, _body = serve_static("../server.py")  # .py not whitelisted anyway
    assert code == 404


def test_serve_static_missing_file_404():
    code, _ctype, _body = serve_static("nope-not-here.js")
    assert code == 404
