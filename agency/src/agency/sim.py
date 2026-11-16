"""Simulated activity, seedable and deterministic: jobs arrive at the Head, flow down as assignments and up as reports.
Every hand-over is a real handoff file (handoff.py) in a bounded temp dir: assignment down, report up, question/answer, escalation/decision,
and cross-department `data` from Lead to Lead (then on to a worker). Agents find their files by name only (list_for) and open just those.
Time is a tick counter (no wall clock), so the same seed always gives the same events. A real runner would replace
Sim.step(): it only has to keep per-agent state and emit the same events."""
import logging
import os
import random
import shutil
import tempfile
import time
import weakref
from collections import deque

from . import net
from .config import ConfigError
from .gates import WORST_CASE, Gates
from .handoff import HandoffError, HandoffStore, parse_name
from .loader import COMMAND
from .paper import Paper
from .real import Real
from .returns import ALLOC
from .scheduler import Scheduler

STATES = ("idle", "working", "waiting", "reporting", "blocked")
KINDS = ("job", "assign", "report", "ask", "answer", "blocked", "unblock", "deliver", "reload", "data", "compact", "stop")
EPOCH = 1767225600          # 2026-01-01T00:00:00Z: simulated clock = EPOCH + tick * tick_s
PLAN_QUEUE = 5              # planned tasks kept queued per department
HANDOFF_KEEP = 300          # archived handoff files kept in the temp dir
GATE_P = 0.25               # share of planned tasks that need an approval before they may start
FAIL_P = 0.3                # chance a finished attempt fails its (simulated) finish check
GATES = {"spend": ("Pay for a data set", 5, 60), "outbound": ("Send a public post", 0, 5), "irreversible": ("Delete an old archive", 0, 2), "rules": ("Change a department schedule", 0, 0)}
CATALOG = (("ceramic mug", 12.5), ("canvas tote bag", 18.0), ("desk plant pot", 9.5), ("linen notebook", 14.0))      # what the simulated shop sells (test mode, operations)
log = logging.getLogger(__name__)
WORK = ("Gather inputs", "Draft deliverable", "Review output", "Package results", "Check quality", "Prepare hand-off", "Compare options")


class Node:
    __slots__ = ("state", "until", "left", "cur", "wait", "inbox", "sup", "prev", "since", "t0", "done", "dur_sum", "errors", "retries", "audit_n", "audit_ok", "last_report", "started",
                 "ctx_add", "compactions", "cur_h", "qname")

    def __init__(self, tick=0):
        self.state, self.until, self.left, self.cur, self.wait, self.inbox, self.sup = "idle", 0, 0, None, set(), [], False   # sup: a manager waiting on its reports
        # work bookkeeping the metrics layer reads (a real orchestrator keeps the same facts in its job ledger)
        self.prev, self.since, self.t0, self.started = "idle", tick, tick, tick          # prev/since: state change tracking; t0: tick the current job started
        self.done, self.dur_sum, self.errors, self.retries, self.audit_n, self.audit_ok, self.last_report = 0, 0, 0, 0, 0, 0, None
        # ctx_add: tokens read from handoffs (metrics layer takes them); cur_h: open assignment files; qname: open question/escalation
        self.ctx_add, self.compactions, self.cur_h, self.qname = 0, 0, [], None


