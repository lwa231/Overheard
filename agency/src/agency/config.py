"""Config: config/agency.json (organisation name, rank names top to bottom, folders, spend cap, title overrides, schedule, gates) and
config/tiers.json (compaction limit per rank, per-agent overrides, model window per runtime)."""
import json
import os
import re
from urllib.parse import urlparse

RUNTIMES = ("claude-code", "local")
MIN_LIMIT = 1000
LOOPBACK = ("127.0.0.1", "localhost", "::1")


class ConfigError(ValueError):
    pass


class Tiers:
    """Compaction limits in tokens: by rank, with per-agent overrides, never above the runtime's real model window."""

    def __init__(self, by_rank, overrides, windows):
        self.by_rank, self.overrides, self.windows = by_rank, overrides, windows

    def limit(self, agent_id, rank, runtime):
        """-> {configured, source ('override'|'tier'), window, effective, capped}; effective = min(configured, window)."""
        src = "override" if agent_id in self.overrides else "tier"
        conf = self.overrides[agent_id] if src == "override" else self.by_rank[rank]
        win = self.windows[runtime]
        return {"configured": conf, "source": src, "window": win, "effective": min(conf, win), "capped": conf > win}


def _int(v, what, path):
    if isinstance(v, bool) or not isinstance(v, int) or v < MIN_LIMIT:
        raise ConfigError("%s: %s must be an integer >= %d" % (path, what, MIN_LIMIT))
    return v


def load_tiers(path, rank_keys):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError) as e:
        raise ConfigError("%s: %s" % (path, e)) from None
    if not isinstance(d, dict) or set(d) - {"_note", "compaction_limit_tokens", "overrides", "context_window_tokens"}:
        raise ConfigError("%s: unknown or missing top-level keys" % path)
    lim = d.get("compaction_limit_tokens")
    if not isinstance(lim, dict) or set(lim) != set(rank_keys):
        raise ConfigError("%s: compaction_limit_tokens needs exactly one entry per rank (%s)" % (path, ", ".join(rank_keys)))
    by_rank = {k: _int(lim[k], "limit for rank %r" % k, path) for k in rank_keys}
    vals = [by_rank[k] for k in rank_keys]
    if any(b > a for a, b in zip(vals, vals[1:], strict=False)):
        raise ConfigError("%s: limits must not increase down the ranks (%s)" % (path, ", ".join("%s=%d" % (k, by_rank[k]) for k in rank_keys)))
    win = d.get("context_window_tokens")
    if not isinstance(win, dict) or set(win) != set(RUNTIMES):
        raise ConfigError("%s: context_window_tokens needs one entry per runtime (%s)" % (path, ", ".join(RUNTIMES)))
    windows = {k: _int(win[k], "window for runtime %r" % k, path) for k in RUNTIMES}
    ov = d.get("overrides", {})
    if not isinstance(ov, dict):
        raise ConfigError("%s: overrides must be an object {agent-id: tokens}" % path)
    return Tiers(by_rank, {k: _int(v, "override for %r" % k, path) for k, v in ov.items()}, windows)


def _pos(v, what, path):
    if isinstance(v, bool) or not isinstance(v, int) or v < 1:
        raise ConfigError("%s: schedule %s must be a positive integer" % (path, what))
    return v


