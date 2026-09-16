"""Deterministic rule engine — the "hands" decide without spending LLM tokens.

A :class:`Rule` inspects :class:`GameState` and, when it applies, performs one
action via :class:`Actions`. The :class:`RuleEngine` runs every applicable rule
per tick (rules must be idempotent). Strategy-level choices (which build order,
whom to attack) belong to the brain, not here — these rules are the routine
housekeeping that keeps the account ticking over.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from nta_agent.execution.actions import Actions
from nta_agent.execution.captcha import ANTI_CHEAT_ECODE, CaptchaRequired
from nta_agent.state.schema import GameState


class Rule(Protocol):
    name: str

    def applies(self, state: GameState, actions: Actions) -> bool: ...
    def act(self, actions: Actions) -> None: ...


def _caps(state: GameState) -> tuple[int, int]:
    """(granaryCap, warehouseCap) from the live player block; 0 if unknown."""
    player = (state.raw or {}).get("player") or {}
    return int(player.get("granaryCap", 0) or 0), int(player.get("warehouseCap", 0) or 0)


@dataclass
class CollectCityOutput:
    """Collect the main city's output while storage has room for it.

    Safe and always beneficial; skipped when storage is at cap (the server would
    reject it anyway) to avoid pointless requests.
    """
    name: str = "collect_city_output"
    fail_cooldown: int = 20  # ticks to wait after a rejection before retrying
    _cooldown: int = 0

    def applies(self, state: GameState, actions: Actions) -> bool:
        if self._cooldown > 0:
            self._cooldown -= 1
            return False
        # Collect only when storage has room; at cap the server rejects it and the
        # gathered output would overflow anyway.
        granary, warehouse = _caps(state)
        if not (granary or warehouse):
            return False  # caps unknown -> don't guess
        r = state.resources
        return (
            (granary and r.cereal < granary)
            or (warehouse and r.timber < warehouse)
            or (warehouse and r.stone < warehouse)
        )

    def act(self, actions: Actions) -> None:
        try:
            actions.collect_city_output()
        except Exception:
            self._cooldown = self.fail_cooldown  # back off, then surface the error
            raise


@dataclass
class BuildOrder:
    """Upgrade buildings along a priority order, respecting prereqs and cost.

    ``sequence`` is a list of build ids in priority order (like the old fixed
    build order); when None, all owned buildings are considered lowest-id first.
    Needs the config tables; if they're absent the rule simply never applies.
    """
    name: str = "build_order"
    sequence: list[int] | None = None
    config: object | None = None
    profile: object = None   # tactics profile: build.order / build.skip
    _pending: object = None  # BuildAction chosen in applies()
    _city: int = 0           # main-city index for construction
    _blocked: set = field(default_factory=set)  # server-rejected steps (2 key shapes)
    _sig: tuple = ()  # last builds signature; changing it clears blocks (retry)

    def _cfg(self):
        if self.config is None:
            from nta_agent.data.config import GameConfig
            try:
                self.config = GameConfig.load()
            except FileNotFoundError:
                self.config = False  # sentinel: unavailable
        return self.config or None

    def applies(self, state: GameState, actions: Actions) -> bool:
        cfg = self._cfg()
        if not cfg:
            return False
        # The build queue holds concurrent build/upgrade tasks; when it is full the
        # server rejects any further build with ecode.500014 ("Construction Queue
        # Full"). Skip entirely rather than churn the whole build list against it.
        slots = state.build_queue_slots or 0
        if slots and len(state.build_queue) >= slots:
            return False
        # When any building level changes, retry previously-blocked steps.
        sig = tuple(sorted((b.uid, b.lv) for b in state.builds))
        if sig != self._sig:
            self._sig = sig
            self._blocked.clear()
        from nta_agent.execution.build_planner import next_build_action
        rt = state.room_type
        seq, skip = self.sequence, None
        if self.profile is not None:
            b = self.profile.build
            skip = b.get("skip") or []
            order = list(b.get("order") or [])
            rest = sorted(set(cfg.in_city_build_ids(rt)) | {x.id for x in state.builds})
            seq = order + [i for i in rest if i not in order]
        self._pending = next_build_action(state, cfg, seq, self._blocked, skip=skip,
                                          room_type=rt)
        self._city = state.main_city_index
        return self._pending is not None

    def act(self, actions: Actions) -> None:
        action = self._pending
        self._pending = None
        if action is None:
            return
        try:
            if action.kind == "construct":
                actions.add_build(self._city, action.build_id)
            else:
                actions.upgrade_build(action.build.index, uid=action.build.uid)
        except Exception:
            # Server rejected (a condition we can't verify locally) — back off this
            # exact step until the builds signature changes, and surface the error.
            if action.kind == "construct":
                self._blocked.add(("construct", action.build_id))
            else:
                self._blocked.add((action.build.uid, action.up.level))
            raise


@dataclass
class OccupyCell:
    """Occupy a nearby resource cell the agent can win, spending stamina for loot.

    Discovers candidates around the main city (GetAreaInfo probe), predicts each
    with battle-A, and sends the strongest garrison army at the lowest-loss win.
    Discovery is throttled (it costs one request per probed cell).
    """
    name: str = "occupy_cell"
    radius: int = 2
    min_stamina: int = 1
    discover_every: int = 8   # ticks between discovery sweeps
    fail_cooldown: int = 8
    predictor: object = None
    use_sim: bool = False      # prefer the headless engine sim for the win verdict
    sim: object = None
    on_event: object = None    # optional on_event(kind, detail) to surface the plan
    profile: object = None     # Profile: group + occupy/loot policy (farming)
    config: object = None      # GameConfig for treasure model (lazy)
    _sim_off: bool = False     # sidecar checked and unavailable -> stop retrying
    _pending: object = None    # (armies_list, target_index)
    _cooldown: int = 0
    _state_ref: object = None  # stashed for act()'s formation optimization
    _land_ref: int = 0

    def _pred(self):
        if self.predictor is None:
            from nta_agent.execution.predictors.battle import BattlePredictor
            try:
                self.predictor = BattlePredictor.from_stats()
            except FileNotFoundError:
                self.predictor = BattlePredictor()
        return self.predictor

    def _sim_pred(self):
        """The headless-sim predictor if enabled and the sidecar is reachable."""
        if not self.use_sim or self._sim_off:
            return None
        if self.sim is None:
            from nta_agent.execution.predictors.sim_bridge import get_bridge
            from nta_agent.execution.predictors.sim_predictor import SimBattlePredictor
            if not get_bridge().available():
                self._sim_off = True
                return None
            self.sim = SimBattlePredictor()
        return self.sim

    @staticmethod
    def _dist(a: int, b: int, width: int = 600) -> int:
        return abs(a % width - b % width) + abs(a // width - b // width)

    def _config(self):
        if self.config is None:
            from nta_agent.data.config import GameConfig
            try:
                self.config = GameConfig.load()
            except FileNotFoundError:
                self.config = False
        return self.config or None

    def _farm_select(self, cands, plans_for, predict, state):
        """Pick the target maximizing loot within the chest budget (profile)."""
        from nta_agent.execution.advisor import best_plan
        from nta_agent.execution.farming import plan_farm
        from nta_agent.execution.treasure_model import cell_loot, chest_budget
        cfg = self._config()
        if cfg is None:  # no treasure model -> fall back to safest win
            return best_plan(cands, plans_for, predict)
        occ = self.profile.occupy
        picks = plan_farm(
            cands,
            lambda c: best_plan([c], plans_for, predict),
            lambda c: cell_loot(c.land_id, cfg),
            budget=chest_budget(state),
            max_loss=occ.get("max_loss", 0),
            min_reward_per_chest=(occ.get("loot") or {}).get("min_reward_per_chest", 0),
            max_march_ms=occ.get("max_march_ms", 0),
        )
        return picks[0].plan if picks else None

    def applies(self, state: GameState, actions: Actions) -> bool:
        if state.resources.stamina < self.min_stamina or not state.main_city_index:
            return False
        if self._cooldown > 0:
            self._cooldown -= 1
            return False
        from nta_agent.execution.occupy_planner import discover_targets
        cands = discover_targets(
            lambda i: actions.get_area(i).get("data", {}),
            state.main_city_index, self.radius, state.user.uid,
        )
        self._cooldown = self.discover_every  # throttle regardless of outcome
        predictor = self._pred()      # stats: fallback verdict
        sim = self._sim_pred()        # engine: authoritative win verdict when available
        from nta_agent.execution.advisor import Plan, best_plan
        from nta_agent.execution.order_strategies import candidate_orders
        from nta_agent.execution.predictors.sim_bridge import SimUnavailable

        cand_by_index = {c.index: c for c in cands}

        def plans_for(i):
            # Candidate selection-orders from the active formation group (or all reachable).
            avail = actions.select_armies(i)
            grp = []
            if self.profile is not None:
                from nta_agent.execution.profile import active_formation
                grp = active_formation(self.profile).get("group") or []
            if grp:
                chosen = [a for a in avail if str(a.get("uid")) in {str(x) for x in grp}]
                avail = chosen or avail
            return [Plan(armies=order, target=i, label=label, prediction=None)
                    for label, order in candidate_orders(avail)]

        def predict(plan):
            c = cand_by_index[plan.target]
            dist = self._dist(state.main_city_index, c.index)
            if sim is not None:
                try:
                    return sim.predict_armies(
                        state, plan.armies,
                        target_index=c.index, land_id=c.land_id, distance=dist)
                except SimUnavailable:
                    pass
            pawns = [p for a in plan.armies for p in (a.get("pawns") or [])]
            return predictor.predict(pawns, c.defenders)

        # Profile-driven farming (chest budget) or the plain safest-win pick.
        loot_on = (self.profile is not None
                   and (self.profile.occupy.get("loot") or {}).get("enabled", True))
        kind = "occupy_plan"
        if loot_on:
            plan = self._farm_select(cands, plans_for, predict, state)
            kind = "farm_plan"
        else:
            plan = best_plan(cands, plans_for, predict)
        if plan is None:
            return False
        self._pending = (list(plan.armies), plan.target)
        self._state_ref = state
        self._land_ref = cand_by_index[plan.target].land_id
        if self.on_event:
            self.on_event(kind, {
                "target": plan.target,
                "label": plan.label,
                "order": [a.get("name") or a.get("uid") for a in plan.armies],
                "loss_percent": round(plan.prediction.loss_percent, 1),
            })
        return True

    def _optimize_formations(self, actions, armies, target) -> None:
        """Reorder each melee army so the beefiest pawn tanks (fewest deaths, tie
        -> best damage spread), applied via ExchangePawnArmy swaps in the city.
        Best-effort: never block the occupy.

        Formation pawns (with hp/id, in list order) come from get_area(city);
        points are stripped before scoring so the sim decides by ORDER (pawns
        stack at the entry, just like a real battle)."""
        from nta_agent.execution.formation import candidate_orderings, swaps_for
        from nta_agent.execution.order_strategies import is_archer_army
        from nta_agent.execution.predictors.sim_bridge import SimUnavailable
        sim = self._sim_pred()
        if sim is None or self._state_ref is None:
            return
        city = self._state_ref.main_city_index
        dist = self._dist(city, target)
        try:
            area = actions.get_area(city).get("data", {})
        except Exception:
            return
        area_by_uid = {a.get("uid"): a for a in (area.get("armys") or [])}

        for army in armies:
            area_army = area_by_uid.get(army.get("uid"))
            if area_army is None:
                continue
            pawns = list(area_army.get("pawns") or [])
            if is_archer_army(area_army) or len(pawns) < 2:
                continue
            cands = candidate_orderings(area_army)
            if len(cands) < 2:
                continue

            au = army.get("uid")
            aidx = area_army.get("index", city)

            def _score(order, au=au, aidx=aidx):
                # strip points -> pawns stack at entry -> ORDER decides who tanks
                posed = {"uid": au, "index": aidx,
                         "pawns": [{k: v for k, v in p.items() if k != "point"} for p in order]}
                try:
                    pred = sim.predict_armies(self._state_ref, [posed], target_index=target,
                                              land_id=self._land_ref, distance=dist)
                except SimUnavailable:
                    return None
                if pred is None or not pred.win:
                    return None
                surv = pred.pawn_survival or []
                worst = max((100 - s.get("curHp", 0) for s in surv if s.get("camp") == 2), default=0)
                return (pred.loss_percent, worst)

            best = None
            for label, order in cands:
                sc = _score(order)
                if sc is None:
                    continue
                if best is None or sc < best[0]:
                    best = (sc, label, order)
            if best is None:
                continue
            sc, label, order = best
            cur_uids = [p.get("uid") for p in pawns]
            target_uids = [p.get("uid") for p in order]
            swaps = swaps_for(cur_uids, target_uids)
            if not swaps:
                continue
            try:
                for a_uid, b_uid in swaps:
                    actions.exchange_pawn_army(city, army["uid"], a_uid, b_uid)
                if self.on_event:
                    self.on_event("formation_plan", {
                        "army": army.get("name") or army.get("uid"),
                        "label": label, "loss_percent": round(sc[0], 1)})
            except Exception:
                pass  # never block the occupy

    def act(self, actions: Actions) -> None:
        if not self._pending:
            return
        armies, target = self._pending
        self._pending = None
        self._optimize_formations(actions, armies, target)
        try:
            actions.occupy_cell(target, armies)
        except Exception:
            self._cooldown = self.fail_cooldown
            raise


@dataclass
class Recruit:
    """Recruit an already-unlocked pawn into an army at the main city.

    A pawn must be *unlocked* (present in player.pawnSlots) before it can be
    drilled — drilling a locked pawn returns ecode.500017. We recruit into a city
    army that has room (<9 pawns), or create a new one while under the army cap.
    Unlocking new pawn types (StudySelect) is a separate concern left to strategy.
    """
    name: str = "recruit"
    barracks_id: int = 2004
    max_army_pawns: int = 9
    max_armies: int = 4
    fail_cooldown: int = 10
    config: object = None
    profile: object = None    # Profile: fill armies toward army.composition
    _pending: object = None   # (build_uid, pawn_id, army_uid, army_name, pawn_count)
    _cooldown: int = 0
    # Armies the server rejected as full (ecode.500019), by uid -> pawn count when
    # rejected. The per-army cap is not in the data (it varies by army), so we learn
    # it: skip an army marked full until its pawn count changes.
    _full: dict = field(default_factory=dict)

    ARMY_FULL_ECODE = "ecode.500019"

    def _is_full(self, army: dict) -> bool:
        uid = str(army.get("uid"))
        if uid not in self._full:
            return False
        if self._full[uid] == len(army.get("pawns", [])):
            return True
        del self._full[uid]  # roster changed -> stale mark, re-evaluate
        return False

    def _cfg(self):
        if self.config is None:
            from nta_agent.data.config import GameConfig
            try:
                self.config = GameConfig.load()
            except FileNotFoundError:
                self.config = False
        return self.config or None

    def _unlocked_pawns(self, state: GameState) -> list[int]:
        slots = (state.raw or {}).get("player", {}).get("pawnSlots") or {}
        return [int(v["id"]) for v in slots.values() if isinstance(v, dict) and v.get("id")]

    def _affordable(self, state: GameState, pawn_id: int) -> bool:
        cfg = self._cfg()
        if not cfg:
            return True  # can't check -> let the server decide
        cost = cfg.pawn_recruit_cost(pawn_id)
        r = state.resources
        have = {"cereal": r.cereal, "timber": r.timber, "stone": r.stone, "iron": r.iron}
        return all(have.get(k, 0) >= v for k, v in cost.items())

    def applies(self, state: GameState, actions: Actions) -> bool:
        if self._cooldown > 0:
            self._cooldown -= 1
            return False
        bu = actions.building_uid(self.barracks_id)
        if not bu or not state.main_city_index:
            return False
        unlocked = self._unlocked_pawns(state)
        if not unlocked:
            return False  # nothing to recruit (needs StudySelect first)
        pawn = next((p for p in unlocked if self._affordable(state, p)), None)
        if pawn is None:
            return False
        armys = actions.get_area(state.main_city_index).get("data", {}).get("armys", []) or []
        # profile-driven: fill the biggest composition gap into its own army.
        if self.profile is not None:
            from nta_agent.execution.profile import active_formation, composition_target
            comp = active_formation(self.profile).get("composition")
            tgt = composition_target(self.profile, armys, unlocked, composition=comp)
            if tgt is not None:
                army_uid, pid = tgt
                army = next((a for a in armys if str(a.get("uid")) == army_uid), None)
                if (army is not None and self._affordable(state, pid)
                        and not army.get("state")
                        and not self._is_full(army)
                        and len(army.get("pawns", [])) < self.max_army_pawns):
                    self._pending = (bu, pid, army_uid, "", len(army.get("pawns", [])))
                    return True
        # recruit into a non-marching city army that still has room
        room = next((a for a in armys
                     if not a.get("state") and not self._is_full(a)
                     and len(a.get("pawns", [])) < self.max_army_pawns), None)
        if room:
            self._pending = (bu, pawn, str(room["uid"]), "", len(room.get("pawns", [])))
        elif len(armys) < self.max_armies:
            self._pending = (bu, pawn, "", f"D{len(armys) + 1}", 0)
        else:
            return False
        return True

    def act(self, actions: Actions) -> None:
        if not self._pending:
            return
        bu, pawn, au, name, count = self._pending
        self._pending = None
        try:
            actions.drill_pawn(bu, pawn, army_uid=au, army_name=name)
        except Exception as e:
            # "Army Soldier Full": our optimistic cap was wrong for this army.
            # Learn it and stop retrying this army — an expected condition, not an
            # error worth surfacing every cooldown.
            if au and self.ARMY_FULL_ECODE in str(e):
                self._full[str(au)] = count
                return
            self._cooldown = self.fail_cooldown
            raise


@dataclass
class ClaimTreasures:
    """Open + claim treasures earned from occupying cells (deterministic).

    A pawn with a non-empty ``treasures`` field has a pending chest. We batch
    open (unopened) then claim, capped at the current chest budget. Best-effort:
    a batch error (e.g. already-opened) never blocks the loop.
    """
    name: str = "claim_treasures"
    _targets: object = None

    @staticmethod
    def _pending(armies) -> list[dict]:
        out = []
        for a in armies or []:
            if any((p.get("treasures") or []) for p in (a.get("pawns") or [])):
                out.append({"index": int(a.get("index", 0)), "auid": str(a.get("uid"))})
        return out

    def applies(self, state: GameState, actions: Actions) -> bool:
        # Cheap gate: only fetch armies when the server flags a new treasure.
        player = (state.raw or {}).get("player", {}) or {}
        if not player.get("hasNewTreasure"):
            return False
        try:
            armies = actions.get_player_armys()
        except Exception:
            return False
        from nta_agent.execution.treasure_model import chest_budget
        budget = chest_budget(state)
        targets = self._pending(armies)
        self._targets = targets[:budget] if budget < 10_000 else targets
        return bool(self._targets)

    def act(self, actions: Actions) -> None:
        targets, self._targets = self._targets, None
        if not targets:
            return
        try:
            actions.open_armys_treasure(targets)
            actions.claim_armys_treasure(targets)
        except Exception:
            pass  # best-effort; never block the loop


@dataclass
class ClaimTasks:
    """Claim completed task rewards (guide / other / today) — server-authoritative.

    Task ``progress`` isn't always maintained server-side (some conditions are
    verified only on claim), so instead of predicting completion we *attempt* the
    claim and let the server decide. A rejected id is backed off until the task
    lists change (progress advanced), then retried. Guide tasks in particular
    carry the early-game gameplay guidance + worthwhile rewards.
    """
    name: str = "claim_tasks"
    sweep_every: int = 20     # ticks between claim attempts (claiming isn't urgent)
    _seen: set = field(default_factory=set)   # (kind,id) already attempted this cycle
    _sig: tuple = ()          # task-list signature; changes reset _seen (retry as play advances)
    _cooldown: int = 0
    _pending: object = None    # (kind, id)

    _KINDS = (("guideTasks", "guide"), ("otherTasks", "other"), ("todayTasks", "today"))

    @staticmethod
    def _tasks(state: GameState, key: str) -> list[dict]:
        return (state.raw or {}).get("player", {}).get(key) or []

    def applies(self, state: GameState, actions: Actions) -> bool:
        if self._cooldown > 0:
            self._cooldown -= 1
            return False
        # When the task lists move (ids/progress changed, e.g. after a claim or as
        # play advances), forget what we tried so completed tasks get another go.
        sig = tuple(
            (kind, t.get("id"), t.get("progress"))
            for key, kind in self._KINDS for t in self._tasks(state, key)
        )
        if sig != self._sig:
            self._sig = sig
            self._seen.clear()
        for key, kind in self._KINDS:
            for t in self._tasks(state, key):
                tid = t.get("id")
                if tid is None or (kind, tid) in self._seen:
                    continue
                self._pending = (kind, tid)
                return True
        return False

    def act(self, actions: Actions) -> None:
        if not self._pending:
            return
        kind, tid = self._pending
        self._pending = None
        self._seen.add((kind, tid))  # attempted once per cycle, win or lose
        claim = {"guide": actions.claim_task,
                 "other": actions.claim_other_task,
                 "today": actions.claim_today_task}[kind]
        self._cooldown = self.sweep_every  # one claim per sweep
        try:
            claim(tid)
        except Exception:  # "not complete" is the expected case — stay quiet, retry next cycle
            return


@dataclass
class RuleEngine:
    rules: list[Rule]

    def tick(self, state: GameState, actions: Actions) -> list[str]:
        """Run every applicable rule once; return the names that fired."""
        fired: list[str] = []
        for rule in self.rules:
            try:
                if rule.applies(state, actions):
                    rule.act(actions)
                    fired.append(rule.name)
            except CaptchaRequired:
                raise
            except Exception as e:  # a failing rule must not kill the loop
                if ANTI_CHEAT_ECODE in str(e):
                    raise CaptchaRequired(str(e)) from e
                detail = str(e).split(":")[-1].strip() or type(e).__name__
                fired.append(f"{rule.name}!ERR:{detail}")
        return fired

    @classmethod
    def default(cls, profile: object = None) -> RuleEngine:
        return cls(rules=[CollectCityOutput(), BuildOrder(profile=profile),
                          Recruit(profile=profile),
                          OccupyCell(use_sim=True, profile=profile),
                          ClaimTreasures(), ClaimTasks()])
