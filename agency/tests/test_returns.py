import json
from datetime import date

import pytest

from agency import returns
from agency.handoff import HandoffError
from agency.returns import Reinvest, ReinvestError, ReturnsError

from test_server import TOKEN, app  # noqa: F401  (fixture)

PERIOD = "2026-11-01-2026-11-30"


def good(dept="marketing", **kw):
    fig = {"value": 40.0, "cash": 2.0, "tokens": 100000, "confidence": 0.8, "notes": "n", "extras": {"paper": True} if dept == "finance-trading" else {"roi_pct": 5}}
    r = returns.make(dept, PERIOD, fig, ["job-001-001"], 30.0)
    r.update(kw)
    return r


def check(r, dept=None):
    return returns.validate(json.dumps(r), dept or r["dept"], "returns-%s-%s" % (dept or r["dept"], PERIOD))


def test_valid_returns_for_every_department():
    for d in returns.DEPTS:
        assert check(good(d))["dept"] == d


@pytest.mark.parametrize("change", [
    {"value_kind": "gossip"}, {"confidence": 1.2}, {"confidence": -0.1}, {"confidence": True}, {"evidence": []}, {"evidence": ["nonsense"]}, {"efficiency": 99.0},
    {"cost": {"usd": -1, "tokens": 5}}, {"dept": "research"}, {"period": "2026-11"}, {"extra": 1}, {"delta_pct": "x"}])
def test_validation_rejects(change):
    with pytest.raises(ReturnsError):
        check(good(**change), "marketing")


def test_money_needs_evidence_but_zero_does_not():
    r = good(evidence=[])
    with pytest.raises(ReturnsError, match="evidence"):
        check(r)
    r["headline"]["value"], r["efficiency"] = 0, 0.0
    assert check(r)


def test_dollars_belong_to_money_and_paper_must_say_so():
    r = good("research")
    r["headline"]["unit"] = "USD"
    with pytest.raises(ReturnsError, match="dollars"):
        check(r)                                              # value_kind knowledge with unit USD
    r = good("finance-trading")
    del r["extras"]["paper"]
    with pytest.raises(ReturnsError, match="paper"):
        check(r)


def test_paper_is_never_added_to_real_money():
    real, paper = good("marketing"), good("finance-trading")
    paper["headline"]["value"] = 1000.0
    t = returns.totals([real, paper])
    assert t["real_usd"] == real["headline"]["value"] and t["paper_usd"] == 1000.0
    assert returns.agency_net([real, paper], 0.0, 0.0) == real["headline"]["value"]
    disguised = good("marketing")
    disguised["extras"]["paper"] = True                      # any paper flag keeps it out too
    assert returns.totals([disguised])["real_usd"] == 0.0


def test_indices_are_never_summed_with_dollars():
    r, i, o = good("marketing"), good("research"), good("implementation")
    i["value_kind"], i["headline"] = "knowledge", {"value": 90, "unit": "index"}
    o["value_kind"], o["headline"] = "output", {"value": 12, "unit": "changes"}
    t = returns.totals([r, i, o])
    assert t["real_usd"] == r["headline"]["value"] and t["paper_usd"] == 0.0
    assert t["indices"] == {"research": {"value": 90, "unit": "index"}, "implementation": {"value": 12, "unit": "changes"}}
    assert returns.agency_net([r, i, o], 1.0, 2.0) == r["headline"]["value"] - 3.0


