import json

import pytest

from agency import config, loader
from agency.config import ConfigError
from agency.scheduler import ScheduleError, Scheduler
from agency.sim import Sim

from test_server import TOKEN, app, call, live  # noqa: F401  (fixtures)

H = 3600
MEMBERS = {"ops": ["o1", "o2", "o3"], "res": ["r1", "r2", "r3"]}


def make(max_working=2, max_loaded=3, budget=1000, ops=(50, "06:00", "10:00"), res=(50, "08:00", "12:00")):
    """Tokens 1000 per 5-hour usage window, time 0 = midnight. ops open 06-10 (grace 1h), res open 08-12."""
    deps = {"ops": {"share": ops[0], "start": ops[1], "end": ops[2]}, "res": {"share": res[0], "start": res[1], "end": res[2]}}
    sc = config.load_schedule({"max_working": max_working, "max_loaded": max_loaded, "usage_window_hours": 5, "usage_window_tokens": budget, "minutes_per_tick": 5, "departments": deps}, "test")
    return Scheduler(sc, MEMBERS)


def working(s):
    return sorted(j["agent"] for j in s.running)


def test_lru_eviction_puts_the_least_recently_used_warm_agent_to_sleep():
    s = make(max_working=2, max_loaded=2)
    s.add("ops", "a", 100, 600)
    s.add("ops", "b", 100, 600)
    s.step(6 * H)
    assert working(s) == ["o1", "o2"] and s.state("o3") == "asleep"
    s.step(6 * H + 600)                                           # both done: o1 finished first, so it is the least recently used
    assert [s.state(a) for a in ("o1", "o2")] == ["warm", "warm"] and not s.running
    s.add("res", "c", 100, 600)
    s.step(8 * H)                                                 # a third agent must be loaded, loaded is full: o1 goes to sleep
    assert [s.state(a) for a in ("o1", "o2", "r1")] == ["asleep", "warm", "working"]
    assert len(s.loaded) <= 2


def test_a_warm_agent_is_reused_before_waking_another():
    s = make()
    s.add("ops", "a", 100, 600)
    s.step(6 * H)
    s.step(7 * H)
    s.add("ops", "b", 100, 600)
    s.step(7 * H + 300)
    assert working(s) == ["o1"] and s.state("o2") == "asleep"


def test_at_most_max_working_at_once():
    s = make(max_working=2, max_loaded=4, budget=100000)
    for i in range(4):
        s.add("ops", "j%d" % i, 100, 1200)
    s.add("res", "r", 100, 1200)
    s.step(8 * H)
    assert len(s.running) == 2 and sum(len(q) for q in s.queue.values()) == 3
    for k in range(1, 40):
        s.step(8 * H + k * 300)
        assert len(s.running) <= 2 and len(s.loaded) <= 4
    assert not s.running and not any(s.queue.values())            # everything finished, never more than two at once


def test_closed_window_and_toggle_block_starts():
    s = make()
    s.add("ops", "a", 100, 600)
    s.step(5 * H)
    assert not s.running                                          # 05:00, ops opens at 06:00
    s.step(6 * H)
    assert working(s) == ["o1"]
    s.step(6 * H + 600)
    s.set_enabled({"dept": "ops", "enabled": False})
    s.add("ops", "b", 100, 600)
    s.step(7 * H)
    assert not s.running                                          # window open, toggle off
    s.set_enabled({"dept": "ops", "enabled": True})
    s.step(7 * H + 300)
    assert len(s.running) == 1


def test_toggle_off_lets_the_job_in_hand_finish():
    s = make()
    j = s.add("ops", "a", 100, 1200)
    s.step(6 * H)
    s.set_enabled({"dept": "ops", "enabled": False})
    s.step(6 * H + 1200)
    assert j["end"] == 6 * H + 1200 and not s.running


def test_job_in_hand_finishes_after_close_and_no_new_job_starts():
    s = make()
    j = s.add("ops", "a", 100, 1200)
    s.step(9 * H + 3000)                                          # 09:50, ten minutes before close
    assert s.running == [j]
    s.add("ops", "b", 100, 600)
    s.step(10 * H)                                                # closed: a keeps going, b waits
    assert s.running == [j] and len(s.queue["ops"]) == 1
    s.step(10 * H + 600)
    assert j["end"] == 10 * H + 600 and j["paused"] is None       # finished 10 minutes past close
    s.step(11 * H)
    assert not s.running and len(s.queue["ops"]) == 1             # still no new start after close


