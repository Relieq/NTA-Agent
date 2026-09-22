"""F2 regression guard — detect a game update silently breaking our config.

These are OFFLINE structural checks (no emulator): the manifest pins the game
version + a fingerprint of every config table, and these tests assert the
load-bearing tables are present and still carry the fields/ids the rules and
predictors depend on. When the game updates and configs are re-extracted,
regenerate the manifest (``python tools/re/gen_config_manifest.py``) and any
real drift shows up as a failure here to review.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from nta_agent.data.config import GameConfig
from nta_agent.version import GAME_VERSION

CONFIG_DIR = Path("nta_agent/data/config")
MANIFEST = CONFIG_DIR / "manifest.json"

# Config tables are extracted from the (gitignored) decrypted engine, so a fresh
# checkout / CI won't have them. Skip the drift checks there; they run on a dev
# machine that has the tables. The manifest itself IS committed as the anchor.
pytestmark = pytest.mark.skipif(
    not (CONFIG_DIR / "pawnBase.json").exists(),
    reason="config tables absent (gitignored) — drift guard runs where tables exist",
)

# Tables the code loads via GameConfig.table(...) — if one goes missing or empty,
# rules/predictors break. Keep in sync with grep '.table("' in nta_agent/.
LOAD_BEARING = [
    "antiCheat", "buildAttr", "buildBase", "buildText", "ecode",
    "equipBase", "equipEffect", "equipText", "land", "landAttr",
    "pawnAttr", "pawnBase", "pawnText", "policy", "treasure",
]


@pytest.fixture(scope="module")
def manifest() -> dict:
    assert MANIFEST.exists(), (
        "config manifest missing — run: python tools/re/gen_config_manifest.py"
    )
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_manifest_version_matches_game_version(manifest):
    assert manifest["game_version"] == GAME_VERSION, (
        "manifest game_version %r != GAME_VERSION %r — bump nta_agent/version.py and "
        "regenerate the manifest after re-extracting config for the new game build"
        % (manifest["game_version"], GAME_VERSION)
    )


def test_manifest_files_still_present(manifest):
    """A file recorded in the manifest must not have vanished from disk."""
    missing = [name for name in manifest["files"] if not (CONFIG_DIR / name).exists()]
    assert not missing, "config files in manifest but missing on disk: %s" % missing


def test_load_bearing_tables_present_and_nonempty():
    gc = GameConfig.load()
    for name in LOAD_BEARING:
        assert (CONFIG_DIR / f"{name}.json").exists(), f"missing config table: {name}.json"
        assert gc.table(name), f"config table is empty: {name}"


def test_recruit_pawn_ids_still_valid():
    """The strike-group feature hard-depends on these pawn ids + their drill cost."""
    gc = GameConfig.load()
    for pawn_id in (3206, 3305):   # rìu khiên (tank), IMP (dps)
        assert gc.pawn_base(pawn_id), f"pawn {pawn_id} vanished from pawnBase"
        assert gc.pawn_recruit_cost(pawn_id), f"pawn {pawn_id} has no drill_cost"


def test_buildbase_rows_carry_bt_count():
    """max_count() and the duplicate-build guard rely on the bt_count field."""
    gc = GameConfig.load()
    rows = gc.table("buildBase")
    assert rows, "buildBase empty"
    assert all("bt_count" in r for r in rows.values()), "buildBase row lost bt_count field"


def test_ecodes_referenced_by_rules_exist():
    """Rules key their quiet-backoff on these ecodes — they must stay in ecode.json."""
    gc = GameConfig.load()
    codes = gc.table("ecode")
    for code in (500012, 500014, 500018, 500019, 500034, 500054):
        assert code in codes, f"ecode {code} missing — rules reference it for backoff"