def test_returns_handoff_rules(app):  # noqa: F811
    sim, hs = app.sim, app.sim.hs
    returns.business(app.ledger, app.reinvest, sim)
    assert any(a.endswith("-001") for q in sim.returns.values() for _, (a, _r) in q["by_dept"].items())
    lead = sim.org.leads["marketing"]
    job = "returns-marketing-" + next(iter(sim.returns))
    args = dict(frm=lead, to="command.general", kind="returns", job=job, title="t", summary="s", context="c", content=json.dumps(good()), needed="none")
    with pytest.raises(HandoffError, match="one per Lead"):
        hs.write_handoff(**args)                              # already published for this period
    other = next(a for a in sim.org.agents.values() if a.dept == "marketing" and a.id != lead)
    with pytest.raises(HandoffError):
        hs.write_handoff(**{**args, "frm": other.id, "job": "returns-marketing-" + PERIOD})          # a worker may not
    with pytest.raises(HandoffError):
        hs.write_handoff(**{**args, "job": "returns-marketing-" + PERIOD, "content": json.dumps(good(confidence=7))})


def dial(app):  # noqa: F811
    return app.ledger.snapshot()["profit"], returns.business(app.ledger, app.reinvest, app.sim)


def test_agency_net_is_the_dials_profit(app):  # noqa: F811
    for goal in ({"amount": 520, "period": "month"}, {"amount": 100, "period": "custom", "start": "2026-10-20", "end": "2026-11-20"}):
        app.ledger.set_goal(goal)
        profit, b = dial(app)
        assert b["net"]["net"] == b["net"]["dial_profit"] == profit
        assert b["net"]["paper_pnl"] == app.ledger.snapshot()["paper_pnl"]
        real = sum(d["headline"]["value"] for d in b["departments"] if d["value_kind"] == "money" and not d["paper"])
        assert real == pytest.approx(b["net"]["revenue"], abs=0.005) and b["net"]["revenue"] == app.ledger.snapshot()["revenue"]


def test_business_endpoint_keeps_kinds_apart(app):  # noqa: F811
    s, _, body = app.route("GET", "/api/business")
    b = json.loads(body)
    assert s == 200 and b["ready"] and [d["dept"] for d in b["departments"]] == list(returns.DEPTS)
    kinds = {d["dept"]: (d["value_kind"], d["headline"]["unit"], d["paper"]) for d in b["departments"]}
    assert kinds["finance-trading"] == ("money", "USD", True) and kinds["research"] == ("knowledge", "index", False) and kinds["marketing"][2] is False
    assert all((d["headline"]["unit"] == "USD") == (d["value_kind"] == "money") for d in b["departments"])
    assert [j["id"] for j in b["jobs"]] == sorted((j["id"] for j in b["jobs"]), reverse=True)


def test_reinvest_start_allocation_and_persistence(tmp_path):
    p = str(tmp_path / "d" / "reinvest.json")
    r = Reinvest(p)
    assert sum(returns.ALLOC.values()) == 80.0 and returns.ALLOC == {"operations": 32.0, "implementation": 16.0, "research": 12.0, "marketing": 12.0, "finance-trading": 8.0}
    assert len(r.entries) == 1 and r.entries[0]["balance"] == 100.0 and r.snapshot()["reserve"] == 20.0
    r.credit("p1", 50.0, "2026-10-31", ["job-001-001"])
    r.credit("p1", 50.0, "2026-10-31", ["job-001-001"])                  # same period again: nothing
    r.credit("p0", -5.0, "2026-09-30", [])                               # a loss is not reinvested
    first = list(r.entries)
    r2 = Reinvest(p)
    assert r2.entries == first and len(first) == 2 and first[-1]["balance"] == 150.0 and set(first[-1]) == Reinvest.KEYS
    with open(p) as f:
        assert json.load(f) == first
    r2.append("2026-11-02", "spend:research", spend=5.0)
    assert Reinvest(p).entries[:2] == first and Reinvest(p).entries[2]["balance"] == 145.0     # earlier entries untouched


