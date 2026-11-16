import json
import threading
import urllib.request

import pytest

from overheard import config, demo, led as ledmod
from overheard.profiles import ProfileStore
from overheard.server import App, Req, serve
from overheard.state import State


@pytest.fixture
def app(tmp_path):
    cfg = config.parse(["--demo", "--data-dir", str(tmp_path)])
    st = State()
    store = ProfileStore(cfg.db_path, everyone=True)
    st.listeners.append(store.observe)
    sprites = ledmod.load_sprites()
    return App(cfg, st, store, ledmod.LedState(str(tmp_path / "led.json"), sprites), sprites)


def feed(app):
    for svc, hosts, _ in demo.SCRIPT[:1]:
        for _ in range(40):
            demo.tick(app.state, svc, hosts)
            app.state.clock = (lambda c=app.state.clock: c() + 1.1)


def test_dashboard_served(app):
    s, ct, body = app.route("GET", "/")
    assert s == 200 and ct.startswith("text/html") and b"Overheard" in body


def test_stats_shape(app):
    feed(app)
    s, _, body = app.route("GET", "/api/stats")
    d = json.loads(body)
    assert s == 200 and d["dns"]["enabled"] and d["devices"] and "now" in d and "recent" in d


def test_profiles_endpoints(app):
    feed(app)
    assert app.route("GET", "/api/profiles")[0] == 403           # locked
    req = Req(cookie="ovu=" + app.sessions.start())
    d = json.loads(app.route("GET", "/api/profiles", req=req)[2])
    assert d["devices"] and "cats" in d
    dev = d["devices"][0]["id"]
    p = json.loads(app.route("GET", "/api/profile?id=" + dev, req=req)[2])
    assert p["total"] > 0 and len(p["week"]) == 168
    assert app.route("GET", "/api/profile", req=req)[0] == 400


def test_led_roundtrip_and_validation(app):
    d = json.loads(app.route("GET", "/api/led")[2])
    assert d["characters"] and d["level_name"] in ledmod.LEVELS
    cid = d["characters"][0]["id"]
    s, _, body = app.route("POST", "/api/led", json.dumps({"character": cid, "brightness": 120}).encode())
    assert s == 200 and json.loads(body)["brightness"] == 120
    assert app.route("POST", "/api/led", b'{"character": "nope"}')[0] == 400
    assert app.route("POST", "/api/led", b"{bad")[0] == 400


def test_led_choice_persists(app, tmp_path):
    cid = next(iter(app.sprites))
    app.led.update(cid, 90)
    again = ledmod.LedState(str(tmp_path / "led.json"), app.sprites)
    assert again.character == cid and again.brightness == 90


def test_activity_levels():
    mk = lambda r: {"devices": [{"id": "a", "rate": r}, {"id": "this board", "rate": 99}]}  # noqa: E731
    assert [ledmod.level_from_stats(mk(r)) for r in (0, 2, 10, 40)] == [0, 1, 2, 3]


def test_unknown_route(app):
    assert app.route("GET", "/nope")[0] == 404


def test_real_http_server(app):
    httpd = serve(app, "127.0.0.1", 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        port = httpd.server_address[1]
        assert json.load(urllib.request.urlopen("http://127.0.0.1:%d/api/health" % port))["ok"]
        req = urllib.request.Request("http://127.0.0.1:%d/api/led" % port, json.dumps({"brightness": 200}).encode(), {"Content-Type": "application/json"}, method="POST")
        assert json.load(urllib.request.urlopen(req))["brightness"] == 200
    finally:
        httpd.shutdown()
