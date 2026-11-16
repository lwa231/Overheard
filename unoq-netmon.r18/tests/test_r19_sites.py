"""r19 sites: a board shows a read-only, locked summary of other boards (peers) over Tailscale.
Peers are faked with local HTTP servers on loopback, which the loader only accepts when a test says so."""
import http.client
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from overheard import config, peers as P
from overheard.server import App, serve
from overheard.state import State

KEY = "k-test-key-0123456789abcdef"
TOKEN = "t" * 32
LEAK = {"host": "peer", "unlocked": True, "settings": {"slowdown": True}, "recent": [{"domain": "recent.example", "client": "10.0.0.5"}],
        "now": {"service": "Video", "mode": "video", "evidence": [{"domain": "evidence.example", "count": 3}]},
        "conns": [{"ip": "203.0.113.9", "host": "conn.example", "count": 2}],
        "adult": {"enabled": True, "slowed": ["10.0.0.9"], "flagged": 3, "listed": 5, "items": [{"domain": "flag.example"}]},
        "devices": [{"id": "10.0.0.5", "label": "Phone", "evidence": [{"domain": "device.example"}], "lookups": 4,
                     "rows": [{"service": "Adult content", "v": [1]}, {"service": "YouTube", "v": [2]}]}],
        "dns": {"enabled": True, "total": 4, "blocked": 1, "clients": 1, "upstream": "tls"}}
LEAKED = ("recent.example", "evidence.example", "conn.example", "flag.example", "device.example")


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def fake_peer(body=None, status=200, delay=0, headers=()):
    """A peer that records what it was asked and answers `body` (bytes or a JSON-able object) to everything."""
    seen = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            seen.append((self.path, self.headers.get("Cookie")))
            if delay:
                threading.Event().wait(delay)
            raw = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(status)
            for k, v in headers:
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, seen


def write_peers(tmp, peers, site="apartment", mode=0o600):
    path = tmp / "peers.json"
    path.write_text(json.dumps({"site": site, "peers": peers}))
    os.chmod(path, mode)


def peer_entry(httpd, name="home", key=KEY):
    return {"name": name, "url": "http://127.0.0.1:%d" % httpd.server_address[1], "key": key}


def front(tmp, httpd, **kw):
    """An App whose only peer is `httpd`."""
    write_peers(tmp, [peer_entry(httpd)])
    pe = P.load(str(tmp), loopback=True, **kw)
    assert pe
    return App(config.parse(["--demo", "--data-dir", str(tmp)]), State(), peers=pe, secret="s" * 12)


def get(app, path):
    s, _, raw = app.route("GET", path)
    return s, raw


# ---- no peers: nothing changes ----

def test_without_peers_file_the_board_is_as_before(tmp_path):
    assert P.load(str(tmp_path)) is None
    st = State()
    st.clock = lambda: 5000.0
    plain = App(config.parse(["--demo", "--data-dir", str(tmp_path)]), st, secret="s" * 12)
    off = App(config.parse(["--demo", "--data-dir", str(tmp_path)]), st, peers=None, secret="s" * 12)
    s, raw = get(plain, "/api/sites")
    d = json.loads(raw)
    assert s == 200 and d["sites"] == [{"name": d["site"], "self": True}]
    assert get(plain, "/api/stats") == get(off, "/api/stats")
    stats = json.loads(get(plain, "/api/stats")[1])
    assert "site" not in stats and "sites" not in stats
    assert get(plain, "/api/site?name=home") == (404, b'{"error": "not found"}')


def test_empty_peers_file_is_off(tmp_path):
    write_peers(tmp_path, [])
    assert P.load(str(tmp_path)) is None


def test_invalid_file_is_off_with_one_line(tmp_path):
    (tmp_path / "peers.json").write_text("{nope")
    os.chmod(tmp_path / "peers.json", 0o600)
    lines = []
    assert P.load(str(tmp_path), log=lines.append) is None and len(lines) == 1


# ---- the loader ----

GOOD = {"name": "home", "url": "http://100.64.0.1:8080", "key": KEY}