@pytest.mark.parametrize("mut", [lambda t: t[:20], lambda t: t.replace('"balance": 100.0', '"balance": "100"'), lambda t: t.replace('"balance": 100.0', '"balance": 99.0'), lambda t: "[]"])
def test_corrupt_reinvest_is_set_aside_not_replaced(tmp_path, mut):
    p = tmp_path / "reinvest.json"
    Reinvest(str(p))
    text = mut(p.read_text())
    p.write_text(text)
    with pytest.raises(ReinvestError, match="reinvest.json.bad"):
        Reinvest(str(p))
    assert not p.exists() and (tmp_path / "reinvest.json.bad").read_text() == text          # nothing overwritten
    Reinvest(str(p))                                                                           # missing file: a fresh start
    p.write_text(text)
    with pytest.raises(ReinvestError):
        Reinvest(str(p))
    assert (tmp_path / "reinvest.json.bad").read_text() == text and len(list(tmp_path.glob("reinvest.json.bad.*"))) == 1    # earlier .bad kept


def test_gates_use_whole_cents():
    g = returns.runway(True, 1.0, 99.999999999, [])["gates"]           # float dust just under $100 is $100.00
    assert g[2]["done"] and not returns.runway(True, 1.0, 99.99, [])["gates"][2]["done"]
    assert returns.runway(True, 1.0, 519.999999999, [])["gates"][3]["done"]


def test_reinvest_never_touches_the_reserve_or_overspends(tmp_path):
    r = Reinvest(str(tmp_path / "r.json"))
    for bad in ({"source": "spend:nowhere", "spend": 1.0}, {"source": "gift", "spend": 1.0}, {"source": "spend:research", "spend": 12.01}, {"source": "spend:research", "spend": -1.0},
                {"source": "spend:research", "spend": 1.0, "amount": 1.0}):
        with pytest.raises(ReinvestError):
            r.append("2026-11-02", **bad)
    for d, a in returns.ALLOC.items():
        r.append("2026-11-02", "spend:" + d, spend=a)                      # every department spends its whole allocation
    assert r.entries[-1]["balance"] == 20.0                               # only the reserve is left
    with pytest.raises(ReinvestError):
        r.append("2026-11-03", "spend:research", spend=0.01)
    r2 = Reinvest(str(tmp_path / "r2.json"))                              # even with money in, the reserve is out of reach
    r2.credit("p", 10.0, "2026-10-31", [])
    r2.append("2026-11-02", "spend:operations", spend=32.0)
    assert r2.snapshot()["balance"] == 78.0 and min(e["balance"] for e in r2.entries) >= 20.0
    assert not any("reserve" in e["source"] for e in r2.entries)


def test_runway_gates():
    def at(running=True, verified=0.0, cum=0.0, nets=()):
        return returns.runway(running, verified, cum, list(nets))
    g0 = at(running=False)
    assert g0["current"] == "G0" and not g0["gates"][0]["done"]
    g1 = at()
    assert g1["current"] == "G1" and g1["gates"][0]["done"] and g1["progress"] == 0.0
    assert at(verified=0.5)["progress"] == 0.5
    g2 = at(verified=1.0)
    assert g2["current"] == "G2" and g2["gates"][1]["done"]
    assert at(verified=1, cum=40)["progress"] == 0.4
    assert at(verified=1, cum=100)["current"] == "G3"
    g3 = at(verified=1, cum=260)
    assert g3["current"] == "G3" and g3["progress"] == 0.5
    g4 = at(verified=1, cum=520, nets=[150, 250])
    assert g4["current"] == "G4" and g4["progress"] == 0.5 and g4["gates"][3]["done"]
    assert at(verified=1, cum=520, nets=[250, 199])["progress"] == 0.0           # the streak is broken
    done = at(verified=1, cum=900, nets=[210, 200])
    assert done["current"] is None and all(g["done"] for g in done["gates"]) and done["progress"] == 1.0
    assert at(verified=1, cum=900, nets=[300, 100, 250])["current"] == "G4"      # not consecutive


def test_months_run_from_the_start_to_today():
    m = returns.months(date(2026, 11, 11))
    assert m[0] == (date(2026, 9, 1), date(2026, 9, 30)) and m[-1] == (date(2026, 11, 1), date(2026, 11, 30)) and len(m) == 3
