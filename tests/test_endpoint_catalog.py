"""F2 regression guard — every game endpoint the code calls must be documented.

``docs/re/game-api.md`` is the living catalog of the game's ``HD_*`` protocol. If
``actions.py`` calls an endpoint that isn't in the catalog, either it's a typo or
the catalog fell behind — both worth catching before a game update makes drift
harder to reason about. This keeps code and catalog in lockstep, offline.
"""
from __future__ import annotations

import re
from pathlib import Path

ACTIONS = Path("nta_agent/execution/actions.py")
CATALOG = Path("docs/re/game-api.md")


def _endpoints_used() -> set[str]:
    text = ACTIONS.read_text(encoding="utf-8")
    return set(re.findall(r"game/(HD_[A-Za-z]+)", text))


def test_all_called_endpoints_are_documented():
    used = _endpoints_used()
    assert used, "no game/HD_* endpoints found in actions.py — regex drifted?"
    catalog = CATALOG.read_text(encoding="utf-8")
    undocumented = sorted(ep for ep in used if ep not in catalog)
    assert not undocumented, (
        "endpoints called in actions.py but missing from docs/re/game-api.md: %s"
        % undocumented
    )
