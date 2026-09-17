"""The dashboard shell: mounts the vendored Vue app from /static."""

INDEX_HTML = """<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NTA Agent</title>
<link rel="stylesheet" href="/static/app.css">
</head><body>
<div id="app"></div>
<script src="/static/vendor/vue.global.prod.js"></script>
<script type="module" src="/static/app.js"></script>
</body></html>"""
