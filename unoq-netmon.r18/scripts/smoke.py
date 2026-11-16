#!/usr/bin/env python3
"""End to end smoke test: start the real program in demo mode, hit every endpoint, stop it with SIGINT."""
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
PORT = 18080


COOKIE = {}


def get(path, data=None):
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (PORT, path), data, COOKIE, method="POST" if data else "GET")
    if data:
        req.add_header("Content-Type", "application/json")
    return urllib.request.urlopen(req, timeout=5).read()


def check_page_scripts(html, tmp):
    """The served dashboard must have inline scripts that parse (needs node; tests/test_r16_page.py does the same offline)."""
    node = shutil.which("node")
    if not node:
        print("smoke: node not found, skipping dashboard script syntax check")
        return
    for i, body in enumerate(re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S | re.I)):
        f = os.path.join(tmp, "page%d.js" % i)
        open(f, "w", encoding="utf-8").write(body)
        r = subprocess.run([node, "--check", f], capture_output=True, text=True)
        assert r.returncode == 0, "dashboard script %d has a syntax error:\n%s" % (i, r.stderr)


def main():
    tmp = tempfile.mkdtemp()
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"))
    p = subprocess.Popen([sys.executable, "-m", "overheard", "--demo", "--port", str(PORT), "--host", "127.0.0.1", "--data-dir", tmp], env=env, stdout=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                get("/api/health")
                break
            except OSError:
                time.sleep(0.1)
        time.sleep(4)
        try:
            get("/api/stats")
            raise AssertionError("dashboard answered without the key")
        except urllib.error.HTTPError as e:
            assert e.code == 401
        key = open(os.path.join(tmp, "token")).read().strip()
        COOKIE["Cookie"] = "ov=" + key
        page = get("/")
        assert b"Overheard" in page
        check_page_scripts(page.decode("utf-8", "replace"), tmp)
        locked = json.loads(get("/api/stats"))
        assert locked["unlocked"] is False and locked["recent"] == [] and locked["dns"]["upstream"] and "refused" in locked, "locked view is wrong"
        assert "settings" not in locked
        for path in ("/api/flagged", "/api/profiles"):
            try:
                get(path)
                raise AssertionError(path + " answered while locked")
            except urllib.error.HTTPError as e:
                assert e.code == 403
        secret = open(os.path.join(tmp, "unlock")).read().strip()
        assert oct(os.stat(os.path.join(tmp, "unlock")).st_mode & 0o777) == "0o600"
        bad = urllib.request.Request("http://127.0.0.1:%d/api/unlock" % PORT, b'{"secret": "nope"}', {**COOKIE, "Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(bad, timeout=5)
            raise AssertionError("wrong unlock secret accepted")
        except urllib.error.HTTPError as e:
            assert e.code == 403
        ok = urllib.request.Request("http://127.0.0.1:%d/api/unlock" % PORT, json.dumps({"secret": secret}).encode(), {**COOKIE, "Content-Type": "application/json"}, method="POST")
        sid = urllib.request.urlopen(ok, timeout=5).headers["Set-Cookie"].split(";")[0]
        COOKIE["Cookie"] = "ov=%s; %s" % (key, sid)
        stats = json.loads(get("/api/stats"))
        assert stats["unlocked"] is True and stats["recent"] and stats["settings"] == {"slowdown": False}
        assert stats["devices"], "no devices after 4 s of demo traffic"
        assert json.loads(get("/api/settings", b'{"slowdown": true}'))["settings"]["slowdown"] is True
        assert json.load(open(os.path.join(tmp, "settings.json"))) == {"slowdown": True}, "slowdown toggle was not persisted"
        led = json.loads(get("/api/led", json.dumps({"brightness": 180}).encode()))
        assert led["brightness"] == 180
    finally:
        p.send_signal(signal.SIGINT)
        p.wait(timeout=10)
    out = subprocess.run([sys.executable, "-m", "overheard", "--export-profiles", "--data-dir", tmp], env=env, capture_output=True, text=True, check=True).stdout
    prof = json.loads(out)
    assert prof["devices"], "profile data was not flushed on shutdown"
    print("smoke ok: %d devices, profiles for %s" % (len(stats["devices"]), ", ".join(prof["devices"])))


if __name__ == "__main__":
    main()
