#!/usr/bin/env python3
"""End to end smoke test: start the real program, check the gate and every endpoint, stop it with SIGINT."""
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 18088
COOKIE = {}


def get(path, data=None):
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (PORT, path), data, COOKIE, method="POST" if data else "GET")
    if data:
        req.add_header("Content-Type", "application/json")
    return urllib.request.urlopen(req, timeout=5).read()


def main():
    tmp = tempfile.mkdtemp()
    proj = os.path.join(tmp, "proj")
    for d in ("config", "departments", "handoffs"):
        shutil.copytree(os.path.join(ROOT, d), os.path.join(proj, d))
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"))
    p = subprocess.Popen([sys.executable, "-m", "agency", "--root", proj, "--port", str(PORT), "--tick", "0.2"], env=env, stdout=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                get("/api/health")
                break
            except OSError:
                time.sleep(0.1)
        try:
            get("/api/org")
            raise AssertionError("answered without the key")
        except urllib.error.HTTPError as e:
            assert e.code == 401
        COOKIE["Cookie"] = "ag=" + open(os.path.join(proj, "data", "token")).read().strip()
        page = get("/").decode()
        assert "Chain of command" in page
        node = shutil.which("node")
        for i, body in enumerate(re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", page, re.S | re.I)):
            if node:
                f = os.path.join(tmp, "page%d.js" % i)
                open(f, "w", encoding="utf-8").write(body)
                r = subprocess.run([node, "--check", f], capture_output=True, text=True)
                assert r.returncode == 0, r.stderr
        t0 = json.loads(get("/api/org"))["tick"]
        time.sleep(1.2)
        org = json.loads(get("/api/org"))
        assert org["tick"] > t0 and len(org["agents"]) == 20, "simulation is not ticking"
        assert json.loads(get("/api/agent/scout"))["instructions"][0]["id"] == "boss"
        assert json.loads(get("/api/feed"))["events"]
        assert "metrics" in json.loads(get("/api/agent/scout")) and "fleet" in org and org["agents"][0]["metrics"]["cpu_pct"] >= 0
        assert all("scout" in (e["src"], e["dst"]) for e in json.loads(get("/api/feed?agent=scout"))["events"])
        ag = json.loads(get("/api/agent/scout"))
        assert ag["tier"]["configured"] == 200000 and ag["metrics"]["model"]["ctx_limit"] <= 200000 and ag["dept"] == "research"
        assert any(e["tag"] and e["hkind"] for e in json.loads(get("/api/feed?limit=200"))["events"])
        body = json.dumps({"actor": "boss", "path": "_shared/tasks/smoke.md", "content": "smoke"}).encode()
        assert json.loads(get("/api/instructions", body))["ok"]
        try:
            get("/api/instructions", json.dumps({"actor": "scout", "path": "_shared/tasks/smoke.md", "content": "no"}).encode())
            raise AssertionError("non-root write accepted")
        except urllib.error.HTTPError as e:
            assert e.code == 403
        assert len(open(os.path.join(proj, "data", "audit.log")).read().splitlines()) == 2
        p.send_signal(signal.SIGINT)
        p.wait(timeout=5)
    finally:
        if p.poll() is None:
            p.kill()
        shutil.rmtree(tmp, ignore_errors=True)
    print("smoke: ok")


if __name__ == "__main__":
    main()
