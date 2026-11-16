"""Returns (v0.4, simulated): what each department Lead reports up as the value of its work, the reinvestment ledger and the runway gates.

A `returns` handoff is one JSON object in the Content section of the usual handoff envelope; there is one active per department Lead per period
(a still-open period is superseded as it grows). The rules enforced here, not by judgment:
- Paper money (finance-trading) is never added to real money; indices (output, knowledge, quality) are never added to dollars or to each other (`totals`).
- Agency net = sum of REAL-money returns - fixed cost - variable costs, worked out by `ledger.profit`: the ONE profit formula the goal dial uses. The returns
  are cut from the ledger's own daily entries (`compute`), so their real revenue adds up to the ledger's revenue and net is the dial's profit.
- The reinvestment ledger is append-only; the $20 emergency reserve is never debited."""
import json
import math
import os
import random
import re
from datetime import date, datetime, timedelta

from . import ledger as led
from .gates import USD_PER_1K_TOKENS, save_json

VALUE_KINDS = ("money", "output", "knowledge", "quality")
DEPTS = {"finance-trading": ("money", "USD"), "marketing": ("money", "USD"), "operations": ("money", "USD"), "implementation": ("output", "changes"), "research": ("knowledge", "index")}
PAPER = ("finance-trading",)
SHARE = {"marketing": 35, "operations": 65}             # percent of the ledger's real revenue each department is credited with
SPLIT = {"operations": 40, "implementation": 20, "research": 15, "marketing": 15, "finance-trading": 10}      # share of the $80 working capital
ALLOC = {d: round(led.WORKING_CAPITAL * w / 100, 2) for d, w in SPLIT.items()}                                # 32 / 16 / 12 / 12 / 8
START = date(2026, 9, 1)                                # the simulated agency's first day
PAPER_BASE = 1000.0                                     # notional paper account (percentages are of it)
KEYS = ("dept", "period", "value_kind", "headline", "delta_pct", "confidence", "evidence", "cost", "efficiency", "notes", "extras")
PERIOD_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{4}-\d{2}-\d{2}$")
HID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*-\d{3,6}$")
NOTES = {"finance-trading": "PAPER trading: simulated, not real money", "marketing": "simulated attributed revenue", "operations": "simulated order revenue",
         "implementation": "simulated merged changes", "research": "simulated usefulness index"}
GATES = (("G0", "Setup running"), ("G1", "First verified $1"), ("G2", "$100 recouped"), ("G3", "$520 cumulative profit"), ("G4", "$200+ net a month, two months running"))
MONTH_NET = 200.0


class ReturnsError(ValueError):
    pass


class ReinvestError(ValueError):
    pass


def num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def is_paper(r):
    return r["extras"].get("paper") is True or r["dept"] in PAPER


def validate(text, dept, job):
    """Strict check of the Content of a `returns` handoff sent by the Lead of `dept` (job must be returns-<dept>-<period>). Returns the dict or raises ReturnsError."""
    try:
        r = json.loads(text)
    except (ValueError, RecursionError):
        raise ReturnsError("Content must be one JSON object") from None
    if not isinstance(r, dict) or set(r) != set(KEYS):
        raise ReturnsError("returns must have exactly the keys: %s" % ", ".join(KEYS))
    if r["dept"] != dept:
        raise ReturnsError("dept must be the sender's department (%s)" % dept)
    if not isinstance(r["period"], str) or not PERIOD_RE.match(r["period"]) or job != "returns-%s-%s" % (dept, r["period"]):
        raise ReturnsError("period must look like 2026-11-01-2026-11-30 and the job must be returns-<dept>-<period>")
    if r["value_kind"] not in VALUE_KINDS:
        raise ReturnsError("value_kind must be one of %s" % ", ".join(VALUE_KINDS))
    h = r["headline"]
    if not isinstance(h, dict) or set(h) != {"value", "unit"} or not num(h["value"]) or not isinstance(h["unit"], str) or not 1 <= len(h["unit"]) <= 24:
        raise ReturnsError("headline must be {value: number, unit: text}")
    if (h["unit"] == "USD") != (r["value_kind"] == "money"):
        raise ReturnsError("dollars (unit USD) are for value_kind money only; an index never carries dollars")
    if r["delta_pct"] is not None and not num(r["delta_pct"]):
        raise ReturnsError("delta_pct must be a number or null")
    if not num(r["confidence"]) or not 0 <= r["confidence"] <= 1:
        raise ReturnsError("confidence must be a number from 0 to 1")
    ev = r["evidence"]
    if not isinstance(ev, list) or len(ev) > 20 or any(not isinstance(i, str) or not HID_RE.match(i) for i in ev):
        raise ReturnsError("evidence must be a list of handoff ids")
    if r["value_kind"] == "money" and h["value"] != 0 and not ev:
        raise ReturnsError("a money claim needs evidence: at least one handoff id")
    c = r["cost"]
    if not isinstance(c, dict) or set(c) != {"usd", "tokens"} or not num(c["usd"]) or c["usd"] < 0 or isinstance(c["tokens"], bool) or not isinstance(c["tokens"], int) or c["tokens"] < 0:
        raise ReturnsError("cost must be {usd: number >= 0, tokens: whole number >= 0}")
    want = round(h["value"] / c["usd"], 4) if c["usd"] > 0 else None
    if (r["efficiency"] is None) != (want is None) or (want is not None and (not num(r["efficiency"]) or abs(r["efficiency"] - want) > 1e-4)):
        raise ReturnsError("efficiency must be the return divided by the cost (null when the cost is 0)")
    if not isinstance(r["notes"], str) or len(r["notes"]) > 200:
        raise ReturnsError("notes must be text of at most 200 characters")
    x = r["extras"]
    if not isinstance(x, dict) or len(x) > 12 or any(not isinstance(k, str) or not (v is None or isinstance(v, (str, bool)) or num(v)) for k, v in x.items()):
        raise ReturnsError("extras must be a map of names to numbers or text")
    if r["value_kind"] == "money" and dept in PAPER and x.get("paper") is not True:
        raise ReturnsError("%s money is paper money and must say so (extras.paper = true)" % dept)
    return r


