import json
import zipfile

import pytest

from nta_agent import gamedata

KEY = b"0123456789abcdef"
ENGINE = b"window.__require = function e(t, n, i) {};\n" * 20


def test_find_engine_entry():
    names = ["assets/src/assets/app/proto/msg.jsc", "assets/assets/main/index.jsc",
             "assets/assets/app/index.jsc"]
    assert gamedata.find_engine_entry(names) == "assets/assets/app/index.jsc"
    assert gamedata.find_engine_entry(["assets/x/app/index.jsc"]) == "assets/x/app/index.jsc"
    assert gamedata.find_engine_entry(["x.png"]) is None


def test_xxtea_roundtrip():
    enc = gamedata.xxtea_encrypt(ENGINE, KEY)
    assert enc != ENGINE
    assert gamedata.xxtea_decrypt(enc, KEY) == ENGINE


def test_decrypt_engine_writes_js_and_rejects_wrong_key(tmp_path):
    apk = tmp_path / "base.apk"
    with zipfile.ZipFile(apk, "w") as z:
        z.writestr("assets/assets/app/index.jsc", gamedata.xxtea_encrypt(ENGINE, KEY))
    out = tmp_path / "engine" / "index.js"
    assert gamedata.decrypt_engine(apk, out, KEY) == len(ENGINE)
    assert out.read_bytes() == ENGINE
    with pytest.raises(ValueError):
        gamedata.decrypt_engine(apk, tmp_path / "bad.js", b"wrongwrongwrong!")


def _fake_apk(path, rows):
    uuid_c = "a" * 22
    uuid = gamedata.decode_uuid(uuid_c)
    cfg = {"paths": {"0": ["common/json/buildBase", 1], "1": ["ui/x", 2]},
           "uuids": [uuid_c, "b" * 22]}
    imp = [0, 0, 0, 0, 0, [[0, "buildBase", rows]]]
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(f"{gamedata.RES_BASE}/config.json", json.dumps(cfg))
        z.writestr(f"{gamedata.RES_BASE}/import/{uuid[:2]}/{uuid}.json", json.dumps(imp))


def test_extract_config_tables_atomic_swap(tmp_path):
    apk = tmp_path / "base.apk"
    _fake_apk(apk, [{"id": 1}])
    out = tmp_path / "config"
    out.mkdir()
    (out / "stale.json").write_text("[]", encoding="utf-8")
    ok, fail = gamedata.extract_config_tables(apk, out)
    assert (ok, fail) == (1, [])
    assert json.loads((out / "buildBase.json").read_text(encoding="utf-8")) == [{"id": 1}]
    assert not (out / "stale.json").exists()
    assert not out.with_name("config.new").exists()


def test_find_xxtea_key_from_native_lib(tmp_path):
    probe = b"(function r(e, n, t) {\nfunction i(u, f) {}\n})" * 4
    lib = (b"\x00junk\x00" + b"not-the-key-at-all-0000\x00" + b"ABCDEFGHIJKLMNOPqrst\x00"
           + b"\x7fELF\x00" + KEY + b"-tail\x00more")   # C strings are NUL-separated
    apk = tmp_path / "base.apk"
    with zipfile.ZipFile(apk, "w") as z:
        z.writestr(gamedata.PROBE_ENTRY, gamedata.xxtea_encrypt(probe, KEY))
        z.writestr("lib/x86_64/libcocos2djs.so", lib)
    assert gamedata.find_xxtea_key(apk) == KEY.decode()


def test_find_xxtea_key_none_when_absent(tmp_path):
    apk = tmp_path / "base.apk"
    with zipfile.ZipFile(apk, "w") as z:
        z.writestr(gamedata.PROBE_ENTRY, gamedata.xxtea_encrypt(b"function x(){}" * 8, KEY))
        z.writestr("lib/x86_64/libcocos2djs.so", b"\x00nothing-useful-here-at-all\x00")
    assert gamedata.find_xxtea_key(apk) is None


def test_extract_also_writes_world_maps(tmp_path):
    """tmp/json/maps/maps_<n> (per-cell landIds of the world map) are extracted too."""
    apk = tmp_path / "base.apk"
    u1, u2 = "a" * 22, "b" * 22
    d1, d2 = gamedata.decode_uuid(u1), gamedata.decode_uuid(u2)
    cfg = {"paths": {"0": ["common/json/land", 1], "1": ["tmp/json/maps/maps_15", 1],
                     "2": ["tmp/image/land/x", 2]},
           "uuids": [u1, u2, "c" * 22]}
    with zipfile.ZipFile(apk, "w") as z:
        z.writestr(f"{gamedata.RES_BASE}/config.json", json.dumps(cfg))
        z.writestr(f"{gamedata.RES_BASE}/import/{d1[:2]}/{d1}.json",
                   json.dumps([0, 0, 0, 0, 0, [[0, "land", [{"id": 301}]]]]))
        z.writestr(f"{gamedata.RES_BASE}/import/{d2[:2]}/{d2}.json",
                   json.dumps([0, 0, 0, 0, 0, [[0, "maps_15", [5, 10, 0]]]]))
    out = tmp_path / "config"
    ok, fail = gamedata.extract_config_tables(apk, out)
    assert (ok, fail) == (2, [])
    assert json.loads((out / "maps_15.json").read_text(encoding="utf-8")) == [5, 10, 0]