@pytest.mark.parametrize("url", [
    "http://8.8.8.8:8080", "http://192.168.1.5:8080", "http://10.0.0.2", "http://127.0.0.1:8080", "http://169.254.169.254",
    "ftp://100.64.0.1", "file:///etc/passwd", "100.64.0.1:8080", "http://100.64.0.1:0", "http://100.64.0.1:70000",
    "http://100.128.0.1", "http://evil.example", "http://evil.example.ts.net.evil.com", "http://home.tail1234.ts.net:8080", "https://a.b.ts.net", "http://100.64.evil.com", "http://100.64.0.1.evil.com", "http://100.064.0.1", "http://100.64.0.1@evil.example",
    "http://user:pw@100.64.0.1", "http://100.64.0.1/x", "http://100.64.0.1/?a=1", "http://localhost:8080", "http://[::1]:8080", "", None, 5])
def test_loader_rejects_bad_urls(tmp_path, url):
    write_peers(tmp_path, [{**GOOD, "url": url}])
    lines = []
    assert P.load(str(tmp_path), log=lines.append) is None
    assert len(lines) == 1 and KEY not in lines[0]


@pytest.mark.parametrize("url", ["http://100.64.0.1:8080", "https://100.127.255.254", "http://100.64.0.1/"])
def test_loader_accepts_tailscale_addresses(tmp_path, url):
    write_peers(tmp_path, [{**GOOD, "url": url}])
    pe = P.load(str(tmp_path))
    assert pe and pe.summary()["sites"][1]["name"] == "home"


def test_loopback_only_with_the_test_flag(tmp_path):
    write_peers(tmp_path, [{**GOOD, "url": "http://127.0.0.1:9"}])
    assert P.load(str(tmp_path)) is None and P.load(str(tmp_path), loopback=True)


def test_loader_rejects_bad_names_keys_duplicates_and_too_many(tmp_path):
    bad = [[{**GOOD, "name": "Home"}], [{**GOOD, "name": "a" * 25}], [{**GOOD, "name": "a b"}], [{**GOOD, "name": ""}],
           [{**GOOD, "name": "apartment"}],                                   # this board's own name
           [GOOD, GOOD], [{**GOOD, "key": "short"}], [{**GOOD, "key": "bad key with spaces"}], [{**GOOD, "key": None}], ["home"],
           [{**GOOD, "name": "p%d" % i} for i in range(9)]]
    for peers in bad:
        write_peers(tmp_path, peers)
        assert P.load(str(tmp_path), log=lambda m: None) is None, peers
    write_peers(tmp_path, [{**GOOD, "name": "p%d" % i} for i in range(8)])
    assert len(P.load(str(tmp_path)).summary()["sites"]) == 9


@pytest.mark.skipif(os.name != "posix", reason="POSIX file modes")
@pytest.mark.parametrize("mode", [0o640, 0o604, 0o644, 0o660])
def test_loader_refuses_a_group_or_world_readable_file(tmp_path, mode):
    write_peers(tmp_path, [GOOD], mode=mode)
    lines = []
    assert P.load(str(tmp_path), log=lines.append) is None and len(lines) == 1 and "chmod 600" in lines[0]
    os.chmod(tmp_path / "peers.json", 0o600)
    assert P.load(str(tmp_path))


# ---- what crosses boards ----

def test_passthrough_is_locked_whatever_the_peer_sends(tmp_path):
    httpd, seen = fake_peer(LEAK)
    app = front(tmp_path, httpd)
    s, raw = get(app, "/api/site?name=home")
    d = json.loads(raw)
    assert s == 200 and d["site"] == "home" and d["unlocked"] is False and "settings" not in d
    for dom in LEAKED:
        assert dom not in raw.decode(), dom
    assert d["recent"] == [] and d["now"]["evidence"] == [] and d["conns"] == [{"ip": "203.0.113.9", "service": "Other", "count": 2, "bytes": 0}]
    assert d["adult"] == {"enabled": True, "slowed": [], "flagged": 0, "listed": 0}
    assert d["devices"][0]["evidence"] == [] and [r["service"] for r in d["devices"][0]["rows"]] == ["YouTube"]
    assert d["devices"][0]["label"] == "Device"        # "Phone" is not a label a board can produce
    assert d["dns"]["total"] == 4 and d["devices"][0]["lookups"] == 4        # totals and labels do cross
    httpd.shutdown()


