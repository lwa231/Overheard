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
from .stats import build_stats


MAX_BODY = 4096
STATIC = {"/skins.css": "text/css; charset=utf-8", "/skins.js": "application/javascript; charset=utf-8"}   # whitelist: nothing else is served from web/

KNOWN_HOSTS = {"localhost", socket.gethostname().lower(), socket.gethostname().lower() + ".local"}


class App:
    def __init__(self, cfg, state, profiles=None, led=None, sprites=None, token=None, guard=None, vitals=None):
        self.cfg, self.state, self.profiles, self.led, self.sprites, self.token, self.guard, self.vitals = cfg, state, profiles, led, sprites, token, guard, vitals

    def route(self, method, url, body=b""):
        """Return (status, content_type, bytes)."""
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
        if method == "GET" and p == "/api/stats":
            return self._json(build_stats(self.state, self.cfg, self.guard, self.vitals))
        if p == "/api/flagged":
            return self._json({"enabled": bool(self.guard), "items": self.guard.flags.snapshot() if self.guard else [], **(self.guard.summary() if self.guard else {})})
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
                    data = json.loads(body or b"{}")
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

        timeout = 10

        def _reply(self, status, ct, body):
            self.send_response(status)
            self.send_header("Content-Type", ct)
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
                self.send_header("Location", u.path or "/")
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
            status, ct, body = app.route(method, self.path, self.rfile.read(n) if n else b"")
            self._reply(status, ct, body)

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
