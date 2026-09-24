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
