"""r16 hardening: parser fuzz, hostile DNS/HTTP input, secrets handling, adult guard immutability."""
import dataclasses
import glob
import http.client
import json
import os
import random
import re
import socket
import stat
import struct
import threading
import time
from email.message import Message

import pytest

from overheard import auth, config, dnsproto, led as ledmod, server as srvmod
from overheard.adult import AdultFilter, FlagLog, Guard, PenaltyBox
from overheard.blocklist import Blocklist
from overheard.dnsserver import UDP_MAX, DnsServer
from overheard.profiles import ProfileStore
from overheard.server import App, Req, make_handler, serve
from overheard.state import State

SRC = os.path.join(os.path.dirname(__file__), "..", "src", "overheard")
TOKEN, SECRET = "t" * 32, "correct-horse"


# ---------- 1. parser fuzz ----------
def _mutants(rng, n):
    seeds = [dnsproto.build_query("www.example.com"), dnsproto.build_query("a.b.c.d.e.f.g.h.example.org", 28),
             dnsproto.blocked_reply(dnsproto.build_query("x.example"), 1, 12 + 11)]
    for i in range(n):
        k = i % 5
        if k == 0:
            yield bytes(rng.getrandbits(8) for _ in range(rng.randrange(0, 600)))
        elif k == 1:                                   # bit flips
            b = bytearray(rng.choice(seeds))
            for _ in range(rng.randrange(1, 6)):
                b[rng.randrange(len(b))] ^= 1 << rng.randrange(8)
            yield bytes(b)
        elif k == 2:                                   # truncation
            yield rng.choice(seeds)[:rng.randrange(0, 40)]
        elif k == 3:                                   # compression pointer loops / forward pointers / oversize labels
            hdr = struct.pack("!HHHHHH", rng.getrandbits(16), rng.choice((0x0100, 0x8180, 0x0000)), rng.choice((1, 1, 0, 65535)), rng.choice((0, 1, 65535)), 0, 0)
            body = bytes([0xC0 | rng.randrange(4), 12 + rng.randrange(3)]) * rng.randrange(1, 5) + bytes([rng.choice((0, 63, 64, 255))]) + b"a" * rng.randrange(0, 80)
            yield hdr + body + struct.pack("!HH", 1, 1)
        else:                                          # many labels, bad counts
            lab = b"".join(bytes([rng.randrange(1, 64)]) + b"a" * rng.randrange(0, 70) for _ in range(rng.randrange(1, 90)))
            yield struct.pack("!HHHHHH", 1, 0x0100, 1, rng.randrange(0, 70000) & 0xFFFF, 0, 0) + lab + b"\x00\x00\x01\x00\x01"


def test_dnsproto_fuzz_never_raises_or_stalls():
    rng, t0, n = random.Random(1616), time.monotonic(), 0
    for pkt in _mutants(rng, 20000):
        n += 1
        try:
            name, qt, end = dnsproto.parse_question(pkt)
        except dnsproto.BadPacket:
            pass
        else:
            assert end <= len(pkt) and len(name) <= 270
            assert len(dnsproto.blocked_reply(pkt, qt, end)) <= end + 16
            assert len(dnsproto.truncated_reply(dnsproto.blocked_reply(pkt, qt, end))) <= end + 1
        assert len(dnsproto.formerr(pkt)) == 12
        out, ips = dnsproto.process_reply(pkt, 30)            # treats the packet as an upstream answer
        assert isinstance(out, bytes) and isinstance(ips, list)
        dnsproto.truncated_reply(pkt) if len(pkt) >= 12 else None
    assert n == 20000 and time.monotonic() - t0 < 15


def test_build_query_roundtrip_and_pointer_loop_is_bad():
    assert dnsproto.parse_question(dnsproto.build_query("A.Example.COM", 28))[:2] == ("a.example.com", 28)
    loop = struct.pack("!HHHHHH", 1, 0x0100, 1, 0, 0, 0) + b"\xc0\x0c" + b"\x00\x01\x00\x01"
    with pytest.raises(dnsproto.BadPacket):
        dnsproto.parse_question(loop)
    looped_answer = struct.pack("!HHHHHH", 1, 0x8180, 0, 1, 0, 0) + b"\xc0\x0c" + b"\x00" * 12
    assert dnsproto.process_reply(looped_answer, 30)[1] == []


