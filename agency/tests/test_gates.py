import json

import pytest

from agency import config, ledger, loader
from agency.__main__ import build
from agency.config import ConfigError
from agency.gates import KINDS, OVERRUN, USD_PER_1K_TOKENS, WORST_CASE, Decided, Gates
from agency.scheduler import Scheduler, ScheduleError
from agency.sim import Sim

from test_server import TOKEN, app, call, live  # noqa: F401  (fixtures)

H = 3600
MEMBERS = {"ops": ["o1", "o2", "o3"]}


def mk(fund=0, cap=0, attempts=3, deadline_min=60, check=None, path=None, budget=1000, window="06:00", close="10:00"):
    """One department, ops (all the share), open 06:00 to close (grace = a quarter of the window past close); 1000 tokens per 5-hour usage window;
    request deadline 60 minutes, so a request raised before 06:00 expires at 06:55."""
    g = Gates(config.load_gates({"overtime_fund_usd": fund, "per_job_cap_usd": cap, "max_attempts": attempts, "deadline_minutes": deadline_min}, "t"))
    sc = config.load_schedule({"max_working": 2, "max_loaded": 3, "usage_window_hours": 5, "usage_window_tokens": budget, "minutes_per_tick": 5,
                               "departments": {"ops": {"share": 100, "start": window, "end": close}}}, "t")
    return Scheduler(sc, MEMBERS, 6 * H - 300, gates=g, check=check, path=path)     # the clock starts just before the window opens


def paused_overrun(**kw):
    """A job paused at the end of its grace (window_cap): its overrun request is pending. Time is 11:00, the request's deadline 12:00."""
    s = mk(**kw)
    j = s.add("ops", "long", 100, 8 * H)
    s.step(6 * H)
    assert s.running == [j]
    s.step(11 * H)
    assert j["paused"] == "window_cap" and not s.running and j["hold"]
    return s, j, s.gates.pending[j["hold"]]


# ---- gates -----------------------------------------------------------------------------------------------------------------------------------------------

def test_a_gated_job_does_not_proceed_until_approved():
    s = mk()
    j = s.add("ops", "x", 100, 600)
    r = s.gate(j, "spend", "Buy a data set", 12.5)
    assert set(r) == {"id", "kind", "dept", "job", "summary", "cost", "created", "deadline"} and r["job"] == j["id"] and r["cost"] == 12.5
    for t in range(6 * H, 6 * H + 1800, 300):
        s.step(t)
        assert not s.running and j["hold"] == r["id"]               # window open, budget free, agent free: only the gate holds it
    s.decide(r["id"], True)
    s.step(6 * H + 1800)
    assert s.running == [j] and j["hold"] is None
    assert s.gates.log[-1]["outcome"] == "approved" and not s.gates.pending


def test_deny_drops_the_job():
    s = mk()
    j, k = s.add("ops", "x", 100, 600), s.add("ops", "y", 100, 600)
    s.gate(j, "outbound", "Send a post", 0)
    s.decide(j["hold"], False)
    s.step(6 * H)
    assert j["dropped"] and j not in s.queue["ops"] and s.running == [k]
    s.step(8 * H)
    assert j["end"] is None and j["t"] == 0


@pytest.mark.parametrize("kind", [k for k in KINDS if k not in OVERRUN])
def test_expiry_is_denied_for_every_non_overrun_kind_even_with_money_in_the_fund(kind):
    s = mk(fund=1000, cap=1000)                                   # a rich fund must not matter: these are never auto-approved
    j = s.add("ops", "x", 100, 600)
    r = s.gate(j, kind, "s", 0.01)
    s.step(6 * H + 3000)
    assert s.gates.pending and not s.running                      # before the deadline (06:55): still waiting
    s.step(7 * H)
    assert not s.gates.pending and s.gates.log[-1] == {"id": r["id"], "kind": kind, "dept": "ops", "job": j["id"], "cost": 0.01, "outcome": "expired", "at": 7 * H}
    assert j["dropped"] and not s.running and s.gates.fund == 1000


def test_expiry_before_the_deadline_does_not_happen_and_decide_after_expiry_is_a_conflict():
    s = mk()
    j = s.add("ops", "x", 100, 600)
    r = s.gate(j, "rules", "s", 0)
    s.step(6 * H + 3299)
    assert r["id"] in s.gates.pending
    s.step(6 * H + 3300)                                          # exactly at the deadline
    with pytest.raises(Decided):
        s.decide(r["id"], True)
    assert not j["over"] and j["dropped"]


