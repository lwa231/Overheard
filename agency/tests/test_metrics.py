import json

import pytest

from agency import loader, metrics
from agency.__main__ import build
from agency.metrics import CgroupMetrics, MetricsProvider, SimulatedMetrics
from agency.sim import Sim


def make(cfg, seed=1, ticks=120):
    o = loader.load_dir(cfg.departments_dir, cfg)
    s = Sim(o, seed, max_events=5000)
    m = SimulatedMetrics(s)
    for _ in range(ticks):
        s.step()
        m.sample()
    return o, s, m


def test_provider_shapes(cfg):
    o, s, m = make(cfg)
    assert isinstance(m, MetricsProvider)
    for aid in o.order:
        a, c = m.agent(aid), m.compact(aid)
        assert set(c) == set(metrics.COMPACT)
        assert set(a["hardware"]) == set(metrics.HARDWARE) and set(a["model"]) == set(metrics.MODEL) and set(a["work"]) == set(metrics.WORK)
        assert set(a["series"]) == set(metrics.SERIES) and all(1 <= len(v) <= metrics.HIST for v in a["series"].values())
        assert a["uptime_s"] == s.tick * s.tick_s
        local = o.agents[aid].runtime == "local"
        assert a["model"]["zero_cost"] is local and (a["model"]["cost_usd"] == 0) is local
        assert (a["hardware"]["vram_mb"] > 0) is local and (c["gpu_pct"] == 0 or local)       # only local models touch the GPU
        assert 0 <= c["ctx_pct"] <= 100 and c["cpu_pct"] >= 0 and a["work"]["errors"] >= a["work"]["retries"]
    f = m.fleet()
    assert set(f["now"]) == set(metrics.FLEET) and set(f["series"]) == set(metrics.FLEET_SERIES)
    now = f["now"]
    assert now["vram_used_mb"] <= now["vram_total_mb"] and now["gpu_pct"] <= 100 and 0 <= now["claude_spend_usd"] < now["claude_cap_usd"]
    assert abs(now["claude_spend_usd"] - sum(m.compact(a)["cost_usd"] for a in o.order)) < 0.05 and now["queue_depth"] == sum(len(n.inbox) for n in s.nodes.values())


def test_work_counters_follow_the_sim(cfg):
    o, s, m = make(cfg, seed=3, ticks=300)
    assert sum(n.done for n in s.nodes.values()) > 10
    w = m.agent("scout")["work"]
    assert w["jobs_done"] > 0 and w["avg_job_s"] > 0 and 0 <= w["audit_pass_rate"] <= 100 and w["last_report_s"] is not None
    assert m.agent("scout")["work"]["state_age_s"] >= 0
    now = m.fleet()["now"]
    assert now["errors_1h"] == sum(n.errors for n in s.nodes.values()) and now["retries_1h"] == sum(n.retries for n in s.nodes.values())   # run is shorter than an hour


def test_deterministic_and_events_independent_of_metrics(cfg):
    _, s1, m1 = make(cfg, 5)
    _, s2, m2 = make(cfg, 5)
    _, s3, _ = make(cfg, 6)
    assert m1.agent("builder") == m2.agent("builder") and m1.fleet() == m2.fleet() and m1.fleet() != make(cfg, 6)[2].fleet()
    o = loader.load_dir(cfg.departments_dir, cfg)
    bare = Sim(o, 5, max_events=5000)
    for _ in range(120):
        bare.step()
    assert list(bare.events) == list(s1.events) and s3.seed == 6                 # sampling metrics never changes the simulated events


def test_rollup_sums_subtree(cfg):
    o, s, m = make(cfg)
    comp = {a: m.compact(a) for a in o.order}
    states = {a: s.shown(a) for a in o.order}
    r = metrics.rollup(o, comp, states, "research-lead")
    ids = ["research-lead", "analyst", "archivist", "scout", "verifier"]
    assert set(r) == set(metrics.ROLLUP) and r["agents"] == 5
    assert abs(r["cpu_pct"] - sum(comp[i]["cpu_pct"] for i in ids)) < 0.5 and r["working"] == sum(states[i] == "working" for i in ids)
    assert metrics.rollup(o, comp, states, "boss")["agents"] == 20