def load_schedule(d, path):
    """The `schedule` section of agency.json -> {max_working, max_loaded, window_s, budget, tick_s, departments: {name: {start, end (minutes of day), share (percent)}}}.
    None if there is no section."""
    if d is None:
        return None
    keys = {"max_working", "max_loaded", "usage_window_hours", "usage_window_tokens", "minutes_per_tick", "departments"}
    if not isinstance(d, dict) or set(d) != keys or not isinstance(d["departments"], dict) or not d["departments"]:
        raise ConfigError("%s: schedule needs exactly the keys %s" % (path, ", ".join(sorted(keys))))
    deps = {}
    for name, w in d["departments"].items():
        if not isinstance(w, dict) or set(w) != {"start", "end", "share"}:
            raise ConfigError("%s: schedule department %r needs start, end and share" % (path, name))
        t = []
        for k in ("start", "end"):
            m = re.fullmatch(r"([01]\d|2[0-3]):([0-5]\d)", w[k]) if isinstance(w[k], str) else None
            if not m:
                raise ConfigError("%s: schedule department %r: %s must be like 08:00" % (path, name, k))
            t.append(int(m[1]) * 60 + int(m[2]))
        if t[0] >= t[1]:
            raise ConfigError("%s: schedule department %r: start must be before end (same day)" % (path, name))
        deps[name] = {"start": t[0], "end": t[1], "share": _pos(w["share"], "share", path)}
    if sum(w["share"] for w in deps.values()) != 100:
        raise ConfigError("%s: schedule shares must add up to 100" % path)
    out = {"max_working": _pos(d["max_working"], "max_working", path), "max_loaded": _pos(d["max_loaded"], "max_loaded", path),
           "window_s": _pos(d["usage_window_hours"], "usage_window_hours", path) * 3600, "budget": _pos(d["usage_window_tokens"], "usage_window_tokens", path),
           "tick_s": _pos(d["minutes_per_tick"], "minutes_per_tick", path) * 60, "departments": deps}
    if out["max_loaded"] < out["max_working"]:
        raise ConfigError("%s: schedule max_loaded must be at least max_working" % path)
    return out


def load_gates(d, path):
    """The `gates` section of agency.json -> {fund (overtime fund, USD), cap (per-job cap, USD), attempts, deadline_s}. Fund and cap default to 0: nothing auto-continues."""
    d = {} if d is None else d
    keys = {"overtime_fund_usd", "per_job_cap_usd", "max_attempts", "deadline_minutes"}
    if not isinstance(d, dict) or set(d) - keys:
        raise ConfigError("%s: gates may only have the keys %s" % (path, ", ".join(sorted(keys))))
    usd = {}
    for k in ("overtime_fund_usd", "per_job_cap_usd"):
        v = d.get(k, 0)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 100000:
            raise ConfigError("%s: gates %s must be a number of dollars from 0 to 100000" % (path, k))
        usd[k] = float(v)
    att, dl = d.get("max_attempts", 3), d.get("deadline_minutes", 720)
    for what, v, hi in (("max_attempts", att, 10), ("deadline_minutes", dl, 10080)):
        if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= hi:
            raise ConfigError("%s: gates %s must be an integer from 1 to %d" % (path, what, hi))
    return {"fund": usd["overtime_fund_usd"], "cap": usd["per_job_cap_usd"], "attempts": att, "deadline_s": dl * 60}