def totals(rets):
    """-> {real_usd, paper_usd, indices: {dept: {value, unit}}}: real dollars, paper dollars and each index are separate figures and are never added to each other."""
    real = paper = 0.0
    idx = {}
    for r in rets:
        v = r["headline"]["value"]
        if r["value_kind"] != "money":
            idx[r["dept"]] = {"value": v, "unit": r["headline"]["unit"]}
        elif is_paper(r):
            paper += v
        else:
            real += v
    return {"real_usd": real, "paper_usd": paper, "indices": idx}


def agency_net(rets, variable, fixed):
    """Real-money returns - fixed - variable, by the ledger's own formula."""
    return led.profit({"revenue": totals(rets)["real_usd"], "variable": variable}, fixed)


def compute(entries, days, seed, start, paper=None):
    """The period's figures per department, cut from the ledger's daily entries [(kind, amount, paper)]: real revenue is split between marketing and operations in whole
    cents so the two add up to the ledger's revenue exactly; paper trades make the finance P&L. Deterministic per (seed, start).
    paper: a paper.Paper snapshot (test mode): its P&L replaces the simulated paper figures; still PAPER, still never in the agency net."""
    t = led.totals(entries)
    r = random.Random("%s:%s:returns" % (seed, start))
    rev_c = round(t["revenue"] * 100)
    mk_c = round(rev_c * SHARE["marketing"] / 100)
    mk, op = mk_c / 100, (rev_c - mk_c) / 100
    cum = peak = dd = 0.0
    pnl = [a for _, a, paper in entries if paper]
    for a in pnl:
        cum += a
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    spend = round(t["marketing"], 2)
    f = {"finance-trading": {"value": round(t["paper_pnl"], 2), "cash": 0.0, "lo": .45, "hi": .7,
                             "extras": {"paper": True, "return_pct": round(t["paper_pnl"] / PAPER_BASE * 100, 2), "max_drawdown_pct": round(dd / PAPER_BASE * 100, 2),
                                        "win_rate_pct": round(100 * sum(a > 0 for a in pnl) / len(pnl)) if pnl else 0}},
         "marketing": {"value": mk, "cash": t["marketing"], "lo": .6, "hi": .9,
                       "extras": {"spend": spend, "roi_pct": round((mk - spend) / spend * 100, 1) if spend else None, "conversions": round(mk / 6)}},
         "operations": {"value": op, "cash": t["fees"], "lo": .7, "hi": .95,
                        "extras": {"margin_pct": round((op - t["fees"]) / op * 100, 1) if op else None, "orders": round(op / 7.5)}},
         "implementation": {"value": round(days * r.uniform(.4, 1)), "cash": 0.0, "lo": .7, "hi": .95,
                            "extras": {"ci_pass_rate_pct": round(r.uniform(88, 99), 1), "cycle_time_h": round(r.uniform(3, 20), 1)}},
         "research": {"value": round(r.uniform(55, 92)), "cash": 0.0, "lo": .6, "hi": .9, "extras": {"claims_verified_pct": round(r.uniform(70, 98))}}}
    if paper:
        f["finance-trading"].update(value=paper["pnl"], extras={"paper": True, "return_pct": paper["pnl_pct"], "max_drawdown_pct": paper["dd_pct"], "win_rate_pct": paper["win_rate_pct"]})
    for d, x in f.items():
        x["tokens"] = round(days * r.randint(8000, 25000))
        x["confidence"] = round(r.uniform(x.pop("lo"), x.pop("hi")), 2)
        x["notes"] = NOTES[d]
    if paper:
        f["finance-trading"]["notes"] = "PAPER, real prices: PLACEHOLDER moving-average rule, not a strategy"
    return f