# ---------- 2. DNS server ----------
def _dns(tmp_path, forward=None, **kw):
    cfg = dataclasses.replace(config.parse(["--data-dir", str(tmp_path)]), rate=10 ** 6, **kw)
    guard = Guard(AdultFilter({"badsite.example"}), PenaltyBox(90), FlagLog(str(tmp_path / "f.json")))
    return DnsServer(cfg, State(), Blocklist(), forward or (lambda p: p), guard)


def test_handle_packet_survives_fuzz_and_never_answers_responses(tmp_path):
    srv, rng = _dns(tmp_path), random.Random(7)
    for pkt in _mutants(rng, 6000):
        r = srv.handle_packet(pkt, "10.0.0.5")
        if len(pkt) >= 3 and pkt[2] & 0x80:
            assert r is None, "a response (QR=1) must never be answered"
        if r is not None:
            assert len(r) <= 4096
    resp = dnsproto.blocked_reply(dnsproto.build_query("x.example"), 1, 23)
    assert srv.handle_packet(resp, "10.0.0.5") is None and srv.handle_packet(resp[:5], "10.0.0.5") is None


def test_non_allowed_sources_get_silence(tmp_path):
    srv = _dns(tmp_path)
    q = dnsproto.build_query("example.org")
    for ip in ("8.8.8.8", "203.0.113.1", "2001:db8::1", "garbage", "", "100.63.255.255", "172.32.0.1"):
        assert srv.handle_packet(q, ip) is None and srv.handle_packet(b"\x00" * 30, ip) is None
    assert srv.handle_packet(q, "192.168.1.9") == q


