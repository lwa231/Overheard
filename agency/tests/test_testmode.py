"""Test mode: real agents (fake model), paper trading (fixture prices, injected time), owner review. Nothing here touches the network except loopback stubs."""
import glob
import http.server
import json
import logging
import os
import random
import socket
import threading
import time
import types

import pytest

from agency import config, net, server
from agency.__main__ import build
from agency.config import ConfigError
from agency.paper import EVERY_S, Paper
from agency.real import KEEP, Real

from test_scheduler import make
from test_server import ROOT, TOKEN, call

REAL = ["boss", "fin-lead", "ops-lead"]
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "coinbase_btc_spot.json")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Tests use fakes: the only real sockets are loopback stubs started below, which go through net._opener(direct=True) only when a test asks."""
    real_open = net._opener

    def guard(direct):
        if not direct:
            raise AssertionError("a test tried to reach the internet")
        return real_open(direct)
    monkeypatch.setattr(net, "_opener", guard)


class Model:
    def __init__(self, reply="Listing draft\n## a heading in the reply\nthree bullets", fail=None):
        self.reply, self.fail, self.prompts = reply, fail, []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        if self.fail:
            raise self.fail
        return self.reply


def start(project, tmp_path, real=REAL, model=None, token=TOKEN, warmup=0, **tm):
    path = os.path.join(project, "config", "agency.json")
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["test_mode"].update(real_agents=real, **tm)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f)
    return build(project, str(tmp_path / "data"), seed=1, token=token, warmup=warmup, model=model or Model(), fetch=lambda s: 100.0)


def run_until(app, cond, limit=3000, settle=True):
    """Tick until cond. settle: after each tick wait for the worker thread, so a run is the same every time (not for a model that blocks)."""
    for _ in range(limit):
        if cond():
            return
        app.tick()
        if settle:
            app.sim.worker.join()
    raise AssertionError("not reached in %d ticks" % limit)


def outputs(app):
    return os.path.join(app.sim.data_dir, "outputs")


def post(app, path, body):
    return app.route("POST", path, json.dumps(body).encode() if not isinstance(body, bytes) else body)


def reply(r):
    return r[0], json.loads(r[2])


# ---- flag off: behaviour as before
def test_flag_off_nothing_real_runs(project, tmp_path):
    m = Model(fail=AssertionError("the model must not be called"))
    app = build(project, str(tmp_path / "d"), seed=1, token=TOKEN, warmup=300, model=m, fetch=lambda s: 1 / 0)
    assert app.sim.real is None and app.sim.paper is None and not m.prompts
    assert not os.path.exists(os.path.join(str(tmp_path / "d"), "outputs")) and not os.path.exists(os.path.join(str(tmp_path / "d"), "paper.json"))
    assert reply(app.route("GET", "/api/business"))[1].get("test") is None
    assert reply(post(app, "/api/review", {"id": "x", "decision": "accept"}))[0] == 404
    assert app.route("GET", "/api/output?id=x")[0] == 404


# ---- real agents
def test_real_job_stores_handoff_and_file(project, tmp_path):
    m = Model()
    app = start(project, tmp_path, model=m)
    run_until(app, lambda: any(i["agent"] != "boss" for i in app.sim.real.items))
    i = next(i for i in app.sim.real.items if i["agent"] != "boss")
    a = app.store.org.agents[i["agent"]]
    assert i["agent"] in ("fin-lead", "ops-lead") and i["file"] == "%s/%s.md" % (a.dept, i["job"]) and i["decision"] is None
    text = open(os.path.join(outputs(app), i["file"]), encoding="utf-8").read()
    assert "three bullets" in text and "## a heading in the reply" in text
    name = next(n for n, v in app.sim.hs.idx.items() if v["frm"] == a.id and v["id"].startswith(i["job"] + "-"))   # the report handoff, written through the one envelope
    assert "__report__" in name and app.sim.hs.read(a.id, name).sections["Content"].splitlines()[1] == " ## a heading in the reply"
    p = next(p for p in m.prompts if "You are %s (%s)" % (a.title, a.id) in p)
    assert a.body[:30] in p and "no tools" in p                         # role file + task text
    assert "Owner feedback" not in p


def test_ops_lead_gets_orders_and_listings_and_boss_works_too(project, tmp_path):
    m = Model()
    app = start(project, tmp_path, model=m)
    run_until(app, lambda: {"boss", "ops-lead", "fin-lead"} <= {i["agent"] for i in app.sim.real.items}, 6000)
    ops = [p for p in m.prompts if "Operations Lead" in p]
    assert any("order ord-" in p and "cust-" in p for p in ops) or any("product listing" in p for p in ops)
    assert any("PAPER portfolio" in p for p in m.prompts if "Finance Lead" in p)
    b = next(i for i in app.sim.real.items if i["agent"] == "boss")
    assert b["dept"] == "command" and os.path.exists(os.path.join(outputs(app), "command", b["job"] + ".md"))


@pytest.mark.parametrize("err", [net.ModelError("down"), TimeoutError("slow"), RuntimeError("anything")])
def test_model_unreachable_three_attempts_then_blocked_no_crash(project, tmp_path, err):
    m = Model(fail=err)
    app = start(project, tmp_path, model=m)
    own = lambda j: j["agent"] in ("fin-lead", "ops-lead")                  # noqa: E731
    run_until(app, lambda: any(j["blocked"] and own(j) for j in app.sim.jobs), 6000)
    j = next(j for j in app.sim.jobs if j["blocked"] and own(j))
    assert j["tries"] == 3 and app.sim.real.items == [] and app.sim.real.error
    assert any(b["job"] == j["id"] and b["attempts"] == 3 for b in app.sim.gates.blocked)
    assert reply(app.route("GET", "/api/business"))[0] == 200 and app.sim.real.snapshot()["error"]


def test_output_path_cannot_escape(tmp_path):
    r = Real(config.load_test_mode({"real_agents": ["x"]}, "t"), Model(), str(tmp_path / "data"), lambda: 1.0)
    mk = lambda dept: types.SimpleNamespace(id="x", title="X", body="b", dept=dept)         # noqa: E731
    for dept, job in (("../evil", "task-001"), ("ok", "../../evil"), ("ok", "a/b"), ("ok", "TASK"), ("ok", ""), ("a/b", "task-001"), ("..", "task-001"), ("ok", "a.b")):
        with pytest.raises(ValueError):
            r.save(mk(dept), job, "t", "text")
    assert not glob.glob(str(tmp_path / "**" / "*.md"), recursive=True) and r.items == []
    a, b = r.save(mk("ok"), "task-001", "t", "one"), r.save(mk("ok"), "task-001", "t", "two")           # a restarted simulation reuses ids: no overwrite
    assert a["file"] == "ok/task-001.md" and b["file"] == "ok/task-001-r2.md" and r.read(b["id"]).endswith("two\n")
    for rid in ("../../etc/passwd", "ok/task-001", None, 5):
        with pytest.raises(Exception, match="no such output"):
            r.read(rid)


def test_tampered_review_file_is_set_aside(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    bad = [{"id": "a.b", "dept": "a", "job": "b", "agent": "x", "title": "t", "file": "../../x.md", "preview": [], "created": 1, "decision": None, "note": "", "decided": None}]
    (d / "reviews.json").write_text(json.dumps(bad))
    r = Real(config.load_test_mode({"real_agents": ["x"]}, "t"), Model(), str(d), lambda: 1.0)
    assert r.items == [] and (d / "reviews.json.bad").exists()


# ---- network
def stub(handler):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_model_client_against_a_local_server():
    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path == "/redir":
                self.send_response(302)
                self.send_header("Location", "http://example.com/")
                self.end_headers()
                return
            out = json.dumps({"response": "hi " + body["model"]} if body["stream"] is False else {}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)
    srv = stub(H)
    try:
        url = "http://127.0.0.1:%d" % srv.server_address[1]
        assert net.ask_model("p", url + "/api/generate", "m1", 5) == "hi m1"
        with pytest.raises(net.ModelError):
            net.ask_model("p", url + "/redir", "m1", 5)                                  # redirects are not followed
    finally:
        srv.shutdown()


def test_model_client_unreachable_and_not_loopback():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    with pytest.raises(net.ModelError):
        net.ask_model("p", "http://127.0.0.1:%d/api/generate" % port, "m", 1)
    for url in ("http://example.com/api/generate", "https://127.0.0.1/api/generate", "http://127.0.0.1.evil.com/x", "file:///etc/passwd"):
        with pytest.raises(net.ModelError):
            net.ask_model("p", url, "m", 1)


def test_fetcher_refuses_hosts_off_the_allow_list():
    with pytest.raises(net.NetError, match="allow-list"):
        net.fetch_price("BTC-USD", ("example.com",))                                   # coinbase is not on this list: refused before any request (no_network would fail the test otherwise)
    with pytest.raises(net.NetError, match="allow-list"):
        net._get("https://evil.example/x", ("api.coinbase.com",), 1)
    with pytest.raises(net.NetError, match="allow-list"):
        net._get("https://api.coinbase.com.evil.example/x", ("api.coinbase.com",), 1)
    with pytest.raises(net.PriceError):
        net.fetch_price("../../x", ("api.coinbase.com",))


def test_only_net_py_opens_connections():
    src = os.path.join(ROOT, "src", "agency")
    for f in glob.glob(os.path.join(src, "*.py")):
        if os.path.basename(f) != "net.py":
            text = open(f, encoding="utf-8").read()
            assert not any(w in text for w in ("urllib.request", "http.client", "urlopen", "create_connection", "smtplib", "ftplib", "subprocess", "import requests")), f


def test_config_rules():
    for bad in ({"model_url": "http://example.com:11434/api/generate"}, {"model_url": "https://127.0.0.1/x"}, {"model_url": "http://127.0.0.1:99999/x"}, {"nope": 1},
                {"real_agents": ["../x"]}, {"price_hosts": ["a b"]}, {"model_timeout_s": 0}, {"paper_assets": ["SPY"]}, {"model": ""}):
        with pytest.raises(ConfigError):
            config.load_test_mode(bad, "t")
    assert config.load_test_mode(None, "t")["real_agents"] == []


def test_unknown_real_agent_refuses_to_start(project, tmp_path):
    with pytest.raises(ConfigError, match="no such agent"):
        start(project, tmp_path, real=["nobody"])


# ---- prices
def test_recorded_price_fixture_parses():
    assert net.parse_spot(open(FIXTURE, "rb").read(), "BTC-USD") == 73654.275


@pytest.mark.parametrize("body", [b"", b"nope", b"[]", b"{}", b'{"data": 5}', b'{"data": {"amount": 73000, "base": "BTC", "currency": "USD"}}',
                                  b'{"data": {"amount": "abc", "base": "BTC", "currency": "USD"}}', b'{"data": {"amount": "NaN", "base": "BTC", "currency": "USD"}}',
                                  b'{"data": {"amount": "Infinity", "base": "BTC", "currency": "USD"}}', b'{"data": {"amount": "-5", "base": "BTC", "currency": "USD"}}',
                                  b'{"data": {"amount": "0", "base": "BTC", "currency": "USD"}}', b'{"data": {"amount": "1e99", "base": "BTC", "currency": "USD"}}',
                                  b'{"data": {"amount": "5", "base": "ETH", "currency": "USD"}}', b'{"data": {"amount": "5", "base": "BTC", "currency": "EUR"}}',
                                  b'{"data": {"base": "BTC", "currency": "USD"}}'])
def test_malformed_price_data_rejected(body):
    with pytest.raises(net.PriceError):
        net.parse_spot(body, "BTC-USD")


# ---- paper portfolio
def paper(tmp_path, fetch=lambda s: 100.0, t=None):
    t = t if t is not None else [0.0]
    return Paper(str(tmp_path / "paper.json"), ["BTC-USD"], fetch, lambda: t[0], 8.0), t


def feed(p, prices):
    for k, x in enumerate(prices):
        p.price("BTC-USD", x, float(k))


def test_paper_buy_and_pnl_maths(tmp_path):
    p, _ = paper(tmp_path)
    feed(p, [100.0] * 9)
    assert p.snapshot()["positions"] == [] and p.s["cash"] == 8.0                          # flat: no cross, no trade
    feed(p, [110.0])
    s = p.snapshot()
    assert [t["side"] for t in s["trades"]] == ["buy"] and s["cash"] == 0.0 and s["positions"][0]["qty"] == pytest.approx(8 / 110)
    feed(p, [121.0])
    s = p.snapshot()
    assert s["equity"] == pytest.approx(8.8) and s["pnl"] == pytest.approx(0.8) and s["pnl_pct"] == pytest.approx(10.0) and s["start"] == 8.0
    feed(p, [60.0, 50.0, 40.0, 30.0])                                                     # a fall crosses the averages down: sell everything
    s = p.snapshot()
    assert [t["side"] for t in s["trades"]] == ["buy", "sell"] and s["positions"] == [] and s["closed"] == 1
    sell = s["trades"][-1]
    assert p.s["cash"] == pytest.approx(8 / 110 * sell["price"]) and s["pnl"] == pytest.approx(p.s["cash"] - 8, abs=1e-4) and s["win_rate_pct"] == (100 if p.s["cash"] > 8 else 0)
    assert s["dd_pct"] > 0


def test_paper_cash_never_negative_and_books_balance(tmp_path):
    for seed in range(20):
        p, _ = paper(tmp_path)
        r, x = random.Random(seed), 100.0
        for k in range(300):
            x = max(0.01, x * (1 + r.uniform(-.08, .08)))
            p.price("BTC-USD", x, float(k))
            assert p.s["cash"] >= 0 and all(q > 0 for q in p.s["qty"].values())
            assert p.equity() == pytest.approx(p.s["cash"] + sum(q * p.s["last"][k] for k, q in p.s["qty"].items()))
        if not p.s["qty"]:                                                                  # flat: all of the equity is cash
            assert p.equity() == pytest.approx(p.s["cash"]) and p.s["wins"] <= p.s["closed"]


def test_paper_no_trade_without_a_price(tmp_path):
    def down(sym):
        raise net.PriceError("down")
    p, t = paper(tmp_path, down)
    p.step(0.0)
    assert p.s["trades"] == [] and p.s["hist"] == {} and p.s["cash"] == 8.0 and p.snapshot()["error"] == "BTC-USD: PriceError"
    for bad in (None, 0, -1, float("nan"), float("inf"), "100", True, 1e12):
        p.price("BTC-USD", bad, 1.0)
    p.price("ETH-USD", 5.0, 1.0)                                                           # not one of the assets
    assert p.s["hist"] == {} and p.s["trades"] == []


def test_paper_fetch_is_paced_by_the_injected_clock(tmp_path):
    n = []
    p, t = paper(tmp_path, lambda s: n.append(s) or 100.0)
    p.step(1000.0)
    p.step(1000.0 + EVERY_S - 1)
    assert len(n) == 1
    p.step(1000.0 + EVERY_S)
    assert len(n) == 2


def test_paper_persists_atomically_and_survives_damage(tmp_path):
    p, _ = paper(tmp_path)
    p.step(0.0)
    feed(p, [100.0] * 8 + [110.0])
    p.step(10000.0)
    q, _ = paper(tmp_path)
    assert q.s == p.s and os.listdir(tmp_path) == ["paper.json"]                            # same state back, no temp files left
    (tmp_path / "paper.json").write_text('{"cash": -5}')
    r, _ = paper(tmp_path)
    assert r.s["cash"] == 8.0 and (tmp_path / "paper.json.bad").exists()


def test_paper_pnl_feeds_the_card_but_never_the_agency_net(project, tmp_path):
    base = build(project, str(tmp_path / "a"), seed=1, token=TOKEN, warmup=200)
    app = start(project, tmp_path, warmup=200)
    app.sim.paper.s["cash"] = 9.5                                                           # +$1.50 of paper P&L
    b0, b1 = reply(base.route("GET", "/api/business"))[1], reply(app.route("GET", "/api/business"))[1]
    fin = next(d for d in b1["departments"] if d["dept"] == "finance-trading")
    assert fin["paper"] is True and fin["headline"]["value"] == 1.5 and fin["extras"]["paper"] is True and "PLACEHOLDER" in fin["notes"]
    assert b1["net"]["paper_pnl"] == 1.5 and b1["net"]["net"] == b0["net"]["net"] == b1["net"]["dial_profit"]       # the same net as without it
    app.sim.paper.s["cash"] = 4.0                                                           # P&L changes: the card follows, the net does not
    b2 = reply(app.route("GET", "/api/business"))[1]
    assert next(d for d in b2["departments"] if d["dept"] == "finance-trading")["headline"]["value"] == -4.0 and b2["net"]["net"] == b0["net"]["net"]
    assert b2["test"]["paper"]["pnl"] == -4.0 and "PLACEHOLDER" in b2["test"]["paper"]["label"]


# ---- owner review
def served(app):
    srv = server.serve(app, "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def with_item(project, tmp_path, **kw):
    app = start(project, tmp_path, **kw)
    run_until(app, lambda: any(i["agent"] != "boss" for i in app.sim.real.items))
    return app, next(i for i in app.sim.real.items if i["agent"] != "boss")


def test_review_endpoint_auth_paths(project, tmp_path):
    app, i = with_item(project, tmp_path)
    srv = served(app)
    try:
        port, ck, js = srv.server_address[1], {"Cookie": "ag=" + TOKEN}, {"Content-Type": "application/json"}
        body = json.dumps({"id": i["id"], "decision": "accept"})
        assert call(port, "POST", "/api/review", body, js)[0] == 401                                  # no key
        assert call(port, "POST", "/api/review", body, {**ck, "Content-Type": "text/plain"})[0] == 403
        assert call(port, "POST", "/api/review", body, {**ck, **js, "Origin": "http://evil.example.com"})[0] == 403
        assert call(port, "GET", "/api/output?id=" + i["id"])[0] == 401
        assert i["decision"] is None
        s, _, out = call(port, "POST", "/api/review", body, {**ck, **js})
        assert s == 200 and json.loads(out)["pending"] == sum(not x["decision"] for x in app.sim.real.items) and i["decision"] == "accept"
        s, h, out = call(port, "GET", "/api/output?id=" + i["id"], None, ck)
        assert s == 200 and h["Content-Type"].startswith("text/plain") and b"three bullets" in out
    finally:
        srv.shutdown()


def test_review_refused_without_access_key(project, tmp_path):
    app, i = with_item(project, tmp_path, token=None)
    assert reply(post(app, "/api/review", {"id": i["id"], "decision": "accept"}))[0] == 403 and i["decision"] is None


def test_review_validation_unknown_double_and_note_length(project, tmp_path):
    app, i = with_item(project, tmp_path)
    ok = {"id": i["id"], "decision": "reject"}
    for bad in ({"id": "nope.task-1", "decision": "accept"}, {"id": "../../x", "decision": "accept"}):
        assert reply(post(app, "/api/review", bad))[0] == 404
    for bad in ({"id": i["id"]}, {"id": i["id"], "decision": "maybe"}, {"id": 5, "decision": "accept"}, {**ok, "extra": 1}, {**ok, "note": "x" * 301}, {**ok, "note": "two\nlines"},
                {**ok, "note": 7}, [], b"{bad json", b"[1]"):
        assert reply(post(app, "/api/review", bad))[0] == 400, bad
    assert i["decision"] is None
    assert reply(post(app, "/api/review", {**ok, "note": "x" * 300}))[0] == 200 and i["note"] == "x" * 300 and i["decision"] == "reject"
    s, d = reply(post(app, "/api/review", {"id": i["id"], "decision": "accept"}))
    assert s == 409 and i["decision"] == "reject"                                                  # a decision is final
    assert app.route("GET", "/api/output?id=nope")[0] == 404


def test_decision_is_a_handoff_and_reaches_the_next_prompt(project, tmp_path):
    m = Model()
    app, i = with_item(project, tmp_path, model=m)
    a = i["agent"]
    note = "Too wordy, lead with the price"
    assert reply(post(app, "/api/review", {"id": i["id"], "decision": "reject", "note": note}))[0] == 200
    assert any("__decision__%s__" % i["job"] in n for n in app.sim.hs.idx) and any(note in open(f, encoding="utf-8").read() for f in glob.glob(app.sim.hs.dd + "/*/inbox/*decision*"))
    n = len(m.prompts)
    title = app.store.org.agents[a].title
    run_until(app, lambda: any(title in p and note in p for p in m.prompts[n:]))
    p = next(p for p in m.prompts[n:] if note in p)
    assert "REJECTED" in p and i["job"] in p
    assert all(note not in q for q in m.prompts[:n])                                         # earlier prompts had no feedback
    snap = reply(app.route("GET", "/api/business"))[1]["test"]["real"]
    assert any(x["note"] == note and x["decision"] == "reject" for x in snap["items"])


def test_feedback_is_only_the_latest_decision_of_the_own_agent(tmp_path):
    r = Real(config.load_test_mode({"real_agents": ["x", "y"]}, "t"), Model(), str(tmp_path / "d"), lambda: 5.0)
    x, y = (types.SimpleNamespace(id=k, title=k.upper(), body="role " + k, dept="ok") for k in "xy")
    for n in range(5):
        r.save(x, "task-%03d" % n, "t%d" % n, "out")
        r.decide({"id": "ok.task-%03d" % n, "decision": "accept", "note": "note%d" % n})
    r.save(y, "task-900", "t", "out")
    r.decide({"id": "ok.task-900", "decision": "reject", "note": "only-y"})
    px = r.prompt(x, "do it")
    assert "note4" in px and "note3" not in px and "only-y" not in px and px.index("role x") < px.index("do it") < px.index("note4")      # task, then only the latest decision
    assert "only-y" in r.prompt(y, "t") and "note4" not in r.prompt(y, "t")


# ---- audit fixes and efficiency rules
class Slow(Model):
    """A model that blocks until released (a small local model that takes a long time)."""
    def __init__(self):
        super().__init__()
        self.entered, self.go = threading.Event(), threading.Event()

    def __call__(self, prompt):
        self.entered.set()
        self.go.wait(30)
        return self.reply


def test_slow_model_does_not_freeze_the_tick_or_the_routes(project, tmp_path):
    m = Slow()
    app = start(project, tmp_path, model=m)
    try:
        run_until(app, m.entered.is_set, 6000, settle=False)
        t = time.monotonic()
        for _ in range(5):
            app.tick()
            assert app.route("GET", "/api/health")[0] == 200 and app.route("GET", "/api/business")[0] == 200
        assert time.monotonic() - t < 2 and not app.sim.real.items                        # the model is still thinking
    finally:
        m.go.set()
    app.sim.worker.join()
    run_until(app, lambda: app.sim.real.items)                                           # the reply is picked up by a later tick
    assert app.sim.real.items[0]["secs"] >= 0


def test_one_model_call_at_a_time(project, tmp_path):
    class Count(Model):
        now = peak = 0
        lock = threading.Lock()

        def __call__(self, prompt):
            with self.lock:
                Count.now += 1
                Count.peak = max(Count.peak, Count.now)
            time.sleep(0.01)
            with self.lock:
                Count.now -= 1
            return self.reply
    app = start(project, tmp_path, model=Count())
    run_until(app, lambda: len(app.sim.real.items) >= 4, 6000)
    assert Count.peak == 1


def test_http_deadline_is_total_not_per_read():
    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.send_header("Content-Length", "100")
            self.end_headers()
            try:
                for _ in range(10):                                                      # a byte every 0.3 s: no single read ever times out
                    time.sleep(0.3)
                    self.wfile.write(b" ")
                    self.wfile.flush()
            except OSError:
                pass
    srv = stub(H)
    try:
        t = time.monotonic()
        with pytest.raises(net.ModelError):
            net.ask_model("p", "http://127.0.0.1:%d/api/generate" % srv.server_address[1], "m", 1)
        assert time.monotonic() - t < 2.5
    finally:
        srv.shutdown()


def test_model_request_carries_keep_alive_and_caps():
    seen = []

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            seen.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            out = b'{"response": "ok"}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)
    srv = stub(H)
    try:
        url = "http://127.0.0.1:%d/api/generate" % srv.server_address[1]
        net.ask_model("p", url, "m", 5)
        net.ask_model("p", url, "m", 5, "2h", 2048, 100)
    finally:
        srv.shutdown()
    assert seen[0]["keep_alive"] == "30m" and seen[0]["options"] == {"num_ctx": 4096, "num_predict": 512}
    assert seen[1]["keep_alive"] == "2h" and seen[1]["options"] == {"num_ctx": 2048, "num_predict": 100}
    d = config.load_test_mode(None, "t")
    assert (d["model_keep_alive"], d["model_num_ctx"], d["model_num_predict"]) == ("30m", 4096, 512)
    for bad in ({"model_keep_alive": "forever"}, {"model_keep_alive": 5}, {"model_num_ctx": 10}, {"model_num_ctx": True}, {"model_num_predict": 99999}, {"model_num_predict": "9"}):
        with pytest.raises(ConfigError):
            config.load_test_mode(bad, "t")


def test_review_decision_of_the_wrong_type_is_400_not_500(project, tmp_path):
    app, i = with_item(project, tmp_path)
    for bad in ({"id": i["id"], "decision": []}, {"id": i["id"], "decision": {}}, {"id": i["id"], "decision": ["accept"]}, {"decision": []}, {}, {"id": [], "decision": "accept"}):
        assert reply(post(app, "/api/review", bad))[0] == 400, bad
    assert i["decision"] is None


def test_output_files_leave_with_their_queue_entry(tmp_path):
    r = Real(config.load_test_mode({"real_agents": ["x"]}, "t"), Model(), str(tmp_path / "d"), lambda: 1.0)
    x = types.SimpleNamespace(id="x", title="X", body="b", dept="ok")
    for n in range(KEEP + 5):
        r.save(x, "task-%03d" % n, "t", "out")
    files = sorted(os.listdir(os.path.join(r.dir, "ok")))
    assert len(r.items) == KEEP and files == sorted(i["file"].split("/")[1] for i in r.items)
    assert "task-000.md" not in files and "task-004.md" not in files and "task-005.md" in files
    q = Real(config.load_test_mode({"real_agents": ["x"]}, "t"), Model(), str(tmp_path / "d"), lambda: 1.0)           # reload: the saved queue matches the files
    assert [i["id"] for i in q.items] == [i["id"] for i in r.items] and q.items[-1]["secs"] == 0.0


def test_paper_keeps_counters_not_a_growing_list(tmp_path):
    p, _ = paper(tmp_path)
    feed(p, [100.0] * 9 + [110.0, 121.0, 60.0, 50.0, 40.0, 30.0])
    assert p.s["closed"] == 1 and p.s["wins"] == 0 and p.snapshot()["win_rate_pct"] == 0
    p.step(0.0)
    assert json.loads((tmp_path / "paper.json").read_text())["closed"] == 1
    r = random.Random(3)
    x = 100.0
    for k in range(2000):
        x = max(0.01, x * (1 + r.uniform(-.1, .1)))
        p.price("BTC-USD", x, float(k))
    assert isinstance(p.s["closed"], int) and p.s["closed"] > 5 and p.s["wins"] <= p.s["closed"] and len(p.s["trades"]) <= 20
    p.step(1e9)
    assert paper(tmp_path)[0].s == p.s                                                   # the saved state reloads


def test_failed_save_writes_no_handoff_and_the_retry_writes_one(project, tmp_path):
    app = start(project, tmp_path)
    real_save, wrote = app.sim.real.save, []
    orig = app.sim.hs.write_handoff
    app.sim.hs.write_handoff = lambda *a, **k: (wrote.append(a) if "local model" in a[6] else None, orig(*a, **k))[1]
    boom = [True]

    def save(*a, **k):
        if boom[0]:
            raise OSError("disk full")
        return real_save(*a, **k)
    app.sim.real.save = save
    own = lambda j: j["agent"] in ("fin-lead", "ops-lead")                              # noqa: E731
    run_until(app, lambda: any(j["tries"] and own(j) for j in app.sim.jobs), 6000)
    assert wrote == [] and app.sim.real.items == []                                      # nothing half-written
    boom[0] = False
    run_until(app, lambda: app.sim.real.items, 6000)
    assert len(wrote) == len(app.sim.real.items) >= 1                                    # one handoff per saved output


def test_prompt_prefix_is_identical_and_comes_first(tmp_path):
    r = Real(config.load_test_mode({"real_agents": ["x"]}, "t"), Model(), str(tmp_path / "d"), lambda: 5.0)
    x = types.SimpleNamespace(id="x", title="X", body="role x", dept="ok")
    first = r.prompt(x, "task one")
    r.save(x, "task-001", "t", "out")
    r.decide({"id": "ok.task-001", "decision": "reject", "note": "shorter"})
    r.save(x, "task-002", "t", "out")
    r.decide({"id": "ok.task-002", "decision": "accept", "note": "good"})
    second = r.prompt(x, "a different, longer task two")
    pre = r.prefix(x).encode()
    assert first.encode().startswith(pre) and second.encode().startswith(pre) and "role x" in r.prefix(x) and "task" not in r.prefix(x).lower().replace("no tools", "")
    assert first.index("task one") >= len(pre) and "feedback" not in first
    assert second.index("task two") < second.index("good") and "shorter" not in second and "REJECTED" not in second     # only the most recent decision, after the task


def test_every_prompt_of_an_agent_starts_with_its_fixed_prefix(project, tmp_path):
    m = Model()
    app = start(project, tmp_path, model=m)
    run_until(app, lambda: len(app.sim.real.items) >= 4, 6000)
    for aid in ("boss", "fin-lead", "ops-lead"):
        a = app.store.org.agents[aid]
        mine = [p for p in m.prompts if p.startswith("You are %s (%s)" % (a.title, aid))]
        assert all(p.encode().startswith(app.sim.real.prefix(a).encode()) for p in mine)


def test_seconds_and_sizes_are_logged_without_the_prompt_text(project, tmp_path, caplog):
    caplog.set_level(logging.INFO)
    m = Model()
    app = start(project, tmp_path, model=m)
    run_until(app, lambda: app.sim.real.items)
    rec = [r.getMessage() for r in caplog.records if r.getMessage().startswith("real job")]
    assert rec and " s, prompt " in rec[0] and " chars, reply " in rec[0]
    assert all(m.prompts[0][:60] not in x and "Task:" not in x for x in rec)
    assert "secs" in app.sim.real.snapshot()["items"][0]


# ---- scheduler: one real job at a time, loaded-agent preference
H = 3600


def sched(real, **kw):
    s = make(**kw)
    s.real = frozenset(real)
    return s


def test_real_jobs_run_one_at_a_time_simulated_keep_the_cap():
    s = sched({"o1", "r1"}, max_working=3, max_loaded=3)
    s.check = lambda j: None if j["agent"] in s.real else True                           # a real job's check waits on the model
    a, c, b = s.add("ops", "a", 100, 600), s.add("ops", "c", 100, 600), s.add("res", "b", 100, 600)
    s.step(8 * H)
    assert sorted(j["agent"] for j in s.running) == ["o1", "o2"] and s.queue["res"] == [b]      # o1 is real; o2 simulated runs beside it; the second real job waits
    s.step(8 * H + 600)
    assert not s.running and s.pending == [a] and s.queue["res"] == [b] and c["end"]            # a is done working but its model call is out: b still waits
    s.resolve(a, True)
    s.step(8 * H + 700)
    assert [j["agent"] for j in s.running] == ["r1"] and not s.pending


def test_a_failed_pending_check_is_retried_like_any_failed_attempt():
    s = sched({"o1"})
    s.check = lambda j: None
    a = s.add("ops", "a", 100, 600)
    s.step(6 * H)
    s.step(6 * H + 600)
    s.resolve(a, False)
    assert a["tries"] == 1 and a in s.queue["ops"] and not s.pending


def after_one_ops_job(real, **kw):
    s = sched(real, max_working=1, **kw)
    s.add("ops", "a1", 100, 600)
    s.step(6 * H)
    s.step(6 * H + 600)
    assert s.last == "o1" and not s.running
    s.step(8 * H - 1)
    return s


def test_the_agent_that_ran_last_goes_on_first_only_when_real_agents_are_on():
    for real, who in (({"o1", "r1"}, "o1"), ((), "r1")):                                  # off: the allocator picks res (furthest below its share)
        s = after_one_ops_job(real)
        s.add("ops", "a2", 100, 600)
        s.add("res", "b1", 100, 600)
        s.step(8 * H)
        assert [j["agent"] for j in s.running] == [who]


def test_preference_never_beats_a_user_task_a_paused_job_a_limit_or_a_toggle():
    def run(tweak):
        s = after_one_ops_job({"o1", "r1"})
        a2, b1 = s.add("ops", "a2", 100, 600), s.add("res", "b1", 100, 600)
        tweak(s, a2, b1)
        s.step(8 * H)
        return [j["agent"] for j in s.running]
    assert run(lambda s, a2, b1: b1.update(user=True)) == ["r1"]                          # the user's task first
    assert run(lambda s, a2, b1: b1.update(checkpoint={"at": 0, "agent": "r1", "done_s": 1, "spent": 1}, paused="window_cap")) == ["r1"]      # a paused job resumes first
    assert run(lambda s, a2, b1: s.spent.update(ops=s.share["ops"])) == ["r1"]            # its department's share is spent
    assert run(lambda s, a2, b1: s.set_enabled({"dept": "ops", "enabled": False})) == ["r1"]          # toggled off
    assert run(lambda s, a2, b1: None) == ["o1"]                                          # and with none of those, the preference holds
    s = after_one_ops_job({"o1", "r1"})
    s.add("ops", "a2", 100, 600)
    s.add("res", "b1", 100, 600)
    s.step(11 * H)                                                                        # ops closed (10:00 plus grace): res only
    assert [j["agent"] for j in s.running] == ["r1"]