def make(dept, period, fig, evidence, prev):
    """One returns object. prev = this department's value in the previous period (None for the first)."""
    kind, unit = DEPTS[dept]
    v = round(fig["value"], 2)
    usd = round(fig["tokens"] / 1000 * USD_PER_1K_TOKENS + fig["cash"], 2)         # nominal token price plus the department's cash costs
    return {"dept": dept, "period": period, "value_kind": kind, "headline": {"value": v, "unit": unit}, "delta_pct": round((v - prev) / abs(prev) * 100, 1) if prev else None,
            "confidence": fig["confidence"], "evidence": list(evidence), "cost": {"usd": usd, "tokens": fig["tokens"]}, "efficiency": round(v / usd, 4) if usd > 0 else None,
            "notes": fig["notes"], "extras": fig["extras"]}


def months(today):
    """Calendar months (first, last) from START up to the one holding today."""
    out, d = [], START
    while d <= today:
        first, last = led.bounds({"period": "month"}, d)
        out.append((first, last))
        d = last + timedelta(days=1)
    return out


class Reinvest:
    """Append-only reinvestment ledger: [{date, source, amount, spend, balance, evidence}] in one JSON file (written to a temp file, then renamed). It starts at $100:
    $80 working capital split by department (ALLOC) plus the $20 reserve, which no spend may touch. The only writer is `append`; nothing edits or removes an entry."""
    KEYS = {"date", "source", "amount", "spend", "balance", "evidence"}

    def __init__(self, path):
        self.path = path
        if not os.path.exists(path):
            self.entries = []
            self.append(START.isoformat(), "start capital", amount=led.START_CAPITAL)
            return
        try:
            with open(path, encoding="utf-8") as f:
                e = json.load(f)
            if not self.sound(e):
                raise ValueError("bad entries")
        except (OSError, ValueError, RecursionError):
            bad = path + ".bad"
            if os.path.exists(bad):
                bad += "." + datetime.now().strftime("%Y%m%d%H%M%S")
            os.replace(path, bad)
            raise ReinvestError("the reinvestment ledger %s is corrupt: it was set aside as %s; inspect that file (the money history is in it), then restore or remove it" % (path, bad)) from None
        self.entries = e

    @classmethod
    def sound(cls, e):
        """Every entry has exactly the keys, finite numbers, text, and each balance is the previous one + amount - spend to the cent."""
        if not isinstance(e, list) or not e:
            return False
        prev = 0.0
        for x in e:
            if not isinstance(x, dict) or set(x) != cls.KEYS or not isinstance(x["date"], str) or not isinstance(x["source"], str) or not isinstance(x["evidence"], list) \
                    or any(not isinstance(i, str) for i in x["evidence"]) or not all(num(x[k]) for k in ("amount", "spend", "balance")) \
                    or round(prev + x["amount"] - x["spend"], 2) != round(x["balance"], 2):
                return False
            prev = x["balance"]
        return True

    def append(self, day, source, amount=0.0, spend=0.0, evidence=()):
        """Add one entry: a credit (amount) or a spend ('spend:<department>', within that department's allocation and never into the reserve). Returns it."""
        if not num(amount) or not num(spend) or amount < 0 or spend < 0 or (amount and spend):
            raise ReinvestError("an entry is one credit or one spend, never negative")
        bal = (self.entries[-1]["balance"] if self.entries else 0.0) + amount - spend
        if spend:
            dept = source[6:] if source.startswith("spend:") else None
            if dept not in ALLOC or spend > ALLOC[dept] - self.spent(dept) + 1e-9:
                raise ReinvestError("a spend must be 'spend:<department>' and within that department's allocation")
            if bal < led.RESERVE - 1e-9:
                raise ReinvestError("the $%d emergency reserve is never debited" % led.RESERVE)
        e = {"date": day, "source": source, "amount": round(amount, 2), "spend": round(spend, 2), "balance": round(bal, 2), "evidence": list(evidence)}
        self.entries = self.entries + [e]
        save_json(self.path, self.entries)
        return e

    def spent(self, dept):
        return sum(e["spend"] for e in self.entries if e["source"] == "spend:" + dept)

    def credit(self, period, net, day, evidence):
        """Reinvest a finished period's profit once (a repeat for the same period changes nothing)."""
        if net > 0 and not any(e["source"] == "profit:" + period for e in self.entries):
            self.append(day, "profit:" + period, amount=net, evidence=evidence)

    def snapshot(self):
        bal = self.entries[-1]["balance"]
        return {"balance": bal, "reserve": led.RESERVE, "working": round(bal - led.RESERVE, 2), "start": led.START_CAPITAL,
                "reinvested": round(sum(e["amount"] for e in self.entries if e["source"].startswith("profit:")), 2),
                "departments": [{"dept": d, "allocated": a, "spent": round(self.spent(d), 2), "left": round(a - self.spent(d), 2)} for d, a in ALLOC.items()],
                "entries": self.entries[::-1][:8]}


