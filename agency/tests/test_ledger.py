import json
from datetime import date

import pytest

from agency import ledger
from agency.__main__ import build
from agency.ledger import GoalError, Ledger

from test_server import TOKEN, app, call, live  # noqa: F401  (fixtures)


def test_profit_counts_only_after_costs_and_never_paper():
    t = ledger.totals([("revenue", 100.0, False), ("marketing", 10.0, False), ("fees", 3.0, False), ("trading_loss", 7.0, False), ("paper_trade", 500.0, True)])
    assert t["variable"] == 20.0 and t["paper_pnl"] == 500.0 and t["revenue"] == 100.0
    assert ledger.profit(t, 70.0) == 10.0                                  # 100 - 70 fixed - 20 variable; the paper 500 is not in it
    assert ledger.profit(ledger.totals([]), 70.0) == -70.0


def test_pace_projection():
    t = {"revenue": 100.0, "variable": 20.0}
    assert ledger.pace(t, 70.0, 10, 30) == pytest.approx(80 / 10 * 30 - 70)       # 170
    assert ledger.pace(t, 70.0, 30, 30) == pytest.approx(10.0)                    # period over: equals the actual profit
    assert ledger.pace(t, 70.0, 0, 30) is None


def test_bands():
    assert [ledger.band(s) for s in (-1, 0.24, 0.25, 0.74, 0.75, 0.99, 1.0, 2.0)] == ["red", "red", "amber", "amber", "green", "green", "gold", "gold"]


def test_goal_validation():
    assert ledger.validate({"amount": 520, "period": "month"}) == {"amount": 520.0, "period": "month"}
    assert ledger.validate({"amount": 99.999, "period": "custom", "start": "2026-11-01", "end": "2026-11-15"})["end"] == "2026-11-15"
    bad = [None, [], {}, {"period": "month"}, {"amount": 0, "period": "month"}, {"amount": -5, "period": "month"}, {"amount": 1e9, "period": "month"}, {"amount": "5", "period": "month"},
           {"amount": True, "period": "month"}, {"amount": float("nan"), "period": "month"},
           {"amount": 10 ** 400, "period": "month"}, {"amount": float("inf"), "period": "month"}, {"amount": 50, "period": "week"}, {"amount": 50, "period": "month", "start": "2026-11-01"},
           {"amount": 50, "period": "custom"}, {"amount": 50, "period": "custom", "start": "2026-11-10", "end": "2026-11-01"}, {"amount": 50, "period": "custom", "start": "x", "end": "y"},
           {"amount": 50, "period": "custom", "start": "2026-01-01", "end": "2027-12-31"}, {"amount": 50, "period": "month", "extra": 1}]
    for b in bad:
        with pytest.raises(GoalError):
            ledger.validate(b)


def test_goal_persists_and_damaged_file_falls_back(tmp_path):
    p = str(tmp_path / "d" / "goal.json")
    assert Ledger(p).goal == ledger.DEFAULT_GOAL                           # default $520 a month
    Ledger(p).set_goal({"amount": 300, "period": "month"})
    assert Ledger(p).goal["amount"] == 300.0
    with pytest.raises(GoalError):
        Ledger(p).set_goal({"amount": -1, "period": "month"})
    assert Ledger(p).goal["amount"] == 300.0                               # a rejected write changes nothing
    open(p, "w").write("{not json")
    assert Ledger(p).goal == ledger.DEFAULT_GOAL


def test_snapshot(tmp_path):
    lg = Ledger(str(tmp_path / "goal.json"), seed=1, today=lambda: date(2026, 11, 10))
    s = lg.snapshot()
    assert s["period"] == {"start": "2026-11-01", "end": "2026-11-30", "days": 30, "elapsed": 10, "days_left": 21} and s["fixed"] == 70.0
    assert s["profit"] == pytest.approx(s["revenue"] - 70 - s["variable"]["variable"], abs=0.02)
    assert s["share"] == pytest.approx(s["profit"] / 520, abs=1e-3) and s["band"] == ledger.band(s["share"])
    assert lg.snapshot() == s                                              # deterministic: same day, same numbers
    lg.set_goal({"amount": 100, "period": "custom", "start": "2026-11-01", "end": "2026-11-15"})
    s = lg.snapshot()
    assert s["period"]["days"] == 15 and s["fixed"] == 35.0 and s["period"]["days_left"] == 6