def test_cgroup_stub_documents_its_sources():
    c = CgroupMetrics()
    assert isinstance(c, MetricsProvider)
    for call in (c.sample, lambda: c.agent("scout"), lambda: c.compact("scout"), c.fleet):
        with pytest.raises(NotImplementedError) as e:
            call()
        msg = str(e.value)
        assert all(f in msg for f in ("cpu.stat", "memory.current", "io.stat", "pids.current", "nvidia-smi"))
    assert "/agent-<id>.scope/" in str(pytest.raises(NotImplementedError, c.sample).value)


def test_base_provider_is_abstract():
    for name in ("sample", "agent", "compact", "fleet"):
        with pytest.raises(NotImplementedError):
            getattr(MetricsProvider(), name)(*(() if name in ("sample", "fleet") else ("x",)))


def test_api_exposes_metrics(project, tmp_path):
    app = build(project, str(tmp_path / "d"), seed=1)
    org = json.loads(app.route("GET", "/api/org")[2])
    assert org["metrics_source"] == "simulated" and set(org["fleet"]["now"]) == set(metrics.FLEET) and set(org["fleet"]["series"]) == set(metrics.FLEET_SERIES)
    assert org["fleet"]["now"]["claude_cap_usd"] == 25.0
    by = {a["id"]: a for a in org["agents"]}
    assert all(set(a["metrics"]) == set(metrics.COMPACT) for a in org["agents"])
    assert by["scout"]["rollup"] is None and set(by["research-lead"]["rollup"]) == set(metrics.ROLLUP) and by["boss"]["rollup"]["agents"] == 20
    ag = json.loads(app.route("GET", "/api/agent/analyst")[2])
    assert ag["metrics"]["source"] == "simulated" and set(ag["metrics"]["series"]) == set(metrics.SERIES) and ag["metrics"]["model"]["zero_cost"] is True


def test_feed_agent_filter(project, tmp_path):
    app = build(project, str(tmp_path / "d"), seed=1)
    allf = json.loads(app.route("GET", "/api/feed?limit=200")[2])["events"]
    mine = json.loads(app.route("GET", "/api/feed?agent=research-lead&limit=200")[2])
    assert mine["agent"] == "research-lead" and mine["events"]
    assert all("research-lead" in (e["src"], e["dst"]) for e in mine["events"])
    assert mine["events"] == [e for e in allf if "research-lead" in (e["src"], e["dst"])] and len(mine["events"]) < len(allf)
    assert json.loads(app.route("GET", "/api/feed?agent=research-lead&since=%d" % mine["latest"])[2])["events"] == []
    assert json.loads(app.route("GET", "/api/feed?agent=scout&limit=2")[2])["events"] == [e for e in allf if "scout" in (e["src"], e["dst"])][-2:]
    assert app.route("GET", "/api/feed?agent=nobody")[0] == 404
    assert all(e["src"] == "boss" or e["dst"] == "boss" for e in json.loads(app.route("GET", "/api/feed?agent=boss")[2])["events"])


def test_config_cap(tmp_path):
    from agency import config
    p = tmp_path / "config"
    p.mkdir()
    (p / "tiers.json").write_text('{"compaction_limit_tokens":{"a":9000,"b":5000},"context_window_tokens":{"claude-code":100000,"local":50000}}')
    (p / "agency.json").write_text('{"ranks":[{"key":"a"},{"key":"b"}],"claude_daily_cap_usd":40}')
    assert config.load(str(p / "agency.json")).claude_daily_cap_usd == 40
    (p / "agency.json").write_text('{"ranks":[{"key":"a"},{"key":"b"}],"claude_daily_cap_usd":-1}')
    with pytest.raises(config.ConfigError):
        config.load(str(p / "agency.json"))