def runway(running, verified, cum, nets):
    """The gates, in order: G0 setup running, G1 first verified $1 (real revenue with evidence), G2 $100 recouped and G3 $520 (cumulative profit), G4 net >= $200 for two
    consecutive months. nets = finished months' net, oldest first. -> {gates: [{id, label, done, progress}], current, progress, text}; current is the first gate not passed."""
    cum = round(cum, 2)                                 # a gate is met at exactly $100 or $520 in cents, not on float dust
    trail = 0
    for n in reversed(nets):
        if n < MONTH_NET:
            break
        trail += 1
    prog = (1.0 if running else 0.0, verified / 1, cum / 100, cum / 520, 1.0 if any(a >= MONTH_NET and b >= MONTH_NET for a, b in zip(nets, nets[1:], strict=False)) else trail / 2)
    prog = tuple(max(0.0, min(1.0, p)) for p in prog)
    text = ("the simulation is not running yet", "$%.2f of $1 verified revenue" % verified, "$%.2f of $100 cumulative profit" % cum, "$%.2f of $520 cumulative profit" % cum,
            "%d of 2 months at $%d+ net" % (min(trail, 2), MONTH_NET))
    gates = [{"id": i, "label": lb, "done": p >= 1, "progress": round(p, 4)} for (i, lb), p in zip(GATES, prog, strict=True)]
    cur = next((k for k, g in enumerate(gates) if not g["done"]), None)
    return {"gates": gates, "current": None if cur is None else gates[cur]["id"], "progress": 1.0 if cur is None else gates[cur]["progress"], "text": "all gates passed" if cur is None else text[cur]}


def _publish(sim, ledger, start, end, today, last):
    """Write (or supersede) the period's returns, one per department Lead. -> (label, {dept: (handoff id, returns)}), or None for the dict while no report exists yet."""
    label = "%s-%s" % (start.isoformat(), end.isoformat())
    upto = min(end, today)
    days = max(1, (upto - start).days + 1)
    old = sim.returns.get(label)
    paper = sim.paper.snapshot() if sim.paper and end >= today else None           # test mode: the period still running gets the real paper P&L
    psig = paper and (paper["pnl"], paper["pnl_pct"], paper["dd_pct"], paper["win_rate_pct"])
    if old and old["days"] == days and old.get("psig") == psig:
        return label, old["by_dept"]
    anyev = [i for q in sim.rep_ids.values() for i in q]
    if not anyev:
        return label, None
    figs, by = compute(ledger.entries(start, upto), days, ledger.seed, start, paper), {}
    for dept in DEPTS:
        lead = sim.org.leads.get(dept)
        if not lead:
            continue
        prev = last.get(dept)
        if prev and end > today and DEPTS[dept][0] != "knowledge":
            prev *= days / 30                           # an open period is compared with last period's pace so far; an index is not a count, it is not scaled
        r = make(dept, label, figs[dept], list(sim.rep_ids.get(dept, ())) or anyev[-3:], prev)
        up = sim.org.agents[sim.org.agents[lead].reports_to]
        name = sim.hs.write_handoff(lead, "%s.%s" % (up.dept, up.role), "returns", "returns-%s-%s" % (dept, label), "returns: %s %s" % (dept, label),
                                    ["%s: %s %s (%s), confidence %.2f" % (dept, r["headline"]["value"], r["headline"]["unit"], "paper" if is_paper(r) else "simulated", r["confidence"])],
                                    "Returns of %s for %s." % (dept, label), json.dumps(r), "none", supersedes=old["by_dept"][dept][0] if old else None, token_estimate=400)
        by[dept] = ("-".join(name[:-3].split("__")[3:]), json.loads(sim.hs.read(lead, name).sections["Content"]))        # read back: what the file says is what we show
    sim.returns[label] = {"days": days, "by_dept": by, "psig": psig}
    return label, by


