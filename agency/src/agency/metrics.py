"""Per-agent and fleet metrics behind one provider interface.

The dashboard and API only ever see the dicts described by the key tuples below. `SimulatedMetrics` fabricates them from the
simulator; `CgroupMetrics` (stub) documents where each field comes from on a real Ubuntu box. Swap the provider in `App(...)`.
Units: cpu_pct is percent of ONE core (can pass 100), ram/vram in MB, disk in KB/s, times in seconds, cost in USD.
"""
import random
from collections import deque

HARDWARE = ("cpu_pct", "ram_mb", "gpu_pct", "vram_mb", "disk_read_kbs", "disk_write_kbs")
MODEL = ("tokens_per_s", "tokens_in", "tokens_out", "cost_usd", "zero_cost", "ctx_pct", "ctx_window", "ctx_tokens", "ctx_limit", "ctx_limit_configured", "limit_source", "limit_capped", "compactions")
WORK = ("job", "jobs_done", "queue_depth", "avg_job_s", "state_age_s", "errors", "retries", "audit_pass_rate", "last_report_s")
SERIES = ("cpu_pct", "ram_mb", "gpu_pct", "vram_mb", "disk_kbs", "tokens_per_s", "ctx_pct", "queue_depth", "cost_usd")
COMPACT = ("cpu_pct", "ram_mb", "gpu_pct", "vram_mb", "tokens_per_s", "ctx_pct", "cost_usd", "zero_cost", "queue_depth")
ROLLUP = ("agents", "working", "cpu_pct", "ram_mb", "gpu_pct", "vram_mb", "tokens_per_s", "cost_usd", "queue_depth")
FLEET = ("tokens_per_s", "claude_spend_usd", "claude_cap_usd", "gpu_pct", "vram_used_mb", "vram_total_mb", "cpu_pct", "cpu_cores", "ram_used_mb", "ram_total_mb",
         "queue_depth", "avg_job_s", "audit_pass_rate", "errors_1h", "retries_1h")
FLEET_SERIES = ("tokens_per_s", "claude_spend_usd", "gpu_pct", "vram_used_mb", "cpu_pct", "ram_used_mb", "queue_depth", "avg_job_s", "audit_pass_rate", "errors_1h")
HIST = 60
CTX_PER_OUT = 120          # simulated context growth per generated token (tool results and reading make context grow much faster than output)
COMPACT_TO = 0.2           # share of the limit left after a compaction (the summary)


class MetricsProvider:
    """What the API needs. `sample()` runs once per tick; the rest are cheap reads.
      agent(id)   -> {"source", "hardware": {HARDWARE}, "model": {MODEL}, "work": {WORK}, "uptime_s", "series": {SERIES: [..<=60]}}
      compact(id) -> {COMPACT}                       (goes into /api/org for every agent)
      fleet()     -> {"now": {FLEET}, "series": {FLEET_SERIES: [..<=60]}}
    Unknown ids raise KeyError."""
    source = "abstract"

    def sample(self):
        raise NotImplementedError

    def agent(self, aid):
        raise NotImplementedError

    def compact(self, aid):
        raise NotImplementedError

    def fleet(self):
        raise NotImplementedError