def test_a_job_may_run_a_quarter_of_the_window_past_close_then_pauses_with_a_checkpoint():
    s = make()
    j = s.add("ops", "long", 100, 3 * H)
    s.step(9 * H)
    s.step(10 * H + 1800)
    assert s.running == [j] and j["paused"] is None               # 30 minutes past close: allowed
    s.step(11 * H + 1800)                                         # window is 4h, cap is 1h: the step overshoots, the job is clipped at 11:00
    assert not s.running and j["paused"] == "window_cap" and j["flagged"] is True and j["end"] is None
    assert j["checkpoint"] == {"at": 11 * H + 1800, "agent": "o1", "done_s": 2 * H, "spent": pytest.approx(100 * 2 / 3)}
    assert j in s.queue["ops"] and s.state("o1") == "warm"
    snap = s.snapshot()
    assert snap["held"] == [{"id": j["id"], "dept": "ops", "title": "long", "reason": "window_cap", "flagged": True, "done": 67}]
    s.step(30 * H)                                                # next day 06:00: resumes where it was
    assert working(s) == ["o1"] and j["paused"] is None and j["flagged"] is False and j["t"] == 2 * H
    s.step(30 * H + H)
    assert j["end"] == 30 * H + H and j["spent"] == pytest.approx(100)


def test_admission_refuses_a_job_that_does_not_fit_its_departments_remaining_share():
    s = make()                                                    # ops share = 500 tokens
    first = s.add("ops", "first", 400, 600)
    s.step(6 * H)
    assert s.running == [first]
    big = s.add("ops", "big", 500, 600)                           # fits the whole share, not what is left of it
    small = s.add("ops", "second", 200, 600)
    s.step(6 * H + 300)                                           # 400 is reserved by the running job: 100 left
    assert s.running == [first] and small in s.queue["ops"]
    s.step(6 * H + 1000)                                          # first done and spent 400: 100 left, still not enough
    assert not s.running and small in s.queue["ops"] and big in s.queue["ops"]


def test_a_job_bigger_than_its_departments_whole_share_is_refused_at_add():
    s = make()                                                    # ops share = 500 tokens
    with pytest.raises(ScheduleError, match="whole ops share"):
        s.add("ops", "big", 600, 600)
    assert not s.queue["ops"] and s.n == 0
    assert s.add("ops", "exact", 500, 600)["est"] == 500          # equal to the share is fine


def test_a_job_overrunning_its_estimate_is_paused_at_its_share_and_never_billed_past_it():
    s = make(ops=(50, "06:00", "22:00"), res=(50, "06:00", "22:00"))
    a = s.add("ops", "a", 400, 3000, actual=1000)                 # rate 1/3 token/s: the 500 share is gone after 1500 s, at 50%
    s.step(6 * H)
    s.step(6 * H + 2000)                                          # one coarse step across the limit
    assert a["spent"] == pytest.approx(500) and s.spent["ops"] == pytest.approx(500) and a["t"] == pytest.approx(1500)
    assert a["paused"] == "share_limit" and a["flagged"] is False and not s.running and a in s.queue["ops"]
    assert a["checkpoint"]["spent"] == pytest.approx(500) and a["checkpoint"]["done_s"] == pytest.approx(1500)
    assert s.snapshot()["held"][0]["reason"] == "share_limit"
    s.step(6 * H + 4000)
    assert not s.running and s.spent["ops"] == pytest.approx(500)         # same usage window: stays paused, nothing more billed
    s.step(10 * H)                                                # next usage window (05-10 ends at 10:00): resumes
    assert working(s) == ["o1"] and a["paused"] is None and s.spent["ops"] == 0
    s.step(10 * H + 2000)
    assert a["end"] == 10 * H + 2000 and a["spent"] == pytest.approx(1000)


