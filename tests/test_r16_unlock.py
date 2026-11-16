"""The stealth lock is enforced by the server: no looked-up name leaves it without the unlock secret."""
import http.client
import json
import os
import stat
import threading
from types import SimpleNamespace

import pytest

from overheard import auth, config, led as ledmod
from overheard.adult import AdultFilter, FlagLog, Guard, PenaltyBox
from overheard.profiles import ProfileStore
from overheard.server import App, Req, make_handler, serve
from overheard.state import State

TOKEN = "t" * 32
SECRET = "correct-horse"
FED = ("secret-site.example.org", "rr1---sn-abc.googlevideo.com", "x.badsite.example", "ads.tracker-corp.example", "swscan.apple.com",
       "gsa.apple.com", "api.private-bank.example")


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def app(tmp_path):
    cfg = config.parse(["--demo", "--data-dir", str(tmp_path)])
    st = State()
    guard = Guard(AdultFilter({"badsite.example"}), PenaltyBox(90), FlagLog(str(tmp_path / "flags.json")), st.settings)
    sprites = ledmod.load_sprites()
    a = App(cfg, st, ProfileStore(cfg.db_path, everyone=True), ledmod.LedState(str(tmp_path / "led.json"), sprites), sprites, TOKEN, guard, secret=SECRET)
    a.clock = Clock()
    a.sessions, a.fails = auth.Sessions(clock=a.clock), auth.FailureLimit(clock=a.clock)
    for i, d in enumerate(FED):
        a.state.clock = (lambda i=i: 5000.0 + i * 2)
        a.state.record("10.0.0.5", d, blocked=d.startswith("ads."), adult=guard.hit("10.0.0.5", d) is not None)
    a.state.clock = lambda: 5000.0 + len(FED) * 2
    a.state.conns = [{"ip": "203.0.113.9", "host": "secret-site.example.org", "service": "Other", "count": 2, "bytes": 5}]
    return a