class CgroupMetrics(MetricsProvider):
    """STUB, not implemented. Real data sources, one per field group (see docs/metrics.md):

    Hardware, per agent, from its systemd scope /sys/fs/cgroup/<slice>/agent-<id>.scope/ (one scope per agent session):
      cpu_pct         cpu.stat `usage_usec`, delta over the sample interval (x100 = percent of one core)
      ram_mb          memory.current (bytes -> MB); memory.peak / memory.events (oom) for alerts
      disk_*_kbs      io.stat `rbytes` / `wbytes`, delta per second, summed over devices
      (threads)       pids.current
    GPU, per agent: `nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader,nounits` (VRAM) and
      `nvidia-smi pmon -c 1 -s u` (SM util per pid); pids are mapped to agents through the scope's cgroup.procs.
      Box totals: `nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total`.
    Model usage:
      local    tokens_per_s, queue_depth: the inference server's /metrics (llama.cpp `llamacpp:predicted_tokens_seconds`,
               `llamacpp:requests_deferred`; vLLM `vllm:generation_tokens_total` rate, `vllm:num_requests_waiting`)
      claude   tokens_in/out, cost_usd, ctx_pct: usage ledger (per-request usage blocks from Claude Code transcripts or the API:
               input_tokens, output_tokens, cache_* tokens) priced per model; ctx_pct = last request's input tokens / window
    Work (job, jobs_done, avg_job_s, errors, retries, audit_pass_rate, last_report_s, state_age_s, queue_depth): the orchestrator's own job ledger.
    uptime_s: now minus the scope's start time (systemctl show -p ActiveEnterTimestamp).
    """
    source = "cgroup"
    FILES = {"cpu": "cpu.stat", "ram": "memory.current", "io": "io.stat", "pids": "pids.current", "procs": "cgroup.procs"}

    def __init__(self, scope_root="/sys/fs/cgroup/agency.slice", scope_fmt="agent-%s.scope", inference_url="http://127.0.0.1:8080/metrics", ledger_path="data/usage.jsonl"):
        self.scope_root, self.scope_fmt, self.inference_url, self.ledger_path = scope_root, scope_fmt, inference_url, ledger_path

    def _todo(self, what):
        paths = ", ".join("%s/%s/%s" % (self.scope_root, self.scope_fmt % "<id>", f) for f in self.FILES.values())
        raise NotImplementedError("CgroupMetrics.%s is not implemented. It will read %s; nvidia-smi --query-compute-apps; %s; %s" % (what, paths, self.inference_url, self.ledger_path))

    def sample(self):
        self._todo("sample")

    def agent(self, aid):
        self._todo("agent")

    def compact(self, aid):
        self._todo("compact")

    def fleet(self):
        self._todo("fleet")


def rollup(org, compact, states, aid):
    """Sum of a subtree's draw (the agent plus everything under it), from the compact dicts; `states` is {id: state}."""
    ids, stack = [], [aid]
    while stack:
        i = stack.pop()
        ids.append(i)
        stack.extend(org.agents[i].children)
    out = {k: sum(compact[i][k] for i in ids) for k in ROLLUP[2:]}
    out["agents"] = len(ids)
    out["working"] = sum(1 for i in ids if states[i] == "working")
    return {k: (round(out[k], 4) if k == "cost_usd" else round(out[k], 1)) if isinstance(out[k], float) else out[k] for k in ROLLUP}


class _St:
    """Rolling state of one simulated agent."""

    def __init__(self, rng, local, lim):
        self.local, self.lim = local, lim                     # lim: config.Tiers.limit(...): the agent's compaction limit and model window
        self.window, self.limit = lim["window"], lim["effective"]
        self.ctx = self.limit * rng.uniform(0.05, 0.4)
        out = rng.uniform(60000, 200000) if local else rng.uniform(20000, 70000)     # tokens already used today, before the sim started
        self.t_out, self.t_in = out, out * rng.uniform(3, 6) if local else out * rng.uniform(4, 7)
        self.vram_base = rng.uniform(800, 1200) if local else 0.0
        self.ram_base = rng.uniform(900, 1400) if local else rng.uniform(330, 460)
        self.v = {"cpu_pct": 2.0, "gpu_w": 0.0, "tokens_per_s": 0.0, "read": 5.0, "write": 8.0}
        self.h = {k: deque(maxlen=HIST) for k in SERIES}
        self.now = None                                    # latest readings, set by the first sample()