def test_overrun_auto_continues_only_when_fund_and_cap_allow_and_the_debit_is_logged():
    s, j, r = paused_overrun(fund=1.0, cap=0.5)
    assert r["kind"] == "overrun_time" and r["cost"] == 0.01
    s.step(11 * H + 1800)
    assert not s.running and r["id"] in s.gates.pending           # not yet: the user still has time
    s.step(12 * H)
    assert s.running == [j] and j["over"] == "overrun_time" and j["paused"] is None
    assert s.gates.fund == 0.99 and s.gates.log[-1]["outcome"] == "auto" and s.gates.log[-1]["cost"] == 0.01
    assert s.gates.snapshot(12 * H)["fund"] == 0.99
    snap = ledger.Ledger("none.json").snapshot()                  # the reserve is a different pot: never touched
    assert (snap["capital"], snap["working_capital"], snap["reserve"]) == (100.0, 80.0, 20.0)


@pytest.mark.parametrize("fund,cap", [(0, 0), (0, 5), (5, 0), (0.005, 5), (5, 0.005)])
def test_overrun_is_denied_at_expiry_when_the_fund_or_the_cap_does_not_allow_it(fund, cap):
    s, j, r = paused_overrun(fund=fund, cap=cap)
    s.step(12 * H)
    assert not s.running and j["over"] is None and j["hold"] is None and j in s.queue["ops"]      # stays paused, not dropped
    assert s.gates.fund == fund and s.gates.log[-1]["outcome"] == "expired"
    s.step(24 * H + 6 * H)                                        # next day's window: it resumes by itself
    assert s.running == [j]


def test_the_default_config_never_auto_continues(cfg):
    assert cfg.gates["fund"] == 0 and cfg.gates["cap"] == 0 and cfg.gates["attempts"] == 3
    assert config.load_gates(None, "t") == {"fund": 0.0, "cap": 0.0, "attempts": 3, "deadline_s": 43200}
    s, j, r = paused_overrun()                                    # fund and cap default to 0
    s.step(13 * H)
    assert not s.running and s.gates.log[-1]["outcome"] == "expired" and s.gates.fund == 0


def test_user_approval_lets_a_job_run_past_the_close_and_deny_leaves_it_paused():
    s, j, r = paused_overrun()
    s.decide(r["id"], True)
    s.step(11 * H + 300)
    assert s.running == [j] and j["over"] == "overrun_time" and s.gates.fund == 0 and s.gates.log[-1]["outcome"] == "approved"
    s2, j2, r2 = paused_overrun()
    s2.decide(r2["id"], False)
    s2.step(11 * H + 300)
    assert not s2.running and j2 in s2.queue["ops"] and not j2["dropped"]


def test_an_approved_usage_overrun_runs_past_the_budget_and_is_not_billed_to_it():
    s = mk(budget=1000)
    j = s.add("ops", "big", 100, 3000, actual=3000)               # 1 token/s: the 1000-token budget is gone after 1000 s
    s.step(6 * H)
    s.step(6 * H + 1100)
    assert j["paused"] == "hard_stop" and j["hold"] and s.gates.pending[j["hold"]]["kind"] == "overrun_usage"
    spent = sum(s.spent.values())
    assert spent == pytest.approx(1000)
    s.decide(j["hold"], True)
    s.step(6 * H + 1200)
    assert s.running == [j]
    s.step(6 * H + 4500)
    assert j["end"] and j["spent"] == pytest.approx(3000) and sum(s.spent.values()) == pytest.approx(spent)


# ---- stop rules ------------------------------------------------------------------------------------------------------------------------------------------

def run_until(s, t0, t1, step=300):
    for t in range(t0, t1, step):
        s.step(t)


def test_three_failed_attempts_block_the_job_and_there_is_no_fourth():
    calls = []
    s = mk(check=lambda j: calls.append(j["id"]) or False)
    j = s.add("ops", "x", 100, 600)
    run_until(s, 6 * H, 9 * H)
    assert len(calls) == 3 and j["tries"] == 3 and j["blocked"] and j["end"] and not s.running and j not in s.queue["ops"]
    assert s.newly_blocked == [j] and [b["job"] for b in s.gates.blocked] == [j["id"]] and s.gates.blocked[0]["attempts"] == 3
    run_until(s, 9 * H, 30 * H)                                   # a day later: still never retried
    assert len(calls) == 3 and not s.running


