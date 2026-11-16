#!/usr/bin/env python3
"""Dev tool (not in CI): run the demo and screenshot the dashboard sheets with Chrome via playwright.
usage: python3 scripts/shots.py OUTDIR   (unlocked; LOCKED=1 for the locked view)"""
import json
import os
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out = sys.argv[1] if len(sys.argv) > 1 else "shots"
os.makedirs(out, exist_ok=True)


def unlock_cookie(port, data_dir):
    """Trade the unlock secret for a session cookie, as the dashboard's unlock form does. LOCKED=1 skips it (shoot the locked view)."""
    if os.environ.get("LOCKED"):
        return []
    req = urllib.request.Request("http://127.0.0.1:%d/api/unlock" % port, json.dumps({"secret": open(os.path.join(data_dir, "unlock")).read().strip()}).encode(),
                                 {"Content-Type": "application/json"}, method="POST")
    ck = urllib.request.urlopen(req, timeout=5).headers["Set-Cookie"].split(";")[0].split("=", 1)
    return [{"name": ck[0], "value": ck[1], "url": "http://127.0.0.1:%d/" % port}]
env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"))
p = subprocess.Popen([sys.executable, "-m", "overheard", "--demo", "--port", "18081", "--host", "127.0.0.1", "--no-auth", "--data-dir", "/tmp/ov-shots"], env=env, stdout=subprocess.DEVNULL)
try:
    time.sleep(12)
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_cookies(unlock_cookie(18081, "/tmp/ov-shots"))
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://127.0.0.1:18081/")
        pg.wait_for_timeout(2500)
        pg.screenshot(path=out + "/main.png")
        pg.click("#ledBtn")
        pg.wait_for_timeout(900)
        pg.screenshot(path=out + "/led.png")
        pg.keyboard.press("Escape")
        if not os.environ.get("LOCKED"):          # the profiles button is hidden while locked
            pg.click("#profBtn")
            pg.wait_for_timeout(900)
            pg.screenshot(path=out + "/profiles.png")
        b.close()
    print("page errors:", errs or "none")
finally:
    p.terminate()
