"""Simulated profit ledger and the user-set profit goal (shown as the dial on the dashboard).

Profit = revenue - fixed cost - variable costs (marketing, platform/listing fees, trading losses). The fixed cost ($70/month: two Claude Pro
subscriptions $40 + Grok $30) is charged in full for the period. Paper-trading results are kept apart and never counted as profit. The entries are fake but
deterministic (seeded per day); a real ledger would replace `Ledger.entries`. The goal is one small JSON file in the data dir; only the
token-gated POST /api/goal changes it.
"""
import json
import os
import random
import tempfile
from datetime import date, timedelta

START_CAPITAL = 100.0
RESERVE = 20.0                  # emergency reserve: shown apart, never spent automatically
WORKING_CAPITAL = START_CAPITAL - RESERVE
FIXED_MONTHLY = 70.0
DEFAULT_GOAL = {"amount": 520.0, "period": "month"}
MIN_AMOUNT, MAX_AMOUNT, MAX_DAYS = 1.0, 100000.0, 366
BANDS = ((0.25, "red"), (0.75, "amber"), (1.0, "green"))        # share of the goal reached; at or over the goal: "gold"


class GoalError(ValueError):
    pass


def _date(v, what):
    try:
        if isinstance(v, str) and len(v) == 10:
            return date.fromisoformat(v)
    except ValueError:
        pass
    raise GoalError("%s must be a date like 2026-12-31" % what)


def validate(d):
    """-> a clean goal dict {amount, period, [start, end]} or raises GoalError."""
    if not isinstance(d, dict):
        raise GoalError("goal must be an object")
    amount, period = d.get("amount"), d.get("period")
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not MIN_AMOUNT <= amount <= MAX_AMOUNT:
        raise GoalError("amount must be a number from %d to %d dollars" % (MIN_AMOUNT, MAX_AMOUNT))
    if period not in ("month", "custom") or set(d) - {"amount", "period", "start", "end"}:
        raise GoalError("period must be 'month' or 'custom' (with start and end dates)")
    g = {"amount": round(float(amount), 2), "period": period}
    if period == "custom":
        s, e = _date(d.get("start"), "start"), _date(d.get("end"), "end")
        if e < s or (e - s).days + 1 > MAX_DAYS:
            raise GoalError("end must be on or after start, within %d days" % MAX_DAYS)
        g["start"], g["end"] = s.isoformat(), e.isoformat()
    elif "start" in d or "end" in d:
        raise GoalError("start and end are only for a custom period")
    return g


def bounds(goal, today):
    """The goal's period as (first day, last day), both inclusive."""
    if goal["period"] == "custom":
        return date.fromisoformat(goal["start"]), date.fromisoformat(goal["end"])
    first = today.replace(day=1)
    return first, (first + timedelta(days=32)).replace(day=1) - timedelta(days=1)


def fixed_cost(goal, days):
    """$70 for a calendar month; a custom period pays pro rata ($70 per 30 days)."""
    return FIXED_MONTHLY if goal["period"] == "month" else round(FIXED_MONTHLY * days / 30, 2)


def totals(entries):
    """entries: [(kind, amount, paper)] with kind in revenue|marketing|fees|trading_loss -> money sums. Paper entries go to paper_pnl only."""
    t = {"revenue": 0.0, "marketing": 0.0, "fees": 0.0, "trading_loss": 0.0, "paper_pnl": 0.0}
    for kind, amount, paper in entries:
        t["paper_pnl" if paper else kind] += amount
    t["variable"] = t["marketing"] + t["fees"] + t["trading_loss"]
    return t


def profit(t, fixed):
    return t["revenue"] - fixed - t["variable"]


def pace(t, fixed, elapsed, total):
    """Projected profit at the end of the period: revenue and variable costs continue at the pace so far, the fixed cost is already charged. None before day 1."""
    if elapsed <= 0:
        return None
    return (t["revenue"] - t["variable"]) / elapsed * total - fixed


def r2(v):
    return None if v is None else round(v, 2)


def band(share):
    for limit, name in BANDS:
        if share < limit:
            return name
    return "gold"


class Ledger:
    def __init__(self, path, seed=1, today=date.today):
        self.path, self.seed, self.today = path, seed, today
        try:
            with open(path, encoding="utf-8") as f:
                self.goal = validate(json.load(f))
        except (OSError, ValueError):                       # missing or damaged file: back to the default
            self.goal = dict(DEFAULT_GOAL)

    def set_goal(self, d):
        goal = validate(d)
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(self.path)))
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(goal, f)
        os.replace(tmp, self.path)
        self.goal = goal
        return goal

    def entries(self, start, end):
        """Simulated money movements for each day from start to end: [(kind, amount, paper)]. Same day, same numbers."""
        out, d = [], start
        while d <= end:
            r = random.Random("%s:%s" % (self.seed, d.isoformat()))
            rev = round(r.uniform(2, 16), 2)
            out += [("revenue", rev, False), ("marketing", round(r.uniform(0, 2), 2), False), ("fees", round(rev * 0.03, 2), False),
                    ("paper_trade", round(r.uniform(-3, 3), 2), True)]
            d += timedelta(days=1)
        return out

    def snapshot(self):
        today, g = self.today(), self.goal
        start, end = bounds(g, today)
        total = (end - start).days + 1
        elapsed = max(0, min(total, (today - start).days + 1))
        t = totals(self.entries(start, min(end, today)))
        fixed = fixed_cost(g, total)
        net = profit(t, fixed)
        return {"simulated": True, "capital": START_CAPITAL, "working_capital": WORKING_CAPITAL, "reserve": RESERVE,
                "goal": g, "period": {"start": start.isoformat(), "end": end.isoformat(), "days": total, "elapsed": elapsed,
                              "days_left": max(0, (end - max(today, start)).days + 1)},
                "revenue": r2(t["revenue"]), "fixed": r2(fixed), "variable": {k: r2(t[k]) for k in ("marketing", "fees", "trading_loss", "variable")}, "paper_pnl": r2(t["paper_pnl"]),
                "profit": r2(net), "share": round(net / g["amount"], 4), "pace": r2(pace(t, fixed, elapsed, total)), "band": band(net / g["amount"])}