def load_test_mode(d, path):
    """The `test_mode` section of agency.json -> {real_agents, model, model_url, model_timeout_s, model_keep_alive, model_num_ctx, model_num_predict, price_hosts,
    paper_assets}. real_agents is [] (test mode off) unless set;
    the model URL must be on this machine (loopback); price_hosts is the only list of hosts the price fetcher may contact."""
    out = {"real_agents": [], "model": "llama3.2:3b", "model_url": "http://127.0.0.1:11434/api/generate", "model_timeout_s": 120, "model_keep_alive": "30m", "model_num_ctx": 4096,
           "model_num_predict": 512, "price_hosts": ["api.coinbase.com"], "paper_assets": ["BTC-USD"]}
    if d is not None:
        if not isinstance(d, dict) or set(d) - set(out):
            raise ConfigError("%s: test_mode may only have the keys %s" % (path, ", ".join(sorted(out))))
        out.update(d)

    def texts(k, rx, top):
        v = out[k]
        if not isinstance(v, list) or len(v) > top or any(not isinstance(x, str) or not re.fullmatch(rx, x) for x in v):
            raise ConfigError("%s: test_mode %s must be a list of at most %d entries matching %s" % (path, k, top, rx))
    texts("real_agents", r"[a-z][a-z0-9_-]*", 10)
    texts("price_hosts", r"[a-z0-9][a-z0-9.-]*", 10)
    texts("paper_assets", r"[A-Z]{2,10}-USD", 5)
    m, t, u = out["model"], out["model_timeout_s"], out["model_url"]
    if not isinstance(m, str) or not 1 <= len(m) <= 64 or not m.isprintable():
        raise ConfigError("%s: test_mode model must be 1 to 64 printable characters" % path)
    if isinstance(t, bool) or not isinstance(t, int) or not 1 <= t <= 600:
        raise ConfigError("%s: test_mode model_timeout_s must be an integer from 1 to 600" % path)
    ka, nc, npd = out["model_keep_alive"], out["model_num_ctx"], out["model_num_predict"]
    if not isinstance(ka, str) or not re.fullmatch(r"\d{1,4}[smh]", ka):
        raise ConfigError("%s: test_mode model_keep_alive must look like 30m (a number and s, m or h)" % path)
    for what, v, lo, hi in (("model_num_ctx", nc, 256, 32768), ("model_num_predict", npd, 16, 4096)):
        if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
            raise ConfigError("%s: test_mode %s must be an integer from %d to %d" % (path, what, lo, hi))
    try:
        pu = urlparse(u) if isinstance(u, str) else None
        ok = pu is not None and pu.scheme == "http" and pu.hostname in LOOPBACK and (pu.port or 80) > 0
    except ValueError:
        ok = False
    if not ok:
        raise ConfigError("%s: test_mode model_url must be an http:// URL on this machine (127.0.0.1, localhost or ::1)" % path)
    return out


class Config:
    def __init__(self, name, ranks, titles, departments_dir, handoffs_dir, tiers, claude_daily_cap_usd=25.0, schedule=None, gates=None, test_mode=None):
        self.name, self.ranks, self.titles, self.schedule = name, ranks, titles, schedule      # ranks: [(key, label)] top first
        self.test_mode = test_mode or load_test_mode(None, "")
        self.gates = gates or load_gates(None, "")
        self.departments_dir, self.handoffs_dir, self.tiers = departments_dir, handoffs_dir, tiers
        self.claude_daily_cap_usd = claude_daily_cap_usd
        self.rank_index = {k: i for i, (k, _) in enumerate(ranks)}
        self.rank_label = dict(ranks)

    @property
    def root(self):
        return os.path.dirname(self.departments_dir)


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError) as e:
        raise ConfigError("%s: %s" % (path, e)) from None
    ranks = [(r["key"], r.get("label") or r["key"]) for r in d.get("ranks", []) if isinstance(r, dict) and r.get("key")]
    if len(ranks) < 2 or len({k for k, _ in ranks}) != len(ranks):
        raise ConfigError("%s: 'ranks' needs at least two entries with unique keys" % path)
    base = os.path.dirname(os.path.dirname(os.path.abspath(path)))
    try:
        cap = float(d.get("claude_daily_cap_usd", 25.0))
    except (TypeError, ValueError):
        cap = -1.0
    if cap <= 0:
        raise ConfigError("%s: 'claude_daily_cap_usd' must be a positive number" % path)

    def folder(key, default):
        v = d.get(key, default)
        return v if os.path.isabs(v) else os.path.join(base, v)
    tiers = load_tiers(os.path.join(os.path.dirname(os.path.abspath(path)), "tiers.json"), [k for k, _ in ranks])
    return Config(str(d.get("name", "Agency")), ranks, dict(d.get("titles", {})), folder("departments_dir", "departments"), folder("handoffs_dir", "handoffs"), tiers, cap,
                  load_schedule(d.get("schedule"), path), load_gates(d.get("gates"), path), load_test_mode(d.get("test_mode"), path))
