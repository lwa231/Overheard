"""HTTP API and dashboard. Routes are plain functions on App so tests can call them directly."""
import json
import os
import ipaddress
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import auth
from .config import PKG
from .stats import adult_summary, build_stats


MAX_BODY = 4096
REQ_TIMEOUT = 10         # seconds a client may stall between bytes
REQ_DEADLINE = 30        # seconds a connection may live in total, however steadily it drips
STATIC = {"/skins.css": "text/css; charset=utf-8", "/skins.js": "application/javascript; charset=utf-8"}   # whitelist: nothing else is served from web/

PROXY_HEADERS = ("X-Forwarded-For", "Forwarded", "X-Real-IP", "Tailscale-User-Login")    # a proxied request is not the board itself
DOCTOR_HEADER = "X-Overheard-Doctor"
SETTINGS = {"slowdown"}       # the only things /api/settings can change; nothing here reaches the adult guard itself

KNOWN_HOSTS = {"localhost", socket.gethostname().lower(), socket.gethostname().lower() + ".local"}


def _loads(body):
    """json.loads that only ever raises ValueError (deeply nested input raises RecursionError otherwise)."""
    try:
        return json.loads(body or b"{}")
    except RecursionError:
        raise ValueError("too deep") from None


class Req:
    """What the route needs to know about the caller. A request made without one is a locked one."""
    def __init__(self, addr="", cookie="", doctor=False):
        self.addr, self.cookie, self.doctor = addr, cookie, doctor
        self.headers = []         # extra response headers set by the route (the session cookie)