def test_attempts_come_from_config_and_a_pass_ends_the_job():
    s = mk(attempts=2, check=lambda j: False)
    j = s.add("ops", "x", 100, 600)
    run_until(s, 6 * H, 9 * H)
    assert j["tries"] == 2 and j["blocked"]
    out = iter([False, False, True])
    s = mk(check=lambda j: next(out))
    j = s.add("ops", "y", 100, 600)
    run_until(s, 6 * H, 9 * H)
    assert j["tries"] == 2 and not j["blocked"] and j["end"] and not s.newly_blocked and not s.queue["ops"]


def test_a_retry_starts_from_scratch():
    s = mk(check=lambda j: False)
    j = s.add("ops", "x", 100, 600)
    s.step(6 * H)
    s.step(6 * H + 600)
    assert j["tries"] == 1 and j["t"] == 0 and j["spent"] == 0 and j["end"] is None and s.running == [j]


def test_the_sim_reports_a_blocked_job_up_the_chain(cfg, monkeypatch):
    monkeypatch.setattr("agency.sim.FAIL_P", 1.0)
    o = loader.load_dir(cfg.departments_dir, cfg)
    sim = Sim(o, 2, max_events=20000)
    for _ in range(700):
        sim.step()
    ev = [e for e in sim.events if e["kind"] == "stop"]
    blocked = sim.sched.gates.blocked
    assert ev and blocked and all(b["attempts"] == 3 for b in blocked) and not sim.sched.newly_blocked
    top = [e for e in ev if e["dst"] == o.root]                   # the last hop of the report: lead -> boss
    assert top and all(o.agents[e["src"]].dept in o.leads and e["src"] == o.leads[o.agents[e["src"]].dept] for e in top)


# ---- sim -------------------------------------------------------------------------------------------------------------------------------------------------

def test_the_sim_raises_gated_requests_deterministically_and_the_schedule_pauses_become_overruns(cfg):
    def run(seed):
        sim = Sim(loader.load_dir(cfg.departments_dir, cfg), seed)
        seen = {}
        for _ in range(900):
            sim.step()
            seen.update({r["id"]: (r["kind"], r["dept"], r["cost"]) for r in sim.sched.gates.pending.values()})
        return list(seen.values()), [e["outcome"] for e in sim.sched.gates.log]
    a, b = run(3), run(3)
    assert a == b and len(a[0]) > 5 and {k for k, _, _ in a[0]} >= {"spend", "outbound", "irreversible", "rules"} and a != run(4)
    assert {k for k, _, _ in a[0]} & set(OVERRUN)              # the clock and usage pauses raised overrun requests too
    assert set(a[1]) == {"expired"}                               # nobody answered, the fund is 0: everything counted as denied


# ---- endpoints -------------------------------------------------------------------------------------------------------------------------------------------

def post(port, path, body, headers=None):
    h = {"Cookie": "ag=" + TOKEN, "Content-Type": "application/json"}
    h.update(headers or {})
    return call(port, "POST", path, body if isinstance(body, (bytes, str)) else json.dumps(body), h)


def gated(app, kind="spend"):  # noqa: F811
    sc = app.sim.sched
    j = sc.add("research", "t", 1000, 600)
    return j, sc.gate(j, kind, "s", 5)


