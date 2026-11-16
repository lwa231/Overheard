"""HTTP API and dashboard. Routes are plain functions on App so tests can call them directly."""
import ipaddress
import json
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from . import auth, gates, ledger, loader, metrics, real, returns, scheduler
from .store import Forbidden

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
MAX_BODY = 80 * 1024
REQ_TIMEOUT = 10
KNOWN_HOSTS = {"localhost", socket.gethostname().lower(), socket.gethostname().lower() + ".local"}


def jr(obj, status=200):
    return status, "application/json; charset=utf-8", json.dumps(obj).encode()


class App:
    def __init__(self, store, sim, token=None, provider=None, goal=None, reinvest=None):
        self.store, self.sim, self.token, self.ledger, self.reinvest = store, sim, token, goal, reinvest
        self.metrics = provider or metrics.SimulatedMetrics(sim, store.org.cfg.claude_daily_cap_usd)
        self.lock = threading.Lock()          # the ticker thread and request threads both touch sim and store

    def tick(self):
        with self.lock:
            self.sim.step()
            self.metrics.sample()

    def route(self, method, path, body=b""):
        u = urlparse(path)
        p, q = u.path, parse_qs(u.query)
        try:
            with self.lock:
                if method == "GET":
                    if p == "/":
                        with open(os.path.join(WEB, "index.html"), "rb") as f:
                            return 200, "text/html; charset=utf-8", f.read()
                    if p == "/api/health":
                        return jr({"ok": True, "simulated": True, "agents": len(self.store.org.agents), "tick": self.sim.tick})
                    if p == "/api/org":
                        return jr(self._org())
                    if p.startswith("/api/agent/"):
                        return self._agent(unquote(p[len("/api/agent/"):]))
                    if p == "/api/business":
                        return self._business()
                    if p == "/api/output":
                        return self._output(q.get("id", [""])[0])
                    if p == "/api/instruction":
                        return self._read(q.get("as", [""])[0], q.get("path", [""])[0])
                    if p == "/api/feed":
                        try:
                            since, limit = int(q.get("since", ["0"])[0]), min(200, max(1, int(q.get("limit", ["50"])[0])))
                        except ValueError:
                            return jr({"error": "bad query"}, 400)
                        who = q.get("agent", [None])[0]
                        if who is not None and who not in self.store.org.agents:
                            return jr({"error": "no such agent"}, 404)
                        return jr({"tick": self.sim.tick, "latest": self.sim.n, "agent": who, "events": self.sim.feed(since, limit, who)})
                elif method == "POST" and p == "/api/instructions":
                    return self._write(body)
                elif method == "POST" and p == "/api/goal":
                    return self._goal(body)
                elif method == "POST" and p == "/api/schedule":
                    return self._schedule(body)
                elif method == "POST" and p == "/api/task":
                    return self._task(body)
                elif method == "POST" and p == "/api/review":
                    return self._review(body)
                elif method == "POST" and p in ("/api/approve", "/api/deny"):
                    return self._decide(body, p == "/api/approve")
        except Exception as e:                  # noqa: BLE001 - never leak a traceback to the client
            return jr({"error": "server error: %s" % type(e).__name__}, 500)
        return jr({"error": "not found"}, 404)

    def _org(self):
        org, sim = self.store.org, self.sim
        agents, comp = [], {aid: self.metrics.compact(aid) for aid in org.order}
        states = {aid: sim.shown(aid) for aid in org.order}
        for aid in org.order:
            a = org.agents[aid]
            agents.append({"id": aid, "title": a.title, "rank": a.rank, "rank_label": a.rank_label, "reports_to": a.reports_to, "children": a.children,
                           "runtime": a.runtime, "dept": a.dept, **sim.state_of(aid), "power": sim.sched.state(aid) if sim.sched else None, "metrics": comp[aid],
                           "rollup": metrics.rollup(org, comp, states, aid) if a.children else None})
        return {"name": org.cfg.name, "root": org.root, "ranks": [{"key": k, "label": lb} for k, lb in org.cfg.ranks], "agents": agents, "tree": org.tree(),
                "tick": sim.tick, "tick_s": sim.tick_s, "seed": sim.seed, "simulated": True, "stats": sim.stats(), "history": sim.history(),
                "metrics_source": self.metrics.source, "fleet": self.metrics.fleet(), "ledger": self.ledger.snapshot() if self.ledger else None,
                "schedule": sim.sched.snapshot() if sim.sched else None, "can_act": bool(self.token)}

    def _agent(self, aid):
        org = self.store.org
        a = org.agents.get(aid)
        if not a:
            return jr({"error": "no such agent"}, 404)
        st = self.sim.state_of(aid)
        return jr({"id": aid, "title": a.title, "rank": a.rank, "rank_label": a.rank_label, "runtime": a.runtime, "dept": a.dept, "role": a.role, "path": a.path, **st,
                   "tier": {"rank": a.rank, **org.cfg.tiers.limit(aid, a.rank, a.runtime)},
                   "superior": a.reports_to, "direct_reports": [{"id": c, "title": org.agents[c].title, **self.sim.state_of(c)} for c in a.children],
                   "instructions": org.effective(aid),
                   "tasks": [{"name": t.name, "title": t.title, "text": t.body, "scope": t.scope} for t in org.tasks_of(aid)],
                   "events": self.sim.agent_events(aid), "metrics": self.metrics.agent(aid)})

    def _read(self, who, path):
        """An agent reads one instruction file; another department's files are refused (403)."""
        try:
            return jr({"as": who, "path": path, "text": self.store.read(who, path)})
        except KeyError:
            return jr({"error": "no such agent"}, 404)
        except loader.IsolationError as e:
            return jr({"error": str(e)}, 403)

    def _write(self, body):
        try:
            d = json.loads(body or b"{}")
        except (ValueError, RecursionError):
            return jr({"error": "bad request"}, 400)
        if not isinstance(d, dict):
            return jr({"error": "bad request"}, 400)
        try:
            res = self.store.write(d.get("actor"), d.get("path"), d.get("content"))
        except Forbidden as e:
            return jr({"error": str(e)}, 403)
        except (ValueError, loader.OrgError) as e:
            return jr({"error": str(e)}, 400)
        self.sim.rebind(self.store.org)
        return jr(res)


    def _goal(self, body):
        """Set the profit goal. Only the user: the request already passed the token gate, and with no token (--no-auth) there is no gate, so it is refused."""
        if not self.token or not self.ledger:
            return jr({"error": "the goal can only be set with the access key enabled"}, 403)
        try:
            self.ledger.set_goal(json.loads(body or b"{}"))
        except (ValueError, RecursionError) as e:                 # bad JSON and ledger.GoalError (a ValueError)
            return jr({"error": str(e) if isinstance(e, ledger.GoalError) else "bad request"}, 400)
        return jr(self.ledger.snapshot())

    def _business(self):
        if not self.ledger or not self.reinvest:
            return jr({"error": "no ledger configured"}, 404)
        b = returns.business(self.ledger, self.reinvest, self.sim)
        if b.get("ready"):
            b["test"] = self.sim.test_snapshot()                # None unless test mode is on
        return jr(b)

    def _output(self, rid):
        """The full text of one real agent's output, found by its id in the review queue (plain text, never a path from the client)."""
        if not self.sim.real:
            return jr({"error": "test mode is off"}, 404)
        try:
            return 200, "text/plain; charset=utf-8", self.sim.real.read(rid).encode()
        except gates.GateError as e:
            return jr({"error": str(e)}, e.status)

    def _review(self, body):
        """The owner accepts or rejects a real agent's output ({"id", "decision", "note"?}). Only the user: refused when the access key is off."""
        if not self.token:
            return jr({"error": "outputs can only be reviewed with the access key enabled"}, 403)
        if not self.sim.real:
            return jr({"error": "test mode is off"}, 404)
        try:
            self.sim.review(json.loads(body or b"{}"))
        except gates.GateError as e:
            return jr({"error": str(e)}, e.status)
        except (ValueError, RecursionError) as e:                 # bad JSON and real.ReviewError (a ValueError)
            return jr({"error": str(e) if isinstance(e, real.ReviewError) else "bad request"}, 400)
        return jr(self.sim.real.snapshot())

    def _schedule(self, body):
        """Switch a department's schedule on or off. Same gate as the goal: only the user, so refused when the access key is off."""
        if not self.token:
            return jr({"error": "the schedule can only be changed with the access key enabled"}, 403)
        if not self.sim.sched:
            return jr({"error": "no schedule configured"}, 404)
        try:
            self.sim.sched.set_enabled(json.loads(body or b"{}"))
        except (ValueError, RecursionError) as e:                 # bad JSON and scheduler.ScheduleError (a ValueError)
            return jr({"error": str(e) if isinstance(e, scheduler.ScheduleError) else "bad request"}, 400)
        return jr(self.sim.sched.snapshot())

    def _task(self, body):
        """The user adds a task to a department's queue. Only the user: refused when the access key is off."""
        if not self.token:
            return jr({"error": "tasks can only be added with the access key enabled"}, 403)
        if not self.sim.sched:
            return jr({"error": "no schedule configured"}, 404)
        try:
            self.sim.jobs.append(self.sim.sched.add_user(json.loads(body or b"{}")))
        except (ValueError, RecursionError) as e:
            return jr({"error": str(e) if isinstance(e, scheduler.ScheduleError) else "bad request"}, 400)
        return jr(self.sim.sched.snapshot())

    def _decide(self, body, approve):
        """The user approves or denies a pending request ({"id": "req-001"}). Only the user: refused when the access key is off."""
        if not self.token:
            return jr({"error": "requests can only be decided with the access key enabled"}, 403)
        if not self.sim.sched or not self.sim.sched.gates:
            return jr({"error": "no schedule configured"}, 404)
        try:
            d = json.loads(body or b"{}")
            if not isinstance(d, dict) or set(d) != {"id"} or not isinstance(d["id"], str):
                raise ValueError("body must be {\"id\": <request id>}")
            self.sim.sched.decide(d["id"], approve)
        except gates.GateError as e:
            return jr({"error": str(e)}, e.status)
        except (ValueError, RecursionError):
            return jr({"error": "bad request"}, 400)
        return jr(self.sim.sched.snapshot())


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        timeout = REQ_TIMEOUT
        server_version = "agency"

        def log_message(self, *a):
            pass

        def _reply(self, status, ct, body, extra=()):
            self.send_response(status)
            self.send_header("Content-Type", ct)
            for k, v in extra:
                self.send_header(k, v)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _gate(self):
            """True if the request may proceed; otherwise a reply was sent. ?key=<token> trades the token for a cookie."""
            u = urlparse(self.path)
            if not app.token or u.path == "/api/health":
                return True
            if auth.same(parse_qs(u.query).get("key", [""])[0], app.token):
                self._reply(302, "text/plain", b"", [("Location", "/" + u.path.lstrip("/")), ("Set-Cookie", "%s=%s; HttpOnly; SameSite=Strict; Path=/; Max-Age=31536000" % (auth.COOKIE, app.token))])
                return False
            if auth.same(auth.cookie_value(self.headers.get("Cookie")), app.token):
                return True
            self._reply(401, "text/plain; charset=utf-8", b"Locked. Open the dashboard with ?key=<token> (see data/token).")
            return False

        def _host_ok(self):
            """Reject Host headers naming a host we do not know: blocks DNS-rebinding pages."""
            h = (self.headers.get("Host") or "").strip().lower()
            h = h[1:h.index("]")] if h.startswith("[") and "]" in h else h.rsplit(":", 1)[0] if h.count(":") == 1 else h
            try:
                ipaddress.ip_address(h)
                return True
            except ValueError:
                return h in KNOWN_HOSTS

        def _do(self, method):
            if not self._host_ok():
                return self._reply(*jr({"error": "unknown host"}, 421))
            if not self._gate():
                return
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = -1
            if n < 0 or n > MAX_BODY:
                return self._reply(*jr({"error": "bad length"}, 413 if n > MAX_BODY else 400))
            if method == "POST":
                origin = self.headers.get("Origin")          # JSON content type forces a CORS preflight for other sites; Origin must be this host
                if not self.headers.get("Content-Type", "").startswith("application/json") or (origin and urlparse(origin).netloc != self.headers.get("Host")):
                    return self._reply(*jr({"error": "forbidden"}, 403))
            self._reply(*app.route(method, self.path, self.rfile.read(n) if n else b""))

        def do_GET(self):
            self._do("GET")

        def do_POST(self):
            self._do("POST")
    return Handler


def serve(app, host, port):
    srv = ThreadingHTTPServer((host, port), make_handler(app))
    srv.daemon_threads = True
    return srv