def test_peer_gets_the_key_cookie_and_nothing_else(tmp_path):
    httpd, seen = fake_peer({"dns": {}})
    app = front(tmp_path, httpd)
    assert get(app, "/api/site?name=home")[0] == 200
    assert seen == [("/api/stats", "ov=" + KEY)]       # the access cookie only: never the unlock cookie ovu
    httpd.shutdown()


def test_a_real_board_as_peer_sends_only_its_locked_view(tmp_path):
    """A board with no changes (its existing /api/stats, behind its access key) works as a peer."""
    ptmp = tmp_path / "peer"
    ptmp.mkdir()
    pst = State()
    pst.record("10.0.0.5", "secret-site.example.org", blocked=False, adult=False)
    papp = App(config.parse(["--demo", "--data-dir", str(ptmp)]), pst, token=TOKEN, secret="p" * 12)
    peer = serve(papp, "127.0.0.1", 0)
    threading.Thread(target=peer.serve_forever, daemon=True).start()
    ftmp = tmp_path / "front"
    ftmp.mkdir()
    write_peers(ftmp, [peer_entry(peer, key=TOKEN)])
    app = App(config.parse(["--demo", "--data-dir", str(ftmp)]), State(), peers=P.load(str(ftmp), loopback=True), secret="s" * 12)
    s, raw = get(app, "/api/site?name=home")
    d = json.loads(raw)
    assert s == 200 and d["unlocked"] is False and d["dns"]["total"] == 1 and "secret-site" not in raw.decode() and TOKEN not in raw.decode()
    peer.shutdown()


# ---- failures ----

@pytest.mark.parametrize("kw", [
    {"body": b"<html>not json</html>"}, {"body": [1, 2]}, {"body": b"x" * (P.MAX_BYTES + 10)}, {"body": {"a": "x" * (P.MAX_BYTES + 10)}},
    {"body": b"[" * 100000}, {"body": {"dns": {}}, "status": 500}, {"body": {"error": "locked"}, "status": 401},
    {"body": {"error": "locked"}}, {"body": {"devices": [], "conns": []}}])
def test_bad_peer_replies_are_a_502(tmp_path, kw):
    httpd, _ = fake_peer(**kw)
    app = front(tmp_path, httpd)
    assert get(app, "/api/site?name=home") == (502, b'{"error": "site unreachable"}')
    assert json.loads(get(app, "/api/sites")[1])["sites"][1] == {"name": "home", "self": False, "ok": False, "age": None}
    httpd.shutdown()


def test_slow_peer_times_out_and_a_dead_one_is_a_502(tmp_path):
    httpd, _ = fake_peer({"dns": {}}, delay=1.5)
    app = front(tmp_path, httpd, timeout=0.3)
    assert get(app, "/api/site?name=home")[0] == 502
    httpd.shutdown()
    httpd.server_close()
    app = front(tmp_path, httpd)               # nothing listens any more
    assert get(app, "/api/site?name=home")[0] == 502


def test_cache_holds_two_seconds_and_an_unreachable_peer_is_not_hammered(tmp_path, monkeypatch):
    clock = Clock()
    real, calls = P._get, []
    monkeypatch.setattr(P, "_get", lambda *a: calls.append(1) or real(*a))
    httpd, seen = fake_peer({"dns": {"total": 1}})
    app = front(tmp_path, httpd, clock=clock)
    assert get(app, "/api/site?name=home")[0] == 200
    clock.t += 1.9
    assert get(app, "/api/site?name=home")[0] == 200 and len(seen) == 1
    assert json.loads(get(app, "/api/sites")[1])["sites"][1] == {"name": "home", "self": False, "ok": True, "age": 1.9}
    clock.t += 0.2
    assert get(app, "/api/site?name=home")[0] == 200 and len(seen) == 2
    httpd.shutdown()
    httpd.server_close()
    clock.t += 3
    n = len(calls)
    assert get(app, "/api/site?name=home")[0] == 502          # one failed attempt ...
    assert get(app, "/api/site?name=home")[0] == 502 and len(calls) == n + 1      # ... then the cached failure, no second connect