class App:
    def __init__(self, cfg, state, profiles=None, led=None, sprites=None, token=None, guard=None, vitals=None, secret=None):
        self.cfg, self.state, self.profiles, self.led, self.sprites, self.token, self.guard, self.vitals = cfg, state, profiles, led, sprites, token, guard, vitals
        self.secret = secret or auth.load_secret(cfg.data_dir)
        self.sessions, self.fails = auth.Sessions(), auth.FailureLimit()

    def _unlock(self, req, body):
        key = req.addr
        if self.fails.blocked(key):
            req.headers.append(("Retry-After", str(auth.FAIL_WINDOW)))
            return self._json({"error": "too many attempts"}, 429)
        try:
            data = _loads(body)
        except ValueError:
            return self._json({"error": "bad request"}, 400)
        if not isinstance(data, dict) or not isinstance(data.get("secret"), str):
            return self._json({"error": "bad request"}, 400)
        if not auth.same(data["secret"], self.secret):
            self.fails.fail(key)
            return self._json({"error": "forbidden"}, 403)
        req.headers.append(("Set-Cookie", "%s=%s; HttpOnly; SameSite=Strict; Path=/; Max-Age=%d" % (auth.UNLOCK_COOKIE, self.sessions.start(), self.sessions.ttl)))
        return self._json({"unlocked": True})

    def _settings(self, body):
        try:
            data = _loads(body)
        except ValueError:
            return self._json({"error": "bad request"}, 400)
        if not isinstance(data, dict) or not data or not set(data) <= SETTINGS or not all(isinstance(v, bool) for v in data.values()):
            return self._json({"error": "bad request"}, 400)
        self.state.settings.slowdown = data["slowdown"]
        return self._json({"settings": {"slowdown": self.state.settings.slowdown}})

    def route(self, method, url, body=b"", req=None):
        """Return (status, content_type, bytes). `req` says who is asking; without one the caller is locked out of every name."""
        req = req or Req()
        sid = auth.cookie_value(req.cookie, auth.UNLOCK_COOKIE)
        unlocked = self.sessions.valid(sid)
        u = urlparse(url)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        p = u.path
        if method == "GET" and p in ("/", "/index.html"):
            with open(os.path.join(PKG, "web", "index.html"), "rb") as f:
                return 200, "text/html; charset=utf-8", f.read()
        if method == "GET" and p in STATIC:
            with open(os.path.join(PKG, "web", p[1:]), "rb") as f:
                return 200, STATIC[p], f.read()
        if method == "GET" and p == "/api/health":
            return self._json({"ok": True})
        if method == "GET" and p == "/3ds":
            with open(os.path.join(PKG, "web", "3ds.html"), "rb") as f:
                return 200, "text/html; charset=utf-8", f.read()
        if method == "GET" and p == "/api/stats":
            out = build_stats(self.state, self.cfg, self.guard, self.vitals, full=unlocked or req.doctor)
            out["unlocked"] = unlocked
            if unlocked or req.doctor:
                out["settings"] = {"slowdown": self.state.settings.slowdown}
            return self._json(out)
        if method == "POST" and p == "/api/unlock":
            return self._unlock(req, body)
        if method == "POST" and p == "/api/lock":
            self.sessions.end(sid)
            req.headers.append(("Set-Cookie", "%s=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0" % auth.UNLOCK_COOKIE))
            return self._json({"unlocked": False})
        if method == "POST" and p == "/api/settings":
            return self._settings(body) if unlocked else self._json({"error": "locked"}, 403)
        if (p == "/api/flagged" or p.startswith("/api/profile")) and not unlocked:
            return self._json({"error": "locked"}, 403)
        if p == "/api/flagged":
            return self._json({"enabled": bool(self.guard), "items": self.guard.flags.snapshot() if self.guard else [], **adult_summary(self.state, self.guard, True)})
        if p.startswith("/api/profile"):
            if not self.profiles:
                return self._json({"error": "profiles disabled"}, 404)
            if p == "/api/profiles":
                return self._json({"devices": self.profiles.devices_seen(), "cats": list(self.profiles.export_vectors()["cats"]),
                                   "bytes": self.profiles.size_bytes()})
            if p == "/api/profile" and q.get("id"):
                return self._json(self.profiles.profile(q["id"]))
            return self._json({"error": "bad request"}, 400)
        if p == "/api/led" and self.led:
            if method == "POST":
                try:
                    data = _loads(body)
                    if not isinstance(data, dict):
                        raise ValueError("body must be an object")
                    self.led.update(data.get("character"), data.get("brightness"))
                except KeyError:
                    return self._json({"error": "unknown character"}, 400)
                except ValueError:       # includes json.JSONDecodeError
                    return self._json({"error": "bad request"}, 400)
            return self._json(self.led.snapshot(build_stats(self.state, self.cfg, self.guard, self.vitals)))
        if p == "/api/sprites" and self.sprites:
            return self._json(self.sprites)
        return self._json({"error": "not found"}, 404)

    @staticmethod
    def _json(obj, status=200):
        return status, "application/json", json.dumps(obj).encode()


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        timeout = REQ_TIMEOUT

        def handle(self):
            """Hard cap on connection lifetime: a client dripping one byte at a time still gets cut off."""
            def cut():
                try:
                    self.connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            t = threading.Timer(REQ_DEADLINE, cut)
            t.daemon = True
            t.start()
            try:
                super().handle()
            finally:
                t.cancel()

        def _reply(self, status, ct, body, extra=()):
            self.send_response(status)
            self.send_header("Content-Type", ct)
            for k, v in extra:
                self.send_header(k, v)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _gate(self):
            """Return True if the request may proceed; otherwise a reply has already been sent."""
            if not app.token or urlparse(self.path).path == "/api/health":
                return True
            u = urlparse(self.path)
            if auth.same(parse_qs(u.query).get("key", [""])[0], app.token):
                self.send_response(302)
                self.send_header("Location", "/" + u.path.lstrip("/"))
                self.send_header("Set-Cookie", "%s=%s; HttpOnly; SameSite=Strict; Path=/; Max-Age=31536000" % (auth.COOKIE, app.token))
                self.send_header("Content-Length", "0")
                self.end_headers()
                return False
            if auth.same(auth.cookie_value(self.headers.get("Cookie")), app.token):
                return True
            self._reply(401, "text/plain; charset=utf-8", b"Locked. Open Overheard.app to get in.")
            return False

        def _host_ok(self):
            """Reject a Host header that is a name we do not know. This blocks DNS-rebinding pages, which reach us by a hostname."""
            h = (self.headers.get("Host") or "").strip().lower()
            h = h[1:h.index("]")] if h.startswith("[") and "]" in h else h.rsplit(":", 1)[0] if h.count(":") == 1 else h
            try:
                ipaddress.ip_address(h)
                return True
            except ValueError:
                return h in KNOWN_HOSTS

        def _doctor(self):
            """The board's own diagnostics: loopback, holding the access cookie, and not relayed by a proxy (which would also appear as loopback)."""
            h = self.headers
            return (self.client_address[0] == "127.0.0.1" and h.get(DOCTOR_HEADER) == "1" and auth.same(auth.cookie_value(h.get("Cookie")), app.token or "")
                    and not any(x in h for x in PROXY_HEADERS))

        def _do(self, method):
            if not self._host_ok():
                return self._reply(*App._json({"error": "unknown host"}, 421))
            if not self._gate():
                return
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = -1
            if n < 0 or n > MAX_BODY:
                return self._reply(*App._json({"error": "bad length"}, 413 if n > MAX_BODY else 400))
            if method == "POST":
                # Only our own dashboard may change settings: JSON content type forces a CORS preflight
                # for other sites, and the Origin check rejects any page not served by this host.
                origin = self.headers.get("Origin")
                if not self.headers.get("Content-Type", "").startswith("application/json") or (origin and urlparse(origin).netloc != self.headers.get("Host")):
                    return self._reply(*App._json({"error": "forbidden"}, 403))
            req = Req(self.client_address[0], self.headers.get("Cookie"), self._doctor())
            status, ct, body = app.route(method, self.path, self.rfile.read(n) if n else b"", req)
            self._reply(status, ct, body, req.headers)

        def do_GET(self):
            self._do("GET")

        def do_POST(self):
            self._do("POST")
    return Handler


class BoundedServer(ThreadingHTTPServer):
    """One thread per request, but capped overall and per device, so a flood of slow connections cannot exhaust the board."""
    daemon_threads = True
    MAX_TOTAL, MAX_PER_IP = 32, 8

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._slots = threading.BoundedSemaphore(self.MAX_TOTAL)
        self._per, self._plock = {}, threading.Lock()

    def process_request(self, request, client_address):
        ip = client_address[0]
        with self._plock:
            ok = self._per.get(ip, 0) < self.MAX_PER_IP
            if ok:
                self._per[ip] = self._per.get(ip, 0) + 1
        if not ok:
            return self.shutdown_request(request)
        if not self._slots.acquire(blocking=False):
            self._release_ip(ip)
            return self.shutdown_request(request)
        super().process_request(request, client_address)

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()
            self._release_ip(client_address[0])

    def _release_ip(self, ip):
        with self._plock:
            self._per[ip] = self._per.get(ip, 1) - 1
            if self._per[ip] <= 0:
                del self._per[ip]


def serve(app, host, port):
    return BoundedServer((host, port), make_handler(app))
