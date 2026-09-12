from pathlib import Path

import pytest

from nta_agent.dashboard.names import build_label, load_build_names

_CONFIG = Path("nta_agent/data/config/buildText.json")


def test_build_label_fallback():
    assert build_label({}, 2001) == "#2001"
    assert build_label({2001: "Thành Chính"}, 2001) == "Thành Chính"
    assert build_label({2001: "Thành Chính"}, 9999) == "#9999"


def test_load_missing_config_returns_empty(tmp_path):
    assert load_build_names(tmp_path) == {}


@pytest.mark.skipif(not _CONFIG.exists(), reason="config not extracted")
def test_load_build_names_vietnamese():
    names = load_build_names()
    assert names[2001] == "Thành Chính"
    assert names[2004] == "Binh Doanh"