def test_one_fetch_at_a_time_per_peer(tmp_path):
    clock = Clock()
    httpd, seen = fake_peer({"dns": {}}, delay=0.8)
    app = front(tmp_path, httpd, clock=clock)
    out = []
    t = threading.Thread(target=lambda: out.append(get(app, "/api/site?name=home")[0]))
    t.start()
    while not seen:
        threading.Event().wait(0.01)
    clock.t += 5                                               # cache stale, but a fetch is already running
    out.append(get(app, "/api/site?name=home")[0])
    t.join()
    assert len(seen) == 1 and sorted(out) == [200, 502]
    httpd.shutdown()


def test_the_key_never_appears_in_a_response_or_a_log_line(tmp_path, capsys):
    httpd, _ = fake_peer(LEAK)
    app = front(tmp_path, httpd)
    for path in ("/api/sites", "/api/site?name=home", "/api/site?name=nope", "/api/site", "/api/site?name=" + KEY):
        s, raw = get(app, path)
        assert KEY not in raw.decode() and "127.0.0.1" not in raw.decode() and "100.64" not in raw.decode(), path
    httpd.shutdown()
    httpd.server_close()
    assert KEY not in get(app, "/api/site?name=home")[1].decode()
    out = capsys.readouterr()
    assert KEY not in out.out + out.err


def test_unknown_site_is_404(tmp_path):
    httpd, _ = fake_peer({"dns": {}})
    app = front(tmp_path, httpd)
    for path in ("/api/site?name=nope", "/api/site", "/api/site?name=", "/api/site?name=apartment"):
        assert get(app, path) == (404, b'{"error": "not found"}'), path
    httpd.shutdown()


def test_sites_lists_names_only_and_the_routes_need_the_access_key(tmp_path):
    peer, _ = fake_peer({"dns": {}})
    write_peers(tmp_path, [peer_entry(peer)])
    app = App(config.parse(["--demo", "--data-dir", str(tmp_path)]), State(), token=TOKEN, peers=P.load(str(tmp_path), loopback=True), secret="s" * 12)
    httpd = serve(app, "127.0.0.1", 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        c = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=5)
        for path in ("/api/sites", "/api/site?name=home"):
            c.request("GET", path)
            r = c.getresponse()
            r.read()
            assert r.status == 401, path
            c.request("GET", path, headers={"Cookie": "ov=" + TOKEN})
            r = c.getresponse()
            body = r.read().decode()
            assert r.status == 200 and KEY not in body and "127.0.0.1" not in body, path
        c.request("GET", "/api/sites", headers={"Cookie": "ov=" + TOKEN})
        d = json.loads(c.getresponse().read())
        assert d == {"site": "apartment", "sites": [{"name": "apartment", "self": True}, {"name": "home", "self": False, "ok": True, "age": d["sites"][1]["age"]}]}
    finally:
        httpd.shutdown()
        peer.shutdown()


def test_default_site_name_is_a_valid_name():
    assert P.NAME.fullmatch(P.default_site())


# ---- owner tooling ----

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_link_sites_script_is_valid_bash_and_never_stores_keys():
    sh = os.path.join(ROOT, "scripts", "link_sites.sh")
    assert subprocess.run(["bash", "-n", sh]).returncode == 0
    text = open(sh, encoding="utf-8").read()
    assert "chmod 600" in text and "last-link-sites.txt" in text and "systemctl restart overheard.service" in text
    assert "echo \"$KEY" not in text and "echo \"$K" not in text
    cmd = open(os.path.join(ROOT, "Link Sites.command"), encoding="utf-8").read()
    assert "scripts/link_sites.sh" in cmd


def test_link_sites_with_fewer_than_two_sites_explains_and_exits_0(tmp_path):
    root = tmp_path / "proj"
    (root / "scripts").mkdir(parents=True)
    (root / "sites").mkdir()
    for f in ("link_sites.sh", "board.sh"):
        (root / "scripts" / f).write_bytes(open(os.path.join(ROOT, "scripts", f), "rb").read().replace(b"\r\n", b"\n"))
    (root / "board.conf").write_text("BOARD_USER=arduino\nBOARD_HOST=100.64.0.1\nSITE=\n")
    (root / "sites" / "home.conf").write_text("BOARD_USER=arduino\nBOARD_HOST=100.64.0.1\n")
    (root / "sites" / "other.conf.example").write_text("BOARD_HOST=CHANGE-ME\n")
    env = dict(os.environ, HOME=str(tmp_path))
    r = subprocess.run(["bash", str(root / "scripts" / "link_sites.sh")], cwd=root, env=env, capture_output=True, text=True)
    assert r.returncode == 0 and "at least two" in r.stdout


