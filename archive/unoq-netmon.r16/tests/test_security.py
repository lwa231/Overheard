"""Hostile input: malformed DNS packets, oversized or forged HTTP requests, bad settings."""
import http.client
import json
import threading

import pytest

from overheard import config, dnsproto, led as ledmod
from overheard.adult import AdultFilter, FlagLog, Guard, PenaltyBox
from overheard.blocklist import Blocklist
from overheard.dnsserver import DnsServer
from overheard.profiles import ProfileStore
from overheard.server import MAX_BODY, App, serve
from overheard.state import State


def G():
    return Guard(AdultFilter(), PenaltyBox(90), FlagLog("/tmp/ov-test-flags.json"))



def server(tmp_path, token=None):
    cfg = config.parse(["--demo", "--data-dir", str(tmp_path)])
    sprites = ledmod.load_sprites()
    app = App(cfg, State(), ProfileStore(cfg.db_path, everyone=True), ledmod.LedState(str(tmp_path / "led.json"), sprites), sprites, token)
    httpd = serve(app, "127.0.0.1", 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def post(httpd, body, headers=None, length=None):
    c = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=5)
    h = {"Content-Type": "application/json", **(headers or {})}
    if length is not None:
        h["Content-Length"] = str(length)
    c.putrequest("POST", "/api/led", skip_accept_encoding=True)
    for k, v in h.items():
        c.putheader(k, v)
    if length is None:
        c.putheader("Content-Length", str(len(body)))
    c.endheaders(body)
    r = c.getresponse()
    return r.status


def test_http_rejects_forged_and_oversized_requests(tmp_path):
    httpd = server(tmp_path)
    try:
        ok = json.dumps({"brightness": 100}).encode()
        assert post(httpd, ok) == 200
        assert post(httpd, ok, {"Content-Type": "text/plain"}) == 403                 # simple cross-site form post
        assert post(httpd, ok, {"Origin": "http://evil.example"}) == 403              # another site's page
        assert post(httpd, ok, {"Origin": "http://127.0.0.1:%d" % httpd.server_address[1]}) == 200
        assert post(httpd, b"", length=MAX_BODY + 1) == 413
        assert post(httpd, b"", length="abc") == 400
        assert post(httpd, b"[1,2]") == 400                                           # JSON but not an object
        assert post(httpd, b'{"brightness": true}') == 400
        assert post(httpd, b'{"brightness": "9"}') == 400
        assert post(httpd, b'{"character": 5}') == 400
        assert post(httpd, b'{"brightness": NaN}') == 400
    finally:
        httpd.shutdown()


def test_unknown_methods_and_paths_do_not_leak(tmp_path):
    httpd = server(tmp_path)
    try:
        c = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=5)
        for path in ("/../../etc/passwd", "/%2e%2e/%2e%2e/etc/passwd", "/api/profile?id=%27%20OR%201%3D1%20--", "/web/index.html"):
            c.request("GET", path)
            r = c.getresponse()
            body = r.read()
            assert b"root:" not in body
            assert r.status in (200, 400, 403, 404)      # 403: the profile lookup needs the unlock session
    finally:
        httpd.shutdown()


def test_sql_injection_attempt_is_just_an_unknown_device(tmp_path):
    cfg = config.parse(["--data-dir", str(tmp_path)])
    store = ProfileStore(cfg.db_path, everyone=True)
    p = store.profile("x' OR '1'='1")
    assert p["total"] == 0


BAD = [b"", b"\x00", b"\x00" * 11, b"\xff" * 12 + b"\x00\x00\x01\x00\x01",
       dnsproto.build_query("a.b")[:-3],                                     # truncated question
       b"\x12\x34\x01\x00\x00\x02\x00\x00\x00\x00\x00\x00\x01a\x00\x00\x01\x00\x01",   # QDCOUNT 2
       b"\x12\x34\x81\x80\x00\x01\x00\x00\x00\x00\x00\x00\x01a\x00\x00\x01\x00\x01",   # a response, not a query
       b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\xc0\x0c\x00\x01\x00\x01",    # compression pointer in a question
       b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00" + bytes([64]) + b"a" * 64 + b"\x00\x00\x01\x00\x01",   # label > 63
       b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x03a\x00b\x00\x00\x01\x00\x01"]   # NUL smuggled in a label


@pytest.mark.parametrize("pkt", BAD)
def test_dns_server_never_crashes_or_forwards_garbage(pkt):
    forwarded = []
    srv = DnsServer(config.parse([]), State(), Blocklist({"ads.com"}), lambda p: forwarded.append(p) or p, G())
    srv.handle_packet(pkt, "10.0.0.2")      # must not raise
    assert not forwarded


def test_blocked_names_cannot_hide_behind_case_or_trailing_dot():
    b = Blocklist({"ads.com"})
    assert b.is_blocked("ADS.com") and b.is_blocked("x.ads.com.")


def test_blocked_reply_keeps_id_and_rd_bit():
    q = bytearray(dnsproto.build_query("x.ads.com"))
    q[2] = 0x01
    name, qt, end = dnsproto.parse_question(bytes(q))
    r = dnsproto.blocked_reply(bytes(q), qt, end)
    assert r[:2] == bytes(q[:2]) and r[2] & 0x81 == 0x81


def _fake_upstream(replies):
    """UDP server that answers every query with the given list of (id_override or None) replies."""
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))

    def run():
        pkt, addr = sock.recvfrom(4096)
        for override in replies:
            sock.sendto((override or pkt[:2]) + b"\x81\x80" + pkt[4:], addr)
    threading.Thread(target=run, daemon=True).start()
    return sock.getsockname()[1]


