#!/usr/bin/env python3
"""End to end smoke test: start the real program in demo mode, hit every endpoint, stop it with SIGINT."""
import json
import os
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
        assert b"Overheard" in get("/")
        stats = json.loads(get("/api/stats"))
        assert stats["devices"], "no devices after 4 s of demo traffic"
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
