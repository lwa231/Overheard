#!/usr/bin/env python3
"""Dev tool (not in CI): run the server and screenshot the dashboard with Chrome via playwright.
usage: python3 scripts/shots.py OUTDIR [ROOT] [AGENT_1440] [AGENT_390]
  -> OUTDIR/live-1440.png (no selection), live-1440-selected.png, live-1440-addtask.png (Add task form open), live-390.png, live-390-selected.png,
   business-1440.png and business-390.png (the Business tab, #business, full page)
Chrome: $CHROME or /usr/bin/google-chrome (macOS: CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"). --data-dir goes to a throwaway dir.
The run is in TEST MODE (a throwaway copy of the project; a canned stand-in for the local model answers on loopback, prices come from the real Coinbase endpoint, so the
Review and Paper cards show; set SSL_CERT_FILE if your Python has no certificates). The server runs with its access key; the pages get it as a cookie, so the Approve/Deny and Add task controls show.
An agent is selected by opening the page with #<agent-id>."""
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out = sys.argv[1] if len(sys.argv) > 1 else "shots"
root = sys.argv[2] if len(sys.argv) > 2 else HERE
pick = {1440: sys.argv[3] if len(sys.argv) > 3 else "research-lead", 390: sys.argv[4] if len(sys.argv) > 4 else "copywriter"}
os.makedirs(out, exist_ok=True)
env = dict(os.environ, PYTHONPATH=os.path.join(HERE, "src"))
if os.path.exists("/etc/ssl/cert.pem"):
    env.setdefault("SSL_CERT_FILE", "/etc/ssl/cert.pem")


class Canned(http.server.BaseHTTPRequestHandler):
    """Stands in for the local model (dev tool only): a short canned answer."""
    def log_message(self, *a):
        pass

    def do_POST(self):
        prompt = json.loads(self.rfile.read(int(self.headers["Content-Length"])))["prompt"]
        text = ("Listing draft: Ceramic mug, hand glazed.\n- Holds 350 ml\n- Dishwasher safe\n- Ships in recycled card\nPrice to confirm with the owner." if "listing" in prompt else
                "Order note: check stock for the item, confirm the address, tell the customer the dispatch day.\nMissing: delivery date promise." if "order-handling" in prompt else
                "Status note: paper portfolio is flat, no closed trades yet, nothing odd.\nNo action needed." if "PAPER portfolio" in prompt else
                "Status: the delivery looks complete.\nNext: spot-check the report.")
        body = json.dumps({"response": text}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


model = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Canned)
threading.Thread(target=model.serve_forever, daemon=True).start()
proj = os.path.join(tempfile.mkdtemp(), "proj")
for d in ("config", "departments", "handoffs"):
    shutil.copytree(os.path.join(root, d), os.path.join(proj, d))
cfg_path = os.path.join(proj, "config", "agency.json")
with open(cfg_path, encoding="utf-8") as f:
    cfg = json.load(f)
cfg["test_mode"].update(real_agents=["boss", "fin-lead", "ops-lead"], model_url="http://127.0.0.1:%d/api/generate" % model.server_address[1])
with open(cfg_path, "w", encoding="utf-8") as f:
    json.dump(cfg, f)
root = proj
data = tempfile.mkdtemp()
srv = subprocess.Popen([sys.executable, "-m", "agency", "--root", root, "--port", "18089", "--data-dir", data, "--tick", "0.5"], env=env, stdout=subprocess.DEVNULL)
try:
    time.sleep(2)
    with open(os.path.join(data, "token")) as f:
        token = f.read().strip()
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=os.environ.get("CHROME", "/usr/bin/google-chrome"), args=["--no-sandbox"])
        errs = []
        for w, h in ((1440, 1100), (390, 844)):
            for sel in (False, True):
                ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=2 if w < 500 else 1)
                ctx.add_cookies([{"name": "ag", "value": token, "url": "http://127.0.0.1:18089"}])
                pg = ctx.new_page()
                pg.on("pageerror", lambda e: errs.append(str(e)))
                pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
                pg.goto("http://127.0.0.1:18089/" + ("#" + pick[w] if sel else ""))
                pg.wait_for_timeout(9000)           # long enough for the schedule to show a paused job
                name = "live-%d%s" % (w, "-selected" if sel else "")
                pg.screenshot(path="%s/%s.png" % (out, name), full_page=w < 500 and not sel)
                if w > 500 and not sel:
                    pg.click("#tAdd")
                    pg.screenshot(path="%s/live-1440-addtask.png" % out)
                ctx.close()
        for w, h in ((1440, 1100), (390, 844)):
            ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=2 if w < 500 else 1)
            ctx.add_cookies([{"name": "ag", "value": token, "url": "http://127.0.0.1:18089"}])
            pg = ctx.new_page()
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
            pg.goto("http://127.0.0.1:18089/#business")
            pg.wait_for_timeout(3000)
            pg.screenshot(path="%s/business-%d.png" % (out, w), full_page=True)
            if pg.evaluate("document.documentElement.scrollWidth > innerWidth"):
                errs.append("horizontal page scroll at %d" % w)
            ctx.close()
        b.close()
    print("page errors:", errs or "none")
finally:
    srv.terminate()
