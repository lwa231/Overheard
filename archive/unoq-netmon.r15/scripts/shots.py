#!/usr/bin/env python3
"""Dev tool (not in CI): run the demo and screenshot the dashboard sheets with Chrome via playwright.
usage: python3 scripts/shots.py OUTDIR"""
import os
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out = sys.argv[1] if len(sys.argv) > 1 else "shots"
os.makedirs(out, exist_ok=True)
env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"))
p = subprocess.Popen([sys.executable, "-m", "overheard", "--demo", "--port", "18081", "--host", "127.0.0.1", "--no-auth", "--data-dir", "/tmp/ov-shots"], env=env, stdout=subprocess.DEVNULL)
try:
    time.sleep(12)
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        pg = b.new_page(viewport={"width": 1440, "height": 900})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://127.0.0.1:18081/")
        pg.wait_for_timeout(2500)
        pg.screenshot(path=out + "/main.png")
        pg.click("#ledBtn")
        pg.wait_for_timeout(900)
        pg.screenshot(path=out + "/led.png")
        pg.keyboard.press("Escape")
        pg.click("#profBtn")
        pg.wait_for_timeout(900)
        pg.screenshot(path=out + "/profiles.png")
        b.close()
    print("page errors:", errs or "none")
finally:
    p.terminate()
