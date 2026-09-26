"""Wire config + bootstrap + session + Agent into a runnable, observable spine."""
from __future__ import annotations

import json
import sys

from nta_agent.data.config import GameConfig
from nta_agent.execution.agent import Agent
from nta_agent.execution.captcha import CaptchaSolver
from nta_agent.execution.heuristics import RuleEngine
from nta_agent.io.adb import DeviceManager
from nta_agent.io.api.client import ServerConfig
from nta_agent.io.api.session import GameSession
from nta_agent.io.bootstrap import make_token_refresher
from nta_agent.runtime.config import RuntimeConfig
from nta_agent.runtime.control import read_mode
from nta_agent.runtime.decision_service import DecisionService
from nta_agent.runtime.eventlog import EventLog
from nta_agent.runtime.snapshot import write_snapshot


def run_services(state, cfg, service, brain, forts, safe, observer=None) -> bool:
    """Run the acting services unless paused. Returns True if it acted."""
    if read_mode(cfg.control_path) == "pause":
        return False  # observe only while paused
    if service is not None:
        safe(service.tick, state)
    if observer is not None:
        safe(observer.tick, state)  # record real losses BEFORE the brain reads them
    safe(brain.tick, state)
    safe(forts.tick, state)
    return True


def build_session(cfg: RuntimeConfig) -> GameSession:
    dm = DeviceManager.connect()
    refresher = make_token_refresher(dm, cfg.token_path)
    session = GameSession(server=ServerConfig(host=cfg.host),
                          token_path=cfg.token_path, token_refresher=refresher)
    session.connect(timeout=15)
    session.login(distinct_id=cfg.distinct_id)
    session.enter_game(distinct_id=cfg.distinct_id)
    return session