def test_upstream_ignores_a_forged_id_and_takes_the_real_answer():
    from overheard.upstream import Forwarder
    port = _fake_upstream([b"\x00\x00", None])
    cfg = config.parse(["--no-tls", "--upstream", "127.0.0.1", "--upstream-port", str(port)])
    q = dnsproto.build_query("ok.org", txid=0x4242)
    assert Forwarder(cfg, {"tls": 0, "plain": 0})(q)[:2] == q[:2]


def test_upstream_with_only_forged_answers_fails():
    from overheard.upstream import Forwarder
    port = _fake_upstream([b"\x00\x00", b"\x00\x01", b"\x00\x02", b"\x00\x03"])
    cfg = config.parse(["--no-tls", "--upstream", "127.0.0.1", "--upstream-port", str(port)])
    with pytest.raises(ConnectionError):
        Forwarder(cfg, {"tls": 0, "plain": 0})(dnsproto.build_query("ok.org", txid=0x4242))


def test_inflight_limit_drops_instead_of_spawning_threads():
    from overheard.dnsserver import MAX_INFLIGHT
    srv = DnsServer(config.parse([]), State(), Blocklist(), lambda p: p, G())
    for _ in range(MAX_INFLIGHT):
        assert srv._slots.acquire(blocking=False)
    assert not srv._slots.acquire(blocking=False)


def test_dashboard_requires_the_key(tmp_path):
    token = "k" * 32
    httpd = server(tmp_path, token)
    try:
        c = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=5)
        for path in ("/", "/api/stats", "/api/profiles", "/api/led", "/skins.js", "/3ds"):
            c.request("GET", path)
            r = c.getresponse()
            r.read()
            assert r.status == 401, path
        c.request("GET", "/api/health")
        assert c.getresponse().status == 200
        c.request("GET", "/?key=" + "x" * 32)
        r = c.getresponse()
        r.read()
        assert r.status == 401
        c.request("GET", "/?key=" + token)
        r = c.getresponse()
        r.read()
        assert r.status == 302 and "HttpOnly" in r.getheader("Set-Cookie") and "SameSite=Strict" in r.getheader("Set-Cookie")
        cookie = r.getheader("Set-Cookie").split(";")[0]
        c.request("GET", "/api/stats", headers={"Cookie": cookie})
        r = c.getresponse()
        r.read()
        assert r.status == 200
        c.request("POST", "/api/led", body=b"{}", headers={"Content-Type": "application/json"})
        r = c.getresponse()
        r.read()
        assert r.status == 401
    finally:
        httpd.shutdown()


def test_token_is_created_private_and_stable(tmp_path):
    import os
    import stat
    from overheard import auth
    t = auth.load_token(str(tmp_path))
    assert len(t) >= 20 and auth.load_token(str(tmp_path)) == t
    assert stat.S_IMODE(os.stat(tmp_path / "token").st_mode) == 0o600


def test_dns_is_not_an_open_resolver():
    srv = DnsServer(config.parse([]), State(), Blocklist(), lambda p: p, G())
    assert srv.permitted("192.168.1.9") and srv.permitted("100.69.33.5")
    assert not srv.permitted("8.8.8.8") and not srv.permitted("2001:db8::1") and not srv.permitted("junk")


def test_dns_rate_limit_per_client():
    srv = DnsServer(config.parse(["--rate", "5"]), State(), Blocklist(), lambda p: p, G())
    allowed = sum(srv.permitted("10.0.0.2") for _ in range(50))
    assert 8 <= allowed <= 12                       # burst of 2x rate, then refused
    assert srv.permitted("10.0.0.3")                # other clients are unaffected


def test_allow_list_override():
    srv = DnsServer(config.parse(["--allow", "10.1.0.0/16"]), State(), Blocklist(), lambda p: p, G())
    assert srv.permitted("10.1.2.3") and not srv.permitted("192.168.1.9")


def test_allow_extra_adds_to_defaults():
    srv = DnsServer(config.parse(["--allow-extra", "203.0.113.254/32"]), State(), Blocklist(), lambda p: p, G())
    assert srv.permitted("203.0.113.254") and srv.permitted("192.168.1.9") and not srv.permitted("8.8.8.8")


