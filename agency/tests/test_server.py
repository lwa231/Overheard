import http.client
import json
import os
import re
import shutil
import subprocess
import threading

import pytest

from agency import server
from agency.__main__ import build

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN = "t" * 24


@pytest.fixture
def app(project, tmp_path):
    return build(project, str(tmp_path / "data"), seed=1, token=TOKEN)


@pytest.fixture
def live(app):
    srv = server.serve(app, "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()
    srv.server_close()


def call(port, method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.request(method, path, body, headers or {})
    r = c.getresponse()
    return r.status, dict(r.getheaders()), r.read()


def test_gate(live):
    assert call(live, "GET", "/api/health")[0] == 200                      # health is open
    for p in ("/", "/api/org", "/api/feed", "/api/agent/scout"):
        assert call(live, "GET", p)[0] == 401
    assert call(live, "GET", "/api/org", headers={"Cookie": "ag=wrong"})[0] == 401
    s, h, _ = call(live, "GET", "/api/org?key=" + TOKEN)
    assert s == 302 and "ag=" + TOKEN in h["Set-Cookie"] and "HttpOnly" in h["Set-Cookie"]
    assert call(live, "GET", "/api/org?key=bad")[0] == 401
    assert call(live, "GET", "/api/org", headers={"Cookie": "ag=" + TOKEN})[0] == 200


def test_host_and_post_checks(live):
    ck = {"Cookie": "ag=" + TOKEN}
    assert call(live, "GET", "/api/org", headers={**ck, "Host": "evil.example.com"})[0] == 421
    body = json.dumps({"actor": "boss", "path": "_shared/tasks/x.md", "content": "hi"})
    assert call(live, "POST", "/api/instructions", body, {**ck, "Content-Type": "text/plain"})[0] == 403
    assert call(live, "POST", "/api/instructions", body, {**ck, "Content-Type": "application/json", "Origin": "http://evil.example.com"})[0] == 403
    assert call(live, "POST", "/api/instructions", body, {"Content-Type": "application/json"})[0] == 401
    assert call(live, "POST", "/api/instructions", body, {**ck, "Content-Type": "application/json", "Content-Length": str(10**7)})[0] == 413
    assert call(live, "POST", "/api/instructions", body, {**ck, "Content-Type": "application/json"})[0] == 200


def test_api_shapes(app):
    s, _, b = app.route("GET", "/api/org")
    d = json.loads(b)
    assert s == 200 and d["root"] == "boss" and len(d["agents"]) == 20 and d["tree"]["id"] == "boss" and d["simulated"] is True
    a = {x["id"]: x for x in d["agents"]}
    assert a["scout"]["reports_to"] == "research-lead" and a["scout"]["state"] in ("idle", "working", "waiting", "reporting", "blocked") and a["boss"]["rank_label"] == "Head"
    assert set(d["stats"]) >= {"running", "idle", "blocked", "jobs_in_flight", "reports_per_min"} and set(d["history"]) == {"running", "idle", "blocked", "jobs_in_flight", "reports_per_min"}
    ag = json.loads(app.route("GET", "/api/agent/scout")[2])
    assert [c["id"] for c in ag["instructions"]] == ["boss", "general", "research-lead", "scout"]
    assert [t["name"] for t in ag["tasks"]] == ["find-sources", "handoff", "status-update"] and ag["superior"] == "research-lead" and ag["direct_reports"] == [] and isinstance(ag["events"], list)
    assert [c["id"] for c in json.loads(app.route("GET", "/api/agent/research-lead")[2])["direct_reports"]] == ["analyst", "archivist", "scout", "verifier"]
    assert app.route("GET", "/api/agent/nobody")[0] == 404 and app.route("GET", "/api/nope")[0] == 404
    f = json.loads(app.route("GET", "/api/feed?limit=5")[2])
    assert len(f["events"]) == 5 and f["latest"] == f["events"][-1]["n"]
    assert json.loads(app.route("GET", "/api/feed?since=%d" % f["latest"])[2])["events"] == []
    assert app.route("GET", "/api/feed?since=x")[0] == 400


def test_write_api_root_only(app):
    def post(actor, path="_shared/tasks/handoff.md", content="---\ntitle: Hand-off\n---\nedited"):
        return app.route("POST", "/api/instructions", json.dumps({"actor": actor, "path": path, "content": content}).encode())
    assert post("scout")[0] == 403 and post("general")[0] == 403 and post(None)[0] == 403
    assert post("boss")[0] == 200
    assert post("boss", "../x.md")[0] == 400 and app.route("POST", "/api/instructions", b"not json")[0] == 400
    assert "edited" in [t for t in json.loads(app.route("GET", "/api/agent/scout")[2])["tasks"] if t["name"] == "handoff"][0]["text"]
    audit = [json.loads(x) for x in open(app.store.audit_path)]
    assert [r["ok"] for r in audit] == [False, False, False, True, False]
    new = "---\nid: extra\ntitle: Extra\nrank: agent\nreports_to: scout\nruntime: local\ntasks: []\n---\nx"
    assert post("boss", "research/instructions/roles/extra.md", new)[0] == 400                  # an agent may not report to an agent
    ok = new.replace("reports_to: scout", "reports_to: research-lead")
    assert post("boss", "research/instructions/roles/extra.md", ok)[0] == 200
    assert len(json.loads(app.route("GET", "/api/org")[2])["agents"]) == 21


def test_page_script_parses():
    html = open(os.path.join(ROOT, "src", "agency", "web", "index.html"), encoding="utf-8").read()
    scripts = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S | re.I)
    assert scripts
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    for i, body in enumerate(scripts):
        f = os.path.join(os.environ.get("TMPDIR", "/tmp"), "agency_page%d.js" % i)
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(body)
        r = subprocess.run([node, "--check", f], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
