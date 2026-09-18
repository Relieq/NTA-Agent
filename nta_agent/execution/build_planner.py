"""Pick the next building upgrade to perform, config- and prereq-aware.

Buildings in NTA gate on prerequisites (``prep_cond``) and can't exceed the main
hall's level, which is why a fixed build order is natural. This planner walks a
priority order and returns the first step that is *actionable now*: not maxed,
within the main-hall cap, prerequisites met, and affordable. Prereq types we
can't verify locally are left for the server to reject (the rule handles that).
"""
from __future__ import annotations

from dataclasses import dataclass

from nta_agent.data.config import GameConfig
from nta_agent.state.schema import Building, GameState

MAIN_HALL_ID = 2001
GRANARY_BUILD = 2002    # Kho Lương — raises the granary (cereal) cap
WAREHOUSE_BUILD = 2003  # Kho — raises the warehouse (timber/stone/iron) cap


@dataclass
class BuildAction:
    kind: str          # "construct" | "upgrade"
    build_id: int
    up: object         # BuildUpgrade for the target level
    build: object = None  # existing Building (upgrades); None for constructs
_PREP_NEED_BUILDING = 4  # prep_cond "4,<buildId>,<lv>": need that building at <lv>


def parse_prep_cond(s: str) -> list[tuple[int, int, int]]:
    """Parse a ``prep_cond`` string into its conditions.

    The game encodes several unlock conditions ``|``-separated with AND
    semantics, each ``<ctype>,<param>,<value>`` (matches the engine's
    ``checkUnlcokBuildCond`` / ``stringToCTypes``). Malformed parts are skipped.
    """
    out: list[tuple[int, int, int]] = []
    for part in (s or "").split("|"):
        fields = part.split(",")
        if len(fields) >= 3:
            try:
                out.append((int(fields[0]), int(fields[1]), int(fields[2])))
            except ValueError:
                continue
    return out


def _prep_ok(prep_cond: str, level_by_id: dict[int, int]) -> bool:
    """True if every prerequisite is met (AND). Only the building-level type (4)
    is checked locally; other types default to True and rely on server validation."""
    for ctype, param, value in parse_prep_cond(prep_cond):
        if ctype == _PREP_NEED_BUILDING and level_by_id.get(param, 0) < value:
            return False
    return True


def _affordable(cost: dict[str, int], state: GameState) -> bool:
    r = state.resources
    have = {"cereal": r.cereal, "timber": r.timber, "stone": r.stone, "iron": r.iron}
    return all(have.get(res, 0) >= amt for res, amt in cost.items())


def _cap_for(state: GameState, resource: str) -> int:
    return (state.granary_cap if resource == "cereal" else state.warehouse_cap) or 0


def capped_storage_upgrade(state: GameState, config: GameConfig,
                           skip: set | None = None) -> BuildAction | None:
    """If a wanted upgrade's cost exceeds what the store can hold, upgrade the
    store first (user rule 2026-09-18: cap < required → must raise the cap, else
    you can never save enough). Returns the storage upgrade or None.

    Only fires when a real cap is set and the storage building exists, its next
    level is affordable now and not itself cap-blocked — so it never loops and is
    inert in tests/early game (caps 0)."""
    skip = skip or set()
    level_by_id = {b.id: b.lv for b in state.builds}
    main_lv = level_by_id.get(MAIN_HALL_ID, 0)
    if not _cap_for(state, "cereal") and not _cap_for(state, "timber"):
        return None
    for b in state.builds:
        if b.id in skip or b.id in (GRANARY_BUILD, WAREHOUSE_BUILD):
            continue
        target = b.lv + 1
        if b.id != MAIN_HALL_ID and target > main_lv:
            continue
        up = config.build_upgrade(b.id, target)
        if up is None or not _prep_ok(up.prep_cond, level_by_id):
            continue
        for res, amt in up.cost.items():
            cap = _cap_for(state, res)
            if not cap or amt <= cap:
                continue
            sid = GRANARY_BUILD if res == "cereal" else WAREHOUSE_BUILD
            store = next((x for x in state.builds if x.id == sid), None)
            if store is None:
                continue
            su = config.build_upgrade(sid, store.lv + 1)
            if su is None or not _affordable(su.cost, state):
                continue
            # the storage upgrade must not itself be cap-blocked (avoid a loop)
            if any(sa > _cap_for(state, sr) for sr, sa in su.cost.items()
                   if _cap_for(state, sr)):
                continue
            return BuildAction(kind="upgrade", build_id=sid, up=su, build=store)
    return None