# ---- the page ----

def test_page_switcher_banner_and_no_switcher_with_one_site(tmp_path):
    """Needs Playwright and Chrome (like tests/test_r17_page.py); skipped where they are missing."""
    sync_api = pytest.importorskip("playwright.sync_api", reason="playwright not installed")
    import shutil
    import time
    import urllib.request
    port = 18086
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"))
    p = subprocess.Popen([sys.executable, "-m", "overheard", "--demo", "--port", str(port), "--host", "127.0.0.1", "--no-auth", "--data-dir", str(tmp_path)],
                         env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/api/health" % port, timeout=2)
                break
            except OSError:
                time.sleep(0.2)
        time.sleep(3)
        stats = urllib.request.urlopen("http://127.0.0.1:%d/api/stats" % port, timeout=5).read()
        with sync_api.sync_playwright() as pw:
            exe = next((x for x in (os.environ.get("CHROME"), shutil.which("google-chrome"), shutil.which("chromium")) if x and os.path.exists(x)), None)
            try:
                b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
            except Exception as e:
                pytest.skip("no Chrome/Chromium: %s" % str(e)[:80])
            url = "http://127.0.0.1:%d/" % port
            one = b.new_context().new_page()                       # this board has no peers: nothing new on screen
            one.goto(url)
            one.wait_for_timeout(2500)
            assert not one.is_visible("#sites") and not one.is_visible("#siteBan")
            two = b.new_context().new_page()                       # a second site is listed: pills and a banner
            two.route("**/api/sites", lambda r: r.fulfill(content_type="application/json", body=json.dumps(
                {"site": "apartment", "sites": [{"name": "apartment", "self": True}, {"name": "home", "self": False, "ok": None, "age": None}]})))
            state = {"up": True}
            two.route("**/api/site?name=home", lambda r: r.fulfill(status=200, content_type="application/json", body=stats) if state["up"]
                      else r.fulfill(status=502, content_type="application/json", body=b'{"error":"site unreachable"}'))
            two.goto(url)
            two.wait_for_timeout(2500)
            assert two.is_visible("#sites") and not two.is_visible("#siteBan")
            two.click("#sites button[data-s=home]")
            two.wait_for_timeout(1800)
            assert "Viewing home (summary only, unlock on that board for detail)" in two.inner_text("#siteBan")
            assert not two.is_visible("#lockBtn") and not two.is_visible("#ledBtn")
            state["up"] = False
            two.wait_for_timeout(2500)
            assert "home is offline" in two.inner_text("#siteBan") and two.is_visible("#sites")
            two.click("#sites button[data-s='']")
            two.wait_for_timeout(1800)
            assert not two.is_visible("#siteBan") and two.is_visible("#lockBtn")
            b.close()
    finally:
        p.terminate()
        p.wait(timeout=10)


# ---- audit round: hard deadline, redirects, allowlist, the script ----

def drip_server(prefix, per=0.05):
    """Accepts, sends `prefix`, then one byte every `per` seconds for as long as the other side listens."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(5)
    stop = threading.Event()

    def feed(c):
        try:
            c.recv(4096)
            c.sendall(prefix)
            while not stop.is_set():
                c.sendall(b"x")
                time.sleep(per)
        except OSError:
            pass
        finally:
            c.close()

    def run():
        while not stop.is_set():
            try:
                threading.Thread(target=feed, args=(srv.accept()[0],), daemon=True).start()
            except OSError:
                return
    threading.Thread(target=run, daemon=True).start()
    return srv, stop


@pytest.mark.parametrize("prefix", [b"HTTP/1.1 200 OK\r\nX-Slow: ", b"HTTP/1.1 200 OK\r\nContent-Length: 100000\r\n\r\n{", b""])
def test_a_peer_that_drips_bytes_is_cut_off_at_the_deadline(tmp_path, prefix):
    srv, stop = drip_server(prefix)
    write_peers(tmp_path, [{"name": "home", "url": "http://127.0.0.1:%d" % srv.getsockname()[1], "key": KEY}])
    app = App(config.parse(["--demo", "--data-dir", str(tmp_path)]), State(), peers=P.load(str(tmp_path), loopback=True, timeout=0.4), secret="s" * 12)
    t0 = time.monotonic()
    assert get(app, "/api/site?name=home") == (502, b'{"error": "site unreachable"}')
    assert time.monotonic() - t0 < 2.0                   # deadline is 2 x 0.4 s; every byte arrives well inside the per-read timeout
    assert app.peers._p["home"].lock.acquire(blocking=False)      # and the peer's lock was released
    stop.set()
    srv.close()


def test_a_redirect_is_not_followed(tmp_path):
    other, seen2 = fake_peer({"dns": {"total": 1}})
    httpd, _ = fake_peer(b"", status=302, headers=[("Location", "http://127.0.0.1:%d/api/stats" % other.server_address[1])])
    app = front(tmp_path, httpd)
    assert get(app, "/api/site?name=home")[0] == 502
    assert seen2 == []
    httpd.shutdown()
    other.shutdown()


def test_an_unlocked_reply_from_a_real_board_cannot_carry_a_name_through(tmp_path):
    """The peer answers as if the caller had unlocked it: only what the locked view has is passed on."""
    from overheard.server import Req
    pst = State()
    doms = ("secret-site.example.org", "rr1---sn-abc.googlevideo.com", "swscan.apple.com", "www.youtube.com", "api.private-bank.example")
    for _ in range(4):
        for dm in doms:
            pst.record("10.0.0.5", dm, blocked=False, adult=False)
    pst.conns = [{"ip": "203.0.113.9", "host": "conn-host.example.net", "service": "Other", "count": 2, "bytes": 5}]
    papp = App(config.parse(["--demo", "--data-dir", str(tmp_path)]), pst, token=TOKEN, secret="p" * 12)
    unlocked = json.loads(papp.route("GET", "/api/stats", b"", Req("10.0.0.7", "ovu=" + papp.sessions.start()))[2])
    assert unlocked["unlocked"] is True and "secret-site.example.org" in json.dumps(unlocked) and unlocked["recent"]       # the fixture really is unlocked
    httpd, _ = fake_peer(unlocked)
    s, raw = get(front(tmp_path, httpd), "/api/site?name=home")
    out = raw.decode()
    assert s == 200 and json.loads(out)["unlocked"] is False and "settings" not in out
    for dm in doms + ("conn-host.example.net", "googlevideo", "private-bank"):
        assert dm not in out, dm
    httpd.shutdown()


def test_a_junk_shaped_reply_passes_nothing_but_known_fields(tmp_path):
    evil = "x.evil.example"
    junk = {"dns": {"enabled": evil, "total": "NAN_HERE", "blocked": True, "clients": "5", "upstream": evil, "extra": evil}, "host": evil,
            "adult": evil, "now": evil, "net": {"iface": evil, "gateway": evil, "addr": evil, "ssid": evil, "wireless": evil},
            "sys": {"cpu": evil, "temp": evil, "cpu_hist": [evil, 1], "other": evil}, "refused": [{"id": evil, "count": 1}], "evil-key": evil,
            "rx": evil, "tx": 5, "recent": [evil, {"domain": evil}], "unlocked": evil, "settings": evil,
            "conns": [evil, {"ip": evil, "host": evil, "service": evil, "count": evil, "bytes": 1, "extra": evil}],
            "devices": [evil, {"id": evil, "label": evil, "rows": [evil]},
                        {"id": "10.0.0.5", "label": evil, "confidence": evil, "evidence": [evil], "now": evil, "extra": evil, "shared": evil, "lookups": evil,
                         "rows": [evil, {"service": evil, "v": [evil]}, {"service": "Adult content", "v": [1]}, {"service": "YouTube", "v": [evil, 2], "x": evil}]}]}
    body = json.dumps(junk).replace('"NAN_HERE"', "NaN").encode()          # NaN is not JSON, but json.loads accepts it: it must not come out
    httpd, _ = fake_peer(body)
    s, raw = get(front(tmp_path, httpd), "/api/site?name=home")
    d = json.loads(raw, parse_constant=lambda c: pytest.fail("non-JSON number passed on"))
    assert s == 200 and "evil" not in raw.decode() and d["unlocked"] is False
    assert d["dns"] == {"enabled": False, "total": 0, "blocked": 0, "clients": 0, "upstream": "idle"} and d["tx"] == 5 and d["rx"] == 0
    assert d["conns"] == [{"ip": "", "service": "Other", "count": 0, "bytes": 1}] and d["net"] == {} and d["sys"]["cpu_hist"] == [0, 1]
    assert d["devices"] == [{"id": "10.0.0.5", "label": "Device", "confidence": "none", "evidence": [], "shared": False, "last": 0, "lookups": 0, "rate": 0,
                             "now": None, "rows": [{"service": "YouTube", "v": [0, 2]}]}]
    assert set(d) == {"host", "demo", "uptime", "t0", "step", "dns", "adult", "now", "devices", "rx", "tx", "recent", "conns", "refused", "net", "sys",
                      "unlocked", "site"}
    httpd.shutdown()


def test_a_normal_locked_reply_passes_through_intact(tmp_path):
    """What an unchanged board really sends (stats.build_stats, locked) comes through unchanged apart from the network name (ssid)."""
    from overheard.stats import build_stats
    from overheard.sysinfo import Vitals
    st = State()
    st.record("10.0.0.5", "swscan.apple.com", blocked=False, adult=False)
    st.conns = [{"ip": "203.0.113.9", "service": "Other", "count": 2, "bytes": 5}]
    v = Vitals()
    v.latest = {"cpu": 3.5, "cores": 4, "mem_used": 1, "mem_total": 2, "temp": None, "disk_used": 1, "disk_total": 2, "load": 0.1, "uptime": 9.0}
    v.net = {"iface": "wlan0", "gateway": "192.168.1.1", "addr": "192.168.1.2", "wireless": True, "ssid": "Home"}
    real = {**build_stats(st, config.parse(["--demo"]), None, v, full=False), "unlocked": False}
    httpd, _ = fake_peer(real)
    d = json.loads(get(front(tmp_path, httpd), "/api/site?name=home")[1])
    del d["site"]
    want = json.loads(json.dumps(real))
    want["net"].pop("ssid")
    want["host"] = ""                                                   # the peer's hostname is dropped on purpose
    for x, y in zip(d["devices"], want["devices"], strict=True):        # the "this board" placeholder has fewer fields; the page copes, we only add defaults
        assert {k: x[k] for k in y} == y
    d["devices"] = want["devices"] = []
    assert d == want
    httpd.shutdown()


# ---- Link Sites against a stubbed ssh ----

needs_bash = pytest.mark.skipif(not shutil.which("bash"), reason="bash not available")
STUB = """#!/usr/bin/env bash
for a in "$@"; do case "$a" in *@*) host="${a#*@}";; esac; done
cmd="${@: -1}"
case "$FAKE_DOWN" in *" $host "*) exit 255;; esac
case "$cmd" in
  "cat ~/netmon/data/token") printf 'tok_%s_padpad' "${host//./_}";;
  "umask 077"*) case "$FAKE_WFAIL" in *" $host "*) exit 1;; esac; cat > "$FAKE_OUT/$host.json";;
  "sudo systemctl restart overheard.service") touch "$FAKE_OUT/$host.restart";;
