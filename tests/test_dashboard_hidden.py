"""The dashboard's "✖ Ẩn" helper (api.js useHidden): per-viewer, remembered in localStorage,
expires after a week, never throws when storage is unavailable."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

API = Path("nta_agent/dashboard/static/api.js").resolve()
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs Node")

HARNESS = """
const store = {};
globalThis.localStorage = %(ls)s;
globalThis.window = { Vue: { ref: (v) => ({ value: v }) } };
import(%(api)s).then(({ useHidden }) => {
  const out = {};
  %(body)s
  console.log(JSON.stringify(out));
});
"""


def _run(body, ls="{ getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = v; } }"):
    js = HARNESS % {"api": json.dumps(API.as_uri()), "body": body, "ls": ls}
    r = subprocess.run(["node", "--input-type=commonjs", "-e", js], capture_output=True,
                       text=True, timeout=30, check=True)
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_hide_is_remembered_and_scoped_by_prefix():
    out = _run("""
      const a = useHidden("upd"), b = useHidden("intel");
      a.hide("0.2.29");
      out.a = a.isHidden("0.2.29"); out.other = a.isHidden("0.2.30"); out.b = b.isHidden("0.2.29");
      const again = useHidden("upd");            // a fresh viewer session reads the store
      out.again = again.isHidden("0.2.29"); out.count = again.hiddenCount();
      again.showAll(); out.after = again.isHidden("0.2.29");
    """)
    assert out == {"a": True, "other": False, "b": False, "again": True, "count": 1, "after": False}


def test_two_components_do_not_overwrite_each_other():
    out = _run("""
      const a = useHidden("upd"), b = useHidden("intel");
      a.hide("x"); b.hide("y");                  // b was created before a wrote
      out.both = useHidden("upd").isHidden("x") && useHidden("intel").isHidden("y");
    """)
    assert out["both"] is True


def test_old_entries_expire_and_broken_storage_is_harmless():
    old = 'store["nta.hidden"] = JSON.stringify({"upd:1": Date.now() - 8*86400*1000});'
    out = _run(old + 'out.old = useHidden("upd").isHidden("1");')
    assert out["old"] is False
    broken = "{ getItem: () => { throw new Error('blocked'); }, setItem: () => { throw new Error('blocked'); } }"
    out = _run('const h = useHidden("upd"); h.hide("1"); out.ok = h.isHidden("1");', ls=broken)
    assert out["ok"] is True   # still hides for this page view