def test_snapshot_edges(tmp_path):
    p = str(tmp_path / "goal.json")
    s = Ledger(p, today=lambda: date(2026, 11, 30)).snapshot()                         # final day still running
    assert s["period"]["days_left"] == 1 and s["period"]["elapsed"] == 30
    s = Ledger(p, today=lambda: date(2026, 11, 1)).snapshot()
    assert s["period"]["days_left"] == 30
    lg = Ledger(p, today=lambda: date(2026, 11, 1))
    lg.set_goal({"amount": 100, "period": "custom", "start": "2026-11-05", "end": "2026-11-09"})
    s = lg.snapshot()                                                                  # period not started: elapsed 0, no pace, no crash
    assert s["period"]["elapsed"] == 0 and s["period"]["days_left"] == 5 and s["pace"] is None
    lg.today = lambda: date(2026, 11, 20)                                              # period over
    assert lg.snapshot()["period"]["days_left"] == 0


def test_december_rolls_into_january(tmp_path):
    lg = Ledger(str(tmp_path / "goal.json"), today=lambda: date(2026, 12, 15))
    assert ledger.bounds(lg.goal, date(2026, 12, 15)) == (date(2026, 12, 1), date(2026, 12, 31))
    s = lg.snapshot()
    assert s["period"]["days"] == 31 and s["period"]["days_left"] == 17
    lg.today = lambda: date(2027, 1, 1)
    assert lg.snapshot()["period"] == {"start": "2027-01-01", "end": "2027-01-31", "days": 31, "elapsed": 1, "days_left": 31}


def test_huge_amount_is_a_400(live, app):  # noqa: F811
    body = ('{"amount": %s, "period": "month"}' % ("9" * 400)).encode()
    assert call(live, "POST", "/api/goal", body, {"Content-Type": "application/json", "Cookie": "ag=" + TOKEN})[0] == 400


def test_goal_write_needs_the_token(live, app):  # noqa: F811
    body = json.dumps({"amount": 250, "period": "month"})
    h = {"Content-Type": "application/json"}
    assert call(live, "POST", "/api/goal", body, h)[0] == 401                                       # no key
    assert call(live, "POST", "/api/goal", body, {**h, "Cookie": "ag=wrong"})[0] == 401
    assert call(live, "POST", "/api/goal", body, {**h, "Cookie": "ag=" + TOKEN, "Origin": "http://evil.example.com"})[0] == 403
    assert app.ledger.goal["amount"] == 520.0                                                        # nothing changed so far
    s, _, b = call(live, "POST", "/api/goal", body, {**h, "Cookie": "ag=" + TOKEN})
    assert s == 200 and json.loads(b)["goal"]["amount"] == 250.0 and app.ledger.goal["amount"] == 250.0
    assert call(live, "POST", "/api/goal", b"{}", {**h, "Cookie": "ag=" + TOKEN})[0] == 400
    assert call(live, "POST", "/api/goal", b"nope", {**h, "Cookie": "ag=" + TOKEN})[0] == 400
    assert json.loads(app.route("GET", "/api/org")[2])["ledger"]["goal"]["amount"] == 250.0


def test_goal_write_refused_without_auth(project, tmp_path):
    open_app = build(project, str(tmp_path / "data"), seed=1, token=None)
    assert open_app.route("POST", "/api/goal", b'{"amount": 250, "period": "month"}')[0] == 403
    assert open_app.ledger.goal["amount"] == 520.0