def strings(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield k
            yield from strings(v)
    elif isinstance(o, (list, tuple)):
        for v in o:
            yield from strings(v)
    elif isinstance(o, str):
        yield o


def call(app, method, path, body=None, sid=None):
    req = Req("10.0.0.7", ("ovu=" + sid) if sid else "")
    s, _, raw = app.route(method, path, json.dumps(body).encode() if body is not None else b"", req)
    return s, json.loads(raw), req


def unlock(app, addr="10.0.0.7"):
    req = Req(addr)
    assert json.loads(app.route("POST", "/api/unlock", json.dumps({"secret": SECRET}).encode(), req)[2]) == {"unlocked": True}
    return req.headers[0][1].split(";")[0].split("=", 1)[1]


def test_locked_stats_contain_no_looked_up_name(app):
    s, d, _ = call(app, "GET", "/api/stats")
    assert s == 200 and d["unlocked"] is False and "settings" not in d
    blob = "\n".join(strings(d))
    for dom in FED + ("googlevideo", "badsite", "tracker-corp", "private-bank"):
        assert dom not in blob, dom
    assert d["recent"] == [] and d["adult"]["flagged"] == 0 and d["adult"]["slowed"] == []
    assert all("host" not in c for c in d["conns"])
    assert d["dns"]["total"] == len(FED) and d["devices"][0]["lookups"] == len(FED)          # totals, labels and counts stay
    assert all(not dv.get("evidence") for dv in d["devices"]) and "Adult content" not in blob


def test_unlocked_stats_are_full_and_carry_settings(app):
    sid = unlock(app)
    s, d, _ = call(app, "GET", "/api/stats", sid=sid)
    assert d["unlocked"] is True and d["settings"] == {"slowdown": False}
    blob = "\n".join(strings(d))
    assert "secret-site.example.org" in blob and "x.badsite.example" in blob and d["recent"] and d["adult"]["flagged"] >= 1


def test_unlock_success_cookie_and_wrong_secret(app):
    req = Req("10.0.0.7")
    s, _, raw = app.route("POST", "/api/unlock", json.dumps({"secret": SECRET}).encode(), req)
    ck = req.headers[0][1]
    assert s == 200 and json.loads(raw) == {"unlocked": True}
    assert ck.startswith("ovu=") and "HttpOnly" in ck and "SameSite=Strict" in ck and "Max-Age=1800" in ck
    for bad in ({"secret": "nope"}, {"secret": ""}):
        s, d, r = call(app, "POST", "/api/unlock", bad)
        assert s == 403 and not r.headers
    for junk in ({"secret": 5}, {"secret": None}, {}, [SECRET]):
        assert call(app, "POST", "/api/unlock", junk)[0] == 400
    assert app.route("POST", "/api/unlock", b"{oops", Req("10.0.0.8"))[0] == 400


def test_unlock_is_rate_limited_per_address(app):
    for _ in range(5):
        assert call(app, "POST", "/api/unlock", {"secret": "x"})[0] == 403
    s, _, req = call(app, "POST", "/api/unlock", {"secret": SECRET})
    assert s == 429 and ("Retry-After", "60") in req.headers and not any(k == "Set-Cookie" for k, _ in req.headers)   # even the right secret waits
    other = Req("10.0.0.99")
    assert app.route("POST", "/api/unlock", json.dumps({"secret": SECRET}).encode(), other)[0] == 200      # another device is unaffected
    app.clock.t += 61
    assert call(app, "POST", "/api/unlock", {"secret": SECRET})[0] == 200


def test_session_expires_after_30_minutes_and_lock_clears_it(app):
    sid = unlock(app)
    app.clock.t += 29 * 60
    assert call(app, "GET", "/api/stats", sid=sid)[1]["unlocked"] is True
    app.clock.t += 2 * 60
    assert call(app, "GET", "/api/stats", sid=sid)[1]["unlocked"] is False
    sid = unlock(app)
    s, d, req = call(app, "POST", "/api/lock", sid=sid)
    assert d == {"unlocked": False} and "Max-Age=0" in req.headers[0][1]
    assert call(app, "GET", "/api/stats", sid=sid)[1]["unlocked"] is False


def test_sessions_are_bounded_and_ids_unguessable(app):
    ids = [unlock(app) for _ in range(auth.MAX_SESSIONS + 5)]
    assert len(set(ids)) == len(ids) and len(app.sessions._s) == auth.MAX_SESSIONS
    assert not app.sessions.valid(ids[0]) and app.sessions.valid(ids[-1])
    assert not app.sessions.valid("") and not app.sessions.valid("guess")


def test_locked_endpoints_that_return_names_are_forbidden(app):
    for path in ("/api/flagged", "/api/profiles", "/api/profile?id=10.0.0.5"):
        assert call(app, "GET", path)[0] == 403, path
        assert call(app, "GET", path, sid="forged")[0] == 403, path
    sid = unlock(app)
    s, d, _ = call(app, "GET", "/api/flagged", sid=sid)
    assert s == 200 and any(i["domain"] == "x.badsite.example" for i in d["items"])
    assert call(app, "GET", "/api/profiles", sid=sid)[0] == 200


def test_settings_need_unlock_and_a_real_bool(app):
    assert call(app, "POST", "/api/settings", {"slowdown": True})[0] == 403
    assert app.state.settings.slowdown is False
    sid = unlock(app)
    for bad in ({"slowdown": 1}, {"slowdown": "true"}, {"slowdown": None}, {}, [], {"slowdown": True, "adult": False}, {"penalty": 0}, {"slowdown": [True]}):
        assert call(app, "POST", "/api/settings", bad, sid=sid)[0] == 400, bad
    assert app.state.settings.slowdown is False
    s, d, _ = call(app, "POST", "/api/settings", {"slowdown": True}, sid=sid)
    assert s == 200 and d == {"settings": {"slowdown": True}} and app.state.settings.slowdown is True
    assert call(app, "GET", "/api/stats", sid=sid)[1]["settings"] == {"slowdown": True}
    assert call(app, "POST", "/api/settings", {"slowdown": False}, sid=sid)[1] == {"settings": {"slowdown": False}}


def test_slowed_indicator_follows_the_switch(app):
    sid = unlock(app)
    assert app.guard.penalty.active() and call(app, "GET", "/api/stats", sid=sid)[1]["adult"]["slowed"] == []
    assert call(app, "GET", "/api/flagged", sid=sid)[1]["slowed"] == []
    app.state.settings.slowdown = True
    assert call(app, "GET", "/api/stats", sid=sid)[1]["adult"]["slowed"][0]["id"] == "10.0.0.5"
    assert call(app, "GET", "/api/stats")[1]["adult"]["slowed"] == []        # but never to a locked viewer


def test_no_route_touches_the_adult_guard_configuration(app):
    sid = unlock(app)
    before = (len(app.guard.filter), app.guard.penalty.cooldown)
    for path in ("/api/guard", "/api/adult", "/api/filter", "/api/penalty"):
        for m in ("GET", "POST"):
            assert call(app, m, path, {"enabled": False, "penalty": 0}, sid=sid)[0] == 404
    call(app, "POST", "/api/settings", {"slowdown": False}, sid=sid)
    assert (len(app.guard.filter), app.guard.penalty.cooldown) == before


def test_doctor_header_only_counts_from_loopback_with_the_cookie(app):
    H = make_handler(app)

    def doctor(addr, cookie="ov=" + TOKEN, **hdr):
        m = http.client.HTTPMessage()
        for k, v in {"Cookie": cookie, "X-Overheard-Doctor": "1", **hdr}.items():
            if v is not None:
                m[k] = v
        return H._doctor(SimpleNamespace(client_address=(addr, 4000), headers=m))
    assert doctor("127.0.0.1") is True
    assert doctor("192.168.1.20") is False and doctor("::1") is False
    assert doctor("127.0.0.1", cookie="ov=wrong") is False and doctor("127.0.0.1", cookie="") is False
    assert doctor("127.0.0.1", **{"X-Overheard-Doctor": "0"}) is False and doctor("127.0.0.1", **{"X-Overheard-Doctor": None}) is False
    assert doctor("127.0.0.1", **{"X-Forwarded-For": "203.0.113.4"}) is False          # a proxy on the board forwarding a stranger
    assert doctor("127.0.0.1", **{"Tailscale-User-Login": "a@b.c"}) is False
    app.token = None
    assert doctor("127.0.0.1") is False
    app.token = TOKEN
    s, _, raw = app.route("GET", "/api/stats", b"", Req("127.0.0.1", "", True))
    d = json.loads(raw)
    assert d["recent"] and d["settings"] == {"slowdown": False}
    assert call(app, "POST", "/api/settings", {"slowdown": True})[0] == 403             # the doctor reads, it does not change anything
    assert app.route("GET", "/api/flagged", b"", Req("127.0.0.1", "", True))[0] == 403


@pytest.fixture
def http_app(app):
    httpd = serve(app, "127.0.0.1", 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield app, httpd.server_address[1]
    httpd.shutdown()


def fetch(port, method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    h = {"Cookie": "ov=" + TOKEN, **(headers or {})}
    if body is not None:
        h.setdefault("Content-Type", "application/json")
    c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
    r = c.getresponse()
    return r.status, r.read(), r


def test_over_http_unlock_stats_lock_and_csrf(http_app):
    app, port = http_app
    assert fetch(port, "POST", "/api/unlock", {"secret": SECRET}, {"Cookie": ""})[0] == 401          # the access token still gates everything
    assert fetch(port, "POST", "/api/unlock", {"secret": SECRET}, {"Content-Type": "text/plain"})[0] == 403
    assert fetch(port, "POST", "/api/unlock", {"secret": SECRET}, {"Origin": "http://evil.example"})[0] == 403
    assert fetch(port, "POST", "/api/settings", {"slowdown": True}, {"Origin": "http://evil.example"})[0] == 403
    assert fetch(port, "POST", "/api/lock", {}, {"Origin": "http://evil.example"})[0] == 403
    s, raw, r = fetch(port, "POST", "/api/unlock", {"secret": SECRET})
    ck = r.getheader("Set-Cookie")
    assert s == 200 and json.loads(raw) == {"unlocked": True} and "HttpOnly" in ck and "SameSite=Strict" in ck
    both = "ov=%s; %s" % (TOKEN, ck.split(";")[0])
    assert json.loads(fetch(port, "GET", "/api/stats", headers={"Cookie": both})[1])["recent"]
    assert not json.loads(fetch(port, "GET", "/api/stats")[1])["recent"]                               # same token, no session: locked
    assert fetch(port, "GET", "/api/flagged")[0] == 403 and fetch(port, "GET", "/api/flagged", headers={"Cookie": both})[0] == 200
    assert fetch(port, "POST", "/api/settings", {"slowdown": True}, {"Cookie": both})[0] == 200
    assert fetch(port, "POST", "/api/lock", {}, {"Cookie": both})[0] == 200
    assert json.loads(fetch(port, "GET", "/api/stats", headers={"Cookie": both})[1])["unlocked"] is False


def test_over_http_doctor_gets_the_full_payload_from_loopback(http_app):
    _, port = http_app
    d = json.loads(fetch(port, "GET", "/api/stats", headers={"X-Overheard-Doctor": "1"})[1])
    assert d["recent"] and d["unlocked"] is False
    assert not json.loads(fetch(port, "GET", "/api/stats", headers={"X-Overheard-Doctor": "1", "X-Forwarded-For": "1.2.3.4"})[1])["recent"]
    assert fetch(port, "GET", "/api/stats", headers={"X-Overheard-Doctor": "1", "Cookie": ""})[0] == 401


def test_3ds_page_is_served_behind_the_token(http_app):
    _, port = http_app
    s, raw, r = fetch(port, "GET", "/3ds")
    assert s == 200 and r.getheader("Content-Type").startswith("text/html") and b"<title>Overheard" in raw
    assert fetch(port, "GET", "/3ds", headers={"Cookie": ""})[0] == 401


def test_unlock_secret_is_created_private_and_stable(tmp_path):
    t = auth.load_secret(str(tmp_path))
    assert len(t) >= 8 and auth.load_secret(str(tmp_path)) == t
    assert stat.S_IMODE(os.stat(tmp_path / "unlock").st_mode) == 0o600
    assert auth.load_token(str(tmp_path)) != t
    cfg = config.parse(["--data-dir", str(tmp_path)])
    assert App(cfg, State()).secret == t