def run(cfg: RuntimeConfig, *, ticks: int = 0, session=None, engine=None) -> None:
    log = EventLog(cfg.event_log_path)
    if session is None:
        session = build_session(cfg)
        log.append("started", {"host": cfg.host})
    from nta_agent.execution.profile import load_profile
    profile = load_profile(cfg.profile_path)  # shared by the rules and the brain
    if engine is None:
        engine = RuleEngine.default(profile=profile)
    from nta_agent.execution.health import HealthMonitor
    health = HealthMonitor(stale_after=getattr(cfg, "stale_after", 90.0))
    agent = Agent(session, engine, max_backoff=cfg.max_backoff, on_event=log.append,
                  health=health)

    try:
        config = GameConfig.load()
    except FileNotFoundError:
        config = None
        log.append("config_missing")

    # Structured error log for unattended runs (morning post-mortem).
    from nta_agent.runtime.errorlog import ErrorLog
    errlog = ErrorLog(cfg.errors_path, config)
    _ERROR_KINDS = {"connection_lost", "recover_retry", "captcha_failed",
                    "captcha_detected", "config_missing", "interrupted",
                    "captured"}  # main city fell: the player must decide (re-create/settle)

    def on_event(kind, detail=None):
        log.append(kind, detail)
        if kind in _ERROR_KINDS:
            errlog.log("agent", kind, detail)

    agent.on_event = on_event
    engine.on_error = errlog.rule_error  # full rule errors (traceback + ecode + reason)
    if config is None:
        errlog.log("runtime", "config_missing", "GameConfig not found")

    service = None
    if config is not None:
        service = DecisionService(agent.actions, config, cfg, on_event=on_event,
                                  profile=profile)
        agent.captcha = CaptchaSolver(agent.actions, config)
    from nta_agent.runtime.brain_service import BrainService
    brain = BrainService(profile, cfg, on_event=on_event, actions=agent.actions)
    from nta_agent.runtime.fort_service import FortService
    forts = FortService(cfg, agent.actions, on_event=on_event)
    # Dig a path to a player-picked cell (dashboard request -> preview -> confirm).
    from nta_agent.runtime.dig_service import (
        DigService,
        make_predict_factory,
        make_stamina_fn,
    )
    dig = DigService(cfg, agent.actions, profile=profile, on_event=on_event,
                     predict_factory=make_predict_factory(agent.actions, profile))
    dig._stamina_fn = make_stamina_fn(
        config, dig.world, lambda: int(getattr(session.state, "main_city_index", 0) or 0))
    # Early warning (capture / incoming hostile marches / approach) -> alerts.json.
    from nta_agent.runtime.alert_service import AlertService
    alerts = AlertService(cfg, agent.actions, on_event=on_event,
                          poll_every=getattr(cfg, "march_poll_every", 6))
    # F2/brain: hands-side failure ledger + loss observer (Cách A — brain only reads).
    from nta_agent.execution.ledger import FailureLedger
    from nta_agent.execution.loss_observer import LossObserver
    from nta_agent.execution.predictors.sim_bridge import get_bridge
    ledger = FailureLedger(cfg.failures_path, cap=cfg.ledger_cap)
    observer = LossObserver(agent.actions, ledger, get_bridge(),
                            player_uid=getattr(session.state.user, "uid", ""),
                            on_event=on_event)

    def _active_lessons():  # Inc 3: occupy reads active lessons for contextual recall
        try:
            from nta_agent.brain.lessons import LessonStore
            return LessonStore(cfg.lessons_path).active()
        except Exception:
            return []
    def _enemy_from_forts():
        # P2: enemy cell indices from the (throttled) FortService output — no request.
        try:
            data = json.loads(cfg.forts_path.read_text(encoding="utf-8"))
        except Exception:
            return set()
        return {int(y) * 600 + int(x) for x, y in (data.get("enemy_cells") or [])}

    def _forts_from_json():
        # Built-fort cell indices from the (throttled) FortService output — detected
        # from the map-chunk city decode (cityType==2), no extra request.
        try:
            data = json.loads(cfg.forts_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        return [int(y) * 600 + int(x) for x, y in (data.get("forts") or [])]

    def _territory_from_forts():
        # (owned cell indices, speed-zone centers = main-city block + built forts)
        # for bridging — from the throttled FortService output, no extra request.
        try:
            data = json.loads(cfg.forts_path.read_text(encoding="utf-8"))
        except Exception:
            return set(), []
        owned = {int(y) * 600 + int(x) for x, y in (data.get("owned_cells") or [])}
        forts = _forts_from_json()
        main = int(getattr(session.state, "main_city_index", 0) or 0)
        centers = ([main, main + 1, main + 600, main + 601] if main else []) + forts
        return owned, centers

    dig._forts_source = _forts_from_json

    def _clear_strike_target():
        from nta_agent.execution.profile import clear_strike_target
        clear_strike_target(cfg.profile_path)
        log.append("composition_target_cleared", {})

    _rules = getattr(agent.engine, "rules", [])
    _composer = next((r for r in _rules if getattr(r, "name", "") == "army_composer"), None)
    _buffers = next((r for r in _rules if getattr(r, "name", "") == "buffer_leveling"), None)
    _spares = next((r for r in _rules if getattr(r, "name", "") == "spare_armies"), None)

    def _make_comp_status_sink():  # defined out of the loop (no loop-var capture)
        state = {"was": False}

        def sink(s):  # persist for the brain advice loop / dashboard + stuck_goal ledger
            try:
                p = cfg.composition_status_path
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass
            blocked = bool(isinstance(s, dict) and s.get("blocked"))
            if blocked and not state["was"]:  # record once, on transition into blocked
                try:
                    ledger.record("stuck_goal", {"goal": "composition",
                                                 "detail": (s or {}).get("issues") or []})
                except Exception:
                    pass
            state["was"] = blocked
        return sink

    # Surface the occupy planner's reasoning (chosen army + predicted loss) to the log.
    for rule in _rules:
        # F2/brain: rules that back off on insufficient resources report it (res_depletion).
        if getattr(rule, "name", "") in ("leveling", "forge", "army_composer"):
            rule.ledger = ledger
        if getattr(rule, "name", "") == "leveling":
            rule.dig_live_source = dig.is_live  # the dig group isn't leveled mid-dig
        if getattr(rule, "name", "") == "spare_armies":
            from nta_agent.runtime.spare_predict import make_spare_predict
            rule.advice_path = cfg.spare_advice_path
            rule.on_event = log.append
            rule.predict = make_spare_predict(cfg, profile)

            def _spare_excluded():  # armies other features own right now
                out = set(getattr(_composer, "locked_uids", set()) if _composer else set())
                if _buffers is not None:
                    out |= _buffers.buffer_uids() | _buffers.away_uids()
                return out
            rule.excluded_source = _spare_excluded
        if getattr(rule, "name", "") == "buffer_leveling":
            rule.state_path = cfg.buffers_path  # proposal/approval/phases (dashboard reads it)
            rule.on_event = log.append
            rule.territory_source = _territory_from_forts  # owned cells for the meeting cell
        if getattr(rule, "name", "") == "occupy_cell":
            rule.on_event = log.append
            rule.threats_source = _enemy_from_forts  # defend contested border cells (P2)
            rule.territory_source = _territory_from_forts  # bridging (forward staging)
            rule.lessons_source = _active_lessons  # Inc 3: contextual lesson recall
            rule.dig_source = dig.next_target      # dig the planned path (after confirm)
            rule.dig_hard_sink = dig.report_hard
            rule.dig_live_source = dig.is_live     # reserve the group while waiting too
            if _buffers is not None:  # buffer leveling: never occupy with buffers / swappers
                rule.away_source = _buffers.away_uids
                rule.buffer_source = _buffers.buffer_uids
            if _spares is not None:  # spares being gathered/sorted aren't sent out
                rule.spare_reserved_source = _spares.reserved_uids
            if _composer is not None:  # skip armies the composer is arranging (it locks them)
                rule.locked_source = lambda: getattr(_composer, "locked_uids", set())
            if config is not None:  # pace discovery by the cheapest occupy cost
                from nta_agent.execution.occupy_planner import min_occupy_stamina
                rule.min_stamina = min_occupy_stamina(config)
        elif getattr(rule, "name", "") in ("recruit", "logistics", "heal_routing"):
            # every rule that moves/fills armies must skip the ones the composer owns
            if _composer is not None:
                rule.locked_source = lambda: getattr(_composer, "locked_uids", set())
            if getattr(rule, "name", "") == "logistics" and _buffers is not None:
                # Logistics packs/moves pawns between armies: keep it off the buffers,
                # the armies a buffer setup draws from and a main army away swapping
                rule.locked_source = lambda: (
                    set(getattr(_composer, "locked_uids", set()) if _composer else set())
                    | _buffers.buffer_uids() | _buffers.away_uids())
            if getattr(rule, "name", "") in ("logistics", "heal_routing"):
                # treat built forts as heal/relay nodes (fortAutoSupports is empty
                # for a freshly built fort; detect them from the chunk city decode)
                rule.forts_source = _forts_from_json
            if getattr(rule, "name", "") == "logistics":
                # drop redeploys to off-territory cells (ecode.500039)
                rule.owned_source = lambda: _territory_from_forts()[0]
        elif getattr(rule, "name", "") == "army_composer":
            rule.on_event = log.append
            # restore the strike armies of an unfinished goal (they were in memory only,
            # so a restart re-picked — wrongly — among idle armies)
            try:
                prev = json.loads(cfg.composition_status_path.read_text(encoding="utf-8"))
                if isinstance(prev, dict) and prev.get("active"):
                    rule.restore_strike(prev.get("strike") or [])
            except (OSError, ValueError):
                pass
            rule.status_sink = _make_comp_status_sink()
            rule.target_sink = _clear_strike_target  # one-shot goal: persist the clear
        elif getattr(rule, "name", "") == "fort_build":
            from nta_agent.runtime import fort_queue
            rule.pending_source = lambda: fort_queue.load(cfg.pending_forts_path)
            rule.remove_fn = lambda i: fort_queue.remove(cfg.pending_forts_path, i)
            rule.on_event = log.append
        elif getattr(rule, "name", "") == "forge":
            from nta_agent.runtime import forge_targets as _ft
            rule.on_event = log.append
            rule.targets_source = lambda: _ft.load(cfg.forge_targets_path)
            rule.spend_fn = lambda uid, iron: _ft.spend(cfg.forge_targets_path, uid, iron)
        elif getattr(rule, "name", "") == "build_order":
            from nta_agent.runtime import fort_queue as _fq
            rule.pending_forts_source = lambda: _fq.load(cfg.pending_forts_path)

    def _safe(fn, *a):
        try:
            fn(*a)
        except Exception as e:  # observability must not kill the loop
            sys.stderr.write(f"[spine] {fn.__name__} failed: {e}\n")
            errlog.log(getattr(fn, "__name__", "service"), "service_error", e)

    from nta_agent.execution.profile import reload_into
    from nta_agent.runtime.new_game import check_new_game

    def _write_forge_view(state):  # recast panel rows for the dashboard
        if config is None:
            return
        from nta_agent.execution.forge import forge_view
        from nta_agent.runtime import forge_targets as _ft
        text = config.table("equipText")
        player = (state.raw or {}).get("player") or {}

        def _vi(key):
            row = text.get(key) or {}
            return row.get("vi") or row.get("en")
        rows = forge_view(player.get("equips") or [],
                          lambda i: config.table("equipBase").get(i),
                          lambda t: config.table("equipEffect").get(t),
                          _ft.load(cfg.forge_targets_path),
                          name_of=lambda i: _vi(f"name_{i}"),
                          effect_text=lambda t: _vi(f"effect_{t}"))
        out = {"equips": rows, "busy": player.get("currForgeEquip") or None,
               "iron": state.resources.iron}
        p = cfg.forge_view_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")

    def _write_health():  # F1: connection-health telemetry for the dashboard
        p = cfg.health_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(health.status(session.last_activity), ensure_ascii=False),
                     encoding="utf-8")

    def on_tick(i, fired, state):
        _safe(write_snapshot, state, cfg.snapshot_path)
        _safe(log.tick, i, fired, state)
        _safe(_write_health)
        _safe(alerts.tick, state)  # observe-only: runs even when paused/captured
        # dig: previews only read map chunks; the digging itself is OccupyCell's
        _safe(dig.tick, state)
        _safe(_write_forge_view, state)
        # pick up dashboard edits + stop the brain from clobbering them (shared obj)
        _safe(reload_into, profile, cfg.profile_path)
        # a NEW main city (re-created after capture) = new game: drop stale uid/cell state
        _safe(check_new_game, profile, cfg, state, on_event)
        run_services(state, cfg, service, brain, forts, _safe, observer=observer)

    try:
        agent.run(ticks=ticks, interval=cfg.interval, on_tick=on_tick,
                  control=lambda: read_mode(cfg.control_path))
    except KeyboardInterrupt:
        log.append("interrupted")
    except Exception as e:  # last-resort: record why the loop died before re-raising
        errlog.log("runtime", "loop_fatal", e)
        log.append("loop_fatal", str(e))
        raise
    finally:
        _safe(write_snapshot, session.state, cfg.snapshot_path)
        log.append("error_summary", errlog.summary())  # morning-friendly roll-up
        session.close()