class SimulatedMetrics(MetricsProvider):
    """Deterministic fake telemetry derived from the simulator's agent states (own seeded RNG: events stay unchanged)."""
    source = "simulated"
    PRICE_IN, PRICE_OUT = 3.0, 15.0                        # USD per million tokens (priced like a mid-size Claude model)
    CORES, RAM_TOTAL, VRAM_TOTAL, OS_RAM, OS_VRAM = 8, 32768, 24576, 3800, 512

    def __init__(self, sim, cap_usd=25.0):
        self.sim, self.cap = sim, cap_usd
        self.rng = random.Random(sim.seed * 104729 + 3)
        self.st = {}
        self.fh = {k: deque(maxlen=HIST) for k in FLEET_SERIES}
        self._fleet = None

    def _get(self, aid):
        if aid not in self.st:
            a = self.sim.org.agents[aid]
            self.st[aid] = _St(self.rng, a.runtime == "local", self.sim.org.cfg.tiers.limit(aid, a.rank, a.runtime))
        return self.st[aid]

    @staticmethod
    def _ease(st, key, target, k=0.55):
        st.v[key] += (target - st.v[key]) * k
        return st.v[key]

    def sample(self):
        sim, rng = self.sim, self.rng
        org = sim.org
        for aid in org.order:                                                  # first: a fixed number of draws per agent per tick
            self._get(aid)
        draw = {aid: [rng.random() for _ in range(6)] for aid in org.order}
        local_w = {aid: 0.6 + 0.4 * draw[aid][4] for aid in org.order if self.st[aid].local and sim.shown(aid) == "working"}
        box_gpu = 70 + 26 * rng.random()
        tot_w = sum(local_w.values()) or 1.0
        tot = {"cpu": 0.0, "ram": 0.0, "gpu": 0.0, "vram": 0.0, "tps": 0.0, "spend": 0.0, "q": 0}
        for aid in org.order:
            n, st, r = sim.nodes[aid], self.st[aid], draw[aid]
            ss = sim.shown(aid)                                                # the tree's state: with a schedule, only a scheduled agent works
            leaf_work = ss == "working"
            cpu_t = {"idle": 1.5 + 2 * r[0], "waiting": 2.5 + 3 * r[0], "blocked": 2 + 2 * r[0], "reporting": 12 + 10 * r[0]}.get(ss)
            if cpu_t is None:
                cpu_t = (25 + 45 * r[0]) if st.local else (14 + 28 * r[0])
            tps_t = (0.0 if not leaf_work and ss != "reporting" else (18 + 37 * r[1]) if st.local else (35 + 55 * r[1])) * (0.4 if ss == "reporting" else 1)
            gpu_t = box_gpu * local_w[aid] / tot_w if aid in local_w else (2.0 * r[2] if st.local and ss == "reporting" else 0.0)
            cpu = self._ease(st, "cpu_pct", cpu_t)
            tps = self._ease(st, "tokens_per_s", tps_t)
            gpu = self._ease(st, "gpu_w", gpu_t) if st.local else 0.0
            dt = sim.tick_s
            out = tps * dt
            st.t_out += out
            st.t_in += out * (5.0 + 2 * r[3])
            st.ctx += out * CTX_PER_OUT + sim.take_ctx_add(aid)                  # generated/tool tokens plus the handoffs this agent read
            if st.ctx >= st.limit:                                                # hit the tier limit: compact
                before, st.ctx = st.ctx, COMPACT_TO * st.limit
                sim.note_compaction(aid, before, st.ctx, st.limit)
            fill = st.ctx / st.limit
            read = self._ease(st, "read", (200 + 2800 * r[4]) if leaf_work else 5 + 40 * r[4])
            write = self._ease(st, "write", (60 + 800 * r[5]) if leaf_work else 8 + 30 * r[5])
            ram = st.ram_base + (140 if not st.local else 500) * fill + 40 * r[5]
            vram = st.vram_base + 900 * fill if st.local else 0.0
            cost = 0.0 if st.local else (st.t_in * self.PRICE_IN + st.t_out * self.PRICE_OUT) / 1e6
            st.now = {"cpu_pct": round(cpu, 1), "ram_mb": round(ram), "gpu_pct": round(gpu, 1), "vram_mb": round(vram), "tokens_per_s": round(tps, 1), "ctx_pct": round(100 * fill, 1),
                      "cost_usd": round(cost, 4), "zero_cost": st.local, "queue_depth": len(n.inbox), "disk_read_kbs": round(read), "disk_write_kbs": round(write)}
            for k, v in (("cpu_pct", cpu), ("ram_mb", ram), ("gpu_pct", gpu), ("vram_mb", vram), ("disk_kbs", read + write), ("tokens_per_s", tps), ("ctx_pct", 100 * fill),
                         ("queue_depth", len(n.inbox)), ("cost_usd", cost)):
                st.h[k].append(round(v, 4) if k == "cost_usd" else round(v, 1))
            tot["cpu"] += cpu
            tot["ram"] += ram
            tot["gpu"] += gpu
            tot["vram"] += vram
            tot["tps"] += tps
            tot["spend"] += cost
            tot["q"] += len(n.inbox)
        done = sum(n.done for n in sim.nodes.values())
        audits = sum(n.audit_n for n in sim.nodes.values())
        errs = sum(1 for _, k in sim.err_log if k == "error")
        rets = sum(1 for _, k in sim.err_log if k == "retry")
        now = {"tokens_per_s": round(tot["tps"], 1), "claude_spend_usd": round(tot["spend"], 2), "claude_cap_usd": self.cap, "gpu_pct": round(min(100.0, tot["gpu"]), 1),
               "vram_used_mb": round(tot["vram"] + self.OS_VRAM), "vram_total_mb": self.VRAM_TOTAL, "cpu_pct": round(min(100.0, (tot["cpu"] + 15) / self.CORES), 1), "cpu_cores": self.CORES,
               "ram_used_mb": round(tot["ram"] + self.OS_RAM), "ram_total_mb": self.RAM_TOTAL, "queue_depth": tot["q"],
               "avg_job_s": round(sum(n.dur_sum for n in sim.nodes.values()) * sim.tick_s / done, 1) if done else None,
               "audit_pass_rate": round(100 * sum(n.audit_ok for n in sim.nodes.values()) / audits, 1) if audits else None, "errors_1h": errs, "retries_1h": rets}
        self._fleet = now
        for k in FLEET_SERIES:
            v = now[k]
            self.fh[k].append(v if v is not None else (self.fh[k][-1] if self.fh[k] else 0))

    def agent(self, aid):
        n, st, sim = self.sim.nodes[aid], self._get(aid), self.sim
        if st.now is None:
            self.sample()
        w = st.now
        t = sim.tick_s
        return {"source": self.source,
                "hardware": {k: w[k] for k in HARDWARE},
                "model": {"tokens_per_s": w["tokens_per_s"], "tokens_in": round(st.t_in), "tokens_out": round(st.t_out), "cost_usd": w["cost_usd"], "zero_cost": st.local,
                          "ctx_pct": w["ctx_pct"], "ctx_window": st.window, "ctx_tokens": round(st.ctx), "ctx_limit": st.limit,
                          "ctx_limit_configured": st.lim["configured"], "limit_source": st.lim["source"], "limit_capped": st.lim["capped"], "compactions": n.compactions},
                "work": {"job": (n.cur or {}).get("job"), "jobs_done": n.done, "queue_depth": len(n.inbox), "avg_job_s": round(n.dur_sum * t / n.done, 1) if n.done else None,
                         "state_age_s": round((sim.tick - n.since) * t, 1), "errors": n.errors, "retries": n.retries,
                         "last_report_s": round((sim.tick - n.last_report) * t, 1) if n.last_report is not None else None,
                         "audit_pass_rate": round(100 * n.audit_ok / n.audit_n, 1) if n.audit_n else None},
                "uptime_s": round((sim.tick - n.started) * t, 1),
                "series": {k: list(st.h[k]) for k in SERIES}}

    def compact(self, aid):
        st = self._get(aid)
        if st.now is None:
            self.sample()
        c = {k: st.now[k] for k in COMPACT}
        c["queue_depth"] = len(self.sim.nodes[aid].inbox)
        return c

    def fleet(self):
        if self._fleet is None:
            self.sample()
        return {"now": dict(self._fleet), "series": {k: list(v) for k, v in self.fh.items()}}