def _status(sim, j):
    if j["dropped"] or j["blocked"] or j["end"] is not None:
        return "dropped" if j["dropped"] else "blocked" if j["blocked"] else "done"
    return "working" if any(j is x for x in sim.sched.running) else "awaiting approval" if j["hold"] else "paused" if j["paused"] else "queued"


def _jobs(sim, goal_rets):
    """The job table, newest first: tokens and cost are the job's own; the return attributed is the department's period headline shared out by tokens among its finished jobs."""
    done = {}
    for j in sim.jobs:
        if _status(sim, j) == "done":
            done[j["dept"]] = done.get(j["dept"], 0.0) + j["spent"]
    rows = []
    for j in sorted(sim.jobs, key=lambda j: -j["n"])[:25]:
        st, got = _status(sim, j), None
        if st == "done" and j["dept"] in goal_rets and done[j["dept"]] > 0:
            r = goal_rets[j["dept"]][1]
            got = {"value": round(r["headline"]["value"] * j["spent"] / done[j["dept"]], 2), "unit": r["headline"]["unit"], "paper": is_paper(r)}
        rows.append({"id": j["id"], "dept": j["dept"], "owner": j["agent"], "status": st, "tokens": round(j["spent"]), "cost": round(j["spent"] / 1000 * USD_PER_1K_TOKENS, 2), "attributed": got,
                     "audit": "pass" if st == "done" else "fail" if st == "blocked" else "retry %d" % j["tries"] if j["tries"] else "-" if st == "dropped" else "pending"})
    return rows


def business(ledger, reinvest, sim):
    """Everything the Business tab shows. Agency net is `agency_net` over the goal period's real returns, with the ledger's fixed and variable costs: the dial's own profit."""
    today = ledger.today()                              # read once: every figure below is for the same day
    gs, ge = led.bounds(ledger.goal, today)
    gt = led.totals(ledger.entries(gs, min(ge, today)))
    gfx = led.fixed_cost(ledger.goal, (ge - gs).days + 1)
    gfixed, gvar = led.r2(gfx), led.r2(gt["variable"])
    mp = months(today)
    pubs, last, rets = [], {}, {}
    for s, e in mp + ([(gs, ge)] if (gs, ge) not in mp else []):
        label, by = _publish(sim, ledger, s, e, today, last)
        if by is None:
            return {"simulated": True, "ready": False}
        rets[label] = by
        if (s, e) in mp:
            pubs.append((s, e, label))
            last = {d: v[1]["headline"]["value"] for d, v in by.items()}
    goal = rets["%s-%s" % (gs.isoformat(), ge.isoformat())]
    nets, ver, cum = [], 0.0, 0.0
    for s, e, label in pubs:
        rs = [r for _, r in rets[label].values()]
        net = agency_net(rs, led.totals(ledger.entries(s, min(e, today)))["variable"], led.fixed_cost({"period": "month"}, 30))
        cum += net
        ver += totals(rs)["real_usd"]
        if e < today:
            nets.append(net)
            reinvest.credit(label, net, e.isoformat(), [rets[label][d][0] for d in SHARE if d in rets[label]])
    gr = [r for _, r in goal.values()]                  # the sparkline series below holds finished months only: the partial one would read as a drop
    t = totals(gr)
    return {"simulated": True, "ready": True, "period": {"start": gs.isoformat(), "end": ge.isoformat()},
            "departments": [{**{k: goal[d][1][k] for k in KEYS if k not in ("period",)}, "paper": is_paper(goal[d][1]), "handoff": goal[d][0],
                             "series": [rets[lb][d][1]["headline"]["value"] for _, e, lb in pubs if e < today and d in rets[lb]]} for d in DEPTS if d in goal],
            "net": {"revenue": led.r2(t["real_usd"]), "fixed": gfixed, "variable": gvar, "paper_pnl": led.r2(t["paper_usd"]),
                    "net": led.r2(agency_net(gr, gvar, gfixed)), "dial_profit": led.r2(led.profit(gt, gfx))},
            "runway": runway(sim.tick > 0, ver, cum, nets), "capital": reinvest.snapshot(), "jobs": _jobs(sim, goal)}