class Sim:
    def __init__(self, org, seed=1, tick_s=1.0, max_events=200, max_jobs=4, data_dir=None, model=None, fetch=None, clock=time.time):
        """Test mode (config test_mode.real_agents non-empty, needs data_dir): model (prompt -> text) and fetch (symbol -> price) default to net.py and are injected by tests."""
        self.org, self.seed, self.tick_s, self.max_jobs, self.data_dir = org, seed, tick_s, max_jobs, data_dir
        tm, self.real, self.paper = org.cfg.test_mode, None, None
        if tm["real_agents"]:
            bad = [a for a in tm["real_agents"] if a not in org.agents]
            if bad or not data_dir:
                raise ConfigError("test_mode.real_agents: %s" % ("no such agent: " + ", ".join(bad) if bad else "test mode needs a data dir"))
            ask = lambda p: net.ask_model(p, tm["model_url"], tm["model"], tm["model_timeout_s"], tm["model_keep_alive"], tm["model_num_ctx"], tm["model_num_predict"])    # noqa: E731
            self.real, self.worker = Real(tm, model or ask, data_dir, clock), net.Worker()          # every model call and price fetch runs on this one thread, one at a time
            self.paper = Paper(os.path.join(data_dir, "paper.json"), tm["paper_assets"], fetch or (lambda s: net.fetch_price(s, tm["price_hosts"])), clock, ALLOC["finance-trading"])
        self.rng = random.Random(seed)
        self.tick, self.n, self.jobs_made, self.jobs_done, self.gen = 0, 0, 0, 0, 0
        self.events = deque(maxlen=max_events)
        self.hist = deque(maxlen=60)
        self._rep = deque(maxlen=max(1, round(60 / tick_s)))     # reports per tick over the last minute
        self.mrng = random.Random(seed * 7919 + 17)              # audit outcomes: own stream, so the event stream does not depend on it
        self.err_log = deque()                                   # (tick, kind) for errors and retries; trimmed to the last hour
        self.prng = random.Random(seed * 4813 + 11)              # planned tasks for the scheduler: own stream too
        self.grng = random.Random(seed * 6571 + 3)               # which planned tasks need an approval (kind, cost): own stream
        self.crng = random.Random(seed * 2711 + 9)               # finish-check outcomes: own stream
        self.hrng = random.Random(seed * 31337 + 5)              # handoff content and cross-department traffic: own stream, the main event stream does not depend on it
        self.gates = Gates(org.cfg.gates, os.path.join(data_dir, "gates.json") if data_dir else None)      # one for the life of the process: _reset keeps it
        self._tmp = tempfile.mkdtemp(prefix="agency-handoffs-")
        weakref.finalize(self, shutil.rmtree, self._tmp, True)
        self._reset()

    def _reset(self):
        self.gen += 1                    # model answers still on their way for the old jobs are dropped
        self.nodes = {a: Node(self.tick) for a in self.org.order}
        self.open = set()
        self.jobs, self.rep_ids, self.returns = deque(maxlen=60), {}, {}        # scheduler jobs seen (Business tab), recent report ids per department (evidence), published returns by period
        sc = self.org.cfg.schedule        # None: no schedule configured
        members = {d: [a for a in self.org.order if self.org.agents[a].dept == d] for d in sc["departments"]} if sc else None
        self.sched = Scheduler(sc, members, EPOCH + self.tick * sc["tick_s"], self.gates, self._check,
                               os.path.join(self.data_dir, "schedule.json") if self.data_dir else None, self.real.agents if self.real else ()) if sc else None
        for d in ("departments", "handoffs"):
            shutil.rmtree(os.path.join(self._tmp, d), ignore_errors=True)
        self.hs = HandoffStore(self.org, os.path.join(self._tmp, "departments"), os.path.join(self._tmp, "handoffs"), lambda: EPOCH + self.tick * self.tick_s, max_archive=HANDOFF_KEEP)

    def rebind(self, org):
        """Org changed. A body-only edit keeps the run going; a changed tree restarts the simulated jobs."""
        same = org.signature() == self.org.signature()
        self.org = self.hs.org = org
        if not same:
            self._reset()
            self._emit("reload", None, None, None, "organisation changed, simulation restarted")

    def _check(self, j):
        """The finish check of a scheduler job: the simulated one, or, for a real agent's job, None (the model call is queued; `_apply` answers it when it is done)."""
        if self.real and j["agent"] in self.real.agents:
            self._real_job(self.org.agents[j["agent"]], j["id"], j["title"], self._task(j), j)
            return None
        return self.crng.random() >= FAIL_P

    def _task(self, j):
        """The task text a real agent gets: its department's simulated world (a customer's order or a listing to draft for operations, the paper portfolio for finance) or the job title."""
        r = random.Random("%s:%s" % (self.seed, j["id"]))
        item, price = r.choice(CATALOG)
        if j["dept"] == "operations" and j["n"] % 2:
            return ("Write an order-handling note for order ord-%04d: customer cust-%03d bought %d x %s at $%.2f each. Say what to check, what to tell the customer and anything missing. "
                    "Nothing is sent; this is a draft." % (r.randint(1, 9999), r.randint(1, 999), r.randint(1, 4), item, price))
        if j["dept"] == "operations":
            return "Draft a product listing (title, three bullet points, short description) for: %s, price $%.2f. This is a draft; nothing is posted." % (item, price)
        if j["dept"] == "finance-trading" and self.paper:
            p = self.paper.snapshot()
            held = ", ".join(x["sym"] for x in p["positions"]) or "none"
            return ("Write a short status note on this PAPER portfolio (simulated money, no broker, rule is a placeholder, not a strategy): equity $%.2f from $%.2f, P&L $%.2f, cash $%.2f, "
                    "positions %s, %d closed trades, last price error: %s." % (p["equity"], p["start"], p["pnl"], p["cash"], held, p["closed"], p["error"] or "none"))
        return "%s (department %s). This is simulated work; write what you would do, in a few lines." % (j["title"], j["dept"])

    def _real_job(self, a, job, title, task, j=None):
        """Queue one model call for agent a (j: the scheduler job waiting on it, None for a one-off note). Returns at once: the worker thread makes the call."""
        p = self.real.prompt(a, task)
        self.worker.submit(("real", self.gen, a, job, title, j, len(p)), self.real.model, p)

    def _apply(self):
        """Take in what the worker has finished (called by step, which runs under the app lock): price samples, and the model's replies."""
        for tag, out, secs in self.worker.collect():
            if tag[0] == "paper":
                self.paper.apply(out, tag[1])
            elif tag[1] == self.gen:
                self._real_done(*tag[2:6], out, secs, tag[6])

    def _real_done(self, a, job, title, j, out, secs, n):
        """A real agent's model call ended: hand the reply up (the usual `report` handoff), keep it as a file and queue it for the owner's review. Never raises; a scheduler job
        waiting on it gets its finish check answer (False = failed attempt)."""
        ok = False
        try:
            text = self.real.check(a, out)
            up = self.org.agents[a.reports_to] if a.reports_to else a
            body = "\n".join(" " + x if x.startswith("## ") else x for x in text.split("\n"))          # a line starting '## ' would open a new section of the envelope
            self.real.save(a, job, title, text, secs)                                                   # the file first: a failed save must not leave a handoff behind to be written again on the retry
            name = self.hs.write_handoff(a.id, "%s.%s" % (up.dept, up.role), "report", job, "report: " + title[:100], [x.strip()[:160] for x in text.split("\n") if x.strip()][:3],
                                         "Job %s (%s). Written by a local model, TEST MODE." % (job, title), body, "none", ttl_s=3600)
            self._emit("report", a.id, None if up is a else up.id, job, "real output for %s, waiting for your review" % job, parse_name(name)["tag"], "report")
            log.info("real job %s by %s: %.1f s, prompt %d chars, reply %d chars", job, a.id, secs, n, len(text))
            ok = True
        except Exception as e:  # noqa: BLE001 - a real job can fail in many ways; none may stop the dashboard
            self.real.error = "%s: %s" % (a.id, type(e).__name__)
            log.warning("real job %s by %s failed after %.1f s (prompt %d chars): %s", job, a.id, secs, n, type(e).__name__)
        if j:
            self.sched.resolve(j, ok)

    def review(self, d):
        """The owner's decision on a real output (body of POST /api/review). It is also written down as a `decision` handoff from the Head to the agent (best effort)."""
        i = self.real.decide(d)
        try:
            a = self.org.agents[i["agent"]]
            self.hs.write_handoff(self.org.root, "%s.%s" % (a.dept, a.role), "decision", i["job"], "decision: " + i["title"][:100], ["Owner %sed %s." % (i["decision"], i["id"])],
                                  "Your output %s." % i["id"], "Owner decision: %s\nNote: %s" % (i["decision"], i["note"] or "none"), "none", ttl_s=3600)
        except (HandoffError, KeyError) as e:
            log.warning("decision handoff for %s not written: %s", i["id"], e)
        return i

    def test_snapshot(self):
        return {"real": self.real.snapshot(), "paper": self.paper.snapshot()} if self.real else None

    def _t(self, i):
        return self.org.agents[i].title if i in self.org.agents else "You"

    def _emit(self, kind, src, dst, job, text, tag=None, hkind=None):
        """tag/hkind: routing tag and kind of the handoff file behind this event (None for events without one)."""
        self.n += 1
        text = "%s: %s" % (self._t(src), text) if kind == "compact" else "%s -> %s: %s" % (self._t(src), self._t(dst), text) if dst or src else text
        self.events.append({"n": self.n, "tick": self.tick, "kind": kind, "src": src, "dst": dst, "job": job, "text": text, "tag": tag, "hkind": hkind})

    def _hand(self, ev, hkind, src, dst, job, title, text, supersedes=None, attach=()):
        """Write a real handoff file from agent src to agent dst and emit the feed event for it. Returns the file name."""
        d, r = self.org.agents[dst].dept, self.org.agents[dst].role
        h = self.hrng
        name = self.hs.write_handoff(src, "%s.%s" % (d, r), hkind, job, "%s: %s" % (hkind, title), [text], "Job %s (%s)." % (job, title),
                                     "Simulated %s from %s to %s." % (hkind, self._t(src), self._t(dst)),
                                     "Reply with the matching handoff when done." if hkind in ("assignment", "question", "escalation") else "none",
                                     attach, ttl_s=3600, supersedes=supersedes, token_estimate=h.randint(600, 4500))
        if hkind == "report":
            self.rep_ids.setdefault(self.org.agents[src].dept, deque(maxlen=3)).append(self._hid(name))
        self._emit(ev, src, dst, job, text, parse_name(name)["tag"], hkind)
        return name

    @staticmethod
    def _hid(name):
        p = parse_name(name)
        return "%s-%s" % (p["job"], p["seq_s"])

    def _open(self, aid, kinds, job=None, finish=True):
        """Find this agent's files by name (list_for), open only those, add their size to its context, and close them."""
        n = self.nodes[aid]
        got = []
        for f in self.hs.list_for(aid, kinds, job):
            n.ctx_add += self.hs.read(aid, f["name"])["token_estimate"]
            if finish:
                self.hs.mark_done(aid, f["name"])
            got.append(f["name"])
        return got

    def _close(self, aid, names):
        for f in names:
            if f in self.hs.idx:
                self.hs.mark_done(aid, f)

    def note_compaction(self, aid, before, after, limit):
        """Called by the metrics layer when an agent's context reached its limit and was compacted."""
        n = self.nodes[aid]
        n.compactions += 1
        self._emit("compact", aid, None, (n.cur or {}).get("job"), "context compacted, %dk -> %dk tokens (limit %dk)" % (before / 1000, after / 1000, limit / 1000))

    def take_ctx_add(self, aid):
        n = self.nodes[aid]
        v, n.ctx_add = n.ctx_add, 0
        return v

    def _send_down(self, src, kids, job, title):
        for k in kids:
            self._hand("assign", "assignment", src, k, job, title, "assign %s (%s)" % (job, title))
            self.nodes[k].inbox.append({"job": job, "title": title, "ready": self.tick + 1})

    def _cross_data(self):
        """Departments talk through their Leads only: a Lead sends `data` to another Lead, who reads it and passes it to one of its workers."""
        org, h = self.org, self.hrng
        for aid in org.order:
            a = org.agents[aid]
            if a.dept == COMMAND:
                continue
            for name in self._open(aid, ("data",)):
                if a.children and org.leads[a.dept] == aid:
                    w = h.choice(a.children)
                    job = parse_name(name)["job"]
                    self._hand("data", "data", aid, w, job, "forwarded input", "data on %s for you" % job, attach=("handoffs/archive/done/" + name,))

    def _plan(self):
        """Each department keeps a few planned tasks queued (the user's own tasks go in with sched.add(..., user=True))."""
        r = self.prng
        for d in self.sched.depts:
            if len(self.sched.queue[d]) < PLAN_QUEUE and r.random() < 0.15:
                est = r.randint(20, 80) * 1000
                j = self.sched.add(d, r.choice(WORK), est, r.randint(2, 8) * 300, actual=round(est * r.uniform(0.9, WORST_CASE)))     # estimates are only estimates
                self.jobs.append(j)
                if self.grng.random() < GATE_P:
                    kind = self.grng.choice(tuple(GATES))
                    what, lo, hi = GATES[kind]
                    self.sched.gate(j, kind, "%s for %s" % (what, j["title"]), self.grng.uniform(lo, hi))

    def step(self):
        self.tick += 1
        reports = 0
        if self.real:
            self._apply()
            syms = self.paper.due()
            if syms:
                self.worker.submit(("paper", self.paper.clock()), self.paper.fetch_all, syms)
        self._cross_data()
        if self.sched:
            self._plan()
            self.sched.step(EPOCH + self.tick * self.sched.cfg["tick_s"])        # the schedule runs on its own clock (minutes_per_tick), so windows and usage periods are watchable
            for j in self.sched.newly_blocked:                 # third failed attempt: report up the chain (worker > lead > boss); the dashboard queue shows it to the user
                lead, text = self.org.leads.get(j["dept"]), "%s blocked after %d failed attempts" % (j["id"], j["tries"])
                if lead and j["agent"] != lead:
                    self._emit("stop", j["agent"], lead, j["id"], text)
                self._emit("stop", lead or j["agent"], self.org.root, j["id"], text + ", passed on to you")
            self.sched.newly_blocked.clear()
        if len(self.open) < self.max_jobs and self.rng.random() < 0.3:
            self.jobs_made += 1
            job, title = "job-%03d" % self.jobs_made, self.rng.choice(WORK)
            self.open.add(job)
            root = self.org.root
            self.nodes[root].inbox.append({"job": job, "title": title, "ready": self.tick})
            self._emit("job", None, root, job, "new job %s (%s)" % (job, title))
        for aid in self.org.order:
            reports += self._node(aid)
            n = self.nodes[aid]
            if n.state != n.prev:
                n.prev, n.since = n.state, self.tick
        horizon = self.tick - round(3600 / self.tick_s)
        while self.err_log and self.err_log[0][0] <= horizon:
            self.err_log.popleft()
        self._rep.append(reports)
        s = self.stats()
        self.hist.append((s["running"], s["idle"], s["blocked"], s["jobs_in_flight"], s["reports_per_min"]))

    def _node(self, aid):
        a, n, rng, t = self.org.agents[aid], self.nodes[aid], self.rng, self.tick
        up = a.reports_to
        if n.state == "idle":
            if n.inbox and n.inbox[0]["ready"] <= t:
                n.cur, n.sup, n.t0 = n.inbox.pop(0), False, t
                n.cur_h = self._open(aid, ("assignment",), n.cur["job"], finish=False)        # read the assignment; it is closed when the report goes up
                n.state, n.left = "working", rng.randint(2, 5) if not a.children else rng.randint(1, 2)
        elif n.state == "working":
            if n.sup:                                           # a manager whose work is out with its reports
                if n.wait:
                    return 0
                n.state, n.until, n.sup = "reporting", t + 1, False
                self._finished(a, n)
                self._open(aid, ("report",), n.cur["job"])                                      # collect what the reports sent up to us
                if up:
                    self.nodes[up].wait.discard(aid)
                    self._hand("report", "report", aid, up, n.cur["job"], n.cur["title"], "report %s done" % n.cur["job"])
                    self._close(aid, n.cur_h)
                else:
                    self.open.discard(n.cur["job"])
                    self.jobs_done += 1
                    self._emit("deliver", aid, None, n.cur["job"], "%s delivered to you" % n.cur["job"])
                    if self.real and aid in self.real.agents:         # the Head (test mode): a short status note on the delivery, once, no retry
                        self._real_job(a, "boss-" + n.cur["job"], n.cur["title"], "Job %s (%s) was just delivered by your team (simulated work: there is no real deliverable). "
                                       "Write the owner a status note of three to five lines." % (n.cur["job"], n.cur["title"]))
                return 1
            n.left -= 1
            r = rng.random()
            if up and r < 0.06:
                n.state, n.until = "waiting", t + rng.randint(2, 4)
                n.qname = self._hand("ask", "question", aid, up, n.cur["job"], n.cur["title"], "needs a decision on %s" % n.cur["job"])
            elif up and r < 0.09:
                n.state, n.until = "blocked", t + rng.randint(4, 8)
                n.errors += 1
                self.err_log.append((t, "error"))
                n.qname = self._hand("blocked", "escalation", aid, up, n.cur["job"], n.cur["title"], "blocked on %s" % n.cur["job"])
            elif n.left <= 0:
                if a.children:
                    kids = sorted(rng.sample(a.children, rng.randint(1, len(a.children))))
                    n.wait, n.sup = set(kids), True
                    self._send_down(aid, kids, n.cur["job"], n.cur["title"])
                    others = sorted(ld for d, ld in self.org.leads.items() if d != a.dept)
                    if a.dept != COMMAND and others and self.hrng.random() < 0.3:             # a Lead needs another department: Lead to Lead
                        self._hand("data", "data", aid, self.hrng.choice(others), n.cur["job"], n.cur["title"], "data on %s for your department" % n.cur["job"])
                else:
                    n.state, n.until = "reporting", t + 1
                    self._finished(a, n)
                    self.nodes[up].wait.discard(aid)
                    self._hand("report", "report", aid, up, n.cur["job"], n.cur["title"], "report %s done" % n.cur["job"])
                    self._close(aid, n.cur_h)
                    return 1
        elif n.state in ("waiting", "blocked"):
            if t >= n.until:
                w = n.state == "waiting"
                self._hand("answer" if w else "unblock", "answer" if w else "decision", up, aid, n.cur["job"], n.cur["title"], "decision on %s" % n.cur["job"] if w else "unblocked %s" % n.cur["job"],
                           supersedes=self._hid(n.qname) if n.qname in self.hs.idx else None)
                self._open(aid, ("answer", "decision"), n.cur["job"])
                n.state, n.left, n.qname = "working", max(n.left, 1), None
        elif n.state == "reporting" and t >= n.until:
            n.state, n.cur = "idle", None
        return 0

    def _finished(self, a, n):
        """A job leaves this agent: book its duration and the superior's audit of it (a failed audit counts an error and a retry)."""
        t = self.tick
        n.done += 1
        n.dur_sum += t - n.t0
        n.last_report = t
        n.audit_n += 1
        if self.mrng.random() < (0.97 if a.runtime == "claude-code" else 0.88):
            n.audit_ok += 1
        else:
            n.errors += 1
            n.retries += 1
            self.err_log.append((t, "error"))
            self.err_log.append((t, "retry"))

    def shown(self, aid):
        """The state the tree shows. With a schedule, the scheduler alone decides who is working; a node holding a job without a slot shows as waiting."""
        n = self.nodes[aid]
        if not self.sched:
            return n.state
        return "working" if self.sched.state(aid) == "working" else "waiting" if n.state == "working" else n.state

    def stats(self):
        c = {s: 0 for s in STATES}
        for aid in self.nodes:
            c[self.shown(aid)] += 1
        window = len(self._rep)
        rpm = round(sum(self._rep) * 60 / (max(1, window) * self.tick_s), 1) if window else 0.0
        return {"agents": len(self.nodes), "running": len(self.nodes) - c["idle"], "idle": c["idle"], "blocked": c["blocked"], "waiting": c["waiting"],
                "jobs_in_flight": len(self.open), "jobs_done": self.jobs_done, "reports_per_min": rpm}

    def state_of(self, aid):
        n, st = self.nodes[aid], self.shown(aid)
        detail = {"idle": "", "working": "working on %s" % (n.cur or {}).get("job", ""), "waiting": "waiting on superior for a decision", "blocked": "blocked, needs superior",
                  "reporting": "reporting %s up" % (n.cur or {}).get("job", "")}[n.state]
        if n.state == "working" and n.sup:
            detail = "supervising %s (%d reports pending)" % (n.cur["job"], len(n.wait))
        if self.sched and st == "working":
            j = next(j for j in self.sched.running if j["agent"] == aid)
            detail = "working on %s (%s)" % (j["id"], j["title"])
        elif self.sched and n.state == "working" and not n.sup:
            detail = "waiting for a work slot"
        return {"state": st, "job": (n.cur or {}).get("job"), "detail": detail.strip()}

    def history(self):
        cols = list(zip(*self.hist, strict=True)) if self.hist else [(), (), (), (), ()]
        return dict(zip(("running", "idle", "blocked", "jobs_in_flight", "reports_per_min"), (list(c) for c in cols), strict=True))

    def feed(self, since=0, limit=50, agent=None):
        """Newest `limit` events after `since`; with `agent`, only events that agent sent or received."""
        ev = [e for e in self.events if e["n"] > since and (agent is None or agent in (e["src"], e["dst"]))]
        return ev[-limit:]

    def agent_events(self, aid, limit=15):
        return self.feed(0, limit, aid)