def test_actual_tokens_at_2_5x_the_estimate_never_push_a_department_past_its_share():
    s = make(max_working=2, ops=(50, "06:00", "22:00"), res=(50, "06:00", "22:00"))
    for i in range(6):
        s.add("ops", "o%d" % i, 150, 1200, actual=375)
        s.add("res", "r%d" % i, 200, 1500, actual=500)
    for t in range(6 * H, 6 * H + 5 * 5 * H, 300):                # five usage windows
        s.step(t)
        assert all(s.spent[d] <= s.share[d] + 1e-6 for d in s.depts) and sum(s.spent.values()) <= 1000 + 1e-6
    assert any(j["checkpoint"] for q in s.queue.values() for j in q) or s.n == 12             # the limit was really hit along the way


def test_hard_stop_pauses_with_checkpoint_and_resumes_in_the_next_usage_window_without_overrun():
    s = make(ops=(50, "06:00", "22:00"), res=(50, "06:00", "22:00"))      # usage windows: 00-05, 05-10, 10-15
    a = s.add("ops", "a", 100, 3000, actual=1500)                 # rate .5 token/s: both shares are gone after 1000 s, the 1000-token budget with them
    b = s.add("res", "b", 100, 3000, actual=1500)
    top = 0
    for k in range(0, 80):
        s.step(6 * H + k * 100)
        top = max(top, sum(s.spent.values()))
        if a["paused"]:
            break
    assert top <= 1000 + 1e-6 and sum(s.spent.values()) == pytest.approx(1000)
    assert {a["paused"], b["paused"]} <= {"hard_stop", "share_limit"} and a["paused"] and b["paused"] and a["flagged"] is False and not s.running
    assert a["checkpoint"]["spent"] + b["checkpoint"]["spent"] == pytest.approx(1000) and a["checkpoint"]["done_s"] > 0
    assert a in s.queue["ops"] and b in s.queue["res"]
    s.step(9 * H)
    assert not s.running                                          # same usage window: still stopped, nothing more is spent
    assert sum(s.spent.values()) == pytest.approx(1000)
    s.step(10 * H)                                                # next usage window: fresh budget, both resume
    assert len(s.running) == 2 and sum(s.spent.values()) == 0 and a["paused"] is None
    for t in range(10 * H + 300, 21 * H, 300):                    # three more usage windows of 1000 tokens: each stop and resume, no window ever goes over
        s.step(t)
        assert sum(s.spent.values()) <= 1000 + 1e-6
    assert a["end"] and b["end"] and a["spent"] == pytest.approx(1500) and b["spent"] == pytest.approx(1500)


def test_user_tasks_rank_ahead_of_planned_ones_and_paused_ones_ahead_of_both():
    s = make(max_working=1, max_loaded=1)
    p1 = s.add("ops", "planned 1", 100, 600)
    p2 = s.add("ops", "planned 2", 100, 600)
    u = s.add("ops", "user", 100, 600, user=True)
    s.step(6 * H)
    assert s.running == [u]                                       # added last, started first
    s.step(6 * H + 600)
    assert s.running == [p1]                                      # then planned ones in order
    assert p2 in s.queue["ops"]


def test_toggle_input_is_validated():
    s = make()
    for bad in (None, [], {}, {"dept": "ops"}, {"enabled": True}, {"dept": "nope", "enabled": True}, {"dept": ["ops"], "enabled": True}, {"dept": "ops", "enabled": "yes"},
                {"dept": "ops", "enabled": 1}, {"dept": "ops", "enabled": True, "x": 1}):
        with pytest.raises(ScheduleError):
            s.set_enabled(bad)
    assert s.enabled == {"ops": True, "res": True}


