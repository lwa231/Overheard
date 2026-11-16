import json
import os

import pytest

from agency import config, loader
from agency.__main__ import build
from agency.metrics import SimulatedMetrics
from agency.sim import Sim


def tiers_file(tmp_path, **over):
    d = {"compaction_limit_tokens": {"head": 500000, "general": 400000, "squad_lead": 300000, "agent": 200000}, "overrides": {}, "context_window_tokens": {"claude-code": 1000000, "local": 131072}}
    d.update(over)
    p = tmp_path / "config"
    p.mkdir(exist_ok=True)
    (p / "tiers.json").write_text(json.dumps(d))
    (p / "agency.json").write_text(json.dumps({"ranks": [{"key": k} for k in d["compaction_limit_tokens"]]}))
    return str(p / "agency.json")


def test_default_limits_by_rank(cfg):
    t = cfg.tiers
    assert [t.by_rank[k] for k, _ in cfg.ranks] == [500000, 400000, 300000, 200000]
    assert t.limit("x", "agent", "claude-code") == {"configured": 200000, "source": "tier", "window": 1000000, "effective": 200000, "capped": False}
    assert t.limit("x", "head", "claude-code")["effective"] == 500000


def test_limit_never_exceeds_the_model_window(cfg):
    lim = cfg.tiers.limit("x", "agent", "local")                  # local window 131072 < the 200k tier limit
    assert lim["effective"] == 131072 and lim["capped"] and lim["configured"] == 200000
    cfg.tiers.overrides["x"] = 5_000_000
    assert cfg.tiers.limit("x", "agent", "claude-code")["effective"] == 1000000


def test_config_validation(tmp_path):
    assert config.load(tiers_file(tmp_path)).tiers.by_rank["agent"] == 200000
    bad = {
        "increases down the ranks": dict(compaction_limit_tokens={"head": 200000, "general": 300000, "squad_lead": 300000, "agent": 200000}),
        "missing rank": dict(compaction_limit_tokens={"head": 500000, "general": 400000, "squad_lead": 300000}),
        "unknown rank": dict(compaction_limit_tokens={"head": 500000, "general": 400000, "squad_lead": 300000, "agent": 200000, "intern": 1000}),
        "not an integer": dict(compaction_limit_tokens={"head": "500k", "general": 400000, "squad_lead": 300000, "agent": 200000}),
        "tiny": dict(compaction_limit_tokens={"head": 500000, "general": 400000, "squad_lead": 300000, "agent": 5}),
        "window per runtime": dict(context_window_tokens={"claude-code": 1000000}),
    }
    for name, over in bad.items():
        (tmp_path / name.replace(" ", "_")).mkdir()
        # tiers.json must list exactly the ranks of agency.json
        path = tiers_file(tmp_path / name.replace(" ", "_"), **over)
        if name in ("unknown rank", "missing rank"):
            json.dump({"ranks": [{"key": k} for k in ("head", "general", "squad_lead", "agent")]}, open(path, "w"))
        with pytest.raises(config.ConfigError):
            config.load(path)


def test_ranks_renameable(tmp_path):
    p = tiers_file(tmp_path)
    d = json.load(open(p))
    d["ranks"] = [{"key": k, "label": "Renamed " + k} for k in ("head", "general", "squad_lead", "agent")]
    json.dump(d, open(p, "w"))
    c = config.load(p)
    assert c.rank_label["head"] == "Renamed head" and c.tiers.by_rank["head"] == 500000          # limits follow the rank key; the label is free text


def test_override_must_name_a_real_agent(cfg):
    cfg.tiers.overrides["ghost"] = 5000
    with pytest.raises(loader.OrgError, match="unknown agent 'ghost'"):
        loader.load_dir(cfg.departments_dir, cfg)


def test_api_exposes_limit_and_fill_is_measured_against_it(project, tmp_path):
    app = build(project, str(tmp_path / "d"), seed=1, token=None)
    ag = json.loads(app.route("GET", "/api/agent/research-lead")[2])
    assert ag["tier"] == {"rank": "squad_lead", "configured": 300000, "source": "tier", "window": 1000000, "effective": 300000, "capped": False}
    m = ag["metrics"]["model"]
    assert m["ctx_limit"] == 300000 and m["ctx_limit_configured"] == 300000 and m["limit_source"] == "tier" and not m["limit_capped"]
    assert abs(m["ctx_pct"] - 100 * m["ctx_tokens"] / m["ctx_limit"]) < 0.1
    sc = json.loads(app.route("GET", "/api/agent/scout")[2])
    assert sc["tier"]["configured"] == 200000 and sc["tier"]["effective"] == 131072 and sc["metrics"]["model"]["limit_capped"]      # local runtime: window caps the tier limit
    bd = json.loads(app.route("GET", "/api/agent/builder")[2])
    assert bd["metrics"]["model"]["ctx_limit"] == 200000 and json.loads(app.route("GET", "/api/agent/boss")[2])["metrics"]["model"]["ctx_limit"] == 500000


def test_compaction_event_and_context_drop(cfg):
    cfg.tiers.overrides["builder"] = 20000
    o = loader.load_dir(cfg.departments_dir, cfg)
    s = Sim(o, 2, max_events=10000)
    m = SimulatedMetrics(s)
    ctx, drops = [], []
    for _ in range(400):
        s.step()
        m.sample()
        ctx.append(m.agent("builder")["model"]["ctx_tokens"])
        assert m.compact("builder")["ctx_pct"] <= 100
    ev = [e for e in s.events if e["kind"] == "compact" and e["src"] == "builder"]
    assert ev and "context compacted" in ev[0]["text"] and "limit 20k" in ev[0]["text"] and ev[0]["tag"] is None
    assert s.nodes["builder"].compactions == len(ev) and m.agent("builder")["model"]["compactions"] == len(ev)
    drops = [(a, b) for a, b in zip(ctx, ctx[1:], strict=False) if b < a]
    assert len(drops) == len(ev) and all(a >= 20000 * 0.5 and b == 20000 * 0.2 for a, b in drops)       # context falls back to a fraction of the limit
    assert max(ctx) < 20000 * 1.4


def test_nobody_compacts_before_its_limit(cfg):
    o = loader.load_dir(cfg.departments_dir, cfg)
    s = Sim(o, 1, max_events=10000)
    m = SimulatedMetrics(s)
    for _ in range(300):
        s.step()
        m.sample()
    for e in (e for e in s.events if e["kind"] == "compact"):
        a = o.agents[e["src"]]
        assert ("limit %dk" % (cfg.tiers.limit(a.id, a.rank, a.runtime)["effective"] / 1000)) in e["text"]
    assert os.path.isdir(cfg.departments_dir)