def next_upgrade(
    state: GameState,
    config: GameConfig,
    sequence: list[int] | None = None,
    blocked: set[tuple[str, int]] | None = None,
) -> tuple[Building, object] | None:
    """Return (building, BuildUpgrade) for the next actionable upgrade, or None.

    ``blocked`` is a set of (uid, target_lv) the server has recently rejected
    (conditions we can't verify locally); those steps are skipped.
    """
    if not state.builds:
        return None
    # Respect build-queue capacity: don't start more than the slots allow.
    if len(state.build_queue) >= state.build_queue_slots:
        return None
    blocked = blocked or set()
    queued_uids = {str(q.get("uid", "")) for q in state.build_queue}
    level_by_id = {b.id: b.lv for b in state.builds}
    main_lv = level_by_id.get(MAIN_HALL_ID, 0)

    order = sequence or sorted({b.id for b in state.builds})
    # index buildings by id preserving instances (walls/towers can repeat)
    by_id: dict[int, list[Building]] = {}
    for b in state.builds:
        by_id.setdefault(b.id, []).append(b)

    for build_id in order:
        for build in by_id.get(build_id, []):
            if build.uid in queued_uids:
                continue  # already upgrading
            target = build.lv + 1
            if (build.uid, target) in blocked:
                continue  # server rejected this step recently
            # non-main buildings can't exceed the main hall's level
            if build_id != MAIN_HALL_ID and target > main_lv:
                continue
            up = config.build_upgrade(build_id, target)
            if up is None:
                continue  # maxed / no such level
            if not _prep_ok(up.prep_cond, level_by_id):
                continue
            if not _affordable(up.cost, state):
                continue
            return build, up
    return None


def next_build_action(
    state: GameState,
    config: GameConfig,
    sequence: list[int] | None = None,
    blocked: set | None = None,
    skip: set | None = None,
    room_type: int | None = None,
) -> BuildAction | None:
    """The next build action — construct a new building (lv1) or upgrade one.

    For each id in the order: if the instance count is below ``max_count`` and a
    fresh lv1 is unlocked/affordable/not-blocked, construct it; otherwise fall
    through to upgrading an existing instance (as :func:`next_upgrade`).
    """
    if not state.builds:
        return None
    if len(state.build_queue) >= state.build_queue_slots:
        return None
    blocked = blocked or set()
    skip = set(skip or ())
    # mode-gated buildings for the wrong room type are excluded like skip.
    in_city = set(config.in_city_build_ids(room_type))
    if room_type is not None:
        skip = skip | (set(config.in_city_build_ids()) - in_city)
    queued_uids = {str(q.get("uid", "")) for q in state.build_queue}
    level_by_id = {b.id: b.lv for b in state.builds}
    main_lv = level_by_id.get(MAIN_HALL_ID, 0)
    counts: dict[int, int] = {}
    for b in state.builds:
        counts[b.id] = counts.get(b.id, 0) + 1
    # Default order also covers not-yet-built in-city types, so new buildings get
    # constructed (existing-only order would never reach an unbuilt type).
    order = sequence or sorted(set(counts) | in_city)

    # Construct-first: build every eligible missing/allowed building before
    # spending on upgrades (upgrades would otherwise starve construction).
    for build_id in order:
        if build_id in skip:
            continue
        if (counts.get(build_id, 0) < config.max_count(build_id)
                and ("construct", build_id) not in blocked):
            up1 = config.build_upgrade(build_id, 1)
            # The real unlock gate lives on the buildBase row (multi-condition,
            # AND). The level-1 upgrade's prep_cond is usually empty, so checking
            # only that lets locked buildings be constructed → server 500033.
            base_prep = (config.build_base(build_id) or {}).get("prep_cond", "")
            if (up1 is not None
                    and _prep_ok(base_prep, level_by_id)
                    and _prep_ok(up1.prep_cond, level_by_id)
                    and _affordable(up1.cost, state)
                    and (build_id == MAIN_HALL_ID or main_lv >= 1)):
                return BuildAction(kind="construct", build_id=build_id, up=up1)

    # Raise a storage cap that would otherwise block a wanted upgrade forever.
    storage = capped_storage_upgrade(state, config, skip)
    if storage is not None and storage.build.uid not in queued_uids:
        return storage

    for build_id in order:
        if build_id in skip:
            continue
        for build in [b for b in state.builds if b.id == build_id]:
            if build.uid in queued_uids:
                continue
            target = build.lv + 1
            if (build.uid, target) in blocked:
                continue
            if build_id != MAIN_HALL_ID and target > main_lv:
                continue
            up = config.build_upgrade(build_id, target)
            if up is None or not _prep_ok(up.prep_cond, level_by_id) \
                    or not _affordable(up.cost, state):
                continue
            return BuildAction(kind="upgrade", build_id=build_id, up=up, build=build)
    return None