esac
"""


def link_run(tmp_path, hosts, down="", wfail=""):
    """Runs scripts/link_sites.sh in a scratch project with one site per entry of `hosts` and a stub ssh on PATH."""
    root, out, fb = tmp_path / "proj", tmp_path / "out", tmp_path / "bin"
    for d in (root / "scripts", root / "sites", out, fb):
        d.mkdir(parents=True, exist_ok=True)
    for f in ("link_sites.sh", "board.sh"):
        (root / "scripts" / f).write_bytes(open(os.path.join(ROOT, "scripts", f), "rb").read().replace(b"\r\n", b"\n"))
    (root / "board.conf").write_text("BOARD_USER=arduino\nBOARD_HOST=100.64.0.1\nSITE=\n")
    (root / "sites" / "zz.conf.example").write_text("BOARD_HOST=CHANGE-ME\n")
    for name, host in hosts.items():
        (root / "sites" / (name + ".conf")).write_text("BOARD_USER=arduino\nBOARD_HOST=%s\n" % host)
    (fb / "ssh").write_bytes(STUB.encode())
    os.chmod(fb / "ssh", 0o755)
    env = dict(os.environ, HOME=tmp_path.as_posix(), PATH=fb.as_posix() + os.pathsep + os.environ["PATH"], FAKE_OUT=out.as_posix(), FAKE_DOWN=down, FAKE_WFAIL=wfail)
    r = subprocess.run(["bash", (root / "scripts" / "link_sites.sh").as_posix()], cwd=root, env=env, capture_output=True, text=True, timeout=60)
    result = tmp_path / "Desktop" / "ArduinoQ" / "last-link-sites.txt"
    return r, out, result.read_text() if result.exists() else ""


@needs_bash
def test_link_sites_writes_each_board_the_others_and_never_shows_a_key(tmp_path):
    r, out, result = link_run(tmp_path, {"apartment": "100.64.0.1", "home": "100.64.0.2"})
    assert r.returncode == 0, r.stdout + r.stderr
    a = json.loads((out / "100.64.0.1.json").read_text())
    assert a == {"site": "apartment", "peers": [{"name": "home", "url": "http://100.64.0.2:8080", "key": "tok_100_64_0_2_padpad"}]}
    assert json.loads((out / "100.64.0.2.json").read_text())["peers"][0]["name"] == "apartment"
    assert (out / "100.64.0.1.restart").exists() and (out / "100.64.0.2.restart").exists()
    assert "apartment: ok" in result and "home: ok" in result
    assert "tok_" not in r.stdout + r.stderr + result       # keys appear only in the files the boards would receive
    shutil.copy(out / "100.64.0.1.json", tmp_path / "peers.json")
    os.chmod(tmp_path / "peers.json", 0o600)
    assert P.load(str(tmp_path)).summary()["sites"][1]["name"] == "home"      # and the board accepts what the script wrote


@needs_bash
def test_link_sites_writes_nothing_when_one_board_is_down(tmp_path):
    r, out, result = link_run(tmp_path, {"apartment": "100.64.0.1", "home": "100.64.0.2", "cabin": "100.64.0.3"}, down=" 100.64.0.3 ")
    assert r.returncode == 1 and not list(out.iterdir())
    assert "cabin: failed" in result and "Nothing was written" in result and "tok_" not in result


@needs_bash
@pytest.mark.parametrize("host", ["100.64.evil.com", "8.8.8.8", "100.128.0.1", "100.63.255.255", "100.64.0.1.5", "100.64.0.256", "100.064.0.2",
                                  "home.tail1234.ts.net", "192.168.1.5", "1" * 60])
def test_link_sites_skips_a_board_whose_host_is_not_a_tailscale_address(tmp_path, host):
    r, out, result = link_run(tmp_path, {"apartment": "100.64.0.1", "home": host})
    assert r.returncode == 1 and not list(out.iterdir())
    assert "home: skipped" in result and "Tailscale address" in result


def test_device_id_must_be_an_ip_or_the_board_marker_and_no_hostname_is_kept():
    """`cafe.bad.de` is all hex digits and dots, so a character-class check let it through as an "id"; ids are now parsed as IP addresses."""
    ids = ["cafe.bad.de", "dead.beef", "ab.cd", "fe80::1%eth0", "evil.example", "10.0.0.5", "this board", "2001:db8::1", "1.2.3"]
    d = P._locked({"dns": {}, "host": "peer-host", "devices": [{"id": i} for i in ids]})
    assert [x["id"] for x in d["devices"]] == ["10.0.0.5", "this board", "2001:db8::1"]
    assert d["host"] == ""


@needs_bash
def test_link_sites_reports_exactly_which_boards_were_written_when_a_later_write_fails(tmp_path):
    r, out, result = link_run(tmp_path, {"apartment": "100.64.0.1", "cabin": "100.64.0.3", "home": "100.64.0.2"}, wfail=" 100.64.0.3 ")
    assert r.returncode == 1
    assert "apartment: ok" in result and "cabin: failed (cannot write" in result and "home: not written" in result and "Stopped part-way" in result
    assert (out / "100.64.0.1.json").exists() and not (out / "100.64.0.3.json").exists() and not (out / "100.64.0.2.json").exists()
