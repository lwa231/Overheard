"""Simulated scheduler: who may work, when, and on how many tokens. Time is passed in (`step(now)`, seconds on the simulated clock), never read from the wall clock.

Agents are asleep, warm (context kept loaded) or working. At most `max_working` work at once and at most `max_loaded` (warm + working) stay loaded;
loading one more puts the least recently used warm agent to sleep. Each department has a clock window and an on/off toggle, and only starts jobs while
the window is open and the toggle is on. A job in hand is never cut off at close; it may run at most GRACE x the window length longer, then it is paused
(checkpoint, flagged). Each simulated usage window has a token budget split between departments by share; a job starts only if its estimate fits both
its department's remaining share and the remaining total. When the total or a department's share is spent, working jobs are paused with a checkpoint and resume in the next
usage window: no overrun (a job whose estimate is more than its department's whole share is refused at add()).
Per department one queue: paused jobs first, then tasks the user added, then planned ones.
With `gates` (gates.py) a job can wait on a human approval (`hold`), the close and usage-limit pauses become overrun requests, and a job that fails its finish
check `check(job)` is retried until `attempts` is used up, then marked blocked (never retried again). Without `gates` none of this applies.
Real agents (`real`, test mode): their jobs run one at a time (a finish check may answer None = still waiting on the model; `resolve` gives the answer later), and among jobs of
the same priority the agent that ran last goes on first. Simulated agents keep the configured cap and the allocator's order.
Granularity is one step: a start, close or window change is noticed at the next step (jobs themselves are clipped exactly at their deadline and at the budget)."""
import json
from collections import OrderedDict

from .gates import OVERRUN, USD_PER_1K_TOKENS, WORST_CASE, save_json

DAY = 86400
GRACE = 0.25                    # a job may run this share of the window length past close
USER_TASK_S = 1200              # simulated work time of a task the user adds
ONE_SHOT = ("spend", "outbound", "irreversible")       # each attempt needs its own approval
MIN_TOKENS, MAX_TITLE, MAX_QUEUE = 1000, 80, 30


class ScheduleError(ValueError):
    pass


def hhmm(minutes):
    return "%02d:%02d" % divmod(int(minutes), 60)