def test_approve_and_deny_endpoints_gate_and_checks(live, app):  # noqa: F811
    j, r = gated(app)
    body = {"id": r["id"]}
    assert post(live, "/api/approve", body, {"Cookie": ""})[0] == 401
    assert post(live, "/api/deny", body, {"Cookie": "ag=wrong"})[0] == 401
    assert post(live, "/api/approve", body, {"Content-Type": "text/plain"})[0] == 403
    assert post(live, "/api/approve", body, {"Origin": "http://evil.example.com"})[0] == 403
    assert j["hold"] == r["id"] and r["id"] in app.sim.sched.gates.pending           # nothing changed so far
    for bad in ({}, {"id": 5}, {"id": None}, {"id": r["id"], "x": 1}, {"id": [r["id"]]}, [], b"not json", b""):
        assert post(live, "/api/approve", bad)[0] == 400, bad
    s, _, b = post(live, "/api/approve", body, {"Origin": "http://127.0.0.1:%d" % live})
    assert s == 200 and j["hold"] is None and r["id"] not in app.sim.sched.gates.pending and j in app.sim.sched.queue["research"]
    assert "gates" in json.loads(b)
    assert post(live, "/api/approve", body)[0] == 409 and post(live, "/api/deny", body)[0] == 409      # double decision, either way
    assert post(live, "/api/approve", {"id": "req-999"})[0] == 404 and post(live, "/api/deny", {"id": "nope"})[0] == 404
    j2, r2 = gated(app, "irreversible")
    assert post(live, "/api/deny", {"id": r2["id"]})[0] == 200 and j2["dropped"] and j2 not in app.sim.sched.queue["research"]
    assert post(live, "/api/approve", {"id": r2["id"]})[0] == 409 and j2["dropped"]


def test_decisions_and_tasks_are_refused_without_the_access_key(project, tmp_path):
    open_app = build(project, str(tmp_path / "data"), seed=1, token=None)
    j, r = gated(open_app)
    for path, body in (("/api/approve", {"id": r["id"]}), ("/api/deny", {"id": r["id"]}), ("/api/task", {"dept": "research", "title": "t", "tokens": 5000})):
        assert open_app.route("POST", path, json.dumps(body).encode())[0] == 403
    assert j["hold"] == r["id"] and r["id"] in open_app.sim.sched.gates.pending and not any(x["user"] for x in open_app.sim.sched.queue["research"])
    assert json.loads(open_app.route("GET", "/api/org")[2])["can_act"] is False


def test_org_carries_the_approval_queue(app):  # noqa: F811
    j, r = gated(app)
    d = json.loads(app.route("GET", "/api/org")[2])
    g = d["schedule"]["gates"]
    assert d["can_act"] is True and {"pending", "blocked", "fund", "cap", "log"} == set(g)
    p = next(x for x in g["pending"] if x["id"] == r["id"])
    assert set(p) == {"id", "kind", "dept", "job", "summary", "cost", "created", "deadline", "left_s"} and p["left_s"] > 0
    assert d["ledger"]["working_capital"] == 80 and d["ledger"]["reserve"] == 20 and d["ledger"]["capital"] == 100


def test_task_endpoint_gate_and_validation(live, app):  # noqa: F811
    sc, q = app.sim.sched, app.sim.sched.queue["research"]
    ok = {"dept": "research", "title": "  Summarise the notes  ", "tokens": 5000}
    n = len(q)
    assert post(live, "/api/task", ok, {"Cookie": ""})[0] == 401
    assert post(live, "/api/task", ok, {"Content-Type": "text/plain"})[0] == 403
    assert post(live, "/api/task", ok, {"Origin": "http://evil.example.com"})[0] == 403
    assert len(q) == n
    share = sc.share["research"]
    bad = [{**ok, "dept": "nope"}, {**ok, "dept": ["research"]}, {**ok, "title": ""}, {**ok, "title": "   "}, {**ok, "title": "x" * 81}, {**ok, "title": 5}, {**ok, "title": "a\nb"},
           {**ok, "tokens": 0}, {**ok, "tokens": 999}, {**ok, "tokens": True}, {**ok, "tokens": 5000.5}, {**ok, "tokens": "5000"}, {**ok, "tokens": share + 1}, {**ok, "x": 1},
           {"dept": "research", "title": "t"}, [], b"not json", b""]
    for b in bad:
        assert post(live, "/api/task", b)[0] == 400, b
    assert len(q) == n
    s, _, b = post(live, "/api/task", ok, {"Origin": "http://127.0.0.1:%d" % live})
    assert s == 200 and len(q) == n + 1 and q[-1]["title"] == "Summarise the notes" and q[-1]["user"] and q[-1]["est"] == 5000
    assert post(live, "/api/task", {**ok, "tokens": int(share)})[0] == 200                # exactly the whole share is allowed
    while len(q) < 30:
        post(live, "/api/task", ok)
    assert post(live, "/api/task", ok)[0] == 400 and len(q) == 30                    # a full queue is refused


