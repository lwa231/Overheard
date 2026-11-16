#!/usr/bin/env python3
"""Dev tool (not in CI): screenshot every skin at desktop and phone size from the demo server.
usage: python3 scripts/skin_shots.py OUTDIR   (unlocked; LOCKED=1 for the locked view)"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out = sys.argv[1] if len(sys.argv) > 1 else "skins"
os.makedirs(out, exist_ok=True)


def unlock_cookie(port, data_dir):
    """Trade the unlock secret for a session cookie, as the dashboard's unlock form does. LOCKED=1 skips it (shoot the locked view)."""
    if os.environ.get("LOCKED"):
        return []
    req = urllib.request.Request("http://127.0.0.1:%d/api/unlock" % port, json.dumps({"secret": open(os.path.join(data_dir, "unlock")).read().strip()}).encode(),
                                 {"Content-Type": "application/json"}, method="POST")
    ck = urllib.request.urlopen(req, timeout=5).headers["Set-Cookie"].split(";")[0].split("=", 1)
    return [{"name": ck[0], "value": ck[1], "url": "http://127.0.0.1:%d/" % port}]
skins = [s for s in re.findall(r"id:'([a-z0-9-]+)'", open(os.path.join(ROOT, "src/overheard/web/skins.js")).read()) if os.environ.get("ONLY","").split(",")==[""] or s in os.environ["ONLY"].split(",")]
env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"))
p = subprocess.Popen([sys.executable, "-m", "overheard", "--demo", "--port", "18082", "--host", "127.0.0.1", "--no-auth", "--data-dir", "/tmp/ov-skins"], env=env, stdout=subprocess.DEVNULL)
try:
    time.sleep(14)
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        errs = []
        for sk in skins:
            for tag, vp in (("lg", {"width": 1440, "height": 900}), ("sm", {"width": 390, "height": 844})):
                ctx = b.new_context(viewport=vp)
                ctx.add_cookies(unlock_cookie(18082, "/tmp/ov-skins"))
                pg = ctx.new_page()
                pg.on("pageerror", lambda e, sk=sk: errs.append("%s: %s" % (sk, e)))
                pg.goto("http://127.0.0.1:18082/?skin=" + sk)
                pg.wait_for_timeout(2200)
                pg.screenshot(path="%s/%s-%s.png" % (out, sk, tag))
                ctx.close()
        b.close()
    print("skins:", len(skins), "errors:", errs or "none")
finally:
    p.terminate()