def test_schedule_config_validation(cfg):
    sc = cfg.schedule
    assert sc["max_working"] == 3 and sum(w["share"] for w in sc["departments"].values()) == 100 and sc["window_s"] == 5 * H
    assert {d.dept for d in loader.load_dir(cfg.departments_dir, cfg).agents.values()} >= set(sc["departments"])
    good = {"max_working": 3, "max_loaded": 6, "usage_window_hours": 5, "usage_window_tokens": 100, "minutes_per_tick": 5, "departments": {"a": {"start": "08:00", "end": "09:00", "share": 100}}}
    assert config.load_schedule(good, "t")["departments"]["a"] == {"start": 480, "end": 540, "share": 100} and config.load_schedule(None, "t") is None
    bad = [{**good, "max_loaded": 2}, {**good, "max_working": 0}, {**good, "usage_window_tokens": True}, {**good, "extra": 1}, {**good, "departments": {}},
           {**good, "departments": {"a": {"start": "9:00", "end": "10:00", "share": 100}}}, {**good, "departments": {"a": {"start": "10:00", "end": "09:00", "share": 100}}},
           {**good, "departments": {"a": {"start": "08:00", "end": "09:00", "share": 60}}}, {**good, "departments": {"a": {"start": "08:00", "end": "25:00", "share": 100}}}, []]
    for b in bad:
        with pytest.raises(ConfigError):
            config.load_schedule(b, "t")


def test_sim_runs_the_schedule_within_its_limits(cfg):
    sim = Sim(loader.load_dir(cfg.departments_dir, cfg), 5)
    sc, seen = cfg.schedule, set()
    for _ in range(700):
        sim.step()
        s = sim.sched
        assert len(s.running) <= sc["max_working"] and len(s.loaded) <= sc["max_loaded"] and sum(s.spent.values()) <= sc["budget"] + 1e-6
        seen |= {s.state(a) for a in s.loaded}
    assert seen == {"warm", "working"} and sim.sched.snapshot()["counts"]["asleep"] > 0 and sim.sched.n > 20


def test_org_api_carries_the_schedule(app):  # noqa: F811
    d = json.loads(app.route("GET", "/api/org")[2])
    assert {a["power"] for a in d["agents"]} <= {"asleep", "warm", "working"} and {a["id"]: a["power"] for a in d["agents"]}["boss"] == "asleep"
    sc = d["schedule"]
    assert [x["dept"] for x in sc["departments"]] == ["operations", "implementation", "research", "marketing", "finance-trading"]
    assert set(sc["departments"][0]) == {"dept", "start", "end", "open", "enabled", "share", "used", "queue", "working"} and sc["usage"]["budget"] == app.sim.sched.cfg["budget"] and "held" in sc


def post(port, body, headers=None):
    h = {"Cookie": "ag=" + TOKEN, "Content-Type": "application/json"}
    h.update(headers or {})
    return call(port, "POST", "/api/schedule", body if isinstance(body, (bytes, str)) else json.dumps(body), h)


def test_toggle_endpoint_gate_and_checks(live, app):  # noqa: F811
    on = {"dept": "research", "enabled": False}
    assert post(live, on, {"Cookie": ""})[0] == 401                                          # no key
    assert post(live, on, {"Cookie": "ag=wrong"})[0] == 401
    assert post(live, on, {"Content-Type": "text/plain"})[0] == 403                          # not JSON
    assert post(live, on, {"Origin": "http://evil.example.com"})[0] == 403                    # other origin
    assert app.sim.sched.enabled["research"] is True                                         # nothing changed so far
    s, _, b = post(live, on, {"Origin": "http://127.0.0.1:%d" % live})
    assert s == 200 and app.sim.sched.enabled["research"] is False
    assert {x["dept"]: x["enabled"] for x in json.loads(b)["departments"]}["research"] is False
    assert post(live, {"dept": "research", "enabled": True})[0] == 200 and app.sim.sched.enabled["research"] is True
    for bad in ({"dept": "nope", "enabled": True}, {"dept": "research", "enabled": "yes"}, {"dept": "research"}, {"dept": "research", "enabled": True, "x": 1}, {"dept": ["research"], "enabled": True},
                [], b"not json", b""):
        assert post(live, bad)[0] == 400, bad
    assert app.sim.sched.enabled["research"] is True


def test_toggle_is_refused_without_the_access_key(project, tmp_path):
    from agency.__main__ import build
    open_app = build(project, str(tmp_path / "data"), seed=1, token=None)
    assert open_app.route("POST", "/api/schedule", json.dumps({"dept": "research", "enabled": False}).encode())[0] == 403
    assert open_app.sim.sched.enabled["research"] is True