def test_a_user_task_runs_ahead_of_planned_ones():
    s = mk()
    p = s.add("ops", "planned", 100, 600)
    u = s.add_user({"dept": "ops", "title": "mine", "tokens": 1000})
    s.step(6 * H)
    assert u["user"] and s.running[0] is u and p in s.queue["ops"]


# ---- persistence and config ------------------------------------------------------------------------------------------------------------------------------

def test_department_toggles_survive_a_restart(project, tmp_path):
    data = str(tmp_path / "data")
    a = build(project, data, seed=1, token=TOKEN, warmup=1)
    a.sim.sched.set_enabled({"dept": "research", "enabled": False})
    a.sim.sched.set_enabled({"dept": "marketing", "enabled": False})
    a.sim.sched.set_enabled({"dept": "marketing", "enabled": True})
    b = build(project, data, seed=1, token=TOKEN, warmup=1)
    assert b.sim.sched.enabled["research"] is False and b.sim.sched.enabled["marketing"] is True and b.sim.sched.enabled["operations"] is True
    assert [d["enabled"] for d in b.sim.sched.snapshot()["departments"] if d["dept"] == "research"] == [False]
    (tmp_path / "data" / "schedule.json").write_text('{"research": "no", "ghost": false}')          # damaged or foreign content is ignored
    assert build(project, data, seed=1, token=TOKEN, warmup=1).sim.sched.enabled["research"] is True
    (tmp_path / "data" / "schedule.json").write_text("not json")
    assert build(project, data, seed=1, token=TOKEN, warmup=1).sim.sched.enabled["research"] is True


def test_a_rejected_toggle_is_not_saved(tmp_path):
    p = tmp_path / "s.json"
    s = mk(path=str(p))
    with pytest.raises(ScheduleError):
        s.set_enabled({"dept": "nope", "enabled": False})
    assert not p.exists()
    s.set_enabled({"dept": "ops", "enabled": False})
    assert json.loads(p.read_text()) == {"ops": False}


def test_gates_config_validation():
    good = {"overtime_fund_usd": 5, "per_job_cap_usd": 2.5, "max_attempts": 3, "deadline_minutes": 30}
    assert config.load_gates(good, "t") == {"fund": 5.0, "cap": 2.5, "attempts": 3, "deadline_s": 1800}
    for bad in ({**good, "x": 1}, {**good, "overtime_fund_usd": -1}, {**good, "per_job_cap_usd": True}, {**good, "max_attempts": 0}, {**good, "max_attempts": 2.5},
                {**good, "deadline_minutes": 0}, {**good, "overtime_fund_usd": "5"}, []):
        with pytest.raises(ConfigError):
            config.load_gates(bad, "t")


# ---- audit fixes -----------------------------------------------------------------------------------------------------------------------------------------

def gcfg(fund=5, cap=5):
    return config.load_gates({"overtime_fund_usd": fund, "per_job_cap_usd": cap, "max_attempts": 3, "deadline_minutes": 60}, "t")


def test_fund_and_pending_requests_survive_a_restart(tmp_path):
    p = str(tmp_path / "gates.json")
    g = Gates(gcfg(), p)
    r1 = g.raise_("overrun_time", "ops", "task-001", "a", 1.5, 0)
    r2 = g.raise_("spend", "ops", "task-002", "b", 9, 0)
    g.expire(3600)                                                # r1 auto-continues (fund 5 -> 3.5), r2 is denied
    r3 = g.raise_("outbound", "ops", "task-003", "c", 0, 3600)
    h = Gates(gcfg(), p)
    assert h.fund == 3.5 and h.auto == {"task-001": 1.5} and list(h.pending) == [r3["id"]] and [e["id"] for e in h.log] == [r1["id"], r2["id"]]
    h.decide(r3["id"], True, 3700)
    assert Gates(gcfg(), p).pending == {}
    assert Gates(gcfg(fund=9), p).fund == 9                      # the configured fund was changed: the new value wins


def test_request_ids_are_never_reused(tmp_path):
    p = str(tmp_path / "gates.json")
    g = Gates(gcfg(), p)
    ids = [g.raise_("rules", "ops", "t", "x", 0, 0)["id"] for _ in range(50)]
    g.expire(10 ** 6)
    ids += [Gates(gcfg(), p).raise_("rules", "ops", "t", "x", 0, 0)["id"] for _ in range(50)]
    assert len(set(ids)) == 100 and all(i.startswith("req-") and i != "req-001" for i in ids)