def test_udp_reply_is_bounded_against_amplification(tmp_path):
    big = lambda p: p[:2] + b"\x81\x80" + p[4:] + b"\x00" * 4000      # noqa: E731 hostile upstream: huge answer
    srv = _dns(tmp_path, big)
    sent = []
    sock = type("S", (), {"sendto": lambda self, d, a: sent.append(d)})()
    q = dnsproto.build_query("example.org")
    srv._slots.acquire()
    srv._udp_one(sock, q, ("10.0.0.5", 5353))
    assert sent and len(sent[0]) <= UDP_MAX and sent[0][2] & 0x02          # TC set, so the client retries over TCP
    assert len(sent[0]) <= 8 * len(q) + 40                                 # TC reply is header+question only
    for pkt in (b"\x00" * 12, b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00", dnsproto.build_query("a" * 63)):
        assert len(srv.handle_packet(pkt, "10.0.0.5") or b"") <= len(pkt) + 4000 + 4


def _udp_tcp_server(tmp_path, **kw):
    srv = _dns(tmp_path, **kw)
    cfg = dataclasses.replace(srv.cfg, bind="127.0.0.1", dns_port=0)
    srv.cfg = cfg
    u, t = srv._bind()
    port = t.getsockname()[1]
    # UDP and TCP may bind different ports with port 0, so rebind UDP on the TCP port
    u.close()
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    u.bind(("127.0.0.1", port))
    threading.Thread(target=srv.serve_tcp, args=(t,), daemon=True).start()
    threading.Thread(target=srv.serve_udp, args=(u,), daemon=True).start()
    return srv, port


def test_loops_survive_hostile_traffic_over_real_sockets(tmp_path):
    srv, port = _udp_tcp_server(tmp_path)
    c = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    c.settimeout(3)
    for pkt in list(_mutants(random.Random(3), 300)) + [b"", b"\x00"]:
        c.sendto(pkt, ("127.0.0.1", port))
    time.sleep(0.5)
    good = dnsproto.build_query("example.org")
    c.sendto(good, ("127.0.0.1", port))
    got = None
    try:
        while True:
            got = c.recv(4096)
            if got == good:
                break
    except TimeoutError:
        pass
    assert got == good, "UDP loop died"
    for junk in (b"\xff\xff" + b"x" * 50, b"\x00\x00", b"\x00\x05abc", b""):       # TCP: bad length prefixes, truncation, garbage
        s = socket.create_connection(("127.0.0.1", port), timeout=3)
        s.sendall(junk)
        s.close()
    s = socket.create_connection(("127.0.0.1", port), timeout=3)
    s.sendall(struct.pack("!H", len(good)) + good)
    assert s.recv(2) == struct.pack("!H", len(good))
    s.close()


def test_tcp_drip_feed_is_cut_off_at_the_lifetime(tmp_path, monkeypatch):
    from overheard import dnsserver
    monkeypatch.setattr(dnsserver, "TCP_LIFETIME", 0.6)
    srv, port = _udp_tcp_server(tmp_path)
    s = socket.create_connection(("127.0.0.1", port), timeout=5)
    s.sendall(b"\x00\x40")                        # promise 64 bytes, then drip one byte at a time
    t0, closed = time.monotonic(), False
    try:
        while time.monotonic() - t0 < 4:
            s.sendall(b"a")
            time.sleep(0.2)
    except OSError:
        closed = True
    assert closed or s.recv(10) == b""
    assert time.monotonic() - t0 < 3


# ---------- 3. HTTP ----------
@pytest.fixture
def app(tmp_path):
    cfg = config.parse(["--demo", "--data-dir", str(tmp_path)])
    st = State()
    guard = Guard(AdultFilter({"badsite.example"}), PenaltyBox(90), FlagLog(str(tmp_path / "flags.json")), st.settings)
    sprites = ledmod.load_sprites()
    a = App(cfg, st, ProfileStore(cfg.db_path, everyone=True), ledmod.LedState(str(tmp_path / "led.json"), sprites), sprites, TOKEN, guard, secret=SECRET)
    st.record("10.0.0.5", "secret-site.example.org", False)
    return a


@pytest.fixture
def web(app):
    httpd = serve(app, "127.0.0.1", 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield app, httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def http_(port, method="GET", path="/api/stats", body=None, headers=None, cookie=True, host=None):
    h = {"Cookie": "ov=" + TOKEN} if cookie is True else ({"Cookie": cookie} if cookie else {})
    h.update(headers or {})
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.putrequest(method, path, skip_host=True)
    c.putheader("Host", host if host is not None else "127.0.0.1:%d" % port)
    for k, v in h.items():
        c.putheader(k, v)
    if body is not None:
        c.putheader("Content-Length", str(len(body)))
    c.endheaders(body)
    r = c.getresponse()
    return r.status, r.read(), r


JSON = {"Content-Type": "application/json"}


@pytest.mark.parametrize("host", ["evil.example", "127.0.0.1.evil.example", "", "localhost.evil.example:80", "attacker:8080:1", "[::1"])
def test_bad_host_header_is_421(web, host):
    _, port = web
    assert http_(port, host=host)[0] == 421


def test_origin_method_and_content_type_checks(web):
    app, port = web
    body = json.dumps({"secret": "x"}).encode()
    for origin in ("http://evil.example", "null", "http://127.0.0.1:1"):
        assert http_(port, "POST", "/api/unlock", body, {**JSON, "Origin": origin})[0] == 403
    assert http_(port, "POST", "/api/unlock", body, {"Content-Type": "text/plain"})[0] == 403
    assert http_(port, "POST", "/api/unlock", body, {})[0] == 403
    for m in ("PUT", "DELETE", "PATCH", "OPTIONS", "HEAD", "TRACE"):
        assert http_(port, m, "/api/settings", b"{}" if m in ("PUT", "PATCH") else None, JSON)[0] in (501, 405)
    assert http_(port, "GET", "/api/unlock")[0] == 404 and http_(port, "GET", "/api/settings")[0] == 404
    assert http_(port, "POST", "/api/unlock", body, {**JSON, "Origin": "http://127.0.0.1:%d" % port})[0] == 403    # wrong secret, passed origin


def test_oversize_and_bad_length_bodies(web):
    _, port = web
    assert http_(port, "POST", "/api/unlock", b"x" * (srvmod.MAX_BODY + 1), JSON)[0] == 413
    for n in ("-5", "abc", "99999999999999999999"):
        s = socket.create_connection(("127.0.0.1", port), timeout=3)
        s.sendall(("POST /api/unlock HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nCookie: ov=%s\r\nContent-Type: application/json\r\nContent-Length: %s\r\n\r\n" % (port, TOKEN, n)).encode())
        assert s.recv(100).split()[1] in (b"400", b"413")
        s.close()


def test_deeply_nested_json_is_a_400_not_a_crash(app):
    deep = b"[" * 3000
    assert app.route("POST", "/api/unlock", deep, Req("10.0.0.5"))[0] == 400
    sid = TestHelper.unlock(app)
    assert app.route("POST", "/api/settings", deep, Req("10.0.0.5", "ovu=" + sid))[0] == 400
    assert app.route("POST", "/api/led", deep, Req("10.0.0.5"))[0] == 400


def test_slow_partial_request_is_dropped(app, monkeypatch):
    monkeypatch.setattr(srvmod, "REQ_TIMEOUT", 0.5)
    httpd = serve(app, "127.0.0.1", 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        s = socket.create_connection(("127.0.0.1", httpd.server_address[1]), timeout=5)
        s.sendall(b"GET /api/stats HTTP/1.1\r\nHost: loc")           # never finishes
        t0 = time.monotonic()
        assert s.recv(100) == b""                                    # server hung up
        assert time.monotonic() - t0 < 3
        # per-address cap still lets a normal client in
        assert http_(httpd.server_address[1], "GET", "/api/health", cookie=False)[0] == 200
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_slow_drip_request_is_cut_off_at_the_deadline(app, monkeypatch):
    monkeypatch.setattr(srvmod, "REQ_DEADLINE", 0.6)
    httpd = serve(app, "127.0.0.1", 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        s = socket.create_connection(("127.0.0.1", httpd.server_address[1]), timeout=5)
        s.sendall(b"GET /api/stats HTTP/1.1\r\nX-A: ")
        t0, closed = time.monotonic(), False
        try:
            while time.monotonic() - t0 < 4:          # a byte every 0.2s stays inside REQ_TIMEOUT
                s.sendall(b"a")
                time.sleep(0.2)
        except OSError:
            closed = True
        assert closed or s.recv(10) == b""
        assert time.monotonic() - t0 < 3
    finally:
        httpd.shutdown()
        httpd.server_close()


@pytest.mark.parametrize("path", ["/../../etc/passwd", "/%2e%2e/%2e%2e/etc/passwd", "/skins.css/../../server.py", "//etc/passwd", "/web/index.html", "/static/../server.py",
                                  "/skins.js%00", "/..%2fserver.py", "/api/../server.py", "/3ds/../../__init__.py"])
def test_path_traversal_serves_nothing_else(web, path):
    _, port = web
    s, body, _ = http_(port, "GET", path)
    assert s == 404 or body[:1] == b"{" or path in ("/web/index.html",) and s == 404
    assert b"import " not in body and b"root:" not in body


def test_cookie_forgery_and_gate(web):
    app, port = web
    assert http_(port, cookie=False)[0] == 401
    for ck in ("ov=" + TOKEN[:-1], "ov=", "ov=" + TOKEN + "x", "ovu=" + TOKEN, "ov=%s%s" % ("", TOKEN.upper()), "x=ov=" + TOKEN):
        assert http_(port, cookie=ck)[0] == 401, ck
    for ck in ("ov=" + TOKEN + "; ovu=forged", "ov=%s; ovu=" % TOKEN, "ov=%s; ovu=%s" % (TOKEN, "A" * 5000), "ov=%s; ovu=../x; ovu=y" % TOKEN):
        s, body, _ = http_(port, cookie=ck)
        assert s == 200 and json.loads(body)["unlocked"] is False and b"secret-site" not in body
    for p in ("/api/flagged", "/api/profiles", "/api/profile?id=x"):
        assert http_(port, "GET", p, cookie="ov=%s; ovu=forged" % TOKEN)[0] == 403
    s, _, r = http_(port, "GET", "//evil.example/?key=" + TOKEN, cookie=False)
    assert s == 302 and r.getheader("Location").startswith("/") and not r.getheader("Location").startswith("//")


class TestHelper:
    @staticmethod
    def unlock(app, addr="10.0.0.7", secret=SECRET):
        req = Req(addr)
        s, _, raw = app.route("POST", "/api/unlock", json.dumps({"secret": secret}).encode(), req)
        return req.headers[0][1].split(";")[0].split("=", 1)[1] if s == 200 else None


def test_unlock_brute_force_limit_is_per_address_and_cookie_independent(app):
    for i in range(5):
        r = Req("10.0.0.9", "ovu=rot%d; ov=%s" % (i, TOKEN))                  # rotating cookies buys nothing
        assert app.route("POST", "/api/unlock", b'{"secret":"no"}', r)[0] == 403
    assert TestHelper.unlock(app, "10.0.0.9") is None                           # even the right secret is refused now
    assert app.route("POST", "/api/unlock", b'{"secret":"no"}', Req("10.0.0.9"))[0] == 429
    assert TestHelper.unlock(app, "10.0.0.10") is not None                      # another address is unaffected


def test_failure_table_and_sessions_are_bounded_and_expire():
    t = [0.0]
    fl = auth.FailureLimit(clock=lambda: t[0])
    for i in range(5000):
        fl.fail("a%d" % i)
    assert len(fl._f) <= auth.MAX_TRACKED
    for _ in range(5):
        fl.fail("victim")
    assert fl.blocked("victim")
    t[0] += auth.FAIL_WINDOW + 1
    assert not fl.blocked("victim")
    ss = auth.Sessions(clock=lambda: t[0])
    ids = [ss.start() for _ in range(100)]
    assert len(ss._s) <= auth.MAX_SESSIONS and ss.valid(ids[-1]) and not ss.valid(ids[0])
    t[0] += auth.SESSION_TTL + 1
    assert not any(ss.valid(i) for i in ids) and not ss.valid("") and not ss.valid(None)


def test_settings_type_confusion(app):
    sid = TestHelper.unlock(app)
    bad = [b"[]", b"null", b"1", b'"slowdown"', b"{}", b'{"slowdown": 1}', b'{"slowdown": "true"}', b'{"slowdown": null}', b'{"slowdown": [true]}',
           b'{"slowdown": true, "adult": false}', b'{"adult": true}', b'{"slowdown": true, "penalty_s": 0}', b'{"__class__": true}', b"\xff\xfe", b'{"slowdown": true', b'{"a": {"b": 1}}']
    for b in bad:
        assert app.route("POST", "/api/settings", b, Req("10.0.0.7", "ovu=" + sid))[0] == 400, b
        assert app.state.settings.slowdown is False
    assert app.route("POST", "/api/settings", b'{"slowdown": true}', Req("10.0.0.7"))[0] == 403
    assert app.route("POST", "/api/settings", b'{"slowdown": true}', Req("10.0.0.7", "ovu=" + sid))[0] == 200 and app.state.settings.slowdown is True


def test_led_type_confusion(app):
    for b in (b'{"character": []}', b'{"character": {"a":1}}', b'{"brightness": "x"}', b'{"brightness": [1]}', b'{"brightness": true}', b"[1]", b'{"character": 5}'):
        assert app.route("POST", "/api/led", b, Req("10.0.0.5"))[0] == 400, b


def test_doctor_header_spoofing(app):
    app.token = TOKEN
    h = make_handler(app)
    def doctor(client, **hd):
        o = object.__new__(h)
        o.client_address = (client, 1)
        o.headers = Message()
        for k, v in {"X-Overheard-Doctor": "1", "Cookie": "ov=" + TOKEN, **hd}.items():
            o.headers[k] = v
        return o._doctor()
    assert doctor("127.0.0.1") is True
    for ip in ("10.0.0.5", "::1", "192.168.1.2", "127.0.0.2"):
        assert doctor(ip) is False
    for hdr in ("X-Forwarded-For", "Forwarded", "X-Real-IP", "Tailscale-User-Login", "x-forwarded-for"):
        assert doctor("127.0.0.1", **{hdr: "1.2.3.4"}) is False
        assert doctor("127.0.0.1", **{hdr: ""}) is False                      # an empty value still marks a proxy
    assert doctor("127.0.0.1", **{"X-Overheard-Doctor": "0"}) is False and doctor("127.0.0.1", Cookie="ov=bad") is False and doctor("127.0.0.1", Cookie="") is False


def test_doctor_over_the_wire_from_loopback_with_proxy_header_is_locked(web):
    _, port = web
    ok = json.loads(http_(port, headers={"X-Overheard-Doctor": "1"})[1])
    assert b"secret-site" in json.dumps(ok).encode()
    bad = json.loads(http_(port, headers={"X-Overheard-Doctor": "1", "X-Forwarded-For": "8.8.8.8"})[1])
    assert "secret-site" not in json.dumps(bad)
    assert http_(port, "GET", "/api/flagged", headers={"X-Overheard-Doctor": "1"})[0] == 403          # doctor gets stats only


# ---------- 4. secrets ----------
def test_secret_files_are_0600_even_when_pre_existing_and_loose(tmp_path):
    for name, fn in (("token", auth.load_token), ("unlock", auth.load_secret)):
        p = tmp_path / name
        v = fn(str(tmp_path))
        assert stat.S_IMODE(p.stat().st_mode) == 0o600
        os.chmod(p, 0o644)
        assert fn(str(tmp_path)) == v and stat.S_IMODE(p.stat().st_mode) == 0o600          # tightened, value kept
        p.write_text("x")
        os.chmod(p, 0o666)
        assert fn(str(tmp_path)) != "x" and stat.S_IMODE(p.stat().st_mode) == 0o600          # too short: regenerated, still private


def test_secrets_never_in_payloads_errors_or_logs(app, capsys):
    sid = TestHelper.unlock(app)
    outs = []
    for req in (Req("10.0.0.7", "ovu=" + sid), Req("10.0.0.7"), Req("10.0.0.7", "ov=%s; ovu=%s" % (TOKEN, sid))):
        for path in ("/api/stats", "/api/flagged", "/api/profiles", "/api/led", "/api/sprites", "/api/health", "/nope"):
            outs.append(app.route("GET", path, b"", req)[2])
    for body in (b'{"secret":"%s-wrong"}' % SECRET.encode(), b"{bad", b'{"secret": 5}', b"[]"):
        outs.append(app.route("POST", "/api/unlock", body, Req("10.0.0.99"))[2])
        outs.append(app.route("POST", "/api/settings", body, Req("10.0.0.7", "ovu=" + sid))[2])
    blob = b"\n".join(outs)
    for secret in (TOKEN, SECRET, sid):
        assert secret.encode() not in blob
    c = capsys.readouterr()
    assert TOKEN not in c.out + c.err and SECRET not in c.out + c.err and sid not in c.out + c.err
    on_disk = open(os.path.join(app.cfg.data_dir, "unlock")).read() if os.path.exists(os.path.join(app.cfg.data_dir, "unlock")) else ""
    assert on_disk not in blob.decode(errors="replace") or not on_disk


def test_led_brightness_infinity_is_clamped(app):
    assert app.route("POST", "/api/led", b'{"brightness": 1e999}', Req("10.0.0.5"))[0] == 200 and app.led.brightness == 255


def test_no_source_line_logs_a_secret():
    for f in glob.glob(SRC + "/*.py"):
        for n, line in enumerate(open(f), 1):
            if re.search(r"\bprint\(|logging\.|log\(", line):
                assert not re.search(r"%\s*\(?[^\"]*\b(token|secret|sid|cookie|self\.token|app\.token)\b", line, re.I), "%s:%d %s" % (f, n, line.strip())


def test_compare_is_constant_time_primitive():
    src = open(os.path.join(SRC, "auth.py")).read()
    assert "hmac.compare_digest" in src
    for f in ("server.py", "auth.py"):
        text = open(os.path.join(SRC, f)).read()
        assert not re.search(r"(token|secret|\bsid\b)\w*\s*(==|!=)|(==|!=)\s*\w*(token|secret)", text), f
    assert auth.same("abc", "abc") and not auth.same("abc", "abd") and not auth.same("", "") and not auth.same(None, "x") and not auth.same("é", "e")


# ---------- 5. adult guard cannot be altered ----------
def test_no_env_var_flag_or_setting_reaches_the_adult_guard():
    assert not [f for f in glob.glob(SRC + "/*.py") if re.search(r"os\.environ|getenv|environb", open(f).read())]      # no env var is read anywhere
    flags = " ".join(a for a in re.findall(r'add_argument\("(--[a-z0-9-]+)"', open(os.path.join(SRC, "config.py")).read()))
    assert not re.search(r"adult|guard|penalt|safe|slow|filter|nsfw|unblock|allow-?adult", flags), flags
    # the only argv names that exist today; a new flag must be added here on purpose
    assert set(flags.split()) <= {"--port", "--host", "--dns", "--dns-port", "--bind", "--upstream", "--upstream-port", "--ttl", "--update-blocklist", "--no-tls", "--strict",
                                  "--tls-port", "--tls-name", "--tls-cafile", "--demo", "--data-dir", "--profile", "--profile-all", "--no-profiles", "--no-auth", "--allow",
                                  "--allow-extra", "--rate", "--profile-max-mb", "--export-profiles", "--purge-profiles", "--expect-ip", "--upstream2", "--tls-port2", "--tls-name2"}
    assert srvmod.SETTINGS == {"slowdown"}
    from overheard import settings
    assert not [a for a in vars(settings.Settings) if re.search("adult|guard|penalt", a)]


def test_every_endpoint_and_input_leaves_blocking_unchanged(app, tmp_path):
    st, guard = app.state, app.guard
    srv = DnsServer(app.cfg, st, Blocklist(), lambda p: p, guard)
    srv.cfg = dataclasses.replace(app.cfg, rate=10 ** 6)
    probe = dnsproto.build_query("www.badsite.example")
    blocked = lambda: srv.handle_packet(probe, "10.0.0.5")[-4:] == b"\x00\x00\x00\x00"        # noqa: E731
    assert blocked()
    sid = TestHelper.unlock(app)
    before = (set(guard.filter.domains), guard.penalty.cooldown if hasattr(guard.penalty, "cooldown") else None, app.cfg)
    keys = ["adult", "adult_filter", "guard", "penalty", "penalty_s", "cooldown", "safesearch", "enabled", "blocking", "slowdown", "domains", "allow", "list", "filter", "disable"]
    for method in ("POST", "GET"):
        for path in ("/api/settings", "/api/led", "/api/flagged", "/api/unlock", "/api/lock", "/api/stats", "/api/profiles", "/api/sprites", "/api/guard", "/api/adult", "/api/config"):
            for k in keys:
                for v in (False, 0, None, "off", [], {"x": 1}):
                    app.route(method, "%s?%s=%s" % (path, k, "0"), json.dumps({k: v}).encode(), Req("10.0.0.7", "ovu=" + sid))
                    assert blocked()
    app.state.settings.slowdown = False
    after = (set(guard.filter.domains), guard.penalty.cooldown if hasattr(guard.penalty, "cooldown") else None, app.cfg)
    assert before == after and blocked()
    assert dnsproto.parse_question(probe)[0] == "www.badsite.example"
    for argv in (["--allow-extra", "8.8.8.8/32"], ["--no-auth"], ["--strict", "--no-tls"], ["--ttl", "0"], ["--rate", "0"], ["--profile-all"]):
        cfg = config.parse(argv + ["--data-dir", str(tmp_path)])
        d = DnsServer(dataclasses.replace(cfg, rate=10 ** 6), State(), Blocklist(), lambda p: p, guard)
        assert d.handle_packet(probe, "10.0.0.5")[-4:] == b"\x00\x00\x00\x00"
