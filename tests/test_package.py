import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("package", Path("tools/package.py"))
package = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(package)


def test_collect_excludes_game_data_and_secrets():
    files = [p.as_posix() for p in package.collect_app_files()]
    assert "nta_agent/paths.py" in files
    assert "tools/battlesim/server.js" in files
    assert "tools/re/extract_config.py" in files and "tools/re/decrypt_jsc.py" in files
    assert not any(f.startswith("tools/battlesim/test/") for f in files)
    assert package.leaks(files) == []


def test_leak_scan_catches_forbidden_members():
    bad = ["NTA-Agent/app/nta_agent/data/config/buildBase.json",
           "app/tools/re/decrypted/index.js", "app/tools/re/KEY.txt", "app/.env",
           "NTA-Agent/app/x/__pycache__/a.pyc", "base.apk", "assets/app/index.jsc"]
    ok = ["NTA-Agent/app/nta_agent/data/config/manifest.json", "app/nta_agent/paths.py",
          "NTA-Agent/VERSION"]
    assert package.leaks(bad) == bad
    assert package.leaks(ok) == []
