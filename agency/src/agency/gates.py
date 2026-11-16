"""Human approval gates, enforced by code (never by an agent's judgment).

Kinds: spend, outbound (public/outbound action), irreversible, rules (instruction files, limits, schedules, incentives) and the two overruns
(overrun_time, overrun_usage: the scheduler's close/usage-limit pauses). A gated job waits (`hold`) until the user approves its request. Only the user
decides (token-gated POST /api/approve, /api/deny). No answer by the deadline = denied, except an overrun, which continues on its own only if the overtime
fund holds its estimated cost AND that cost is within the per-job cap (then the fund is debited and the decision logged). Both default to $0, so by default
nothing auto-continues. spend/outbound/irreversible/rules are never auto-approved. Time is passed in (simulated seconds). The $20 emergency reserve
(ledger.py) is not touched here: only the overtime fund is ever debited.
"""
import json
import logging
import math
import os
import secrets
import tempfile
from collections import deque

KINDS = ("spend", "outbound", "irreversible", "rules", "overrun_time", "overrun_usage")
OVERRUN = ("overrun_time", "overrun_usage")
USD_PER_1K_TOKENS = 0.01            # simulated price used to estimate an overrun's cost
WORST_CASE = 1.7                    # real usage can be this many times a job's estimate (the sim's upper bound); overrun costs are estimated from it
REQ_KEYS = {"id", "kind", "dept", "job", "summary", "cost", "created", "deadline"}
log = logging.getLogger(__name__)


class GateError(ValueError):
    status = 400


class NotFound(GateError):
    status = 404


class Decided(GateError):
    status = 409


def save_json(path, obj):
    """Atomic write, the way the goal is saved."""
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


class Gates:
    def __init__(self, cfg, path=None):
        """cfg: config.load_gates(...) -> {fund, cap, attempts, deadline_s}; path: file where the fund balance, the log, the pending requests and the per-job auto-spend
        are kept across restarts (a missing or damaged file: the config values, said in the log)."""
        self.cfg, self.fund, self.path = cfg, cfg["fund"], path
        self.pending, self.log, self.blocked, self.auto = {}, deque(maxlen=50), deque(maxlen=20), {}      # auto: job -> overtime-fund dollars auto-spent on it
        if path:
            self._load()

    def _load(self):
        num = lambda x: isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and x >= 0      # noqa: E731
        try:
            with open(self.path, encoding="utf-8") as f:
                s = json.load(f)
            ok = (isinstance(s, dict) and num(s["fund"]) and num(s["base"]) and isinstance(s["log"], list) and all(isinstance(e, dict) for e in s["log"])
                  and isinstance(s["auto"], dict) and all(num(v) for v in s["auto"].values()) and isinstance(s["pending"], dict)
                  and all(isinstance(r, dict) and set(r) == REQ_KEYS and r["kind"] in KINDS and isinstance(r["id"], str) and num(r["cost"]) and num(r["created"]) and num(r["deadline"])
                          for r in s["pending"].values()))
            if not ok:
                raise ValueError("unexpected content")
        except FileNotFoundError:
            return
        except (OSError, ValueError, KeyError, TypeError) as e:
            log.warning("gate state %s unreadable (%s): starting from the config (fund $%s, no pending requests)", self.path, e, self.cfg["fund"])
            return
        if s["base"] == self.cfg["fund"]:                  # the configured fund was changed: start from the new value
            self.fund = s["fund"]
        self.pending, self.auto = s["pending"], s["auto"]
        self.log.extend(s["log"][-50:])

    def _save(self):
        if self.path:
            save_json(self.path, {"fund": self.fund, "base": self.cfg["fund"], "pending": self.pending, "log": list(self.log), "auto": self.auto})

    def raise_(self, kind, dept, job, summary, cost, now):
        if kind not in KINDS:
            raise GateError("unknown gate kind")
        r = {"id": "req-" + secrets.token_hex(4), "kind": kind, "dept": dept, "job": job, "summary": summary, "cost": round(cost, 2), "created": now, "deadline": now + self.cfg["deadline_s"]}
        self.pending[r["id"]] = r
        self._save()
        return r

    def _close(self, r, outcome, now):
        self.pending.pop(r["id"], None)
        self.log.append({"id": r["id"], "kind": r["kind"], "dept": r["dept"], "job": r["job"], "cost": r["cost"], "outcome": outcome, "at": now})
        self._save()

    def decide(self, rid, approve, now):
        """The user's answer -> the request. Unknown id: NotFound (404); already decided or expired: Decided (409)."""
        r = self.pending.get(rid) if isinstance(rid, str) else None
        if not r:
            if any(e["id"] == rid for e in self.log):
                raise Decided("request %s is already decided" % rid)
            raise NotFound("no such request")
        self._close(r, "approved" if approve else "denied", now)
        return r

    def expire(self, now):
        """Requests past their deadline -> [(request, approved)]. Overruns continue only if fund >= cost and the job's total auto-spend stays within the per-job cap (debited, logged); else denied."""
        out = []
        for r in sorted((r for r in self.pending.values() if now >= r["deadline"]), key=lambda r: r["created"]):
            auto = r["kind"] in OVERRUN and self.fund >= r["cost"] and self.auto.get(r["job"], 0) + r["cost"] <= self.cfg["cap"]
            if auto:
                self.fund = round(self.fund - r["cost"], 2)
                self.auto[r["job"]] = round(self.auto.get(r["job"], 0) + r["cost"], 2)
            self._close(r, "auto" if auto else "expired", now)
            out.append((r, auto))
        return out

    def block(self, j, now):
        """A job that failed its last attempt: an informational item in the user's queue (the sim reports it up the chain lead > boss)."""
        self.blocked.append({"job": j["id"], "dept": j["dept"], "title": j["title"], "attempts": j["tries"], "at": now})

    def snapshot(self, now):
        return {"pending": [{**r, "left_s": max(0, round(r["deadline"] - now))} for r in self.pending.values()], "blocked": list(self.blocked), "fund": self.fund,
                "cap": self.cfg["cap"], "log": list(self.log)[-10:]}