@pytest.mark.parametrize("text", ["not json", "[]", '{"fund": -1}', '{"fund": 1, "base": 5, "log": [], "auto": {}, "pending": {"a": {"id": "a"}}}', ""])
def test_a_damaged_gate_state_file_falls_back_to_config(tmp_path, caplog, text):
    p = tmp_path / "gates.json"
    p.write_text(text)
    g = Gates(gcfg(), str(p))
    assert g.fund == 5 and not g.pending and not g.log and "unreadable" in caplog.text
    g.raise_("rules", "ops", "t", "x", 0, 0)                      # and it can save over the damaged file
    assert len(Gates(gcfg(), str(p)).pending) == 1


def test_one_gates_instance_survives_a_sim_reset_and_a_restart(cfg, tmp_path):
    o = loader.load_dir(cfg.departments_dir, cfg)
    sim = Sim(o, 1, data_dir=str(tmp_path))
    g = sim.gates
    r = g.raise_("rules", "operations", "task-001", "x", 0, 0)
    g.fund = 2.5
    sim._reset()
    assert sim.gates is g and sim.sched.gates is g and g.fund == 2.5 and list(g.pending) == [r["id"]]
    g.raise_("rules", "operations", "task-002", "y", 0, 0)       # saved
    assert list(Sim(o, 1, data_dir=str(tmp_path)).gates.pending) == list(g.pending)


def test_a_stale_overrun_approval_is_cleared_at_rollover():
    s, j, r = paused_overrun()
    s.enabled["ops"] = False                                      # it waits in the queue after the approval
    s.decide(r["id"], True)
    assert j["over"] == "overrun_time"
    s.step(11 * H + 300)
    assert j["over"] == "overrun_time"                            # same usage window and day: still valid
    s.enabled["ops"] = True
    s.step(20 * H)                                                # a new usage window
    assert j["over"] is None and not j["hold"]
    s2, j2, r2 = paused_overrun()
    s2.enabled["ops"] = False
    s2.decide(r2["id"], True)
    s2.step(24 * H + 300)                                         # the next day (and usage window)
    assert j2["over"] is None


def test_the_per_job_cap_is_cumulative():
    g = Gates(gcfg(fund=10, cap=1.0))
    out = []
    for cost, job in ((0.6, "a"), (0.6, "a"), (0.6, "b")):
        g.raise_("overrun_usage", "ops", job, "x", cost, 0)
        out += [ok for _, ok in g.expire(10 ** 6)]
    assert out == [True, False, True] and g.fund == 8.8 and g.auto == {"a": 0.6, "b": 0.6}


@pytest.mark.parametrize("kind", ["spend", "outbound", "irreversible"])
def test_one_approval_is_one_attempt_for_spend_outbound_and_irreversible(kind):
    s = mk(check=lambda j: False, deadline_min=6000)
    j = s.add("ops", "x", 100, 600)
    s.gate(j, kind, "do it", 1)
    s.decide(j["hold"], True)
    run_until(s, 6 * H, 8 * H)
    assert j["tries"] == 1 and j["hold"] and not s.running       # the retry waits for a new approval
    first = j["hold"]
    s.decide(first, True)
    run_until(s, 8 * H, 9 * H)
    assert j["tries"] == 2 and j["hold"] and j["hold"] != first
    s.decide(j["hold"], False)                                    # denied: no more attempts
    assert j["dropped"] and j not in s.queue["ops"]


def test_a_retry_of_a_rules_job_needs_no_new_approval():
    s = mk(check=lambda j: False, deadline_min=6000)
    j = s.add("ops", "x", 100, 600)
    s.gate(j, "rules", "x", 0)
    s.decide(j["hold"], True)
    run_until(s, 6 * H, 9 * H)
    assert j["tries"] == 3 and j["blocked"]


def test_overrun_cost_is_estimated_from_the_worst_case():
    s2 = mk(budget=10 ** 6)
    j2 = s2.add("ops", "long", 100_000, 8 * H)
    s2.step(6 * H)
    s2.step(11 * H)
    r2 = s2.gates.pending[j2["hold"]]
    assert r2["cost"] == round((100_000 * WORST_CASE - j2["spent"]) / 1000 * USD_PER_1K_TOKENS, 2) > round((100_000 - j2["spent"]) / 1000 * USD_PER_1K_TOKENS, 2)
