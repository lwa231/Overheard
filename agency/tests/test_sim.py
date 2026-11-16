from agency import loader
from agency.sim import KINDS, STATES, Sim


def run(org, seed, n=300):
    s = Sim(org, seed, max_events=10000)
    for _ in range(n):
        s.step()
    return s


def test_deterministic(cfg):
    o = loader.load_dir(cfg.departments_dir, cfg)
    a, b, c = run(o, 7), run(o, 7), run(o, 8)
    assert list(a.events) == list(b.events) and a.stats() == b.stats() and a.history() == b.history()
    assert list(a.events) != list(c.events)


def test_flow_and_invariants(cfg):
    o = loader.load_dir(cfg.departments_dir, cfg)
    s = Sim(o, 3, max_events=10000)
    for _ in range(400):
        s.step()
        assert all(n.state in STATES for n in s.nodes.values()) and len(s.open) <= s.max_jobs
    kinds = {e["kind"] for e in s.events}
    assert {"job", "assign", "report", "ask", "answer", "blocked", "unblock", "deliver"} <= kinds <= set(KINDS)
    assert s.jobs_done > 5
    seen = set()
    for e in s.events:
        seen.add(e["n"])
        if e["kind"] == "assign":
            assert o.agents[e["dst"]].reports_to == e["src"]            # work only goes down one level at a time
        if e["kind"] == "report":
            assert o.agents[e["src"]].reports_to == e["dst"]            # reports only go up one level
    assert len(seen) == len(s.events)


def test_bounded_feed_and_history(cfg):
    o = loader.load_dir(cfg.departments_dir, cfg)
    s = Sim(o, 1, max_events=50)
    for _ in range(500):
        s.step()
    assert len(s.events) == 50 and s.events[-1]["n"] == s.n > 50
    assert all(len(v) == 60 for v in s.history().values())
    assert [e["n"] for e in s.feed(since=s.n - 3)] == [s.n - 2, s.n - 1, s.n]


def test_stats_consistent(cfg):
    o = loader.load_dir(cfg.departments_dir, cfg)
    s = run(o, 2, 120)
    st = s.stats()
    assert st["running"] + st["idle"] == st["agents"] == 20 and st["reports_per_min"] >= 0


def test_rebind_keeps_run_when_tree_same(cfg):
    o = loader.load_dir(cfg.departments_dir, cfg)
    s = run(o, 2, 50)
    nodes, open_ = s.nodes, set(s.open)
    s.rebind(loader.load_dir(cfg.departments_dir, cfg))
    assert s.nodes is nodes and s.open == open_



def test_events_are_backed_by_real_handoffs(cfg):
    from agency.handoff import KINDS as HKINDS
    from agency.handoff import parse_name
    o = loader.load_dir(cfg.departments_dir, cfg)
    s = run(o, 3, 500)
    want = {"assign": "assignment", "report": "report", "ask": "question", "answer": "answer", "blocked": "escalation", "unblock": "decision", "data": "data"}
    by = {}
    for e in s.events:
        if e["kind"] in want:
            assert e["hkind"] == want[e["kind"]] and parse_name("HANDOFF__%s.md" % e["tag"])["job"] == e["job"]
            by.setdefault(e["hkind"], []).append(e)
        elif e["kind"] != "reload":
            assert e["hkind"] is None and e["tag"] is None
    assert set(by) == set(HKINDS) - {"returns"}                            # the other six kinds flow; returns are published by the Business view
    for e in by["assignment"]:
        assert e["tag"].startswith(o.agents[e["dst"]].dept + "." + o.agents[e["dst"]].role + "__")
    for e in by["data"]:                                                   # Lead -> Lead across departments, then Lead -> its own worker
        a, b = o.agents[e["src"]], o.agents[e["dst"]]
        assert (a.dept != b.dept and o.leads[a.dept] == a.id and o.leads[b.dept] == b.id) or (a.dept == b.dept and o.leads[a.dept] == a.id)
    for e in s.events:
        if e["src"] in o.agents and e["dst"] in o.agents and e["hkind"]:   # no handoff ever skips the chain between departments
            a, b = o.agents[e["src"]], o.agents[e["dst"]]
            assert a.dept == b.dept or "command" in (a.dept, b.dept) or o.leads[a.dept] == a.id
    assert s.hs.reads > 100 and all(r["ok"] for r in s.hs.audit_tail)


def test_handoff_store_is_bounded_and_unseen_files_are_not_opened(cfg):
    o = loader.load_dir(cfg.departments_dir, cfg)
    s = run(o, 4, 900)
    assert len(s.hs.active()) < 60 and len(s.hs.archived()) <= 300 and len(s.hs.audit_tail) <= 300
    assert len(s.hs._arch) <= 300
    assert s.hs.archived("superseded") or s.hs.archived("done")
    t = s._tmp
    s.rebind(loader.load_dir(cfg.departments_dir, cfg))                    # same tree: files stay
    assert s.hs.active() or s.hs.archived()
    del s
    import gc
    gc.collect()
    assert not __import__("os").path.exists(t)                             # the temp dir goes with the simulator


def test_tree_working_set_is_the_schedulers(cfg):
    o = loader.load_dir(cfg.departments_dir, cfg)
    s = Sim(o, 4, max_events=10000)
    seen = 0
    for _ in range(3000):
        s.step()
        shown = {a for a in o.order if s.shown(a) == "working"}
        assert shown == {a for a, p in s.sched.loaded.items() if p == "working"} == {j["agent"] for j in s.sched.running}
        assert len(shown) <= s.sched.cfg["max_working"] and all(s.state_of(a)["state"] == "working" for a in shown)
        seen += bool(shown)
    assert seen > 100