def test_failed_tls_upstream_is_skipped_for_a_while_instead_of_slowing_every_lookup():
    from overheard.upstream import DOT_RETRY_S, Forwarder
    f = Forwarder(config.parse([]), {"tls": 0, "plain": 0})
    now, calls = [100.0], []
    f.clock = lambda: now[0]

    def dot(pkt):
        calls.append("dot")
        raise OSError("port 853 blocked")
    f._dot = dot
    f._plain = lambda pkt: b"plain-answer"
    assert f(b"q") == b"plain-answer" and calls == ["dot"]
    assert f(b"q") == b"plain-answer" and calls == ["dot"]        # TLS not retried right away
    now[0] += DOT_RETRY_S + 1
    f(b"q")
    assert calls == ["dot", "dot"]                                 # retried after the pause


def test_tcp_queries_that_arrive_in_pieces_are_answered():
    import socket as so
    import time
    from overheard.adult import AdultFilter, FlagLog, Guard, PenaltyBox
    s = so.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    cfg = config.parse(["--bind", "127.0.0.1", "--dns-port", str(port)])
    srv = DnsServer(cfg, State(), Blocklist({"ads.example"}), lambda p: p, Guard(AdultFilter(), PenaltyBox(90), FlagLog("/tmp/ov-test-flags.json")))
    assert srv.start() is None
    q = dnsproto.build_query("ads.example")
    c = so.create_connection(("127.0.0.1", port), timeout=3)
    framed = len(q).to_bytes(2, "big") + q
    for i in range(len(framed)):                       # one byte at a time
        c.sendall(framed[i:i + 1])
        time.sleep(0.005)
    head = c.recv(2)
    assert len(head) == 2 and int.from_bytes(head, "big") > 12
    c.close()


def test_responses_are_never_answered():
    srv = DnsServer(config.parse([]), State(), Blocklist(), lambda p: p, G())
    resp = bytearray(dnsproto.build_query("x.org"))
    resp[2] |= 0x80
    assert srv.handle_packet(bytes(resp), "192.168.1.5") is None


def test_big_udp_answers_are_truncated_so_clients_retry_over_tcp():
    q = dnsproto.build_query("big.example")
    big = q[:2] + b"\x81\x80" + q[4:6] + b"\x00\x01\x00\x00\x00\x00" + q[12:] + b"x" * 3000
    t = dnsproto.truncated_reply(big)
    assert len(t) < 100 and t[2] & 0x02 and t[:2] == q[:2]


def test_bad_flag_file_cannot_disable_the_penalty_box(tmp_path):
    from overheard.adult import AdultFilter, FlagLog, Guard, PenaltyBox
    p = tmp_path / "f.json"
    p.write_text('{"bad.com": {"nonsense": 1}}')
    g = Guard(AdultFilter({"bad.com"}), PenaltyBox(90), FlagLog(str(p)))
    assert g.hit("10.0.0.2", "bad.com") == "list" and g.penalty.remaining("10.0.0.2") > 0


def test_empty_adult_list_file_is_refetched_not_trusted(tmp_path, monkeypatch):
    from overheard import adult
    (tmp_path / "adult.txt").write_text("")
    tried = []

    def offline(url, timeout=0):
        tried.append(url)
        raise OSError("offline")
    monkeypatch.setattr(adult.urllib.request, "urlopen", offline)
    got = []
    adult.AdultFilter.load(str(tmp_path), log=got.append)
    assert len(tried) == len(adult.SOURCES) and any("incomplete" in m for m in got)
    assert (tmp_path / "adult.txt").read_text() == ""            # an empty download never replaces anything


def test_safesearch_covers_country_google_names_and_leaves_youtube_alone():
    from overheard import safesearch
    for n in ("google.co.uk", "www.google.ca", "google.com.au", "www.google.de"):
        assert safesearch.target(n) == "forcesafesearch.google.com"
    assert safesearch.target("music.youtube.com") is None and safesearch.target("youtube.com") is None
    assert safesearch.target("googleapis.com") is None


def test_dashboard_rejects_unknown_host_names(tmp_path):
    import http.client
    from overheard.server import serve
    cfg = config.parse(["--no-auth", "--data-dir", str(tmp_path)])
    app = App(cfg, __import__("overheard.state", fromlist=["State"]).State(), None, ledmod.LedState("/tmp/ov-led-h.json", {"x": []}), {"x": []}, None, None)
    httpd = serve(app, "127.0.0.1", 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]
    for host, code in (("evil.example.com", 421), ("127.0.0.1:%d" % port, 200), ("localhost", 200)):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        c.putrequest("GET", "/api/health", skip_host=True)
        c.putheader("Host", host)
        c.endheaders()
        assert c.getresponse().status == code, host
    httpd.shutdown()