class Scheduler:
    def __init__(self, cfg, members, now=0, gates=None, check=None, path=None, real=()):
        """cfg: config.load_schedule(...); members: {department: [agent ids]}; gates: gates.Gates or None; check: job -> bool (the simulated finish check) or None;
        path: file where the department toggles are kept across restarts; real: ids of agents whose jobs are done by a model (see above)."""
        self.cfg, self.members, self.t0, self.now, self.n = cfg, members, now, now, 0
        self.gates, self.check, self.path, self.newly_blocked = gates, check, path, []
        self.real, self.pending, self.last = frozenset(real), [], None          # pending: finished jobs whose check has not answered yet; last: the agent that started a job last
        self.max_attempts = gates.cfg["attempts"] if gates else 3
        self.depts = list(cfg["departments"])
        self.share = {d: cfg["budget"] * w["share"] / 100 for d, w in cfg["departments"].items()}      # tokens per usage window
        self.spent, self.win = dict.fromkeys(self.depts, 0.0), 0
        self.enabled = dict.fromkeys(self.depts, True)
        try:
            with open(path, encoding="utf-8") as f:
                self.enabled.update({d: v for d, v in json.load(f).items() if d in self.enabled and isinstance(v, bool)})
        except (OSError, ValueError, AttributeError, TypeError):           # no file, or a damaged one: all on
            pass
        self.loaded = OrderedDict()                       # agent -> "warm" | "working", least recently used first; an agent not in it is asleep
        self.queue = {d: [] for d in self.depts}
        self.running = []

    def state(self, aid):
        return self.loaded.get(aid, "asleep")

    def add(self, dept, title, est, dur, user=False, actual=None):
        """Queue a task: est = estimated tokens, actual = tokens it really uses (default est), dur = seconds of work."""
        if dept not in self.queue or min(est, dur, actual or est) <= 0:
            raise ScheduleError("unknown department or non-positive size")
        if est > self.share[dept]:
            raise ScheduleError("estimate %g is more than the whole %s share (%g tokens): it could never be admitted" % (est, dept, self.share[dept]))
        self.n += 1
        actual = actual or est
        j = {"id": "task-%03d" % self.n, "n": self.n, "dept": dept, "title": title, "est": est, "dur": dur, "rate": actual / dur, "user": user,
             "t": 0.0, "spent": 0.0, "agent": None, "deadline": None, "paused": None, "flagged": False, "checkpoint": None, "end": None,
             "hold": None, "over": None, "over_key": None, "gate": None, "tries": 0, "blocked": False, "dropped": False}
        self.queue[dept].append(j)
        return j

    def set_enabled(self, d):
        """d = {"dept": name, "enabled": true|false}, the body of POST /api/schedule."""
        if not isinstance(d, dict) or set(d) != {"dept", "enabled"} or not isinstance(d["dept"], str) or d["dept"] not in self.enabled or not isinstance(d["enabled"], bool):
            raise ScheduleError('body must be {"dept": <department>, "enabled": true|false}')
        self.enabled[d["dept"]] = d["enabled"]
        if self.path:
            save_json(self.path, self.enabled)

    def add_user(self, d):
        """d = {"dept", "title", "tokens"}, the body of POST /api/task: a task the user adds (ranks ahead of planned ones). Raises ScheduleError on bad input."""
        if not isinstance(d, dict) or set(d) != {"dept", "title", "tokens"} or not isinstance(d["dept"], str) or d["dept"] not in self.queue:
            raise ScheduleError('body must be {"dept": <department>, "title": <text>, "tokens": <number>}')
        title, tok, share = d["title"].strip() if isinstance(d["title"], str) else "", d["tokens"], self.share[d["dept"]]
        if not 1 <= len(title) <= MAX_TITLE or not title.isprintable():
            raise ScheduleError("title must be 1 to %d printable characters" % MAX_TITLE)
        if isinstance(tok, bool) or not isinstance(tok, int) or not MIN_TOKENS <= tok <= share:
            raise ScheduleError("tokens must be a whole number from %d up to the %s share (%d)" % (MIN_TOKENS, d["dept"], share))
        if len(self.queue[d["dept"]]) >= MAX_QUEUE:
            raise ScheduleError("the %s queue is full" % d["dept"])
        return self.add(d["dept"], title, tok, USER_TASK_S, user=True)

    def gate(self, j, kind, summary, cost):
        """Hold job j until the user decides a new request of this kind; returns the request."""
        r = self.gates.raise_(kind, j["dept"], j["id"], summary, cost, self.now)
        j["hold"] = r["id"]
        if kind in ONE_SHOT:
            j["gate"] = (kind, summary, cost)               # a retry raises it again
        return r

    def decide(self, rid, approve):
        """The user's answer to a request (POST /api/approve, /api/deny)."""
        r = self.gates.decide(rid, approve, self.now)
        self._resolve(r, approve)
        return r

    def _resolve(self, r, ok):
        """Apply a decision. Approved: the job proceeds (an approved overrun may run past the close or the budget). Denied: a gated job is dropped; an overrun job stays
        paused until its next window."""
        j = next((j for q in self.queue.values() for j in q if j["hold"] == r["id"]), None)
        if not j:
            return
        j["hold"] = None
        if ok:
            j["over"] = r["kind"] if r["kind"] in OVERRUN else None
            j["over_key"] = self._key()
        elif r["kind"] not in OVERRUN:
            self.queue[j["dept"]].remove(j)
            j["dropped"] = True

    def _key(self):
        """(usage window, day) of the simulated clock: an overrun approval is valid only inside the one it was granted in."""
        return int((self.now - self.t0) // self.cfg["window_s"]), self.now // DAY

    def is_open(self, dept, now):
        w = self.cfg["departments"][dept]
        return w["start"] * 60 <= now % DAY < w["end"] * 60

    def step(self, now):
        prev, self.now = self.now, now
        if self.gates:
            for r, ok in self.gates.expire(now):             # no answer by the deadline: denied, or (overrun only) continued from the overtime fund
                self._resolve(r, ok)
        w = int((now - self.t0) // self.cfg["window_s"])
        if w != self.win:
            self.win, self.spent = w, dict.fromkeys(self.depts, 0.0)           # a new usage window: budgets are fresh, paused jobs wait in their queues
        for j in self.running + [j for q in self.queue.values() for j in q]:
            if j["over"] and j["over_key"] != self._key():
                j["over"] = None                              # a stale overrun approval: rollover ends it
        budget, total = self.cfg["budget"], sum(self.spent.values())
        for j in list(self.running):
            dt = min(max(0, min(now, j["deadline"]) - prev), j["dur"] - j["t"])
            tok = min(j["rate"] * dt, budget - total, self.share[j["dept"]] - self.spent[j["dept"]])      # never past the total nor past its department's share...
            if j["over"] == "overrun_usage":
                tok = j["rate"] * dt                              # ...unless the user approved running past it
            if tok < j["rate"] * dt:
                dt = tok / j["rate"]
            j["t"] += dt
            j["spent"] += tok
            if j["over"] != "overrun_usage":
                self.spent[j["dept"]] += tok
                total += tok
            if j["t"] >= j["dur"] - 1e-6:
                self._finish(j, now)
            elif now >= j["deadline"]:
                self._pause(j, "window_cap", True)
        for j in list(self.running):
            if j["over"] == "overrun_usage":
                continue
            if total >= budget - 1e-6:
                self._pause(j, "hard_stop", False)
            elif self.spent[j["dept"]] >= self.share[j["dept"]] - 1e-6:
                self._pause(j, "share_limit", False)           # its department's share is gone: checkpoint, resume next usage window
        self._start(now)

    def _finish(self, j, now):
        """Done working: run the finish check. A failure retries from the start; the last allowed attempt blocks the job for good (reported up by the sim)."""
        self._release(j)
        j["end"] = now
        ok = True if self.check is None else self.check(j)
        if ok is None:
            self.pending.append(j)
        else:
            self.resolve(j, ok)

    def resolve(self, j, ok):
        """The finish check's answer for job j (at once, or later for a check that answered None)."""
        if j in self.pending:
            self.pending.remove(j)
        if ok:
            return
        now = self.now
        j["tries"] += 1
        if j["tries"] >= self.max_attempts:
            j["blocked"] = True
            self.newly_blocked.append(j)
            if self.gates:
                self.gates.block(j, now)
            return
        j["end"], j["t"], j["spent"], j["checkpoint"], j["over"] = None, 0.0, 0.0, None, None
        self.queue[j["dept"]].append(j)
        if j["gate"]:
            self.gate(j, *j["gate"])

    def _release(self, j):
        self.running.remove(j)
        self.loaded[j["agent"]] = "warm"
        self.loaded.move_to_end(j["agent"])

    def _pause(self, j, reason, flagged):
        self._release(j)
        j["paused"], j["flagged"], j["over"] = reason, flagged, None
        j["checkpoint"] = {"at": self.now, "agent": j["agent"], "done_s": j["t"], "spent": j["spent"]}      # enough to resume: progress is kept on the job
        self.queue[j["dept"]].append(j)
        if self.gates:
            timed = reason == "window_cap"
            self.gate(j, "overrun_time" if timed else "overrun_usage", "%s: keep going past the %s" % (j["title"], "close of its window" if timed else "usage limit"),
                      max(0.01, round(max(0, j["est"] * WORST_CASE - j["spent"]) / 1000 * USD_PER_1K_TOKENS, 2)))

    def _free(self, dept):
        """Tokens a new job in dept can still claim: (its department's share, the total), each minus what is spent and what running jobs are estimated to still need."""
        need = lambda js: sum(max(0, j["est"] - j["spent"]) for j in js)       # noqa: E731
        return (self.share[dept] - self.spent[dept] - need(j for j in self.running if j["dept"] == dept),
                self.cfg["budget"] - sum(self.spent.values()) - need(self.running))

    def _agent_for(self, dept):
        """A warm agent of the department (most recently used first), else a sleeping one if it can be loaded; None if all are working or nothing can be evicted."""
        mine = self.members.get(dept, ())
        for a in reversed(self.loaded):
            if a in mine and self.loaded[a] == "warm":
                return a
        asleep = [a for a in mine if a not in self.loaded]
        if asleep and (len(self.loaded) < self.cfg["max_loaded"] or "warm" in self.loaded.values()):
            return asleep[0]
        return None

    def _pick(self, dept, now):
        """The first queued job (paused, then user, then planned) that fits, with its agent; None if the window is closed, the toggle is off, or nothing fits."""
        if not self.enabled[dept]:
            return None
        ok = self.is_open(dept, now), self.cfg["budget"] - sum(self.spent.values()) > 1e-6 and self.share[dept] - self.spent[dept] > 1e-6      # (window open, budget left)
        agent = self._agent_for(dept)
        if agent in self.real and any(j["agent"] in self.real for j in self.running + self.pending):
            return None                                       # one real job at a time (its model call may still be in flight)
        free = min(self._free(dept))
        for j in sorted(self.queue[dept], key=lambda j: (not j["checkpoint"], not j["user"], j["n"])):
            o = j["over"]            # an approved overrun may go past the close (time) or past the budget (usage)
            if agent and not j["hold"] and (ok[0] or o) and (o == "overrun_usage" or (ok[1] and max(0, j["est"] - j["spent"]) <= free)):
                return j, agent
        return None

    def _start(self, now):
        while len(self.running) < self.cfg["max_working"]:
            got = [(d, *p) for d in sorted(self.depts, key=lambda d: self.spent[d] / self.share[d]) if (p := self._pick(d, now))]     # the lead-level allocator: furthest below its share first
            if not got:
                return
            if self.real:         # priority first (paused, then the user's), then the agent that ran last, then the allocator's order (the sort is stable)
                got.sort(key=lambda g: (not g[1]["checkpoint"], not g[1]["user"], g[2] != self.last))
            _, j, agent = got[0]
            self.queue[j["dept"]].remove(j)
            if agent not in self.loaded and len(self.loaded) >= self.cfg["max_loaded"]:
                del self.loaded[next(a for a, s in self.loaded.items() if s == "warm")]       # LRU warm agent goes to sleep
            self.loaded[agent] = "working"
            self.loaded.move_to_end(agent)
            self.last = agent
            w = self.cfg["departments"][j["dept"]]
            j["agent"], j["paused"], j["flagged"] = agent, None, False
            j["deadline"] = (now if j["over"] else now - now % DAY + w["end"] * 60) + GRACE * (w["end"] - w["start"]) * 60
            self.running.append(j)

    def snapshot(self):
        cfg, now = self.cfg, self.now
        deps = [{"dept": d, "start": hhmm(w["start"]), "end": hhmm(w["end"]), "open": self.is_open(d, now), "enabled": self.enabled[d], "share": round(self.share[d]), "used": round(self.spent[d]),
                 "queue": len(self.queue[d]), "working": sum(1 for j in self.running if j["dept"] == d)} for d, w in cfg["departments"].items()]
        held = [{"id": j["id"], "dept": d, "title": j["title"], "reason": j["paused"], "flagged": j["flagged"], "done": round(100 * j["t"] / j["dur"])}
                for d in self.depts for j in self.queue[d] if j["paused"]]
        states = [self.state(a) for dept in self.members.values() for a in dept]
        return {"clock": hhmm(now % DAY // 60), "max_working": cfg["max_working"], "max_loaded": cfg["max_loaded"], "departments": deps, "held": held,
                "usage": {"budget": cfg["budget"], "used": round(sum(self.spent.values())), "left_s": round(self.t0 + (self.win + 1) * cfg["window_s"] - now)},
                "counts": {s: states.count(s) for s in ("asleep", "warm", "working")}, "gates": self.gates.snapshot(now) if self.gates else None}
